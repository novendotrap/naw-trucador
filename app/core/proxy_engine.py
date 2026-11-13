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
        self._lifecycle_lock = threading.RLock()
        self._mitm_readers = []
        self._mitm_output = deque(maxlen=40)
        self.last_error: Optional[str] = None
        self._proxy_settings = None
        self._applied_pac_url = None
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
            key = None
            try:
                reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
                current, _ = winreg.QueryValueEx(key, "AutoConfigURL")
                if current == self._applied_pac_url:
                    applied = self._pac_url()
                    winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, applied)
                    self._applied_pac_url = applied
            except Exception:
                pass
            finally:
                if key is not None:
                    winreg.CloseKey(key)
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
        """Temporarily apply our PAC and restore all settings we changed."""
        names = ("ProxyEnable", "ProxyServer", "AutoDetect", "AutoConfigURL", "ProxyOverride")
        key = None
        try:
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                if self._proxy_settings is None:
                    saved = {}
                    for name in names:
                        try:
                            saved[name] = winreg.QueryValueEx(key, name)
                        except FileNotFoundError:
                            saved[name] = None
                    self._proxy_settings = saved
                if not self._start_pac_server():
                    self._proxy_settings = None
                    return False
                self._applied_pac_url = self._pac_url()
                # Mark ownership before writing so partial failures can be rolled back.
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                try:
                    winreg.DeleteValue(key, "ProxyServer")
                except FileNotFoundError:
                    pass
                winreg.SetValueEx(key, "AutoDetect", 0, winreg.REG_DWORD, 0)
                winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, self._applied_pac_url)
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "<local>;localhost;127.*")
                self.log(
                    f"PAC Windows OK → {self._pac_url()} · tráfico Mundo Gaturro al proxy :{self.port}",
                    "NETWORK",
                )
            else:
                if self._proxy_settings is not None:
                    try:
                        current, _ = winreg.QueryValueEx(key, "AutoConfigURL")
                    except FileNotFoundError:
                        current = None
                    # Do not overwrite changes made meanwhile by another proxy/VPN.
                    if current == self._applied_pac_url:
                        self._restore_proxy_settings(key)
                    else:
                        self.log("La configuración de red cambió fuera de naw; se conserva la configuración actual.", "WARN")
                    self._proxy_settings = None
                    self._applied_pac_url = None
                self._stop_pac_server()
                self.log("Proxy del juego desactivado.", "NETWORK")
            self._refresh_wininet()
            return True
        except Exception as e:
            if enable and key is not None and self._proxy_settings is not None:
                try:
                    self._restore_proxy_settings(key)
                    self._proxy_settings = None
                    self._applied_pac_url = None
                    self._refresh_wininet()
                except Exception as restore_error:
                    self.log(f"No se pudo restaurar la configuración de red: {restore_error}", "ERROR")
            self.log(f"Error configurando el proxy: {e}", "ERROR")
            return False
        finally:
            if key is not None:
                winreg.CloseKey(key)

    def _restore_proxy_settings(self, key):
        for name, previous in self._proxy_settings.items():
            if previous is None:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
            else:
                value, kind = previous
                winreg.SetValueEx(key, name, 0, kind, value)

    def is_system_proxy_enabled(self) -> bool:
        try:
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
            try:
                auto, _ = winreg.QueryValueEx(key, "AutoConfigURL")
            except FileNotFoundError:
                auto = ""
            winreg.CloseKey(key)
            return bool(self._applied_pac_url and str(auto or "") == self._applied_pac_url)
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
        cat_m = re.search(r"catalog\\s+([A-Za-z0-9_]+)", raw_desc or "", re.I)
        ban_m = re.search(r"modal\\.banner\\s+([A-Za-z0-9_]+)", raw_desc or "", re.I)
        room_m = re.search(r"room\\.change\\s+([0-9]+)", raw_desc or "", re.I)
        mini_m = re.search(r"minigame\\s+([A-Za-z0-9_]+)", raw_desc or "", re.I)

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
                    self._mitm_output.append(text)
                    level = "MITM"
                    low = text.lower()
                    if "error" in low or "traceback" in low:
                        level = "ERROR"
                    elif "interceptado" in low or "swf override" in low:
                        level = "INTERCEPTADO"
                    self.log(f"[{label}] {text}", level)
            except Exception as error:
                self.log(f"No se pudo leer la salida del proxy: {error}", "ERROR")

        for stream, label in ((proc.stdout, "mitm-out"), (proc.stderr, "mitm-err")):
            if stream is None:
                continue
            t = threading.Thread(target=_read, args=(stream, label), daemon=True)
            t.start()
            self._mitm_readers.append(t)

    def _start_error(self, message: str) -> bool:
        self.last_error = message
        self.log(message, "ERROR")
        return False

    def _process_error(self, returncode=None, timed_out=False) -> str:
        detail = " | ".join(list(self._mitm_output)[-6:])[-2400:]
        low = detail.lower()
        hint = ""
        if "no module named" in low or "importerror" in low:
            hint = " Ejecutá Instalar.bat en esta misma carpeta para revisar las dependencias."
        elif "dll" in low or returncode in (3221225781, -1073741515):
            hint = " Falta cargar una biblioteca nativa. Revisá el redistribuible Microsoft Visual C++ x64 y el detalle del error."
        elif "10048" in low or "address already in use" in low:
            hint = f" El puerto {self.port} fue ocupado por otro proceso; cerrá la otra aplicación de proxy."
        elif "10013" in low or "permissionerror" in low or "access is denied" in low:
            hint = " Windows rechazó el acceso al puerto o a un archivo. Revisá permisos y el bloqueo indicado por Windows."
        elif "config.yaml" in low or "config.yml" in low:
            hint = " Revisá la configuración de mitmproxy indicada en el error; no borres tus certificados."
        if timed_out:
            message = f"El proxy no abrió 127.0.0.1:{self.port} dentro de 20 segundos."
        else:
            message = f"El proceso del proxy terminó (código {returncode})."
        return message + hint + (f" Detalle: {detail}" if detail else " No emitió detalles; revisá si Windows bloqueó el proceso.")

    def _close_process(self, proc) -> None:
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        finally:
            for reader in self._mitm_readers:
                reader.join(timeout=0.5)
            self._mitm_readers = []
            for stream in (proc.stdout, proc.stderr):
                if stream:
                    stream.close()

    def _watch_process(self, proc) -> None:
        code = proc.wait()
        with self._lifecycle_lock:
            if self.process is not proc:
                return
            for reader in self._mitm_readers:
                reader.join(timeout=0.5)
            self._start_error(self._process_error(code))
            self.set_system_proxy(False)
            self._stop_pac_server()
            self.process = None
            self.is_running = False
            self._close_process(proc)

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
        with self._lifecycle_lock:
            return self._start_locked()

    def _start_locked(self) -> bool:
        if self.is_running and self.process and self.process.poll() is None:
            return True
        # A dead previous child must not leave the Windows PAC pointing at it.
        if self.process is not None:
            self.stop()
        self.last_error = None
        self._mitm_output.clear()
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", self.port))
        except OSError as error:
            return self._start_error(f"No se puede usar el puerto local {self.port}: {error}. Cerrá la otra aplicación de proxy si está ocupado.")

        try:
            cert_ok = self.ensure_cert()
            if not cert_ok:
                return self._start_error("No se pudo preparar el certificado del proxy. Revisá el error [CERT] anterior; no se cambió el proxy de Windows.")
            self._write_addon_script()
            compile(ADDON_SCRIPT_PATH.read_text(encoding="utf-8"), str(ADDON_SCRIPT_PATH), "exec")
            self._reset_session_stats()
            cmd = [
                sys.executable, "-I", "-u", "-X", "utf8", "-c",
                "from mitmproxy.tools.main import mitmdump; mitmdump()",
                "--listen-host", "127.0.0.1", "--listen-port", str(self.port),
                "-s", str(ADDON_SCRIPT_PATH),
                "--allow-hosts", r".*mundogaturro.*", "--quiet",
            ]
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8:replace"
            self.log(f"Iniciando proxy · Python {sys.version.split()[0]} · {sys.executable} · 127.0.0.1:{self.port}", "DIAG")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=str(ROOT_DIR),
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._drain_mitm_pipes()
            # Slow PCs may need more than three seconds to import native libraries.
            ready = False
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    break
                try:
                    with socket.create_connection(("127.0.0.1", self.port), timeout=0.12):
                        ready = True
                        break
                except OSError:
                    time.sleep(0.08)
            if self.process.poll() is not None or not ready:
                code = self.process.poll()
                self._close_process(self.process)
                self.process = None
                return self._start_error(self._process_error(code, timed_out=code is None))

            self.is_running = True
            pac_ok = self.set_system_proxy(True)
            if not pac_ok:
                self.set_system_proxy(False)
                self._stop_pac_server()
                self._close_process(self.process)
                self.process = None
                self.is_running = False
                return self._start_error("El proxy arrancó, pero Windows no permitió aplicar su configuración PAC. Revisá el error de configuración anterior.")

            self._log_startup_diagnostics()
            if not cert_ok:
                self.log("Proxy up con advertencia: certificado no instalado.", "WARN")
            self.log(
                f"Proxy OK en :{self.port}. Abrí el juego con 'Abrir MG aplicado', "
                f"hablá con Lola y en Logs tiene que aparecer [INTERCEPTADO] / [MG-HIT].",
                "SUCCESS",
            )
            threading.Thread(target=self._watch_process, args=(self.process,), daemon=True).start()
            return True
        except Exception as e:
            self.stop()
            return self._start_error(f"No se pudo iniciar el proxy: {type(e).__name__}: {e}")

    def stop(self) -> bool:
        with self._lifecycle_lock:
            return self._stop_locked()

    def _stop_locked(self) -> bool:
        if self.process is None and not self.is_running and self._pac_server is None and self._proxy_settings is None:
            return True
        network_restored = self.set_system_proxy(False)
        self._stop_pac_server()
        proc = self.process
        self.process = None
        if proc is not None:
            self._close_process(proc)

        self.is_running = False
        self.log("Proxy detenido.", "INFO")
        return network_restored

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
            "last_error": self.last_error,
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
