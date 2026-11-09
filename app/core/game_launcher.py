"""
game_launcher.py - Utility to manage Mundo Gaturro desktop client lifecycle.
Handles killing the process, purging cache while preserving cookies, and launching.
Includes resilient multi-strategy game detection for any Windows environment.
"""

import os
import re
import shutil
import subprocess
import time
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional, List, Tuple

# Win32 definitions
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.OpenProcess.restype = wintypes.HANDLE
k32.CloseHandle.argtypes = [wintypes.HANDLE]

u32 = ctypes.WinDLL("user32", use_last_error=True)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

GAME_PATH_FILE = Path(__file__).resolve().parent.parent / "data" / "game_path.txt"

# Process name patterns that match Mundo Gaturro or Flash players
GAME_EXE_NAMES = {
    "mundogaturro.exe", "gaturro.exe", "mg.exe", "mgdesktop.exe",
    "gaturro-desktop.exe", "flashplayer.exe", "flashplayer_32_sa.exe",
    "saflashplayer.exe", "flashplayerdebugger.exe"
}

# Processes to exclude from detection
EXCLUDED_NAMES = {
    "python.exe", "pythonw.exe", "mitmdump.exe", "mitmproxy.exe",
    "code.exe", "git.exe", "conhost.exe", "powershell.exe", "cmd.exe"
}

# Nunca cachear/lanzar navegadores (pasó: game_path.txt → zen.exe)
BROWSER_EXE_NAMES = {
    "zen.exe", "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "opera.exe", "opera_gx.exe", "vivaldi.exe", "iexplore.exe", "safari.exe",
    "chromium.exe", "waterfox.exe", "librewolf.exe", "arc.exe",
}


def _is_valid_game_exe(path: Optional[Path]) -> bool:
    """True solo para el cliente MG / Flash, nunca un browser genérico."""
    if not path:
        return False
    try:
        p = path if isinstance(path, Path) else Path(path)
        if not p.exists() or not p.is_file():
            return False
        name = p.name.lower()
        if name in BROWSER_EXE_NAMES or name in EXCLUDED_NAMES:
            return False
        if "uninstall" in name:
            return False
        full = str(p).lower().replace("/", "\\")
        if any(b in full for b in ("\\zen browser\\", "\\google\\chrome", "\\mozilla firefox", "\\microsoft\\edge")):
            return False
        if name in GAME_EXE_NAMES:
            return True
        if "gaturro" in full or "mundogaturro" in full:
            return name.endswith(".exe")
        return False
    except Exception:
        return False


def _iter_processes():
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value:
        return
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not k32.Process32FirstW(snap, ctypes.byref(pe)):
            return
        while True:
            yield pe.th32ProcessID, pe.th32ParentProcessID, pe.szExeFile
            if not k32.Process32NextW(snap, ctypes.byref(pe)):
                break
    finally:
        k32.CloseHandle(snap)


def get_process_image_path(pid: int) -> Optional[str]:
    """Retrieves full image path for a process using Win32 API."""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
    except Exception:
        pass
    finally:
        k32.CloseHandle(h)
    return None


