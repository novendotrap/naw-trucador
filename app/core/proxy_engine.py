"""
proxy_engine.py - Core local interception proxy engine using mitmproxy.
Handles automated Windows proxy configuration, root certificates, and asset redirection.
"""

import atexit
import ctypes
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import winreg
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Any, Optional, List

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
OVERRIDES_DIR = DATA_DIR / "overrides"
ACTIVE_PAYLOAD_PATH = DATA_DIR / "active_payload.txt"
LOGS_FILE_PATH = DATA_DIR / "interceptor_logs.txt"
ADDON_SCRIPT_PATH = DATA_DIR / "mitm_addon.py"
PAC_FILE_PATH = DATA_DIR / "mg-proxy.pac"
INTERCEPT_LIST_PATH = DATA_DIR / "intercept_swfs.txt"
STATS_PATH = DATA_DIR / "intercept_stats.json"

PROXY_PORT = 8080
PAC_PORT_START = 18081
TARGET_NPC_URL = "cdn-ar.mundogaturro.com/juego/npc/lola.npc"

WININET_SETTINGS_CHANGED = 39
WININET_REFRESH = 37


def _safe_pac_token(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum() or ch in ".-_")


def list_override_files() -> List[str]:
    if not OVERRIDES_DIR.exists():
        return []
    return sorted(f.name for f in OVERRIDES_DIR.glob("*.swf"))


def list_intercept_swfs() -> List[str]:
    """
    SWFs that mitm must rewrite:
      1) packs referenced in the current Lola payload
      2) EVERY file in data/overrides/ (clothes + class changes)
    Without (2), a class-only truco (food.almond → Holder) never gets served
    if Quick-Start cleared Lola or the item wasn't queued.
    """
    names: List[str] = []
    if ACTIVE_PAYLOAD_PATH.exists():
        try:
            text = ACTIVE_PAYLOAD_PATH.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        for match in re.finditer(
            r"inventory\.add(?:Options)?\s+\d+\s+([A-Za-z0-9_]+)\.",
            text,
            flags=re.IGNORECASE,
        ):
            names.append(f"{match.group(1)}.swf")
    if OVERRIDES_DIR.exists():
        for f in OVERRIDES_DIR.glob("*.swf"):
            names.append(f.name)
    seen = set()
    ordered: List[str] = []
    for name in names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(name)
    return ordered


def _build_pac(
    proxy_host: str = "127.0.0.1",
    proxy_port: int = PROXY_PORT,
    extra_files: Optional[List[str]] = None,
) -> str:
    """
    Route ALL Mundo Gaturro hosts through mitmproxy.

    Why host-based (not only lola.npc in the URL):
    On HTTPS, Windows/Electron PAC often evaluates with url=https://host:443/
    (no path). Path checks like indexOf("lola.npc") then fail → DIRECT →
    Lola never hits the proxy while the UI still shows "Proxy activo".

    The addon still only *rewrites* Lola / listed SWFs / catalogs; everything
    else is transparent pass-through. Non-MG traffic stays DIRECT.
    """
    _ = extra_files  # kept for API compatibility; SWF filter lives in the addon
    return f"""function FindProxyForURL(url, host) {{
    host = (host || "").toLowerCase();
    url = (url || "").toLowerCase();
    if (host.indexOf("mundogaturro") !== -1 || url.indexOf("mundogaturro") !== -1) {{
        return "PROXY {proxy_host}:{proxy_port}";
    }}
    return "DIRECT";
}}
"""


class _PacRequestHandler(BaseHTTPRequestHandler):
    # HTTP/1.0 + Connection:close evita CLOSE_WAIT eternos (Electron deja el socket abierto).
    protocol_version = "HTTP/1.0"

    def do_GET(self):
        path = (self.path or "/").split("?", 1)[0]
        if path in ("/", "/proxy.pac", "/mg-proxy.pac"):
            body = getattr(self.server, "pac_bytes", b"")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, *_args):
        return


