"""Biblioteca local de SWFs: catálogo desde el MMO, faltantes, descarga y zip."""
from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import threading
import time
import zipfile
import zlib
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CDN_BASE = "https://cdn-ar.mundogaturro.com/juego"

CONFIRMED_MINIGAMES = [
    "accesibilidad", "aquawoman", "baby", "ball", "basket", "bibliotecav2", "bouncer",
    "clima", "climbing", "colourcode", "cooking", "dance", "decathlon", "dressers",
    "driving", "dungeon", "ecofotos", "extraterrestres", "feria1", "feria2", "feria3",
    "feria4", "feria5", "findthecat", "flymetothemoon", "fracciones", "fruitbouncer",
    "huesos", "inflaglobo", "ingredientes", "islandPlatform", "islandcannon",
    "islandhunters", "jetpack", "jetpackSpace", "jumprope", "letras",
    "maquinadeltiempo", "martillo", "mascotaball", "matatopos", "match", "matematica",
    "misiongps", "naturalessupermercado", "penales", "penguin", "personajes", "petglamor",
    "petpower", "petrolling", "petvet", "petwit", "pirates", "planes", "platformDream",
    "ratonBala", "runjump", "skate", "skateJump", "skateNieve", "snowPenguin", "snowball",
    "snowwar", "spacehunters", "speed", "stranger", "supershake", "temperaturas",
    "termometro", "treasurehunters", "tumba", "turismo", "whackacat2",
]

SEED_MMOS = []  # The portable catalogue is shipped in data/swf_catalog_seed.json.
LOCAL_ASSET_DIRS = [
    Path.home() / "Desktop" / "assets",
    Path.home() / "Desktop" / "swfs_mundogaturro",
]


# Sin un MMO bueno (el del CDN viene cifrado), el catálogo de assets/fondos
# se arma desde este seed embebido extraído de un MMO real.
CATALOG_SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "swf_catalog_seed.json"
RESOURCE_TAGS_DIR = Path(__file__).resolve().parent.parent / "data" / "mmo_resource_tags"

# Si el catálogo no llega a esto, NO digas "está todo" (caso amigo: solo minigames).
MIN_CATEGORY_COUNTS = {
    "assets": 500,
    "backgrounds": 200,
    "minigames": 40,
}
# content/ a veces 404 en CDN público; no lo exigimos para marcar completo.
REQUIRED_FOLDERS = ("assets", "backgrounds", "banners", "core", "map", "minigames", "ui")
OPTIONAL_FOLDERS = ("content", "news", "npc", "cfgs")

_job_lock = threading.Lock()
_job: dict[str, Any] = {
    "running": False,
    "kind": "",
    "done": 0,
    "total": 0,
    "message": "",
    "result": None,
}


def tool_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def library_dir() -> Path:
    path = tool_root() / "swfs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_mmo_path() -> Path:
    return library_dir() / "core" / "mmo.swf"


def zip_path() -> Path:
    return tool_root() / "swfs_mundogaturro.zip"


def manifest_path() -> Path:
    return library_dir() / "manifiesto.json"


def _set_job(**kwargs) -> None:
    with _job_lock:
        _job.update(kwargs)


def job_snapshot() -> dict[str, Any]:
    with _job_lock:
        return dict(_job)


def save_mmo(data: bytes) -> Path:
    dest = library_mmo_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def seed_mmo_if_missing() -> Optional[Path]:
    dest = library_mmo_path()
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    for src in SEED_MMOS:
        if src.exists() and src.stat().st_size > 1000:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            return dest
    return dest if dest.exists() else None


def is_valid_swf(data: bytes) -> bool:
    return len(data) >= 100 and data[:3] in (b"CWS", b"FWS", b"ZWS")