def find_game_processes() -> List[Tuple[int, str]]:
    """
    Finds running Mundo Gaturro processes using multiple detection strategies:
    1. Executable name matching (case-insensitive substring 'gaturro' or 'mundogaturro').
    2. Known executable names list (e.g. mg.exe, flashplayer.exe).
    3. Executable image path matching (path containing 'gaturro' or 'mundogaturro').
    4. Top-level window titles containing 'Mundo Gaturro' or 'Gaturro'.
    5. Automatic inclusion of all descendant child processes (Electron GPU/renderer/Flash).
    """
    procs = list(_iter_processes() or [])
    if not procs:
        return []

    roots: dict[int, str] = {}

    for pid, _parent, name in procs:
        n_low = name.lower()
        if n_low in EXCLUDED_NAMES or "uninstall" in n_low or n_low.endswith((".py", ".bat", ".cmd", ".ps1")):
            continue

        # Strategy 1: Name contains gaturro or mundogaturro
        if "mundogaturro" in n_low or "gaturro" in n_low:
            roots[pid] = name
            continue

        # Strategy 2: Known game/flash exe names
        if n_low in GAME_EXE_NAMES:
            img = get_process_image_path(pid)
            if img and ("gaturro" in img.lower() or "mundo" in img.lower()):
                roots[pid] = name
            elif n_low in ("mg.exe", "mgdesktop.exe"):
                roots[pid] = name

    # Strategy 3: Check visible windows for 'gaturro' in title
    try:
        def _enum_win_cb(hwnd, lparam):
            if u32.IsWindowVisible(hwnd):
                length = u32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    u32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.lower()
                    if "gaturro" in title or "mundo gaturro" in title:
                        wpid = wintypes.DWORD()
                        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                        if wpid.value > 0 and wpid.value not in roots:
                            roots[wpid.value] = "MundoGaturro.exe"
            return True

        u32.EnumWindows(WNDENUMPROC(_enum_win_cb), 0)
    except Exception:
        pass

    if not roots:
        return []

    # Strategy 4: Include all descendants (Electron / Flash child & grandchild processes)
    all_pids = dict(roots)
    added = True
    while added:
        added = False
        for pid, parent, name in procs:
            if parent in all_pids and pid not in all_pids:
                all_pids[pid] = name
                added = True

    # Cache found path for future launches (nunca browsers)
    for pid in roots:
        img_path = get_process_image_path(pid)
        if img_path and _is_valid_game_exe(Path(img_path)):
            _save_game_path(Path(img_path))
            break

    return list(all_pids.items())


def find_pids_connected_to_proxy(port: int = 8080) -> List[int]:
    """Finds PIDs of processes actively connected to the proxy port."""
    pids = set()
    try:
        output = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        my_pid = os.getpid()
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper() == "TCP":
                remote = parts[2]
                state = parts[3]
                pid_str = parts[4]
                if f":{port}" in remote and state.upper() in ("ESTABLISHED", "TIME_WAIT", "CLOSE_WAIT"):
                    if pid_str.isdigit():
                        p = int(pid_str)
                        if p > 0 and p != my_pid:
                            pids.add(p)
    except Exception:
        pass
    return list(pids)


def is_game_running() -> bool:
    """
    Robust check if Mundo Gaturro is running.
    Checks:
    1. Win32 Toolhelp32 process list and process tree.
    2. Window titles.
    3. Active proxy traffic (if proxy is running and received traffic for mundogaturro recently).
    4. Tasklist fallback with errors="replace".
    """
    try:
        pids = find_game_processes()
        if pids:
            return True
    except Exception:
        pass

    # Proxy traffic correlation: if proxy intercepted MG traffic in the last 120s, game is active
    try:
        from core import proxy_engine
        st = proxy_engine.proxy_engine.get_status()
        if st.get("running"):
            stats = st.get("stats", {})
            last_mg = stats.get("last_mg_ago_sec")
            last_lola = stats.get("last_lola_ago_sec")
            if (last_mg is not None and last_mg < 120) or (last_lola is not None and last_lola < 120):
                return True
    except Exception:
        pass

    # Tasklist fallback with errors="replace"
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq MundoGaturro.exe", "/FO", "CSV"],
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return "mundogaturro.exe" in output.lower()
    except Exception:
        pass

    return False


def kill_game() -> bool:
    killed_any = False
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/IM", "MundoGaturro.exe"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        killed_any = True
    except Exception:
        pass

    try:
        for pid, _ in find_game_processes():
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            killed_any = True
    except Exception:
        pass

    return killed_any


