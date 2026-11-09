"""
Remoción de fondo automática para imágenes y capturas de pantalla.
Soporta:
1. 'smart' (OpenCV GrabCut + morfología): Ultra-rápido (~100ms), ideal para gráficos de juegos/sprites.
2. 'ai' (BRIA RMBG-1.4 ONNX): Red neuronal profunda de última generación para fotos complejas.
"""
from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
RMBG_MODEL_DIR = BASE_DIR / "data" / "models" / "rmbg"
RMBG_MODEL_PATH = RMBG_MODEL_DIR / "onnx" / "model_quantized.onnx"

_rmbg_session = None
_rmbg_failed = False


def _get_rmbg_session():
    global _rmbg_session, _rmbg_failed
    if _rmbg_failed:
        return None
    if _rmbg_session is not None:
        return _rmbg_session

    if not RMBG_MODEL_PATH.is_file():
        try:
            from huggingface_hub import hf_hub_download
            RMBG_MODEL_DIR.mkdir(parents=True, exist_ok=True)
            hf_hub_download(
                "briaai/RMBG-1.4",
                "onnx/model_quantized.onnx",
                local_dir=str(RMBG_MODEL_DIR),
            )
        except Exception as e:
            print(f"[bg_remove] no se pudo descargar RMBG ONNX: {e}")
            _rmbg_failed = True
            return None

    try:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 4
        _rmbg_session = ort.InferenceSession(
            str(RMBG_MODEL_PATH),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        return _rmbg_session
    except Exception as e:
        print(f"[bg_remove] fallo al cargar sesión ONNX: {e}")
        _rmbg_failed = True
        return None


def remove_background_grabcut(pil_img: Image.Image, margin_pct: float = 0.03) -> Image.Image:
    """
    Segmentación por GrabCut optimizada para objetos recortados en juegos y sprites.
    Conserva bordes pixel art, no horada objetos que toquen el borde y rellena agujeros internos.
    """
    rgb = pil_img.convert("RGB")
    arr = np.array(rgb)
    h, w = arr.shape[:2]

    if w < 8 or h < 8:
        return pil_img.convert("RGBA")

    orig_rgba = pil_img.convert("RGBA")
    alpha_channel = np.array(orig_rgba.getchannel("A"))
    has_alpha = bool(np.any(alpha_channel < 240))

    margin_x = max(1, int(w * margin_pct))
    margin_y = max(1, int(h * margin_pct))

    rect_w = w - 2 * margin_x
    rect_h = h - 2 * margin_y
    if rect_w < 4 or rect_h < 4:
        return pil_img.convert("RGBA")

    # Inicialización con máscara:
    # Todo el canvas como GC_PR_BGD (probable fondo).
    # Región central como GC_PR_FGD (probable primer plano).
    # Solo las 4 esquinas extremas como GC_BGD (fondo seguro).
    mask = np.full((h, w), cv2.GC_PR_BGD, dtype=np.uint8)
    cx0 = max(1, int(w * 0.12))
    cx1 = min(w - 1, int(w * 0.88))
    cy0 = max(1, int(h * 0.15))
    cy1 = min(h - 1, int(h * 0.85))
    if cx1 > cx0 and cy1 > cy0:
        mask[cy0:cy1, cx0:cx1] = cv2.GC_PR_FGD

    if has_alpha:
        mask[alpha_channel < 32] = cv2.GC_BGD

    corner_r = max(2, min(w, h) // 16)
    mask[:corner_r, :corner_r] = cv2.GC_BGD
    mask[:corner_r, -corner_r:] = cv2.GC_BGD
    mask[-corner_r:, :corner_r] = cv2.GC_BGD
    mask[-corner_r:, -corner_r:] = cv2.GC_BGD

    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    try:
        cv2.grabCut(arr, mask, None, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_MASK)
        fg_mask = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")

        # Rellenar agujeros internos del objeto para que no queden huecos
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            cv2.drawContours(fg_mask, [cnt], 0, 255, -1)

        # Si el resultado borró casi todo (<3%) o no borró nada (>98%), fallback a rect
        fg_ratio = float(np.mean(fg_mask > 128))
        if fg_ratio < 0.03 or fg_ratio > 0.98:
            mask_rect = np.zeros((h, w), np.uint8)
            rect = (margin_x, margin_y, rect_w, rect_h)
            cv2.grabCut(arr, mask_rect, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)
            fg_mask = np.where((mask_rect == cv2.GC_FGD) | (mask_rect == cv2.GC_PR_FGD), 255, 0).astype("uint8")
            contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                cv2.drawContours(fg_mask, [cnt], 0, 255, -1)

        # Solo suavizar en imágenes medianas/grandes para no arruinar el pixel art
        if max(w, h) >= 160:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
            fg_mask = cv2.GaussianBlur(fg_mask, (3, 3), 0)

        out = pil_img.convert("RGBA")
        out.putalpha(Image.fromarray(fg_mask))
        return out
    except Exception as e:
        print(f"[bg_remove] GrabCut fallo: {e}")
        return pil_img.convert("RGBA")


def remove_background_ai(pil_img: Image.Image) -> Image.Image:
    """
    Segmentación neuronal con RMBG-1.4 (ONNX quantized).
    """
    sess = _get_rmbg_session()
    if sess is None:
        return remove_background_grabcut(pil_img)

    orig_img = pil_img.convert("RGB")
    w, h = orig_img.size

    # Padding del 15% para que elementos en el borde no se confundan con fondo
    pad_x = max(8, int(w * 0.15))
    pad_y = max(8, int(h * 0.15))
    padded_w = w + 2 * pad_x
    padded_h = h + 2 * pad_y

    padded = Image.new("RGB", (padded_w, padded_h), (128, 128, 128))
    padded.paste(orig_img, (pad_x, pad_y))

    # Preprocesamiento 1024x1024 segun config RMBG
    resized = padded.resize((1024, 1024), Image.BILINEAR)
    arr = ((np.array(resized, dtype=np.float32) / 255.0 - [0.5, 0.5, 0.5]) / [1.0, 1.0, 1.0]).transpose(2, 0, 1)[np.newaxis, ...].astype(np.float32)

    try:
        out = sess.run(None, {"input": arr})[0]
        mask_1024 = out[0, 0]
        mask_padded = Image.fromarray((mask_1024 * 255).astype(np.uint8)).resize((padded_w, padded_h), Image.BILINEAR)
        mask_crop = mask_padded.crop((pad_x, pad_y, pad_x + w, pad_y + h))

        out_rgba = orig_img.convert("RGBA")
        out_rgba.putalpha(mask_crop)

        # Si RMBG no detectó fondo (>98% opaco) o borró todo (<2% opaco), fallback al segmentador sprite
        mask_arr = np.array(mask_crop)
        fg_ratio = float(np.mean(mask_arr > 128))
        if fg_ratio > 0.98 or fg_ratio < 0.02:
            return remove_background_grabcut(pil_img)

        return out_rgba
    except Exception as e:
        print(f"[bg_remove] AI fallo: {e}")
        return remove_background_grabcut(pil_img)


def remove_background(pil_img: Image.Image, mode: str = "smart") -> Image.Image:
    """
    Función principal de remoción de fondo.
    'smart': Combina GrabCut de alta velocidad optimizado para sprites de juegos.
    'ai': Usa la red neuronal profunda RMBG-1.4.
    """
    if mode == "ai":
        result = remove_background_ai(pil_img)
    else:
        result = remove_background_grabcut(pil_img)
    # Applying background removal after the eraser must not restore erased pixels.
    from PIL import ImageChops
    result = result.convert("RGBA")
    result.putalpha(ImageChops.darker(result.getchannel("A"), pil_img.convert("RGBA").getchannel("A")))
    return result
