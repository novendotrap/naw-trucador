"""
Búsqueda visual sobre thumbs.

Primario: CLIP ONNX (512-d) — calidad tipo Shein.
Fallback: fingerprint clásico si CLIP no está disponible.
"""
from __future__ import annotations

import io
import math
import pickle
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter
import imagehash

from core import thumb_store
from core import clip_embed

FEAT_VER = 5  # CLIP letterbox; bump to 6 when 120px recapture finishes
GRID = 12
H_BINS = 30
S_BINS = 10
V_BINS = 10
MIN_OPAQUE_RATIO = 0.002
JUNK_NAMES = {
    "catalogbtn",
    "btn",
    "button",
    "loading",
    "loader",
    "placeholder",
    "iconloading",
    "empty",
    "null",
    "undefined",
}
# Fondos/texturas: solo si el NOMBRE arranca así (no "dragomovilTecho")
TEXTURE_PREFIX_RE = re.compile(
    r"^(pared|wall|piso|floor|cielo|sky|techo|cesped|grass|fondo|tiled|tile)",
    re.I,
)
TEXTURE_PACK_RE = re.compile(
    r"(wall|pared|piso|floor|privatehomewalls)",
    re.I,
)

_lock = threading.RLock()
_index: List[Dict[str, Any]] = []
_built = False
_clip_matrix: Optional[np.ndarray] = None  # (N, 512) alineado con _index
_feat_path = thumb_store.THUMB_ROOT / f"_features_v{FEAT_VER}.npz"
_meta_path = thumb_store.THUMB_ROOT / f"_features_v{FEAT_VER}_meta.pkl"
_legacy_pkl = thumb_store.THUMB_ROOT / f"_features_v{FEAT_VER}.pkl"
_build_progress = {"running": False, "done": 0, "total": 0, "message": ""}
_warm_started = False
_ready = threading.Event()


def get_build_progress() -> Dict[str, Any]:
    return dict(_build_progress)


def is_ready() -> bool:
    with _lock:
        return bool(_built and _index)


def _open_image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def _is_junk_name(name: str) -> bool:
    n = "".join(ch for ch in str(name or "").lower() if ch.isalnum())
    if not n:
        return True
    if n in JUNK_NAMES:
        return True
    if "catalogbtn" in n or n.startswith(("btncatalog", "scrollarrow", "scrollbar")) or n.endswith("skin") or n == "maintimeline":
        return True
    return False


def _is_texture_name(pack: str, name: str) -> bool:
    leaf = str(name or "").split(".")[-1]
    leaf = re.sub(r"_so$", "", leaf, flags=re.I)
    if TEXTURE_PREFIX_RE.match(leaf):
        return True
    if TEXTURE_PACK_RE.search(str(pack or "")):
        return True
    return False


def _alpha_bbox(rgba: Image.Image, thr: int = 18) -> Optional[Tuple[int, int, int, int]]:
    alpha = rgba.getchannel("A")
    mask = alpha.point(lambda a: 255 if a >= thr else 0)
    return mask.getbbox()