def wait_game_dead(timeout_sec: float = 6.0) -> bool:
    """
    Mata en loop hasta que no quede ningún proceso MG.
    Si queda una instancia vieja, Electron single-instance ignora el relaunch
    con --proxy-server → cero [MG-HIT] y Lola 'normal'.
    """
    deadline = time.time() + max(0.5, float(timeout_sec))
    while time.time() < deadline:
        kill_game()
        try:
            alive = bool(find_game_processes())
        except Exception:
            alive = False
        if not alive:
            # Doble check tasklist
            try:
                output = subprocess.check_output(
                    ["tasklist", "/FI", "IMAGENAME eq MundoGaturro.exe", "/FO", "CSV"],
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if "mundogaturro.exe" not in output.lower():
                    return True
            except Exception:
                return True
        time.sleep(0.3)
    try:
        return not bool(find_game_processes())
    except Exception:
        return False


def clean_game_cache(light: bool = False) -> bool:
    """
    light=True: limpia TODA la caché Pepper Flash (menos SharedObjects) —
    si queda un toys.swf viejo en disco, el MG abre minijuegos sin pegarle al proxy.
    light=False: también Cache/GPU de Electron.
    """
    appdata = os.environ.get("APPDATA")
    local_appdata = os.environ.get("LOCALAPPDATA")

    target_dirs = []
    if appdata:
        target_dirs.extend([
            Path(appdata) / "MundoGaturro",
            Path(appdata) / "gaturro-desktop",
        ])
    if local_appdata:
        target_dirs.extend([
            Path(local_appdata) / "MundoGaturro",
            Path(local_appdata) / "gaturro-desktop",
        ])

    keep_flash_names = {"#sharedobjects", "sharedobjects", "mms.cfg"}

    for base in target_dirs:
        if not base.exists():
            continue
        pepper_flash = base / "Pepper Data" / "Shockwave Flash"
        if pepper_flash.exists():
            try:
                for child in pepper_flash.iterdir():
                    if child.name.lower() in keep_flash_names:
                        continue
                    try:
                        if child.is_dir():
                            shutil.rmtree(child, ignore_errors=True)
                        else:
                            child.unlink(missing_ok=True)
                    except Exception:
                        pass
            except Exception:
                pass
        # Por las dudas el path clásico
        for extra in (
            pepper_flash / "CacheWritableAdobeRoot",
            pepper_flash / "WritableRoot",
        ):
            try:
                if extra.exists():
                    shutil.rmtree(extra, ignore_errors=True)
            except Exception:
                pass
        if not light:
            for target in (
                base / "Cache",
                base / "Code Cache",
                base / "GPUCache",
                base / "blob_storage",
            ):
                try:
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target, ignore_errors=True)
                        else:
                            target.unlink(missing_ok=True)
                except Exception:
                    pass

    return True


def _save_game_path(path: Path) -> None:
    if not _is_valid_game_exe(path):
        return
    try:
        GAME_PATH_FILE.parent.mkdir(parents=True, exist_ok=True)
        GAME_PATH_FILE.write_text(str(path.resolve()), encoding="utf-8")
    except Exception:
        pass


def _resolve_lnk_file(lnk_path: Path) -> Optional[Path]:
    """Extracts target path from Windows .lnk shortcut without external dependencies."""
    if not lnk_path.exists():
        return None
    try:
        data = lnk_path.read_bytes()
        ascii_matches = re.findall(rb'[A-Za-z]:\\[^<>\":|?*\x00-\x1f\x7f-\x9f]+?\.exe', data, re.IGNORECASE)
        for m in ascii_matches:
            target = Path(m.decode("ascii", errors="ignore"))
            if target.exists() and "uninstall" not in target.name.lower():
                return target
        utf16_matches = re.findall(rb'(?:[A-Za-z]\x00:\x00\\(?:[^\x00]\x00)+?\.exe)', data, re.IGNORECASE)
        for m in utf16_matches:
            target = Path(m.decode("utf-16-le", errors="ignore"))
            if target.exists() and "uninstall" not in target.name.lower():
                return target
    except Exception:
        pass
    return None


