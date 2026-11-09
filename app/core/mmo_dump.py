"""Saca el mmo.swf de la RAM del juego abierto.

El CDN entrega un MMO que no sirve. El que sirve es el que Flash
ya cargó en el proceso de Mundo Gaturro: se buscan SWF en memoria
y se guarda el más pesado.
"""
from __future__ import annotations

import ctypes
import struct
import zlib
from ctypes import wintypes
from typing import Optional

from core.asset_library import library_mmo_path, save_mmo

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
PROCESS_ACCESS = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
TH32CS_SNAPPROCESS = 0x00000002
_REGION_MAX = 160 * 1024 * 1024
_MIN_UNCOMPRESSED = 1_800_000
_MAX_UNCOMPRESSED = 80_000_000
_CHUNK = 4 * 1024 * 1024


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


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_uint64),
        ("AllocationBase", ctypes.c_uint64),
        ("AllocationProtect", wintypes.DWORD),
        ("__pad1", wintypes.DWORD),
        ("RegionSize", ctypes.c_uint64),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("__pad2", wintypes.DWORD),
    ]


k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.OpenProcess.restype = wintypes.HANDLE
k32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
k32.CloseHandle.argtypes = [wintypes.HANDLE]


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


def _target_pids() -> list[tuple[int, str]]:
    from core.game_launcher import find_game_processes, find_pids_connected_to_proxy
    procs = find_game_processes()
    if procs:
        return procs

    # Fallback: check processes connected to the proxy
    try:
        from core import proxy_engine
        st = proxy_engine.proxy_engine.get_status()
        port = st.get("port", 8080)
        conn_pids = find_pids_connected_to_proxy(port)
        if conn_pids:
            return [(p, f"ProxyClient_{p}.exe") for p in conn_pids]
    except Exception:
        pass

    return []


def _readable(protect: int) -> bool:
    bits = protect & 0xFF
    if protect & PAGE_GUARD or bits in (0, PAGE_NOACCESS):
        return False
    return True


def _read(h, addr: int, size: int) -> bytes:
    out = bytearray()
    left = size
    off = 0
    while left > 0:
        take = left if left < _CHUNK else _CHUNK
        buf = (ctypes.c_ubyte * take)()
        nread = ctypes.c_size_t(0)
        ok = k32.ReadProcessMemory(
            h, ctypes.c_void_p(addr + off), buf, take, ctypes.byref(nread)
        )
        if not ok or not nread.value:
            break
        out.extend(bytes(buf[: nread.value]))
        if nread.value < take:
            break
        off += take
        left -= take
    return bytes(out)


def _try_extract(h, addr: int) -> Optional[bytes]:
    hdr = _read(h, addr, 8)
    if len(hdr) < 8 or hdr[:3] not in (b"CWS", b"FWS", b"ZWS"):
        return None
    version = hdr[3]
    if version < 6 or version > 50:
        return None
    file_len = struct.unpack_from("<I", hdr, 4)[0]
    if file_len < _MIN_UNCOMPRESSED or file_len > _MAX_UNCOMPRESSED:
        return None

    if hdr[:3] == b"FWS":
        data = _read(h, addr, file_len)
        if len(data) >= min(file_len, 100) and data[:3] == b"FWS":
            return data[:file_len] if len(data) >= file_len else data
        return None

    if hdr[:3] == b"CWS":
        blob = _read(h, addr, min(file_len, 28_000_000))
        if len(blob) < 64 or blob[:3] != b"CWS":
            return None
        try:
            body = zlib.decompress(blob[8:])
        except zlib.error:
            return None
        if len(body) < _MIN_UNCOMPRESSED - 8:
            return None
        packed = zlib.compress(body, 6)
        return b"CWS" + bytes([version]) + struct.pack("<I", 8 + len(body)) + packed

    return None


def _scan_pid(pid: int) -> list[bytes]:
    found: list[bytes] = []
    h = k32.OpenProcess(PROCESS_ACCESS, False, pid)
    if not h:
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        return found
    try:
        addr = 0
        mbi = MEMORY_BASIC_INFORMATION64()
        while addr < 0x00007FFFFFFF0000:
            got = k32.VirtualQueryEx(
                h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)
            )
            if not got:
                break
            size = int(mbi.RegionSize or 0)
            base = int(mbi.BaseAddress or 0)
            if size <= 0:
                addr = base + 0x10000 if base >= addr else addr + 0x10000
                continue
            nxt = base + size
            if mbi.State == MEM_COMMIT and _readable(mbi.Protect) and 0 < size <= _REGION_MAX:
                remain = size
                off = 0
                prev = b""
                while remain > 0:
                    take = remain if remain < _CHUNK else _CHUNK
                    chunk = _read(h, base + off, take)
                    if not chunk:
                        break
                    blob = prev + chunk
                    start = 0
                    while True:
                        i_c = blob.find(b"CWS", start)
                        i_f = blob.find(b"FWS", start)
                        hits = [i for i in (i_c, i_f) if i >= 0]
                        if not hits:
                            break
                        i = min(hits)
                        abs_addr = base + off + i - len(prev)
                        extracted = _try_extract(h, abs_addr)
                        if extracted:
                            found.append(extracted)
                        start = i + 3
                    prev = chunk[-2:] if len(chunk) >= 2 else chunk
                    off += take
                    remain -= take
            addr = nxt if nxt > addr else addr + 0x1000
    finally:
        k32.CloseHandle(h)
    return found


def dump_mmo_from_game() -> dict:
    pids = _target_pids()
    if not pids:
        return {
            "ok": False,
            "error": "El juego no está abierto. Entrá a un mundo y volvé a intentar.",
        }

    best: Optional[bytes] = None
    scanned = []
    for pid, name in pids:
        scanned.append(f"{name} ({pid})")
        for swf in _scan_pid(pid):
            if best is None or len(swf) > len(best):
                best = swf

    if not best:
        return {
            "ok": False,
            "error": "No encontré el archivo del juego en la memoria. Entrá bien a un mundo y reintentá.",
            "scanned": scanned,
        }

    dest = save_mmo(best)
    return {
        "ok": True,
        "path": str(dest),
        "bytes": len(best),
        "mb": round(len(best) / (1024 * 1024), 2),
        "scanned": scanned,
        "had_previous": library_mmo_path().exists(),
    }