def _prepare_content(img: Image.Image) -> Tuple[Image.Image, Image.Image, float]:
    rgba = img.convert("RGBA")
    bbox = _alpha_bbox(rgba)
    if bbox:
        rgba = rgba.crop(bbox)
    w, h = rgba.size
    side = max(w, h, 1)
    pad = max(2, side // 16)
    canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
    canvas.paste(rgba, ((side - w) // 2 + pad, (side - h) // 2 + pad), rgba)
    rgba = canvas
    alpha = rgba.getchannel("A")
    opaque = sum(1 for a in alpha.getdata() if a >= 18)
    total = max(rgba.size[0] * rgba.size[1], 1)
    ratio = opaque / total
    bg = Image.new("RGBA", rgba.size, (148, 148, 156, 255))
    rgb = Image.alpha_composite(bg, rgba).convert("RGB")
    return rgb, rgba, ratio


def _smart_query_crop(img: Image.Image) -> Image.Image:
    rgba = img.convert("RGBA")
    w, h = rgba.size
    if w * h < 80 * 80:
        return rgba
    px = rgba.load()

    def is_dark(x, y):
        r, g, b, a = px[x, y]
        return a < 10 or (r + g + b) < 45

    left, top, right, bottom = 0, 0, w, h
    while left < right - 8 and all(is_dark(left, y) for y in range(0, h, max(1, h // 40))):
        left += 1
    while right > left + 8 and all(is_dark(right - 1, y) for y in range(0, h, max(1, h // 40))):
        right -= 1
    while top < bottom - 8 and all(is_dark(x, top) for x in range(0, w, max(1, w // 40))):
        top += 1
    while bottom > top + 8 and all(is_dark(x, bottom - 1) for x in range(0, w, max(1, w // 40))):
        bottom -= 1
    cropped = rgba.crop((left, top, right, bottom))
    cw, ch = cropped.size
    if cw > 220 or ch > 220:
        tile = 96
        best = None
        best_score = -1.0
        step = max(16, tile // 2)
        src = cropped.convert("RGB")
        for y in range(0, max(1, ch - tile), step):
            for x in range(0, max(1, cw - tile), step):
                cell = src.crop((x, y, min(x + tile, cw), min(y + tile, ch)))
                hsv = cell.convert("HSV")
                sats = [p[1] for p in hsv.getdata()]
                vals = [p[2] for p in hsv.getdata()]
                score = (sum(sats) / max(len(sats), 1)) * (sum(vals) / max(len(vals), 1) / 255.0)
                if score > best_score:
                    best_score = score
                    best = (x, y, min(x + tile, cw), min(y + tile, ch))
        if best and best_score > 20:
            cropped = cropped.crop(best)
    return cropped


def _hist_content(rgba: Image.Image) -> List[float]:
    hsv = rgba.convert("HSV")
    pixels = list(hsv.getdata())
    alphas = list(rgba.getchannel("A").getdata())
    h_hist = [0.0] * H_BINS
    s_hist = [0.0] * S_BINS
    v_hist = [0.0] * V_BINS
    weight_sum = 0.0
    for (h, s, v), a in zip(pixels, alphas):
        if a < 18:
            continue
        w = 0.35 + 0.65 * (s / 255.0) * (0.5 + 0.5 * (v / 255.0))
        h_hist[min(H_BINS - 1, (h * H_BINS) // 256)] += w
        s_hist[min(S_BINS - 1, (s * S_BINS) // 256)] += w
        v_hist[min(V_BINS - 1, (v * V_BINS) // 256)] += w
        weight_sum += w
    if weight_sum <= 1e-9:
        return [0.0] * (H_BINS + S_BINS + V_BINS)
    return [c / weight_sum for c in h_hist + s_hist + v_hist]


def _grid_colors(rgb: Image.Image, rgba: Image.Image) -> List[float]:
    small_rgb = rgb.resize((GRID, GRID), Image.Resampling.LANCZOS)
    small_a = rgba.getchannel("A").resize((GRID, GRID), Image.Resampling.BILINEAR)
    vals: List[float] = []
    for (r, g, b), a in zip(small_rgb.getdata(), small_a.getdata()):
        if a < 40:
            vals.extend([0.0, 0.0, 0.0])
        else:
            vals.extend([r / 255.0, g / 255.0, b / 255.0])
    return vals


def _normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _edge_signature(rgb: Image.Image) -> List[float]:
    g = rgb.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    e = g.filter(ImageFilter.FIND_EDGES).resize((8, 8), Image.Resampling.BOX)
    return _normalize([p / 255.0 for p in e.getdata()])


def extract_classic(img_or_bytes, *, is_query: bool = False) -> Dict[str, Any]:
    if isinstance(img_or_bytes, (bytes, bytearray)):
        img = _open_image(bytes(img_or_bytes))
    else:
        img = img_or_bytes
    if is_query:
        img = _smart_query_crop(img)
    rgb, rgba, opaque_ratio = _prepare_content(img)
    grid = _grid_colors(rgb, rgba)
    hist = _hist_content(rgba)
    edges = _edge_signature(rgb)
    vec = _normalize(hist + hist + grid + edges)
    return {
        "vec": vec,
        "phash": str(imagehash.phash(rgb, hash_size=8)),
        "dhash": str(imagehash.dhash(rgb, hash_size=8)),
        "chash": str(imagehash.colorhash(rgb, binbits=3)),
        "opaque": opaque_ratio,
    }


def _hamming_hex(a: str, b: str) -> float:
    try:
        ha = imagehash.hex_to_hash(a)
        hb = imagehash.hex_to_hash(b)
        bits = max(len(ha.hash.flatten()) if hasattr(ha, "hash") else 64, 1)
        return (ha - hb) / float(bits)
    except Exception:
        return 1.0


def _classic_score(query: Dict[str, Any], cand: Dict[str, Any]) -> float:
    n = min(len(query["vec"]), len(cand["vec"]))
    cos = sum(query["vec"][i] * cand["vec"][i] for i in range(n)) if n else 0.0
    ph = 1.0 - _hamming_hex(query["phash"], cand["phash"])
    dh = 1.0 - _hamming_hex(query["dhash"], cand["dhash"])
    ch = 1.0 - min(1.0, _hamming_hex(query.get("chash", ""), cand.get("chash", "")))
    raw = 0.50 * cos + 0.18 * ph + 0.12 * dh + 0.20 * ch
    op = float(cand.get("opaque") or 0)
    if op < 0.01:
        raw *= 0.65
    elif op < 0.03:
        raw *= 0.85
    return raw


def _save_cache(rows: List[Dict[str, Any]], clip_mat: Optional[np.ndarray]) -> None:
    """Cache rápido: NPZ (clip+classic) + meta pickle chico."""
    try:
        thumb_store.ensure_root()
        if not rows:
            return
        classic = np.asarray([r.get("vec") or [] for r in rows], dtype=np.float32)
        clip = (
            clip_mat.astype(np.float32)
            if clip_mat is not None
            else np.zeros((len(rows), 0), dtype=np.float32)
        )
        np.savez_compressed(_feat_path, clip=clip, classic=classic)
        meta = {
            "ver": FEAT_VER,
            "rows": [
                {
                    "pack": r["pack"],
                    "name": r["name"],
                    "phash": r.get("phash"),
                    "dhash": r.get("dhash"),
                    "chash": r.get("chash"),
                    "opaque": r.get("opaque", 0),
                    "texture": r.get("texture", False),
                }
                for r in rows
            ],
        }
        _meta_path.write_bytes(pickle.dumps(meta, protocol=4))
    except Exception as e:
        print(f"[image_search] cache save failed: {e}")


def _load_cache() -> Optional[Tuple[List[Dict[str, Any]], Optional[np.ndarray]]]:
    # Formato nuevo NPZ+meta
    if _feat_path.is_file() and _meta_path.is_file():
        try:
            meta = pickle.loads(_meta_path.read_bytes())
            if meta.get("ver") != FEAT_VER:
                return None
            rows_meta = meta.get("rows") or []
            data = np.load(_feat_path, allow_pickle=False)
            clip = np.asarray(data["clip"], dtype=np.float32)
            classic = np.asarray(data["classic"], dtype=np.float32)
            if clip.ndim != 2 or clip.shape[0] != len(rows_meta):
                return None
            rows = []
            for i, m in enumerate(rows_meta):
                row = dict(m)
                if i < classic.shape[0]:
                    row["vec"] = classic[i].tolist()
                else:
                    row["vec"] = []
                rows.append(row)
            return rows, clip if clip.shape[1] > 0 else None
        except Exception as e:
            print(f"[image_search] npz cache load failed: {e}")

    # Legacy pickle (lento) — migrar al vuelo
    if _legacy_pkl.is_file():
        try:
            t0 = time.time()
            payload = pickle.loads(_legacy_pkl.read_bytes())
            if payload.get("ver") != FEAT_VER:
                return None
            rows = payload.get("rows") or []
            clip = payload.get("clip")
            if clip is not None:
                clip = np.asarray(clip, dtype=np.float32)
                if clip.ndim != 2 or clip.shape[0] != len(rows):
                    clip = None
            print(f"[image_search] legacy pickle loaded in {time.time()-t0:.1f}s — migrating")
            if rows and clip is not None:
                _save_cache(rows, clip)
            return rows, clip
        except Exception as e:
            print(f"[image_search] legacy load failed: {e}")
    return None


def rebuild_index(force: bool = False) -> Dict[str, Any]:
    """
    Carga cache o rebuild. El trabajo pesado NO sostiene el lock global
    (así /api/status y la UI no se cuelgan).
    """
    global _index, _built, _clip_matrix, _build_progress

    if not force:
        with _lock:
            if _built and _index:
                return {
                    "ok": True,
                    "indexed": len(_index),
                    "clip": _clip_matrix is not None,
                    "cached": True,
                    "engine": "clip" if _clip_matrix is not None else "classic",
                }
        cached = _load_cache()
        if cached is not None:
            rows, clip = cached
            if clip is not None and len(rows) > 0:
                with _lock:
                    _index = rows
                    _clip_matrix = clip
                    _built = True
                    _ready.set()
                return {
                    "ok": True,
                    "indexed": len(rows),
                    "clip": True,
                    "cached": True,
                    "engine": "clip",
                }

    with _lock:
        if _build_progress.get("running"):
            return {
                "ok": True,
                "indexed": len(_index),
                "building": True,
                "build": dict(_build_progress),
            }
        _build_progress = {
            "running": True,
            "done": 0,
            "total": 0,
            "message": "Preparando features…",
        }

    try:
        items = thumb_store.list_items()
        _build_progress["total"] = len(items)

        candidates: List[Tuple[Dict[str, Any], bytes]] = []
        skipped = 0
        for it in items:
            pack = it["pack"]
            name = it["name"]
            if _is_junk_name(name):
                skipped += 1
                continue
            path = thumb_store.thumb_path(pack, name)
            try:
                png = path.read_bytes()
                if len(png) < 64:
                    skipped += 1
                    continue
                feat = extract_classic(png)
                if feat.get("opaque", 0) < MIN_OPAQUE_RATIO:
                    skipped += 1
                    continue
            except Exception:
                skipped += 1
                continue
            row = {
                "pack": pack,
                "name": name,
                "vec": feat["vec"],
                "phash": feat["phash"],
                "dhash": feat["dhash"],
                "chash": feat["chash"],
                "opaque": feat.get("opaque", 0),
                "texture": _is_texture_name(pack, name),
            }
            candidates.append((row, png))

        rows = [c[0] for c in candidates]
        pngs = [c[1] for c in candidates]

        clip_mat = None
        engine = "classic"
        if clip_embed.ensure_model():
            _build_progress["message"] = "Calculando embeddings CLIP…"
            _build_progress["total"] = len(pngs)
            embs: List[np.ndarray] = []
            bs = 24
            t0 = time.time()
            for i in range(0, len(pngs), bs):
                chunk = pngs[i : i + bs]
                arr = clip_embed.embed_images(chunk, batch_size=len(chunk))
                if arr is None:
                    embs = []
                    break
                embs.append(arr)
                _build_progress["done"] = min(len(pngs), i + len(chunk))
                _build_progress["message"] = (
                    f"CLIP {_build_progress['done']}/{len(pngs)} "
                    f"({time.time() - t0:.0f}s)"
                )
            if embs:
                clip_mat = np.concatenate(embs, axis=0).astype(np.float32)
                engine = "clip"

        with _lock:
            _index = rows
            _clip_matrix = clip_mat
            _built = True
            _ready.set()
        _save_cache(rows, clip_mat)
        _build_progress = {
            "running": False,
            "done": len(rows),
            "total": len(rows),
            "message": f"Listo · {engine} · {len(rows)} items",
        }
        return {
            "ok": True,
            "indexed": len(rows),
            "skipped": skipped,
            "clip": clip_mat is not None,
            "cached": False,
            "engine": engine,
        }
    except Exception as e:
        _build_progress = {
            "running": False,
            "done": 0,
            "total": 0,
            "message": f"Error: {e}",
        }
        raise


def ensure_index(timeout: Optional[float] = None) -> bool:
    """Asegura índice listo. Si timeout y aún no, False (no bloquea eternamente)."""
    with _lock:
        if _built and _index:
            return True
    warm_index_background()
    if timeout is None:
        _ready.wait()
        return is_ready()
    ok = _ready.wait(timeout=timeout)
    return bool(ok and is_ready())


def warm_index_background() -> None:
    """Carga/rebuild en un hilo daemon — no bloquea Flask."""
    global _warm_started
    with _lock:
        if _built and _index:
            _ready.set()
            return
        if _warm_started and _build_progress.get("running"):
            return
        _warm_started = True

    def _run():
        try:
            rebuild_index(force=False)
        except Exception as e:
            print(f"[image_search] warm failed: {e}")
            _build_progress["running"] = False
            _build_progress["message"] = f"Error índice: {e}"

    threading.Thread(target=_run, name="clip-warm", daemon=True).start()


def invalidate(delete_files: bool = False) -> None:
    """Marca el índice como stale. Por defecto NO borra el cache en disco."""
    global _built, _clip_matrix, _warm_started
    with _lock:
        _built = False
        _clip_matrix = None
        _warm_started = False
        _ready.clear()
    if delete_files:
        for p in (_feat_path, _meta_path, _legacy_pkl):
            try:
                if p.is_file():
                    p.unlink()
            except Exception:
                pass


def add_or_update(pack: str, name: str, png: bytes) -> None:
    if _is_junk_name(name) or len(png) < 64:
        return
    try:
        feat = extract_classic(png)
    except Exception:
        return
    if feat.get("opaque", 0) < MIN_OPAQUE_RATIO:
        return
    emb = None
    if clip_embed.model_ready():
        emb = clip_embed.embed_one(png)

    # Si el índice aún no cargó, no forzar rebuild acá (bloquearía ingest).
    if not is_ready():
        return
    with _lock:
        global _index, _clip_matrix
        if not _index or _clip_matrix is None:
            return
        keep_idx = [i for i, r in enumerate(_index) if not (r["pack"] == pack and r["name"] == name)]
        _index = [_index[i] for i in keep_idx]
        if len(keep_idx) > 0:
            _clip_matrix = _clip_matrix[keep_idx]
        else:
            _clip_matrix = np.zeros((0, _clip_matrix.shape[1]), dtype=np.float32)

        row = {
            "pack": pack,
            "name": name,
            "vec": feat["vec"],
            "phash": feat["phash"],
            "dhash": feat["dhash"],
            "chash": feat["chash"],
            "opaque": feat.get("opaque", 0),
            "texture": _is_texture_name(pack, name),
        }
        _index.append(row)
        if emb is not None:
            vec = emb.reshape(1, -1).astype(np.float32)
            if _clip_matrix.shape[0] == 0:
                _clip_matrix = vec
            else:
                _clip_matrix = np.concatenate([_clip_matrix, vec], axis=0)


def _phash_bits(a: str, b: str) -> int:
    try:
        return int(imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b))
    except Exception:
        return 64


def _color_hist(img: Image.Image, bins: int = 4) -> np.ndarray:
    """Histograma RGB 4³ sobre píxeles opacos (o todos si no hay alpha)."""
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba)
    a = arr[:, :, 3] >= 16
    if not np.any(a):
        pix = arr[:, :, :3].reshape(-1, 3)
    else:
        pix = arr[:, :, :3][a]
    # 4 bins por canal
    q = np.clip(pix.astype(np.int32) * bins // 256, 0, bins - 1)
    idx = q[:, 0] * (bins * bins) + q[:, 1] * bins + q[:, 2]
    hist = np.bincount(idx, minlength=bins ** 3).astype(np.float32)
    s = float(hist.sum())
    if s < 1:
        return hist
    hist /= s
    return hist


def _color_sim(a: np.ndarray, b: np.ndarray) -> float:
    # Bhattacharyya-ish
    return float(np.sqrt(a * b).sum())


def search_bytes(
    png: bytes,
    *,
    top_k: int = 40,
    theme: str = "",
    min_score: float = 0.18,
    exclude: Optional[Tuple[str, str]] = None,
) -> List[Dict[str, Any]]:
    from core import theme_tags

    if not ensure_index(timeout=1.5):
        # No bloquear la request minutos: el warm corre en background.
        raise RuntimeError(
            "El índice visual todavía está cargando. Esperá unos segundos y reintentá."
        )
    try:
        _qim = _open_image(png)
        q_area = _qim.size[0] * _qim.size[1]
    except Exception:
        q_area = 0
        _qim = None
    query_classic = extract_classic(png, is_query=True)
    # Iconos UI / capturas / recortes marcados: CLIP casi puro
    # (classic por color empeora mucho; thumbs Flash suelen tener alpha)
    opaque_q = float(query_classic.get("opaque") or 0)
    external_query = (
        exclude is None
        or q_area >= 40 * 40
        or clip_embed.needs_knockout(png)
        or opaque_q >= 0.85
    )
    # Captura in-game con pasto/pelo/otros props → color del centro manda
    busy_scene = bool(_qim is not None and clip_embed.is_busy_scene(_qim))
    if busy_scene:
        external_query = True
    query_clips: List[np.ndarray] = []
    # Shortlist solo con embed "completo" (los crops de escena sesgan a sillones/pasto)
    shortlist_clip: Optional[np.ndarray] = None
    q_hist: Optional[np.ndarray] = None
    if _clip_matrix is not None and _clip_matrix.shape[0] == len(_index):
        # Thumb limpio → embed alineado al índice.
        # Iconos/capturas → también embed con knockout de fondo + blobs.
        e0 = clip_embed.embed_one(png, knockout_bg=False)
        if e0 is not None:
            query_clips.append(e0)
            shortlist_clip = e0
        if external_query or clip_embed.needs_knockout(png):
            e1 = clip_embed.embed_one(png, knockout_bg=True, descreen=True)
            if e1 is not None:
                query_clips.append(e1)
                if shortlist_clip is None:
                    shortlist_clip = e1
            try:
                rgba = _open_image(png).convert("RGBA")
                if busy_scene:
                    # Color del CENTRO; crops solo para score final, no para shortlist
                    crops = clip_embed.center_crops(rgba, scales=(0.70, 0.50))
                    if crops:
                        q_hist = _color_hist(crops[0])
                    for crop in crops:
                        eb = clip_embed.embed_one(crop, knockout_bg=False, descreen=True)
                        if eb is not None:
                            query_clips.append(eb)
                    if q_hist is None:
                        q_hist = _color_hist(rgba)
                else:
                    ko = clip_embed._knockout_flat_bg(rgba)
                    q_hist = _color_hist(ko)
                    # Multi-objeto (labial + tela): buscar cada blob por separado
                    for blob in clip_embed.opaque_blobs(ko, min_frac=0.08, max_blobs=3):
                        if blob.size[0] * blob.size[1] < 24 * 24:
                            continue
                        eb = clip_embed.embed_one(blob, knockout_bg=False, descreen=True)
                        if eb is not None:
                            query_clips.append(eb)
            except Exception:
                pass

        if external_query:
            try:
                from core import bg_remove
                q_pil = _open_image(png)
                seg = bg_remove.remove_background(q_pil, mode="smart")
                e_seg = clip_embed.embed_one(seg, knockout_bg=False)
                if e_seg is not None:
                    query_clips.append(e_seg)
            except Exception:
                pass

    with _lock:
        rows = list(_index)
        clip_mat = _clip_matrix

    use_clip = bool(query_clips) and clip_mat is not None and clip_mat.shape[0] == len(rows)
    item_like = float(query_classic.get("opaque") or 0) < 0.85
    limit = max(1, min(int(top_k or 40), 120))


    scored: List[Dict[str, Any]] = []
    if use_clip:
        sims = None
        for qc in query_clips:
            s = clip_mat @ qc.astype(np.float32)
            sims = s if sims is None else np.maximum(sims, s)
        # Shortlist: tomar el mejor score de similitud entre todas las representaciones
        sims_short = sims
        order = np.argsort(-sims_short)
        short_n = max(
            1200 if busy_scene else (500 if external_query else 220),
            limit * 5,
        )
        shortlist: List[Tuple[int, float]] = []
        for i in order:
            i = int(i)
            row = rows[i]
            if exclude and row["pack"] == exclude[0] and row["name"] == exclude[1]:
                continue
            if _is_junk_name(row["name"]):
                continue
            if theme and theme != "todos":
                if not (
                    theme_tags.pack_matches_theme(row["pack"], theme)
                    or theme_tags.item_matches_theme(row["pack"], row["name"], theme)
                ):
                    continue
            shortlist.append((i, float(sims[i])))
            if len(shortlist) >= short_n:
                break

        # Aspecto de la query (ancho/alto) para penalizar candidatos muy distintos
        q_ar = 1.0
        try:
            qw, qh = _open_image(png).size
            q_ar = max(qw, 1) / max(qh, 1)
        except Exception:
            q_ar = 1.0

        # 2) rerank
        for i, clip_s in shortlist:
            row = rows[i]
            classic = _classic_score(query_classic, row)
            ph = _phash_bits(query_classic["phash"], row.get("phash") or "")
            dh = _phash_bits(query_classic["dhash"], row.get("dhash") or "")
            if busy_scene:
                # Escena in-game: max(CLIP puro, CLIP+color).
                # Si solo usamos color, un moño rojo sobre cabeza amarilla
                # pierde contra sillones/zapatos rojos; si solo CLIP, el
                # gorro teal se ahoga. El max cubre ambos casos.
                s_clip = 0.92 * clip_s + 0.04 * classic
                s_col = 0.62 * clip_s + 0.04 * classic
                if q_hist is not None:
                    try:
                        cpath = thumb_store.thumb_path(row["pack"], row["name"])
                        c_hist = _color_hist(Image.open(cpath))
                        s_col += 0.30 * _color_sim(q_hist, c_hist)
                    except Exception:
                        pass
                s = max(s_clip, s_col)
            elif external_query:
                # CLIP manda; classic complementario sin penalizaciones destructivas
                s = 0.94 * clip_s + 0.06 * classic
                if q_hist is not None:
                    try:
                        cpath = thumb_store.thumb_path(row["pack"], row["name"])
                        c_hist = _color_hist(Image.open(cpath))
                        s += 0.05 * _color_sim(q_hist, c_hist)
                    except Exception:
                        pass
            else:
                # Thumb del juego: classic ayuda near-dupes de color/forma
                s = 0.85 * clip_s + 0.15 * classic
            # Near-duplicate visual (mismo thumb / clone)
            if ph <= 4:
                s = max(s, 0.97 + (4 - ph) * 0.005)
            elif ph <= 10:
                s += 0.06 * (1.0 - ph / 10.0)
            if dh <= 6:
                s += 0.03
            if item_like and _is_texture_name(row["pack"], row["name"]) and not external_query:
                s *= 0.70
            # Penalizar suavemente si la proporción es extremadamente dispar (lápiz vs skate)
            if external_query:
                try:
                    tw, th = Image.open(thumb_store.thumb_path(row["pack"], row["name"])).size
                    c_ar = max(tw, 1) / max(th, 1)
                    ratio = max(q_ar, c_ar) / max(min(q_ar, c_ar), 1e-6)
                    if ratio >= 4.0:
                        s *= 0.92
                    elif ratio >= 3.0:
                        s *= 0.96
                except Exception:
                    pass
            if s < min_score:
                continue
            scored.append({
                "pack": row["pack"],
                "name": row["name"],
                "score": float(s),
                "clip": round(clip_s, 4),
                "thumb_url": f"/api/thumbs/file?pack={row['pack']}&name={row['name']}",
            })
    else:
        for row in rows:
            if exclude and row["pack"] == exclude[0] and row["name"] == exclude[1]:
                continue
            if _is_junk_name(row["name"]):
                continue
            if theme and theme != "todos":
                if not (
                    theme_tags.pack_matches_theme(row["pack"], theme)
                    or theme_tags.item_matches_theme(row["pack"], row["name"], theme)
                ):
                    continue
            s = _classic_score(query_classic, row)
            if item_like and _is_texture_name(row["pack"], row["name"]):
                s *= 0.65
            if s < max(min_score, 0.42):
                continue
            scored.append({
                "pack": row["pack"],
                "name": row["name"],
                "score": float(s),
                "thumb_url": f"/api/thumbs/file?pack={row['pack']}&name={row['name']}",
            })

    scored.sort(key=lambda r: -r["score"])
    top = scored[:limit]

    if top:
        for row in top:
            raw = row["score"]
            if use_clip:
                shown = max(0.0, min(0.99, (raw + 0.02) / 1.02))
            else:
                shown = max(0.0, min(0.99, raw))
            row["score"] = round(float(shown), 4)
            row["engine"] = "clip" if use_clip else "classic"
    return top


def search_data_url(data_url: str, **kwargs) -> List[Dict[str, Any]]:
    raw = (data_url or "").strip()
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    import base64

    png = base64.b64decode(raw, validate=False)
    return search_bytes(png, **kwargs)


def index_stats() -> Dict[str, Any]:
    """No bloquea: si el índice no está listo, reporta building."""
    warm_index_background()
    with _lock:
        ready = bool(_built and _index and _clip_matrix is not None)
        return {
            "ok": True,
            "indexed": len(_index) if ready else 0,
            "feat_ver": FEAT_VER,
            "engine": "clip" if ready else ("building" if _build_progress.get("running") else "classic"),
            "clip_ready": ready,
            "ready": ready,
            "build": get_build_progress(),
            **thumb_store.stats(),
        }