def get_game_executable_path() -> Optional[Path]:
    """
    Discovers the Mundo Gaturro executable path across any computer:
    1. From a currently running process (100% exact).
    2. From previously saved/cached location (data/game_path.txt).
    3. Common install directories across LocalAppData, AppData, ProgramFiles, ProgramFiles(x86).
    4. Start Menu shortcuts and Desktop shortcuts.
    """
    # 1. Saved path primero (rápido; evita escanear procesos/atajos en cada Abrir MG)
    if GAME_PATH_FILE.exists():
        try:
            saved = Path(GAME_PATH_FILE.read_text(encoding="utf-8").strip())
            if _is_valid_game_exe(saved):
                return saved
            try:
                GAME_PATH_FILE.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            pass

    # 2. From currently running process (solo exe válido de MG)
    procs = find_game_processes()
    for pid, _ in procs:
        img = get_process_image_path(pid)
        if img:
            p = Path(img)
            if _is_valid_game_exe(p):
                _save_game_path(p)
                return p

    # 3. Known standard install directories
    local_app = os.environ.get("LOCALAPPDATA", "")
    app_data = os.environ.get("APPDATA", "")
    prog_files = os.environ.get("ProgramFiles", "")
    prog_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    user_prof = os.environ.get("USERPROFILE", "")

    candidate_dirs = [
        Path(local_app) / "Programs" / "gaturro-desktop" if local_app else None,
        Path(local_app) / "gaturro-desktop" if local_app else None,
        Path(app_data) / "MundoGaturro" if app_data else None,
        Path(prog_files) / "MundoGaturro" if prog_files else None,
        Path(prog_files) / "Mundo Gaturro" if prog_files else None,
        Path(prog_files_x86) / "MundoGaturro" if prog_files_x86 else None,
        Path(prog_files_x86) / "Mundo Gaturro" if prog_files_x86 else None,
        Path(user_prof) / "Desktop" if user_prof else None,
    ]

    exe_names = ["MundoGaturro.exe", "Mundo Gaturro.exe", "gaturro.exe", "mg.exe"]
    for c_dir in candidate_dirs:
        if not c_dir or not c_dir.exists():
            continue
        for name in exe_names:
            candidate = c_dir / name
            if _is_valid_game_exe(candidate):
                _save_game_path(candidate)
                return candidate

    # 4. Search Start Menu and Desktop shortcuts (.lnk)
    shortcut_dirs = [
        Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs" if app_data else None,
        Path(os.environ.get("ProgramData", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(user_prof) / "Desktop" if user_prof else None,
        Path(os.environ.get("PUBLIC", "")) / "Desktop",
    ]

    for s_dir in shortcut_dirs:
        if not s_dir or not s_dir.exists():
            continue
        try:
            for lnk in s_dir.rglob("*.lnk"):
                if "gaturro" in lnk.name.lower() or "mundo" in lnk.name.lower():
                    target = _resolve_lnk_file(lnk)
                    if _is_valid_game_exe(target):
                        _save_game_path(target)
                        return target
        except Exception:
            pass

    return None


def focus_game_window() -> bool:
    """Brings any running Mundo Gaturro window to the foreground and un-minimizes it."""
    try:
        ps_cmd = (
            "$p = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '(?i)mundogaturro|gaturro' -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1; "
            "if ($p) { "
            "$sig = '[DllImport(\"user32.dll\")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow); [DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr hWnd);'; "
            "$type = Add-Type -MemberDefinition $sig -Name Win32Utils -Namespace Win32 -PassThru; "
            "$type::ShowWindowAsync($p.MainWindowHandle, 9); " # 9 = SW_RESTORE
            "$type::SetForegroundWindow($p.MainWindowHandle); "
            "}"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except Exception:
        return False


def launch_game(
    executable_path: Optional[str] = None,
    proxy_pac_url: Optional[str] = None,
) -> bool:
    """
    Launch Mundo Gaturro (como en GitHub).
    Con proxy_pac_url: Electron --proxy-pac-url (sin --proxy-server ni ignore-cert).
    """
    path = Path(executable_path) if executable_path else get_game_executable_path()

    if proxy_pac_url and path and path.exists():
        try:
            args = [
                str(path),
                f"--proxy-pac-url={proxy_pac_url}",
                "--proxy-bypass-list=<-loopback>",
            ]
            subprocess.Popen(args, cwd=str(path.parent), shell=False)
            return True
        except Exception:
            pass

    desktop_bat = Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "mg.bat"
    if not executable_path and not proxy_pac_url and desktop_bat.exists():
        try:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(desktop_bat)], shell=False)
            return True
        except Exception:
            pass

    if not path or not path.exists():
        return False

    try:
        if proxy_pac_url:
            args = [
                str(path),
                f"--proxy-pac-url={proxy_pac_url}",
                "--proxy-bypass-list=<-loopback>",
            ]
            subprocess.Popen(args, cwd=str(path.parent), shell=False)
        else:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(path)], cwd=str(path.parent), shell=False)
        return True
    except Exception:
        try:
            os.startfile(str(path))
            return True
        except Exception:
            return False


def restart_game_with_clean_cache() -> bool:
    kill_game()
    clean_game_cache()
    return launch_game()
