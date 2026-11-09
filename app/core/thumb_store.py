"""
Persistencia de thumbs renderizados por Flash (preview.swf → PNG).
Los JPEGs embebidos en SWF casi no existen; el corpus visual real sale de Ruffle.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
THUMB_ROOT = BASE_DIR / "data" / "thumb_cache"
META_PATH = THUMB_ROOT / "_index.json"
EXPORT_ZIP_PATH = BASE_DIR / "data" / "thumbs_index.zip"

# preview.swf BitmapData max edge (patched from original 38). Thumbs below
# STALE_MAX_EDGE are treated as missing so the auto-indexer recaptures them.
CAPTURE_MAX = 120
STALE_MAX_EDGE = 50

_lock = threading.RLock()
_meta: Optional[Dict[str, Any]] = None

_export_lock = threading.Lock()
_export_job: Dict[str, Any] = {
    "running": False,
    "kind": "",
    "done": 0,
    "total": 0,
    "pct": 0,
    "message": "",
    "result": None,
}


def _png_max_edge(png: bytes) -> int:
    """Read IHDR width/height without full decode."""
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        return 0
    w = int.from_bytes(png[16:20], "big")
    h = int.from_bytes(png[20:24], "big")
    return max(w, h)


def _safe_part(s: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", str(s or "").strip())
    return s[:120] or "_"


def thumb_path(pack: str, name: str) -> Path:
    return THUMB_ROOT / _safe_part(pack) / f"{_safe_part(name)}.png"


def ensure_root() -> Path:
    THUMB_ROOT.mkdir(parents=True, exist_ok=True)
    return THUMB_ROOT


def rebuild_meta_from_disk() -> Dict[str, Any]:
    """Escanea data/thumb_cache/ y regenera _index.json con todos los PNG en disco."""
    global _meta
    ensure_root()
    items: Dict[str, Any] = {}
    with _lock:
        for pack_dir in THUMB_ROOT.iterdir():
            if not pack_dir.is_dir() or pack_dir.name.startswith("."):
                continue
            pack_name = pack_dir.name
            for png in pack_dir.glob("*.png"):
                name = png.stem
                try:
                    max_edge = _png_max_edge(png.read_bytes())
                except Exception:
                    max_edge = CAPTURE_MAX
                key = f"{pack_name}.{name}"
                items[key] = {
                    "pack": pack_name,
                    "name": name,
                    "path": f"data/thumb_cache/{pack_name}/{png.name}",
                    "bytes": png.stat().st_size,
                    "source": "flash",
                    "mtime": png.stat().st_mtime,
                    "feat_ver": 0,
                    "max_edge": max_edge if max_edge > 0 else CAPTURE_MAX,
                    "capture_max": CAPTURE_MAX,
                }
        _meta = {"items": items, "updated_at": time.time()}
        META_PATH.write_text(json.dumps(_meta, ensure_ascii=False), encoding="utf-8")
    return stats()


def _load_meta() -> Dict[str, Any]:
    global _meta
    with _lock:
        if _meta is not None:
            return _meta
        ensure_root()
        if META_PATH.exists() and META_PATH.stat().st_size > 10:
            try:
                _meta = json.loads(META_PATH.read_text(encoding="utf-8"))
            except Exception:
                _meta = {"items": {}, "updated_at": 0}
        else:
            _meta = {"items": {}, "updated_at": 0}
        if "items" not in _meta:
            _meta["items"] = {}
        if not _meta["items"]:
            # Auto-reconstruir si el archivo estaba vacío pero hay carpetas con PNGs
            try:
                if any(THUMB_ROOT.glob("*/*.png")):
                    rebuild_meta_from_disk()
            except Exception:
                pass
        return _meta


def _save_meta() -> None:
    with _lock:
        ensure_root()
        meta = _load_meta()
        meta["updated_at"] = time.time()
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def key_for(pack: str, name: str) -> str:
    return f"{pack}.{name}"


def save_png_bytes(pack: str, name: str, png: bytes, source: str = "flash", *, persist: bool = True) -> Dict[str, Any]:
    """Guarda PNG y actualiza índice liviano (sin features)."""
    if not pack or not name or not png:
        return {"ok": False, "error": "datos incompletos"}
    path = thumb_path(pack, name)
    max_edge = _png_max_edge(png)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        meta = _load_meta()
        meta["items"][key_for(pack, name)] = {
            "pack": pack,
            "name": name,
            "path": str(path.relative_to(BASE_DIR)).replace("\\", "/"),
            "bytes": len(png),
            "source": source,
            "mtime": time.time(),
            "feat_ver": 0,
            "max_edge": max_edge,
            "capture_max": CAPTURE_MAX,
        }
        if persist:
            _save_meta()
    return {"ok": True, "pack": pack, "name": name, "path": str(path)}


def save_data_url(pack: str, name: str, data_url: str, source: str = "flash", *, persist: bool = True) -> Dict[str, Any]:
    raw = (data_url or "").strip()
    if not raw:
        return {"ok": False, "error": "sin imagen"}
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        png = base64.b64decode(raw, validate=False)
    except Exception as e:
        return {"ok": False, "error": f"base64 inválido: {e}"}
    if len(png) < 32:
        return {"ok": False, "error": "imagen demasiado chica"}
    return save_png_bytes(pack, name, png, source=source, persist=persist)


def save_data_urls(items: List[Tuple[str, str, str]]) -> List[Tuple[str, str]]:
    """Persist the shared metadata once for the entire batch."""
    saved = []
    with _lock:
        for pack, name, png in items:
            if save_data_url(pack, name, png, persist=False).get("ok"):
                saved.append((pack, name))
        if saved:
            _save_meta()
    return saved


def get_png_path(pack: str, name: str) -> Optional[Path]:
    path = thumb_path(pack, name)
    return path if path.is_file() else None


def read_png(pack: str, name: str) -> Optional[bytes]:
    path = get_png_path(pack, name)
    return path.read_bytes() if path else None


def list_items() -> List[Dict[str, Any]]:
    # Snapshot bajo lock: el indexer muta meta["items"] en paralelo.
    with _lock:
        meta = _load_meta()
        rows = list(meta.get("items", {}).values())
    out = []
    for row in rows:
        pack = row.get("pack") or ""
        name = row.get("name") or ""
        path = thumb_path(pack, name)
        if not path.is_file():
            continue
        out.append({**row, "abs_path": str(path)})
    return out


def stats() -> Dict[str, Any]:
    """Conteo liviano (no recorre disco); seguro con ingest concurrente."""
    with _lock:
        meta = _load_meta()
        items = meta.get("items", {})
        thumbs = len(items)
        packs = {str(v.get("pack") or "") for v in list(items.values()) if v.get("pack")}
    return {
        "ok": True,
        "thumbs": thumbs,
        "packs": len(packs),
        "root": str(THUMB_ROOT),
    }


def _pack_is_fresh(pack_items: List[Dict[str, Any]]) -> bool:
    """True if pack has thumbs captured at the current (post-38px) resolution."""
    if not pack_items:
        return False
    # Meta without capture_max/max_edge = pre-upgrade 38px corpus → recapture.
    for it in pack_items:
        if int(it.get("max_edge") or 0) > STALE_MAX_EDGE:
            continue
        return False
    return True


def _expected_item_counts() -> Dict[str, int]:
    """pack → item_count desde valid_swfs.json (best-effort)."""
    path = BASE_DIR / "data" / "valid_swfs.json"
    out: Dict[str, int] = {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    rows = raw if isinstance(raw, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").replace(".swf", "").strip()
        try:
            n = int(row.get("item_count") or 0)
        except (TypeError, ValueError):
            n = 0
        if name and n > 0:
            out[name] = n
    return out


KNOWN_EMPTY_PACKS = {
    "anoNuevo2017/deco", "antro2017/deco", "bebes2017/deco", "butterflies",
    "campamento/deco", "campamento/wears", "carsColors", "diaTrabajador2018/deco",
    "easterCostumes2", "escenarioVip/deco", "faro2018/deco", "faro2018/wears",
    "gatoons2", "gatubers/deco", "geocat", "hospital2018/deco", "hospital2018/wears",
    "latincat", "peluqueria2018/deco", "peluqueria2018/wears", "privateHomeRoof1",
    "river2018/deco", "salitaMedicaDolencias", "sanValentin2019/wears", "subtes", "vigutsCatalog",
    "codeMachines",
}


def _pack_is_incomplete(pack_name: str, pack_items: List[Dict[str, Any]], expected: Dict[str, int]) -> bool:
    """True si hay thumbs pero faltan muchos símbolos (ej. greek 2/13)."""
    if not pack_items:
        return False
    exp = expected.get(pack_name) or expected.get(pack_name.replace("/", "_")) or 0
    if exp < 4:
        return False
    have = len(pack_items)
    if have >= exp:
        return False
    missing = exp - have
    return missing >= 4 and have < exp * 0.45


def coverage(all_pack_names: List[str], include_stale: bool = False) -> Dict[str, Any]:
    """Packs con thumbs vs pendientes.

    Los thumbs ya capturados (aunque sean 38px) cuentan como *done* para no
    “resetear” el índice. La recaptura HD (stale) es opcional.
    """
    items = list_items()
    by_pack: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        p = it.get("pack") or ""
        if not p:
            continue
        by_pack.setdefault(p, []).append(it)

    expected = _expected_item_counts()

    done = []
    never = []  # 0 thumbs — indexar YA
    incomplete = []  # thumbs parciales (ej. greek 2/13)
    stale = []  # thumbs viejos 38px — upgrade HD opcional
    for raw in all_pack_names:
        if isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("filename") or "").replace(".swf", "").strip()
        else:
            name = str(raw or "").replace(".swf", "").strip()
        if not name:
            continue
        # list_available_swfs a veces manda "pack/sub"; thumbs usan pack_sub
        pack_items = by_pack.get(name) or by_pack.get(name.replace("/", "_")) or []
        exp_count = expected.get(name, expected.get(name.replace("/", "_"), -1))
        if not pack_items:
            # Packs vacíos o sin símbolos exportables se consideran completos
            if exp_count == 0 or name in KNOWN_EMPTY_PACKS:
                done.append(name)
            else:
                never.append(name)
        elif _pack_is_incomplete(name, pack_items, expected):
            incomplete.append(name)
        else:
            # Ya hay corpus usable → done (aunque sea 38px)
            done.append(name)
            if not _pack_is_fresh(pack_items):
                stale.append(name)

    def _recency_key(name: str) -> tuple:
        low = name.lower()
        year = 0
        for y in range(2030, 2010, -1):
            if str(y) in low:
                year = y
                break
        return (-year, low)

    never_sorted = sorted(never, key=_recency_key)
    incomplete_sorted = sorted(incomplete, key=_recency_key)
    stale_sorted = sorted(stale, key=_recency_key)
    # Obligatorio: vacíos + incompletos. HD solo si lo piden.
    missing = never_sorted + incomplete_sorted
    if include_stale:
        missing = missing + stale_sorted

    expected_missing = {
        name: expected[name]
        for name in missing
        if name in expected
    }

    return {
        "ok": True,
        "thumbs": len(items),
        "total_packs": len(done) + len(never) + len(incomplete),
        "done_packs": len(done),
        "missing_packs": len(missing),
        "never_indexed": len(never),
        "incomplete_packs": len(incomplete),
        "stale_packs": len(stale),
        "include_stale": bool(include_stale),
        "capture_max": CAPTURE_MAX,
        "done": done,
        "missing": missing,
        "never": never_sorted,
        "incomplete": incomplete_sorted,
        "stale": stale_sorted,
        "expected": expected_missing,
        "root": str(THUMB_ROOT),
    }


def mark_features(pack: str, name: str, feat_ver: int) -> None:
    with _lock:
        meta = _load_meta()
        k = key_for(pack, name)
        if k in meta["items"]:
            meta["items"][k]["feat_ver"] = feat_ver
            _save_meta()


def reload_meta() -> None:
    """Fuerza releer _index.json (después de import)."""
    global _meta
    with _lock:
        _meta = None
        _load_meta()


def export_zip_path() -> Path:
    return EXPORT_ZIP_PATH


def _set_export_job(**kwargs: Any) -> None:
    with _export_lock:
        _export_job.update(kwargs)
        total = int(_export_job.get("total") or 0)
        done = int(_export_job.get("done") or 0)
        _export_job["pct"] = int(round(100.0 * done / total)) if total > 0 else 0


def export_job_snapshot() -> Dict[str, Any]:
    with _export_lock:
        return dict(_export_job)


def export_index_zip(feat_ver: int = 5) -> Dict[str, Any]:
    """Empaqueta thumb_cache (+ features CLIP actuales) para pasárselo a otra PC."""
    ensure_root()
    out = EXPORT_ZIP_PATH
    out.parent.mkdir(parents=True, exist_ok=True)

    feat_prefix = f"_features_v{int(feat_ver)}"
    files: List[Path] = []
    for p in THUMB_ROOT.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        # Saltar índices CLIP viejos (pesan mucho y no sirven)
        if name.startswith("_features_v") and not name.startswith(feat_prefix):
            continue
        files.append(p)

    if not files:
        result = {"ok": False, "error": "No hay thumbs para exportar. Indexá primero."}
        _set_export_job(running=False, message=result["error"], result=result, done=0, total=0)
        return result

    _set_export_job(
        running=True,
        kind="export",
        done=0,
        total=len(files),
        message=f"Armando zip · 0/{len(files)}…",
        result=None,
    )

    if out.exists():
        try:
            out.unlink()
        except Exception:
            pass

    t0 = time.time()
    try:
        # STORED: los PNG casi no comprimen; export mucho más rápido
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:
            for i, p in enumerate(files, 1):
                arc = p.relative_to(THUMB_ROOT).as_posix()
                zf.write(p, arcname=arc)
                if i == 1 or i == len(files) or i % 80 == 0:
                    _set_export_job(
                        done=i,
                        message=f"Armando zip · {i}/{len(files)} ({int(round(100 * i / len(files)))}%)",
                    )
        mb = out.stat().st_size / (1024 * 1024)
        result = {
            "ok": True,
            "path": str(out),
            "files": len(files),
            "size_mb": round(mb, 1),
            "seconds": round(time.time() - t0, 1),
            "download": "/api/thumbs/export/file",
            "message": f"Índice exportado · {len(files)} archivos · {mb:.0f} MB",
        }
        _set_export_job(
            running=False,
            done=len(files),
            message=result["message"],
            result=result,
        )
        return result
    except Exception as e:
        result = {"ok": False, "error": str(e)}
        _set_export_job(running=False, message=f"Falló el export: {e}", result=result)
        return result


def start_export_async(feat_ver: int = 5) -> Dict[str, Any]:
    with _export_lock:
        if _export_job.get("running"):
            return {"ok": False, "error": "Ya hay un export en curso."}

    def _run():
        export_index_zip(feat_ver=feat_ver)

    threading.Thread(target=_run, name="thumbs-export", daemon=True).start()
    return {"ok": True, "started": True, "message": "Exportando índice…"}


def _safe_zip_member(name: str) -> Optional[str]:
    """Evita zip-slip; solo paths relativos limpios dentro del cache."""
    raw = (name or "").replace("\\", "/").strip()
    if not raw or raw.endswith("/"):
        return None
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return None
    parts = [p for p in raw.split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts):
        return None
    # Si el zip trae un wrapper thumb_cache/..., lo aplanamos
    if parts[0] in ("thumb_cache", "data"):
        if parts[0] == "data" and len(parts) > 1 and parts[1] == "thumb_cache":
            parts = parts[2:]
        elif parts[0] == "thumb_cache":
            parts = parts[1:]
        if not parts:
            return None
    return "/".join(parts)


def import_index_zip(zip_path: Path) -> Dict[str, Any]:
    """Fusiona un zip de thumbs sobre thumb_cache (no borra lo local)."""
    zp = Path(zip_path)
    if not zp.is_file():
        return {"ok": False, "error": "No se encontró el zip"}
    ensure_root()

    written = 0
    written_pngs = 0
    kept_pngs = 0
    skipped = 0
    t0 = time.time()
    try:
        with zipfile.ZipFile(zp, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                rel = _safe_zip_member(info.filename)
                if not rel:
                    skipped += 1
                    continue
                # Solo png / índice / features
                low = rel.lower()
                ok_name = (
                    low.endswith(".png")
                    or low.endswith(".npz")
                    or low.endswith(".pkl")
                    or low.endswith(".json")
                )
                if not ok_name or low.endswith("_index.json"):
                    skipped += 1
                    continue
                dest = THUMB_ROOT / rel
                # No salir de THUMB_ROOT
                try:
                    dest.resolve().relative_to(THUMB_ROOT.resolve())
                except ValueError:
                    skipped += 1
                    continue
                if low.endswith(".png"):
                    incoming = zf.read(info)
                    edge = _png_max_edge(incoming)
                    if not edge:
                        skipped += 1
                        continue
                    if dest.is_file() and _png_max_edge(dest.read_bytes()) >= edge:
                        skipped += 1
                        kept_pngs += 1
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(incoming)
                    written_pngs += 1
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info, "r") as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                written += 1
    except zipfile.BadZipFile:
        return {"ok": False, "error": "El archivo no es un zip válido"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    if written <= 0 and kept_pngs <= 0:
        return {"ok": False, "error": "El zip no traía thumbs reconocibles"}

    if written_pngs:
        rebuild_meta_from_disk()
    st = stats()
    return {
        "ok": True,
        "written": written,
        "skipped": skipped,
        "thumbs": st.get("thumbs") or 0,
        "packs": st.get("packs") or 0,
        "seconds": round(time.time() - t0, 1),
        "message": f"Importados {written} archivos · {st.get('thumbs') or 0} thumbs en índice",
    }