def extract_embedded_tags(mmo_path: Path) -> dict[int, bytes]:
    tags: dict[int, bytes] = {}
    if not mmo_path.exists():
        return tags
    raw = mmo_path.read_bytes()
    sig = raw[:3]
    if sig == b"CWS":
        payload = zlib.decompress(raw[8:])
    elif sig == b"FWS":
        payload = raw[8:]
    else:
        return tags

    nbits = payload[0] >> 3
    rect_bytes = (5 + nbits * 4 + 7) // 8
    pos = rect_bytes + 4
    while pos + 2 <= len(payload):
        tag_hdr = struct.unpack_from("<H", payload, pos)[0]
        tag_type = tag_hdr >> 6
        tag_len = tag_hdr & 0x3F
        pos += 2
        if tag_len == 0x3F:
            if pos + 4 > len(payload):
                break
            tag_len = struct.unpack_from("<I", payload, pos)[0]
            pos += 4
        if tag_type == 0:
            break
        if tag_type == 87 and pos + 6 <= pos + tag_len:
            tag_id = struct.unpack_from("<H", payload, pos)[0]
            tags[tag_id] = payload[pos + 6:pos + tag_len]
        pos += tag_len
    return tags


_SOURCE_RANK = {
    "mmo": 50,
    "tags": 40,
    "seed": 30,
    "assets_xml": 25,
    "local_scan": 10,
    "minigames": 5,
}


def _add_catalog_entry(
    catalog: dict[str, dict],
    dest: str,
    *,
    url: str,
    category: str,
    name: str,
    source: str,
) -> None:
    dest = dest.replace("\\", "/").lstrip("/")
    if not dest.endswith(".swf"):
        return
    prev = catalog.get(dest)
    if prev and _SOURCE_RANK.get(str(prev.get("source") or ""), 0) >= _SOURCE_RANK.get(source, 0):
        return
    catalog[dest] = {
        "url": url,
        "category": category or dest.split("/", 1)[0],
        "name": name,
        "source": source,
    }


def _merge_xml_resources(catalog: dict[str, dict], xml_bytes: bytes, source: str) -> int:
    """Parse MMO resource XML (tags 2083/2085/2088). Returns entries added/updated."""
    added = 0
    try:
        tree = ET.fromstring(xml_bytes.decode("utf-8", errors="ignore"))
    except Exception:
        return 0
    for el in tree.findall(".//file"):
        p = (el.get("path") or "").strip().replace("\\", "/")
        if not p.endswith(".swf"):
            continue
        folder = (el.get("folder") or "").strip().replace("\\", "/")
        # Tag 2083/2088 often omit folder and live under assets/backgrounds.
        if not folder:
            # Infer from path style; callers pass preferred default via source name.
            if source.endswith("2083") or "assets" in source:
                folder = "assets"
            elif source.endswith("2088") or "backgrounds" in source:
                folder = "backgrounds"
            else:
                folder = "ui"
        dest = f"{folder}/{p}" if not p.startswith(f"{folder}/") else p
        url = f"{CDN_BASE}/{dest}"
        before = dest in catalog
        _add_catalog_entry(
            catalog, dest, url=url, category=folder, name=Path(p).name, source=source.split(":")[0]
        )
        if not before or catalog[dest].get("source") == source.split(":")[0]:
            added += 1
    return added