class ProxyEngine:
    def __init__(self, port: int = PROXY_PORT):
        self.port = port
        # Si la UI Flask corre (ej. :5500), el PAC se sirve ahí (más estable que :18081).
        self.ui_port: Optional[int] = None
        self.process: Optional[subprocess.Popen] = None
        self.is_running = False
        self.logs = deque(maxlen=400)
        self.lock = threading.Lock()
        self.active_payload = "INICIO: DO\n    on activate A1\n\nA1: DO\n    user.state get\n    after 1 INICIO\n"
        self.pac_port: Optional[int] = None
        self._pac_server: Optional[HTTPServer] = None
        self._pac_thread: Optional[threading.Thread] = None
        self._saved_autoconfig: Optional[str] = None
        self._mitm_reader: Optional[threading.Thread] = None
        self._ensure_paths()
        atexit.register(self.stop)

    def _ensure_paths(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)
        if not ACTIVE_PAYLOAD_PATH.exists():
            ACTIVE_PAYLOAD_PATH.write_text(self.active_payload, encoding="utf-8")
        else:
            self.active_payload = ACTIVE_PAYLOAD_PATH.read_text(encoding="utf-8")

    def log(self, message: str, level: str = "INFO"):
        with self.lock:
            timestamp = time.strftime("%H:%M:%S")
            entry = f"[{timestamp}] [{level}] {message}"
            self.logs.append(entry)
            try:
                with open(LOGS_FILE_PATH, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
            except Exception:
                pass

    def get_logs(self, limit: int = 50) -> List[str]:
        """Prefer the on-disk log so addon [INTERCEPTADO] lines show in the UI."""
        lines: List[str] = []
        try:
            if LOGS_FILE_PATH.exists():
                raw = LOGS_FILE_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
                lines = [ln for ln in raw if ln.strip()]
        except Exception:
            lines = []
        if lines:
            return lines[-limit:]
        with self.lock:
            return list(self.logs)[-limit:]

    def _read_stats(self) -> Dict[str, Any]:
        try:
            if STATS_PATH.exists():
                import json
                return json.loads(STATS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _payload_summary(self) -> Dict[str, Any]:
        text = self.get_payload() or ""
        items = re.findall(
            r"inventory\.add(?:Options)?\s+(\d+)\s+([A-Za-z0-9_.]+)",
            text,
            flags=re.IGNORECASE,
        )
        return {
            "item_count": len(items),
            "items": [f"{qty}x {name}" for qty, name in items[:12]],
            "has_inventory_add": bool(items),
            "bytes": len(text.encode("utf-8")),
        }

    def set_payload(self, payload_text: str):
        self.active_payload = payload_text.strip() + "\n"
        ACTIVE_PAYLOAD_PATH.write_text(self.active_payload, encoding="utf-8")
        summary = self._payload_summary()
        self.log(
            f"Payload de Lola actualizado · {summary['item_count']} item(s)"
            + (f": {', '.join(summary['items'])}" if summary["items"] else " (sin inventory.add)"),
            "CONFIG",
        )
        self.refresh_pac()

    def get_payload(self) -> str:
        if ACTIVE_PAYLOAD_PATH.exists():
            return ACTIVE_PAYLOAD_PATH.read_text(encoding="utf-8")
        return self.active_payload

    def is_cert_installed(self) -> bool:
        # Cache: PowerShell/certutil en cada arranque sumaba varios segundos.
        cached = getattr(self, "_cert_ok_cached", None)
        if cached is not None:
            return bool(cached)
        try:
            res = subprocess.run(
                ["certutil", "-user", "-store", "-silent", "Root", "mitmproxy"],
                capture_output=True,
                text=True,
                timeout=6,
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out = (res.stdout or "") + (res.stderr or "")
            ok = res.returncode == 0 and "mitmproxy" in out.lower()
            self._cert_ok_cached = ok
            return ok
        except Exception:
            self._cert_ok_cached = False
            return False

    def ensure_cert(self) -> bool:
        cert_path = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.cer"
        if not cert_path.exists():
            self.log("Generando certificado SSL de mitmproxy...", "CERT")
            try:
                from mitmproxy.certs import CertStore
                cert_dir = cert_path.parent
                cert_dir.mkdir(parents=True, exist_ok=True)
                CertStore.create_store(cert_dir, "mitmproxy", 2048)
            except Exception as e:
                self.log(f"Error generando certificado: {e}", "ERROR")
                return False

        if not self.is_cert_installed():
            self.log("Instalando certificado en Trusted Root de Windows...", "CERT")
            try:
                res = subprocess.run(
                    ["certutil", "-user", "-addstore", "-f", "ROOT", str(cert_path)],
                    capture_output=True, text=True, errors="replace"
                )
                if res.returncode == 0:
                    self._cert_ok_cached = True
                    self.log("Certificado instalado correctamente.", "CERT")
                    return True
                else:
                    self.log(f"Fallo al instalar certificado: {res.stderr or res.stdout}", "ERROR")
                    return False
            except Exception as e:
                self.log(f"Excepcion instalando certificado: {e}", "ERROR")
                return False
        return True

    def _refresh_wininet(self) -> None:
        try:
            wininet = ctypes.windll.Wininet
            wininet.InternetSetOptionW(0, WININET_SETTINGS_CHANGED, 0, 0)
            wininet.InternetSetOptionW(0, WININET_REFRESH, 0, 0)
        except Exception:
            pass

    def _write_pac_file(self) -> bytes:
        files = list_intercept_swfs()
        INTERCEPT_LIST_PATH.write_text("\n".join(files), encoding="utf-8")
        text = _build_pac("127.0.0.1", self.port, extra_files=files)
        PAC_FILE_PATH.write_text(text, encoding="utf-8", newline="\n")
        return text.encode("utf-8")

    def refresh_pac(self) -> None:
        pac_bytes = self._write_pac_file()
        if self._pac_server is not None:
            self._pac_server.pac_bytes = pac_bytes
        if self.is_running and self.pac_port:
            try:
                reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, self._pac_url())
                winreg.CloseKey(key)
            except Exception:
                pass
            self._refresh_wininet()
        names = list_intercept_swfs()
        extra = f" · SWF a reescribir: {', '.join(names)}" if names else " · sin SWF trucado en cola"
        self.log(
            f"PAC: todo *.mundogaturro* → :{self.port} (addon reescribe Lola{extra}). Resto de internet DIRECT.",
            "NETWORK",
        )

    def _start_pac_server(self) -> bool:
        # Con UI Flask no hace falta el helper :18081 (era el que se trababa).
        if self.ui_port:
            self._write_pac_file()
            self.pac_port = int(self.ui_port)
            return True

        self._stop_pac_server()
        pac_bytes = self._write_pac_file()

        class _BoundHandler(_PacRequestHandler):
            pass

        last_err = None
        for port in range(PAC_PORT_START, PAC_PORT_START + 10):
            try:
                # Threading: un GET de Electron no puede colgar al resto.
                server = ThreadingHTTPServer(("127.0.0.1", port), _BoundHandler)
                server.daemon_threads = True
                server.pac_bytes = pac_bytes
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                self._pac_server = server
                self._pac_thread = thread
                self.pac_port = port
                return True
            except OSError as e:
                last_err = e
                continue
        self.log(f"No se pudo abrir el helper del proxy: {last_err}", "ERROR")
        return False

    def _stop_pac_server(self) -> None:
        server = self._pac_server
        self._pac_server = None
        self._pac_thread = None
        # No borrar pac_port si apunta al puerto de la UI Flask.
        if not self.ui_port:
            self.pac_port = None
        if server is None:
            return

        def _shutdown():
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass

        threading.Thread(target=_shutdown, daemon=True).start()

    def _pac_url(self) -> str:
        port = self.ui_port or self.pac_port or PAC_PORT_START
        return f"http://127.0.0.1:{port}/proxy.pac?t={int(time.time())}"

    def set_system_proxy(self, enable: bool) -> bool:
        """
        Use a PAC so ONLY Lola and the tricked base pack hit mitmproxy.
        Graphic packs, the rest of the game, and other apps go DIRECT.
        """
        try:
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                if not self._start_pac_server():
                    winreg.CloseKey(key)
                    return False
                try:
                    current, _ = winreg.QueryValueEx(key, "AutoConfigURL")
                    if current and "127.0.0.1" not in str(current):
                        self._saved_autoconfig = str(current)
                except FileNotFoundError:
                    self._saved_autoconfig = None
                # Igual que GitHub: solo PAC (ProxyEnable=0). No forzar ProxyServer
                # a todo Windows — eso rompía el cliente / otras apps.
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                try:
                    winreg.DeleteValue(key, "ProxyServer")
                except FileNotFoundError:
                    pass
                winreg.SetValueEx(key, "AutoDetect", 0, winreg.REG_DWORD, 0)
                winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, self._pac_url())
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "<local>;localhost;127.*")
                self.log(
                    f"PAC Windows OK → {self._pac_url()} · tráfico Mundo Gaturro al proxy :{self.port}",
                    "NETWORK",
                )
            else:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                try:
                    winreg.DeleteValue(key, "ProxyServer")
                except FileNotFoundError:
                    pass
                if self._saved_autoconfig:
                    winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, self._saved_autoconfig)
                else:
                    try:
                        winreg.DeleteValue(key, "AutoConfigURL")
                    except FileNotFoundError:
                        pass
                self._stop_pac_server()
                self.log("Proxy del juego desactivado.", "NETWORK")
            winreg.CloseKey(key)
            self._refresh_wininet()
            return True
        except Exception as e:
            self.log(f"Error configurando el proxy: {e}", "ERROR")
            return False

    def is_system_proxy_enabled(self) -> bool:
        try:
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
            try:
                auto, _ = winreg.QueryValueEx(key, "AutoConfigURL")
            except FileNotFoundError:
                auto = ""
            try:
                enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            except FileNotFoundError:
                enabled = 0
            winreg.CloseKey(key)
            auto_s = str(auto or "")
            if "127.0.0.1" in auto_s and ("/proxy.pac" in auto_s or "mg-proxy.pac" in auto_s):
                return True
            if self.ui_port and f"127.0.0.1:{self.ui_port}" in auto_s:
                return True
            if self.pac_port and f"127.0.0.1:{self.pac_port}" in auto_s:
                return True
            return bool(enabled == 1)
        except Exception:
            return False

    def _write_addon_script(self):
        # Generated at each start() so disk always matches this version.
        script_content = f'''"""mitmproxy addon generated by naw-tool."""
from mitmproxy import http
from pathlib import Path
import base64
import json
import re
import time

PAYLOAD_PATH = r"{ACTIVE_PAYLOAD_PATH}"
OVERRIDES_DIR = r"{OVERRIDES_DIR}"
INTERCEPT_LIST = r"{INTERCEPT_LIST_PATH}"
LOGS_FILE = r"{LOGS_FILE_PATH}"
STATS_FILE = r"{STATS_PATH}"

_seen_pass = set()
_pass_count = 0

def _ts():
    return time.strftime("%H:%M:%S")

def log_event(msg, level="INFO"):
    try:
        with open(LOGS_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{{_ts()}}] [{{level}}] {{msg}}\\n")
    except Exception:
        pass

def _inc_stat(**kwargs):
    try:
        data = {{}}
        p = Path(STATS_FILE)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {{}}
        for k, v in kwargs.items():
            if k.endswith("_hits") and isinstance(v, int) and v == 1:
                data[k] = int(data.get(k) or 0) + 1
            else:
                data[k] = v
        data["updated_at"] = time.time()
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def _payload_items(raw_text):
    return re.findall(
        r"inventory\\.add(?:Options)?\\s+(\\d+)\\s+([A-Za-z0-9_.]+)",
        raw_text or "",
        flags=re.IGNORECASE,
    )

def request(flow: http.HTTPFlow) -> None:
    global _pass_count
    url = flow.request.pretty_url or ""
    host = (flow.request.pretty_host or "").lower()
    path = flow.request.path or ""
    method = flow.request.method or "?"
    url_l = url.lower()
    path_l = path.lower()

    if "mundogaturro" in host or "mundogaturro" in url_l:
        key = f"{{method}} {{host}}{{path.split('?', 1)[0]}}"
        _pass_count += 1
        _inc_stat(last_mg_hit_at=time.time(), last_mg_url=url[:240], mg_hits=_pass_count)
        if key not in _seen_pass and len(_seen_pass) < 100:
            _seen_pass.add(key)
            log_event(f"[MG-HIT] {{method}} {{url[:220]}}", "DIAG")

    if "lola.npc" in url_l or path_l.endswith("lola.npc") or "/lola.npc" in path_l:
        items_preview = []
        try:
            raw_text = Path(PAYLOAD_PATH).read_text(encoding="utf-8")
            try:
                decoded = base64.b64decode(raw_text.strip().encode("utf-8")).decode("utf-8")
                if "on activate" in decoded or "inventory.add" in decoded or "initial" in decoded:
                    b64_payload = raw_text.strip()
                    items_preview = _payload_items(decoded)
                else:
                    b64_payload = base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")
                    items_preview = _payload_items(raw_text)
            except Exception:
                b64_payload = base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")
                items_preview = _payload_items(raw_text)
        except Exception as exc:
            fallback = "initial: DO\\r\\n    on activate A1\\r\\n\\r\\nINICIO: DO\\r\\n    on activate A1\\r\\n\\r\\nA1: DO\\r\\n    user.state get\\r\\n    after 1 initial\\r\\n"
            b64_payload = base64.b64encode(fallback.encode("utf-8")).decode("utf-8")
            log_event(f"[LOLA-WARN] No se pudo leer active_payload.txt ({{exc}}); fallback sin items", "ERROR")

        flow.response = http.Response.make(
            200,
            b64_payload,
            {{
                "Content-Type": "text/plain; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Content-Encoding": "identity",
            }}
        )
        raw_desc = raw_text
        try:
            raw_desc = decoded if "decoded" in locals() and decoded else raw_text
        except Exception:
            raw_desc = raw_text
        cat_m = re.search(r"catalog\s+([A-Za-z0-9_]+)", raw_desc or "", re.I)
        ban_m = re.search(r"modal\.banner\s+([A-Za-z0-9_]+)", raw_desc or "", re.I)
        room_m = re.search(r"room\.change\s+([0-9]+)", raw_desc or "", re.I)
        mini_m = re.search(r"minigame\s+([A-Za-z0-9_]+)", raw_desc or "", re.I)

        if items_preview:
            items_txt = ", ".join(f"{{q}}x {{n}}" for q, n in items_preview[:8])
        elif cat_m:
            items_txt = f"Catálogo: {{cat_m.group(1)}}"
        elif ban_m:
            items_txt = f"Banner: {{ban_m.group(1)}}"
        elif room_m:
            items_txt = f"Portal: Sala {{room_m.group(1)}}"
        elif mini_m:
            items_txt = f"Minijuego: {{mini_m.group(1)}}"
        else:
            items_txt = "(behavior activo)"

        log_event(f"[INTERCEPTADO] Lola NPC · {{url}} · {{items_txt}}", "INTERCEPTADO")
        _inc_stat(
            last_lola_at=time.time(),
            last_lola_url=url[:240],
            last_lola_items=items_txt,
            lola_hits=1,
        )
        print(f"[INTERCEPTADO] Lola NPC -> {{url}}")
        return

    if ".swf" in url_l:
        filename = url.split("?")[0].split("/")[-1]
        try:
            allowed = {{
                line.strip().lower()
                for line in Path(INTERCEPT_LIST).read_text(encoding="utf-8").splitlines()
                if line.strip()
            }}
        except Exception:
            allowed = set()
        override_file = Path(OVERRIDES_DIR) / filename
        if filename.lower() in allowed and override_file.exists():
            data = override_file.read_bytes()
            flow.response = http.Response.make(
                200,
                data,
                {{
                    "Content-Type": "application/x-shockwave-flash",
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                }}
            )
            log_event(f"[SWF OVERRIDE] {{filename}} · {{len(data)}} bytes · {{url[:180]}}", "SWF")
            _inc_stat(last_swf_at=time.time(), last_swf_name=filename, swf_hits=1)
            print(f"[SWF OVERRIDE] {{filename}}")
            return
        if filename.lower() in allowed and not override_file.exists():
            log_event(f"[SWF-MISS] {{filename}} en lista pero sin archivo en overrides/", "ERROR")

    if "/juego/catalogs/" in path or "cdn-ar.mundogaturro.com/juego/catalogs/" in url:
        cat_name = url.split("?")[0].split("/")[-1]
        override_cat = Path(OVERRIDES_DIR) / "catalogs" / cat_name
        if override_cat.exists():
            data = override_cat.read_bytes()
            flow.response = http.Response.make(
                200,
                data,
                {{
                    "Content-Type": "application/json; charset=utf-8",
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-cache",
                }}
            )
            log_event(f"[CATALOG OVERRIDE] {{cat_name}}", "TIENDA")
            return
'''
        ADDON_SCRIPT_PATH.write_text(script_content, encoding="utf-8")

    def _find_mitmdump(self) -> Optional[str]:
        # Python Scripts candidate
        scripts_dir = Path(sys.executable).parent / "Scripts"
        for cand in [
            scripts_dir / "mitmdump.exe",
            scripts_dir / "mitmdump",
            Path(sys.executable).parent / "mitmdump.exe"
        ]:
            if cand.exists():
                return str(cand)
        return shutil.which("mitmdump")

    def _kill_port_owner(self):
        """Termina cualquier proceso residual que retenga el puerto del proxy (netstat, sin PowerShell)."""
        try:
            res = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                timeout=4,
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            needle = f":{self.port}"
            pids = set()
            for line in (res.stdout or "").splitlines():
                if needle not in line:
                    continue
                upper = line.upper()
                if "LISTENING" not in upper and "ESCUCHANDO" not in upper:
                    continue
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(int(parts[-1]))
            my_pid = os.getpid()
            killed = False
            for pid in pids:
                if pid != my_pid and pid > 0:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    self.log(f"Puerto {self.port} liberado (proceso residual PID {pid} cerrado).", "INFO")
                    killed = True
            if killed:
                time.sleep(0.25)
        except Exception:
            pass

    def _drain_mitm_pipes(self) -> None:
        proc = self.process
        if not proc:
            return

        def _read(stream, label: str):
            try:
                for line in iter(stream.readline, ""):
                    text = (line or "").strip()
                    if not text:
                        continue
                    level = "MITM"
                    low = text.lower()
                    if "error" in low or "traceback" in low:
                        level = "ERROR"
                    elif "interceptado" in low or "swf override" in low:
                        level = "INTERCEPTADO"
                    self.log(f"[{label}] {text}", level)
            except Exception:
                pass

        for stream, label in ((proc.stdout, "mitm-out"), (proc.stderr, "mitm-err")):
            if stream is None:
                continue
            t = threading.Thread(target=_read, args=(stream, label), daemon=True)
            t.start()

    def _reset_session_stats(self) -> None:
        try:
            import json
            STATS_PATH.write_text(
                json.dumps(
                    {
                        "session_started_at": time.time(),
                        "mg_hits": 0,
                        "lola_hits": 0,
                        "swf_hits": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _log_startup_diagnostics(self) -> None:
        cert_ok = self.is_cert_installed()
        pac_ok = self.is_system_proxy_enabled()
        summary = self._payload_summary()
        overrides = list_override_files()
        intercept = list_intercept_swfs()
        self.log(
            f"Diagnóstico arranque · cert={'OK' if cert_ok else 'FALTA'} · "
            f"PAC={'OK' if pac_ok else 'NO'} · payload_items={summary['item_count']} · "
            f"overrides={len(overrides)} · intercept_swfs={intercept or '-'}",
            "DIAG",
        )
        if summary["items"]:
            self.log(f"Lola va a entregar: {', '.join(summary['items'])}", "CONFIG")
        else:
            self.log(
                "Payload sin inventory.add: al tocar Lola no va a tirar items (aunque el proxy ande).",
                "WARN",
            )
        if not cert_ok:
            self.log(
                "Certificado mitmproxy NO está en Trusted Root: HTTPS del juego puede ignorar el proxy.",
                "ERROR",
            )
        try:
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
            try:
                auto, _ = winreg.QueryValueEx(key, "AutoConfigURL")
            except FileNotFoundError:
                auto = ""
            winreg.CloseKey(key)
            self.log(f"AutoConfigURL actual: {auto or '(vacío)'}", "DIAG")
        except Exception as e:
            self.log(f"No se pudo leer AutoConfigURL: {e}", "ERROR")

    def start(self) -> bool:
        if self.is_running and self.process and self.process.poll() is None:
            return True

        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                self.log(f"El puerto {self.port} está ocupado. Cerrá la otra aplicación de proxy antes de iniciar naw.", "ERROR")
                return False
        except OSError:
            pass
        cert_ok = self.ensure_cert()
        self._write_addon_script()
        self._reset_session_stats()

        cmd = [
            sys.executable, "-c", "from mitmproxy.tools.main import mitmdump; mitmdump()",
            "--listen-port", str(self.port),
            "-s", str(ADDON_SCRIPT_PATH),
            "--allow-hosts", r".*mundogaturro.*",
            "--quiet",
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._drain_mitm_pipes()
            # Esperar a que el puerto escuche (suele ser <0.5s) en vez de sleep fijo 1.2s.
            ready = False
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if self.process.poll() is not None:
                    break
                try:
                    with socket.create_connection(("127.0.0.1", self.port), timeout=0.12):
                        ready = True
                        break
                except OSError:
                    time.sleep(0.08)
            if self.process.poll() is not None or not ready:
                self.log("Fallo al iniciar mitmdump (proceso salió al toque). Mirá líneas [mitm-err].", "ERROR")
                try:
                    if self.process and self.process.poll() is None:
                        self.process.terminate()
                except Exception:
                    pass
                self.process = None
                return False

            self.is_running = True
            pac_ok = self.set_system_proxy(True)
            if not pac_ok:
                self.log("mitmdump está up pero NO se pudo aplicar el PAC de Windows.", "ERROR")
                try:
                    self.process.terminate()
                except Exception:
                    pass
                self.process = None
                self.is_running = False
                return False

            self._log_startup_diagnostics()
            if not cert_ok:
                self.log("Proxy up con advertencia: certificado no instalado.", "WARN")
            self.log(
                f"Proxy OK en :{self.port}. Abrí el juego con 'Abrir MG aplicado', "
                f"hablá con Lola y en Logs tiene que aparecer [INTERCEPTADO] / [MG-HIT].",
                "SUCCESS",
            )
            return True
        except Exception as e:
            self.log(f"Excepcion al iniciar proxy: {e}", "ERROR")
            return False

    def stop(self) -> bool:
        if self.process is None and not self.is_running and self._pac_server is None:
            return True
        self.set_system_proxy(False)
        self._stop_pac_server()
        proc = self.process
        self.process = None
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            # Drop pipe handles so reader threads can exit on Windows.
            for stream in (proc.stdout, proc.stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass

        self.is_running = False
        self.log("Proxy detenido.", "INFO")
        return True

    def get_status(self) -> Dict[str, Any]:
        running = bool(self.is_running and self.process and self.process.poll() is None)
        self.is_running = running
        stats = self._read_stats()
        now = time.time()

        def _ago(key: str) -> Optional[float]:
            val = stats.get(key)
            try:
                return max(0.0, now - float(val))
            except Exception:
                return None

        summary = self._payload_summary()
        last_lola_ago = _ago("last_lola_at")
        last_mg_ago = _ago("last_mg_hit_at")
        return {
            "running": running,
            "port": self.port,
            "system_proxy_enabled": self.is_system_proxy_enabled(),
            "pac_url": self._pac_url() if self.pac_port else "",
            "cert_installed": self.is_cert_installed(),
            "active_overrides": [f.name for f in OVERRIDES_DIR.glob("*.swf")],
            "intercept_swfs": list_intercept_swfs(),
            "payload_summary": summary,
            "stats": {
                "mg_hits": int(stats.get("mg_hits") or 0),
                "lola_hits": int(stats.get("lola_hits") or 0),
                "swf_hits": int(stats.get("swf_hits") or 0),
                "last_lola_ago_sec": last_lola_ago,
                "last_mg_ago_sec": last_mg_ago,
                "last_lola_items": stats.get("last_lola_items") or "",
                "last_mg_url": stats.get("last_mg_url") or "",
                "last_swf_name": stats.get("last_swf_name") or "",
            },
            "health": {
                "seeing_mg_traffic": bool(last_mg_ago is not None and last_mg_ago < 120),
                "saw_lola": bool(last_lola_ago is not None),
                "hint": (
                    "OK: Lola llegó al proxy"
                    if last_lola_ago is not None and last_lola_ago < 300
                    else (
                        "El juego está pegándole al proxy, pero todavía no tocó Lola"
                        if last_mg_ago is not None and last_mg_ago < 120
                        else (
                            "Proxy up pero sin tráfico MG: el cliente probablemente no está usando el PAC. "
                            "Usá 'Abrir MG aplicado' (mata + limpia caché + relaunch)."
                            if running
                            else "Proxy apagado"
                        )
                    )
                ),
            },
        }


engine = ProxyEngine()
