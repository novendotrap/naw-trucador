"""
Embeddings CLIP (ONNX) para búsqueda visual tipo Shein.
Modelo: Xenova/clip-vit-base-patch32 vision quantized → image_embeds 512-d.
"""
from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "data" / "models" / "clip"
MODEL_FILE = MODEL_DIR / "onnx" / "vision_model_quantized.onnx"

MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)

_lock = threading.RLock()
_session = None
_failed = False


def model_ready() -> bool:
    return MODEL_FILE.is_file()


_warned = False


def ensure_model() -> bool:
    """Descarga el ONNX si falta (una sola vez)."""
    global _failed, _warned
    if _failed:
        return False
    if model_ready():
        return True
    try:
        import onnxruntime  # noqa: F401
        from huggingface_hub import hf_hub_download

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        hf_hub_download(
            "Xenova/clip-vit-base-patch32",
            "onnx/vision_model_quantized.onnx",
            local_dir=str(MODEL_DIR),
        )
        hf_hub_download(
            "Xenova/clip-vit-base-patch32",
            "preprocessor_config.json",
            local_dir=str(MODEL_DIR),
        )
        return model_ready()
    except Exception as e:
        _failed = True
        if not _warned:
            _warned = True
            print(f"[clip_embed] Búsqueda visual CLIP opcional no disponible ({e}). Usando búsqueda visual clásica.")
        return False


def _get_session():
    global _session, _failed
    with _lock:
        if _failed:
            return None
        if _session is not None:
            return _session
        if not ensure_model():
            _failed = True
            return None
        try:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 2
            opts.intra_op_num_threads = 4
            _session = ort.InferenceSession(
                str(MODEL_FILE),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            return _session
        except Exception as e:
            print(f"[clip_embed] falló cargar ONNX: {e}")
            _failed = True
            return None


def _to_rgba(img: Image.Image) -> Image.Image:
    return img.convert("RGBA")


def _composite_white(rgba: Image.Image) -> Image.Image:
    """Sprites Flash: fondo blanco (mejor para CLIP que negro)."""
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, rgba).convert("RGB")