def _load_seed_catalog(catalog: dict[str, dict]) -> int:
    if not CATALOG_SEED_PATH.exists():
        return 0
    try:
        data = json.loads(CATALOG_SEED_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        return 0
    n = 0
    for dest, info in files.items():
        if not isinstance(info, dict):
            continue
        url = str(info.get("url") or f"{CDN_BASE}/{dest}")
        category = str(info.get("category") or dest.split("/", 1)[0])
        name = str(info.get("name") or Path(dest).name)
        before = dest in catalog
        _add_catalog_entry(catalog, dest, url=url, category=category, name=name, source="seed")
        if not before:
            n += 1
    return n


def _load_bundled_tag_xmls(catalog: dict[str, dict]) -> int:
    if not RESOURCE_TAGS_DIR.exists():
        return 0
    n = 0
    mapping = {
        "tag_2083.xml": "tags:2083",
        "tag_2088.xml": "tags:2088",
        "tag_2085.xml": "tags:2085",
    }
    for fname, source in mapping.items():
        path = RESOURCE_TAGS_DIR / fname
        if not path.exists():
            continue
        n += _merge_xml_resources(catalog, path.read_bytes(), source)
    return n


def _load_assets_xml(catalog: dict[str, dict]) -> int:
    """Union con assets.xml (viewer / item_catalog) por si el MMO está atrasado."""
    candidates = [
        Path(__file__).resolve().parent.parent / "data" / "assets.xml",
    ]
    n = 0
    for path in candidates:
        if not path.exists():
            continue
        try:
            tree = ET.parse(path)
        except Exception:
            continue
        for el in tree.findall(".//file"):
            p = (el.get("path") or "").strip().replace("\\", "/")
            if not p.endswith(".swf"):
                continue
            name = Path(p).name
            dest = f"assets/{name}"
            before = dest in catalog
            _add_catalog_entry(
                catalog,
                dest,
                url=f"{CDN_BASE}/assets/{name}",
                category="assets",
                name=name,
                source="assets_xml",
            )
            if not before and dest in catalog:
                n += 1
        break
    return n


def _category_counts(catalog: dict[str, dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for info in catalog.values():
        cat = str(info.get("category") or "other")
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def catalog_is_healthy(catalog: dict[str, dict]) -> tuple[bool, list[str]]:
    counts = _category_counts(catalog)
    problems: list[str] = []
    for cat, minimum in MIN_CATEGORY_COUNTS.items():
        have = counts.get(cat, 0)
        if have < minimum:
            problems.append(f"{cat}: {have}/{minimum}")
    return (not problems), problems


def refresh_catalog_seed_from_mmo(mmo_path: Optional[Path] = None) -> dict[str, Any]:
    """Rebuild bundled seed when a fresh memory-dumped MMO is available."""
    path = mmo_path or library_mmo_path()
    if not path.exists():
        return {"ok": False, "error": "No hay mmo.swf"}
    catalog = {}
    tags = extract_embedded_tags(path)
    if 2083 in tags:
        _merge_xml_resources(catalog, tags[2083], "mmo")
    if 2088 in tags:
        _merge_xml_resources(catalog, tags[2088], "mmo")
    if 2085 in tags:
        _merge_xml_resources(catalog, tags[2085], "mmo")
    for game in CONFIRMED_MINIGAMES:
        dest = f"minigames/{game}.swf"
        _add_catalog_entry(
            catalog,
            dest,
            url=f"{CDN_BASE}/mini/{game}/client/deploy/Game.swf",
            category="minigames",
            name=f"{game}.swf",
            source="minigames",
        )
    healthy, problems = catalog_is_healthy(catalog)
    if not healthy:
        return {"ok": False, "error": f"MMO sin catálogo completo ({', '.join(problems)})", "count": len(catalog)}

    RESOURCE_TAGS_DIR.mkdir(parents=True, exist_ok=True)
    for tid, fname in ((2083, "tag_2083.xml"), (2088, "tag_2088.xml"), (2085, "tag_2085.xml")):
        if tid in tags:
            (RESOURCE_TAGS_DIR / fname).write_bytes(tags[tid])

    files = {
        rel: {"url": info["url"], "category": info["category"], "name": info["name"]}
        for rel, info in sorted(catalog.items())
    }
    CATALOG_SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_SEED_PATH.write_text(
        json.dumps(
            {
                "version": 1,
                "source": "mmo_tags",
                "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(files),
                "files": files,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {"ok": True, "count": len(files), "by_category": _category_counts(catalog)}


def build_catalog(mmo_path: Optional[Path] = None) -> dict[str, dict]:
    """
    Catálogo multi-fuente (unión):
      1) tags XML del mmo.swf local (memoria / seed copiado)
      2) seed embebido data/swf_catalog_seed.json
      3) XML embebidos data/mmo_resource_tags/
      4) escaneo de carpetas locales de assets
      5) lista fija de minijuegos
    El CDN no publica un índice; el MMO de internet viene cifrado y no sirve.
    """
    catalog: dict[str, dict] = {}
    path = mmo_path or library_mmo_path()
    tags = extract_embedded_tags(path) if path and path.exists() else {}

    if 2083 in tags:
        _merge_xml_resources(catalog, tags[2083], "mmo")
    if 2088 in tags:
        _merge_xml_resources(catalog, tags[2088], "mmo")
    if 2085 in tags:
        _merge_xml_resources(catalog, tags[2085], "mmo")

    # Seed / bundled XMLs cover friends without a dumped MMO.
    # NO sumar Desktop/assets al catálogo: ensucia con fondos/banners sueltos
    # que no están en el índice del juego y después dice que "faltan".
    # Esas carpetas solo sirven como fuente de copia en _find_local_source.
    _load_seed_catalog(catalog)
    _load_bundled_tag_xmls(catalog)
    _load_assets_xml(catalog)

    for game in CONFIRMED_MINIGAMES:
        dest = f"minigames/{game}.swf"
        _add_catalog_entry(
            catalog,
            dest,
            url=f"{CDN_BASE}/mini/{game}/client/deploy/Game.swf",
            category="minigames",
            name=f"{game}.swf",
            source="minigames",
        )
    return catalog


def _local_file(rel: str) -> Path:
    return library_dir() / rel.replace("/", os.sep)


def _find_local_source(rel: str, info: dict) -> Optional[Path]:
    """Preferir copiar desde carpetas locales grandes antes de pegarle al CDN."""
    name = info.get("name") or Path(rel).name
    category = str(info.get("category") or "")
    rel_os = rel.replace("/", os.sep)
    for root in LOCAL_ASSET_DIRS:
        if not root.exists():
            continue
        candidates = [
            root / rel_os,
            root / name,
            root / "assets" / name,
            root / category / name if category else None,
            root / "assets" / rel_os if category == "assets" else None,
            root / "backgrounds" / name if category == "backgrounds" else None,
        ]
        for cand in candidates:
            if cand and cand.exists() and cand.stat().st_size > 100:
                return cand
    cache = Path(__file__).resolve().parent.parent / "data" / "swf_cache" / name
    if cache.exists() and cache.stat().st_size > 100:
        return cache
    return None


def _disk_swf_counts() -> dict[str, int]:
    root = library_dir()
    counts: dict[str, int] = {}
    for path in root.rglob("*.swf"):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        top = rel.split("/", 1)[0]
        counts[top] = counts.get(top, 0) + 1
    return counts


def review_library() -> dict[str, Any]:
    seed_mmo_if_missing()
    mmo = library_mmo_path()
    catalog = build_catalog(mmo)
    present = []
    missing = []
    have_by: dict[str, int] = {}
    miss_by: dict[str, int] = {}
    for rel, info in sorted(catalog.items()):
        dest = _local_file(rel)
        cat = str(info.get("category") or "other")
        if dest.exists() and dest.stat().st_size > 100:
            present.append({"path": rel, "bytes": dest.stat().st_size, "category": cat})
            have_by[cat] = have_by.get(cat, 0) + 1
        else:
            missing.append({"path": rel, "category": cat, "name": info.get("name") or Path(rel).name})
            miss_by[cat] = miss_by.get(cat, 0) + 1

    catalog_by = _category_counts(catalog)
    healthy, health_problems = catalog_is_healthy(catalog)
    disk_by = _disk_swf_counts()

    # Carpetas esperadas presentes en disco (aunque el catálogo no liste core/).
    folders_on_disk = {k for k, n in disk_by.items() if n > 0}
    folders_missing = [f for f in REQUIRED_FOLDERS if f not in folders_on_disk and f != "core"]
    # core solo cuenta si hay mmo.swf
    if not (library_mmo_path().exists() and library_mmo_path().stat().st_size > 1000):
        folders_missing.append("core")

    mmo_info = None
    mmo_has_tags = False
    if mmo.exists():
        st = mmo.stat()
        tags = extract_embedded_tags(mmo)
        mmo_has_tags = 2083 in tags and 2088 in tags
        mmo_info = {
            "path": str(mmo),
            "bytes": st.st_size,
            "mb": round(st.st_size / (1024 * 1024), 2),
            "updated": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M"),
            "has_resource_tags": mmo_has_tags,
        }

    sources_used = sorted({
        str(info.get("source") or "")
        for info in catalog.values()
        if info.get("source")
    })

    # content/* a veces no está en el CDN público; no bloquear "completo" por eso.
    blocking_missing = [m for m in missing if str(m.get("category") or "") != "content"]
    # Nunca digas "completo" si el catálogo es incompleto (solo minigames).
    really_complete = (
        healthy
        and len(blocking_missing) == 0
        and "assets" in folders_on_disk
        and "backgrounds" in folders_on_disk
    )

    result = {
        "ok": True,
        "folder": str(library_dir()),
        "exe_folder": str(tool_root()),
        "mmo": mmo_info,
        "has_mmo": bool(mmo_info),
        "mmo_has_tags": mmo_has_tags,
        "catalog": len(catalog),
        "have": len(present),
        "missing": len(missing),
        "missing_files": missing[:120],
        "missing_more": max(0, len(missing) - 120),
        "by_category": catalog_by,
        "have_by_category": have_by,
        "missing_by_category": miss_by,
        "disk_by_category": disk_by,
        "folders_on_disk": sorted(folders_on_disk),
        "folders_missing": folders_missing,
        "catalog_healthy": healthy,
        "catalog_problems": health_problems,
        "complete": really_complete,
        "sources": sources_used,
        "seed_present": CATALOG_SEED_PATH.exists(),
        "zip_ready": zip_path().exists(),
        "zip_path": str(zip_path()) if zip_path().exists() else "",
        "needs_fresh_mmo": not mmo_has_tags,
    }
    try:
        manifest_path().write_text(
            json.dumps({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_cataloged": len(catalog),
                "have": len(present),
                "missing": len(missing),
                "complete": really_complete,
                "catalog_healthy": healthy,
                "catalog_problems": health_problems,
                "by_category": catalog_by,
                "have_by_category": have_by,
                "missing_by_category": miss_by,
                "disk_by_category": disk_by,
                "folders_on_disk": sorted(folders_on_disk),
                "folders_missing": folders_missing,
                "sources": sources_used,
                "files": [
                    {
                        "path": rel,
                        "category": info.get("category"),
                        "url": info.get("url"),
                        "source": info.get("source"),
                        "present": (_local_file(rel).exists() and _local_file(rel).stat().st_size > 100),
                    }
                    for rel, info in sorted(catalog.items())
                ],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return result


def _download_one(rel: str, info: dict) -> dict:
    dest = _local_file(rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 100:
        return {"path": rel, "status": "have", "bytes": dest.stat().st_size}

    src = _find_local_source(rel, info)
    if src:
        try:
            shutil.copy2(src, dest)
            return {"path": rel, "status": "copied", "bytes": dest.stat().st_size}
        except Exception:
            pass

    for _ in range(2):
        try:
            req = Request(info["url"], headers={"User-Agent": UA})
            with urlopen(req, timeout=20) as resp:
                data = resp.read()
            if is_valid_swf(data):
                dest.write_bytes(data)
                return {"path": rel, "status": "downloaded", "bytes": len(data)}
        except Exception:
            time.sleep(0.25)
    return {"path": rel, "status": "failed", "bytes": 0}


def download_missing(workers: int = 12) -> dict[str, Any]:
    with _job_lock:
        if _job["running"]:
            return {"ok": False, "error": "Ya hay una descarga en curso."}
    _set_job(running=True, kind="download", done=0, total=0, message="Revisando qué falta...", result=None)

    try:
        seed_mmo_if_missing()
        catalog = build_catalog()
        healthy, problems = catalog_is_healthy(catalog)
        if not healthy:
            result = {
                "ok": False,
                "error": (
                    "La lista de archivos está incompleta "
                    f"({', '.join(problems)}). Sacá el MMO del juego abierto "
                    "o asegurate de tener data/swf_catalog_seed.json."
                ),
                "catalog_problems": problems,
                "catalog": len(catalog),
            }
            _set_job(running=False, message="Lista incompleta: no bajo así.", result=result)
            return result

        todo = [
            (rel, info) for rel, info in catalog.items()
            if not (_local_file(rel).exists() and _local_file(rel).stat().st_size > 100)
        ]
        _set_job(total=len(todo), message=f"Bajando {len(todo)} archivo(s)...")
        if not todo:
            result = {
                "ok": True,
                "downloaded": 0,
                "copied": 0,
                "failed": 0,
                "have": len(catalog),
                "complete": True,
                "by_category": _category_counts(catalog),
            }
            _set_job(running=False, message="No faltaba nada (lista completa).", result=result)
            return result

        downloaded = copied = failed = 0
        failed_paths: list[str] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_download_one, rel, info): rel for rel, info in todo}
            done = 0
            for fut in as_completed(futs):
                res = fut.result()
                done += 1
                if res["status"] == "downloaded":
                    downloaded += 1
                elif res["status"] == "copied":
                    copied += 1
                elif res["status"] == "failed":
                    failed += 1
                    failed_paths.append(res["path"])
                _set_job(done=done, message=f"Bajando {done} de {len(todo)}...")

        review = review_library()
        result = {
            "ok": True,
            "downloaded": downloaded,
            "copied": copied,
            "failed": failed,
            "failed_paths": failed_paths[:40],
            "have": review.get("have"),
            "missing": review.get("missing"),
            "complete": review.get("complete"),
            "by_category": review.get("have_by_category"),
            "folders_missing": review.get("folders_missing"),
        }
        msg = (
            f"Listo: +{downloaded} bajados, +{copied} copiados, {failed} fallaron. "
            f"Tenés {result['have']} de {len(catalog)}."
        )
        _set_job(running=False, message=msg, result=result)
        return result
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        _set_job(running=False, message="No se pudo bajar.", result=result)
        return result


def start_download_async() -> dict[str, Any]:
    with _job_lock:
        if _job["running"]:
            return {"ok": False, "error": "Ya hay una descarga en curso."}
    threading.Thread(target=download_missing, daemon=True).start()
    return {"ok": True}


def build_zip() -> dict[str, Any]:
    root = library_dir()
    dest = zip_path()
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".swf"]
    if not files:
        return {"ok": False, "error": "No hay archivos para armar el zip."}
    _set_job(running=True, kind="zip", done=0, total=len(files), message="Armando el zip...", result=None)
    try:
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for i, path in enumerate(files, 1):
                zf.write(path, path.relative_to(root).as_posix())
                _set_job(done=i, message=f"Metiendo {i} de {len(files)}...")
        result = {
            "ok": True,
            "path": str(dest),
            "files": len(files),
            "mb": round(dest.stat().st_size / (1024 * 1024), 2),
        }
        _set_job(running=False, message="Zip listo.", result=result)
        return result
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        _set_job(running=False, message="No se pudo armar el zip.", result=result)
        return result


def start_zip_async() -> dict[str, Any]:
    with _job_lock:
        if _job["running"]:
            return {"ok": False, "error": "Esperá que termine lo que está corriendo."}
    threading.Thread(target=build_zip, daemon=True).start()
    return {"ok": True}