def _alpha_crop(rgba: Image.Image, thr: int = 16) -> Image.Image:
    mask = rgba.getchannel("A").point(lambda a: 255 if a >= thr else 0)
    bbox = mask.getbbox()
    if not bbox:
        return rgba
    cropped = rgba.crop(bbox)
    # padding chico
    w, h = cropped.size
    pad = max(2, max(w, h) // 20)
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    canvas.paste(cropped, (pad, pad), cropped)
    return canvas


def _knockout_flat_bg(rgba: Image.Image) -> Image.Image:
    """
    Capturas / pegados: fondo de UI (negro, gris, amarillo catálogo).
    Flood-fill desde los BORDES — no borra objetos oscuros (capa negra,
    tubo morado, araña) que el viejo umbral por luminancia se comía.
    """
    rgba = rgba.convert("RGBA")
    arr = np.asarray(rgba).copy()
    if arr.size == 0:
        return rgba
    h, w = arr.shape[:2]
    if h < 4 or w < 4:
        return rgba

    corners = np.array(
        [
            arr[0, 0, :3],
            arr[0, w - 1, :3],
            arr[h - 1, 0, :3],
            arr[h - 1, w - 1, :3],
            arr[0, w // 2, :3],
            arr[h - 1, w // 2, :3],
            arr[h // 2, 0, :3],
            arr[h // 2, w - 1, :3],
        ],
        dtype=np.float32,
    )
    avg = corners.mean(axis=0)
    corner_lum = float(corners.mean())
    corner_sat = float((corners.max(axis=1) - corners.min(axis=1)).mean())
    corner_spread = float(np.abs(corners - avg).mean())
    # Fondo poco uniforme (foto de pantalla con UI) → tolerancia más alta
    tol = 48.0 if corner_spread < 12 else 62.0
    if corner_lum < 55:
        tol = max(tol, 70.0)  # negro ruidoso de foto-al-monitor
    if corner_sat > 28 and corner_lum > 140:
        tol = max(tol, 55.0)  # amarillo/color de icono catálogo

    rgb = arr[:, :, :3].astype(np.float32)
    # Candidatos "parecen fondo" (antes de conectividad)
    dist = np.abs(rgb - avg).sum(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    lum = rgb.mean(axis=2)
    if corner_spread < 8 and corner_sat > 35 and corner_lum <= 140 and arr[:, :, 3].min() >= 250:
        # Uniform colored backgrounds (grass/colored UI) are backgrounds too.
        # Connectivity and the killed-fraction guard below protect the object.
        bgish = dist < 48
    elif corner_lum < 80:
        # UI oscura: fondo = cerca del color de esquina y poco saturado
        bgish = (dist < tol) & (sat < 28)
    elif corner_sat > 25 and corner_lum > 140:
        bgish = (dist < tol) & (np.abs(lum - corner_lum) < 40)
    else:
        bgish = (dist < tol) & (sat < 35)

    opaque = arr[:, :, 3] >= 16
    bgish &= opaque

    # Semillas: píxeles de borde que parecen fondo
    kill = np.zeros((h, w), dtype=bool)
    stack: List[tuple] = []
    for x in range(w):
        if bgish[0, x]:
            stack.append((0, x))
        if bgish[h - 1, x]:
            stack.append((h - 1, x))
    for y in range(h):
        if bgish[y, 0]:
            stack.append((y, 0))
        if bgish[y, w - 1]:
            stack.append((y, w - 1))

    while stack:
        y, x = stack.pop()
        if kill[y, x] or not bgish[y, x]:
            continue
        kill[y, x] = True
        if y > 0 and not kill[y - 1, x]:
            stack.append((y - 1, x))
        if y + 1 < h and not kill[y + 1, x]:
            stack.append((y + 1, x))
        if x > 0 and not kill[y, x - 1]:
            stack.append((y, x - 1))
        if x + 1 < w and not kill[y, x + 1]:
            stack.append((y, x + 1))

    # Si el flood falló (casi nada o casi todo), no destruir el objeto
    killed_frac = float(kill.mean()) if kill.size else 0.0
    if killed_frac < 0.08 or killed_frac > 0.92:
        # Fallback suave: solo esquinas muy parecidas al avg (anillo fino)
        yy, xx = np.mgrid[0:h, 0:w]
        edge_band = (yy < 3) | (yy >= h - 3) | (xx < 3) | (xx >= w - 3)
        kill = edge_band & bgish
        # Si aún así mata demasiado, no tocar
        if float(kill.mean()) > 0.5:
            return rgba

    arr[kill, 3] = 0

    # Segundo paso: marcos / celdas de inventario (blanco-gris conectado al borde).
    # Fotos del catálogo dejan un rectángulo blanco que sesga CLIP.
    rgb2 = arr[:, :, :3].astype(np.float32)
    lum2 = rgb2.mean(axis=2)
    sat2 = rgb2.max(axis=2) - rgb2.min(axis=2)
    light_edge = (lum2 > 175) & (sat2 < 40) & (arr[:, :, 3] >= 16)
    kill2 = np.zeros((h, w), dtype=bool)
    stack2: List[tuple] = []
    for x in range(w):
        if light_edge[0, x]:
            stack2.append((0, x))
        if light_edge[h - 1, x]:
            stack2.append((h - 1, x))
    for y in range(h):
        if light_edge[y, 0]:
            stack2.append((y, 0))
        if light_edge[y, w - 1]:
            stack2.append((y, w - 1))
    while stack2:
        y, x = stack2.pop()
        if kill2[y, x] or not light_edge[y, x]:
            continue
        kill2[y, x] = True
        if y > 0 and not kill2[y - 1, x]:
            stack2.append((y - 1, x))
        if y + 1 < h and not kill2[y + 1, x]:
            stack2.append((y + 1, x))
        if x > 0 and not kill2[y, x - 1]:
            stack2.append((y, x - 1))
        if x + 1 < w and not kill2[y, x + 1]:
            stack2.append((y, x + 1))
    if 0.01 < float(kill2.mean()) < 0.45:
        arr[kill2, 3] = 0

    return Image.fromarray(arr, "RGBA")


def descreen_photo(rgba: Image.Image) -> Image.Image:
    """Suaviza moiré de foto-al-monitor sin matar la silueta."""
    rgba = rgba.convert("RGBA")
    w, h = rgba.size
    if max(w, h) < 160:
        return rgba
    # Baja un poco y vuelve: mata la grilla del monitor
    scale = 0.55 if max(w, h) >= 280 else 0.7
    nw = max(32, int(round(w * scale)))
    nh = max(32, int(round(h * scale)))
    small = rgba.resize((nw, nh), Image.Resampling.BILINEAR)
    return small.resize((w, h), Image.Resampling.BILINEAR)


def opaque_blobs(
    rgba: Image.Image,
    *,
    min_frac: float = 0.04,
    max_blobs: int = 3,
) -> List[Image.Image]:
    """
    Recortes por componente conexa (labial + telaraña, etc.).
    Devuelve hasta max_blobs crops RGBA ordenados por área.
    """
    rgba = rgba.convert("RGBA")
    arr = np.asarray(rgba)
    h, w = arr.shape[:2]
    opaque = arr[:, :, 3] >= 16
    if not opaque.any():
        return []
    seen = np.zeros((h, w), dtype=bool)
    blobs: List[Tuple[int, Tuple[int, int, int, int]]] = []
    for y0 in range(h):
        for x0 in range(w):
            if not opaque[y0, x0] or seen[y0, x0]:
                continue
            stack = [(y0, x0)]
            seen[y0, x0] = True
            minx = maxx = x0
            miny = maxy = y0
            area = 0
            while stack:
                y, x = stack.pop()
                area += 1
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < h and 0 <= nx < w and opaque[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            blobs.append((area, (minx, miny, maxx + 1, maxy + 1)))
    total = int(opaque.sum())
    blobs.sort(reverse=True)
    out: List[Image.Image] = []
    for area, box in blobs:
        if area < total * min_frac and len(out) >= 1:
            continue
        if area < max(40, total * 0.02):
            continue
        crop = rgba.crop(box)
        # descartar marcos casi vacíos / líneas
        ca = np.asarray(crop)[:, :, 3] >= 16
        if float(ca.mean()) < 0.08:
            continue
        out.append(crop)
        if len(out) >= max_blobs:
            break
    return out


def is_busy_scene(img_or_bytes: Union[Image.Image, bytes]) -> bool:
    """
    Captura in-game con fondo lleno (pasto, pelo, otros props).
    No es UI plana → el knockout no alcanza; hay que centrar + color.
    Recortes chicos (marca del modal) NO cuentan: el usuario ya enfocó.
    """
    if isinstance(img_or_bytes, (bytes, bytearray)):
        img = Image.open(io.BytesIO(bytes(img_or_bytes)))
    else:
        img = img_or_bytes
    rgba = _to_rgba(img)
    arr = np.asarray(rgba)
    if arr.size == 0:
        return False
    h, w = arr.shape[:2]
    if w < 80 or h < 60:
        return False
    # Marca/recorte del usuario: CLIP puro anda mejor que color-de-escena
    if w * h < 130 * 100:
        return False
    # Si ya es fondo UI plano, no es "escena"
    if needs_knockout(rgba) and w * h < 220 * 220:
        return False
    alpha = arr[:, :, 3]
    if float((alpha >= 16).mean()) < 0.92:
        return False
    corners = np.array(
        [
            arr[0, 0, :3],
            arr[0, w - 1, :3],
            arr[h - 1, 0, :3],
            arr[h - 1, w - 1, :3],
            arr[0, w // 2, :3],
            arr[h - 1, w // 2, :3],
            arr[h // 2, 0, :3],
            arr[h // 2, w - 1, :3],
        ],
        dtype=np.float32,
    )
    corner_spread = float(np.abs(corners - corners.mean(axis=0)).mean())
    # Esquinas distintas entre sí → fondo variado (pasto vs cielo vs tronco)
    if corner_spread > 28:
        return True
    # Alta saturación media en bordes → escena colorida
    edge = np.concatenate(
        [
            arr[0, :, :3],
            arr[-1, :, :3],
            arr[:, 0, :3],
            arr[:, -1, :3],
        ],
        axis=0,
    ).astype(np.float32)
    sat = edge.max(axis=1) - edge.min(axis=1)
    if float(sat.mean()) > 35 and corner_spread > 14:
        return True
    return False


def center_crops(
    rgba: Image.Image,
    scales: Sequence[float] = (0.72, 0.52),
) -> List[Image.Image]:
    """Recortes centrados para enfocar el objeto al que apunta la captura."""
    rgba = rgba.convert("RGBA")
    w, h = rgba.size
    out: List[Image.Image] = []
    for sc in scales:
        cw = max(16, int(round(w * sc)))
        ch = max(16, int(round(h * sc)))
        x0 = max(0, (w - cw) // 2)
        y0 = max(0, (h - ch) // 2)
        out.append(rgba.crop((x0, y0, x0 + cw, y0 + ch)))
    return out


def needs_knockout(img_or_bytes: Union[Image.Image, bytes]) -> bool:
    """
    True para capturas/iconos UI con fondo opaco plano.
    Thumbs Flash con alpha → False.
    """
    if isinstance(img_or_bytes, (bytes, bytearray)):
        img = Image.open(io.BytesIO(bytes(img_or_bytes)))
    else:
        img = img_or_bytes
    rgba = _to_rgba(img)
    arr = np.asarray(rgba)
    if arr.size == 0:
        return False
    alpha = arr[:, :, 3]
    opaque = float((alpha >= 16).mean())
    if opaque < 0.92:
        return False
    h, w = arr.shape[:2]
    corners = np.array(
        [
            arr[0, 0, :3],
            arr[0, w - 1, :3],
            arr[h - 1, 0, :3],
            arr[h - 1, w - 1, :3],
        ],
        dtype=np.float32,
    )
    corner_lum = float(corners.mean())
    corner_sat = float((corners.max(axis=1) - corners.min(axis=1)).mean())
    # esquinas muy parecidas entre sí → fondo plano
    corner_spread = float(np.abs(corners - corners.mean(axis=0)).mean())
    if corner_lum < 50 and (w >= 100 or h >= 100):
        return True
    if opaque > 0.98 and (w >= 160 or h >= 160) and corner_lum < 80:
        return True
    # Iconos de catálogo (fondo amarillo/plano)
    if opaque > 0.96 and corner_spread < 18 and (corner_sat > 25 or corner_lum > 160):
        return True
    return False


def preprocess_image(
    img_or_bytes: Union[Image.Image, bytes],
    *,
    knockout_bg: bool = False,
    descreen: bool = False,
) -> np.ndarray:
    if isinstance(img_or_bytes, (bytes, bytearray)):
        img = Image.open(io.BytesIO(bytes(img_or_bytes)))
    else:
        img = img_or_bytes
    rgba = _to_rgba(img)
    if knockout_bg:
        rgba = _knockout_flat_bg(rgba)
        if descreen or max(rgba.size) >= 160:
            rgba = descreen_photo(rgba)
    elif descreen:
        rgba = descreen_photo(rgba)
    rgba = _alpha_crop(rgba)
    rgb = _composite_white(rgba)

    # Letterbox a 224x224 (NO center-crop).
    # Los thumbs anchos (skates 38x13, autos) con center-crop perdían la silueta.
    w, h = rgb.size
    if w < 1 or h < 1:
        rgb = Image.new("RGB", (224, 224), (255, 255, 255))
        w, h = 224, 224
    scale = min(224.0 / w, 224.0 / h)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    rgb = rgb.resize((nw, nh), Image.Resampling.BICUBIC)
    canvas = Image.new("RGB", (224, 224), (255, 255, 255))
    canvas.paste(rgb, ((224 - nw) // 2, (224 - nh) // 2))
    rgb = canvas

    arr = np.asarray(rgb, dtype=np.float32) * 0.00392156862745098  # /255
    arr = (arr - MEAN) / STD
    arr = np.transpose(arr, (2, 0, 1))  # CHW
    return arr


def _l2_normalize(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return vecs / norms


def embed_images(
    images: Sequence[Union[Image.Image, bytes]],
    batch_size: int = 16,
    *,
    knockout_bg: bool = False,
    descreen: bool = False,
) -> Optional[np.ndarray]:
    """Devuelve (N, 512) float32 L2-normalizado, o None si CLIP no está."""
    session = _get_session()
    if session is None or not images:
        return None

    outs: List[np.ndarray] = []
    for i in range(0, len(images), batch_size):
        chunk = images[i : i + batch_size]
        batch = np.stack(
            [
                preprocess_image(im, knockout_bg=knockout_bg, descreen=descreen)
                for im in chunk
            ],
            axis=0,
        )
        result = session.run(None, {"pixel_values": batch})[0]
        outs.append(np.asarray(result, dtype=np.float32))
    stacked = np.concatenate(outs, axis=0)
    return _l2_normalize(stacked)


def embed_one(
    img_or_bytes: Union[Image.Image, bytes],
    *,
    knockout_bg: Optional[bool] = None,
    descreen: bool = False,
) -> Optional[np.ndarray]:
    if knockout_bg is None:
        knockout_bg = needs_knockout(img_or_bytes)
    arr = embed_images(
        [img_or_bytes],
        batch_size=1,
        knockout_bg=knockout_bg,
        descreen=descreen,
    )
    if arr is None:
        return None
    return arr[0]
