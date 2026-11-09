import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, Eraser, Crop, RotateCcw, Loader2 } from "lucide-react";
import { api } from "../api/client";

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("No se pudo leer la imagen"));
    reader.readAsDataURL(file);
  });
}

async function imageFromClipboardEvent(e) {
  const items = e.clipboardData?.items;
  if (!items) return null;
  for (const item of items) {
    if (item.type && item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) return file;
    }
  }
  return null;
}

async function imageFromClipboardApi() {
  if (!navigator.clipboard?.read) return null;
  try {
    const items = await navigator.clipboard.read();
    for (const item of items) {
      const type = item.types.find((t) => t.startsWith("image/"));
      if (!type) continue;
      const blob = await item.getType(type);
      return new File([blob], "clipboard.png", { type: blob.type || "image/png" });
    }
  } catch (_) {
    return null;
  }
  return null;
}

/** Recorta dataURL al rect normalizado (0..1) sobre la imagen natural. */
function cropDataUrl(dataUrl, normRect) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const nw = img.naturalWidth || img.width;
      const nh = img.naturalHeight || img.height;
      const x = Math.max(0, Math.floor(normRect.x * nw));
      const y = Math.max(0, Math.floor(normRect.y * nh));
      const w = Math.max(8, Math.floor(normRect.w * nw));
      const h = Math.max(8, Math.floor(normRect.h * nh));
      const cw = Math.min(w, nw - x);
      const ch = Math.min(h, nh - y);
      if (cw < 8 || ch < 8) {
        resolve(dataUrl);
        return;
      }
      const canvas = document.createElement("canvas");
      canvas.width = cw;
      canvas.height = ch;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, x, y, cw, ch, 0, 0, cw, ch);
      resolve(canvas.toDataURL("image/png"));
    };
    img.onerror = () => reject(new Error("No se pudo recortar"));
    img.src = dataUrl;
  });
}

function clientToNorm(imgEl, clientX, clientY) {
  const rect = imgEl.getBoundingClientRect();
  const x = (clientX - rect.left) / Math.max(rect.width, 1);
  const y = (clientY - rect.top) / Math.max(rect.height, 1);
  return {
    x: Math.min(1, Math.max(0, x)),
    y: Math.min(1, Math.max(0, y)),
  };
}

/**
 * Ventana de búsqueda visual:
 * - Pegá con Ctrl+V, arrastrá, o elegí un archivo.
 * - Recorte rectangular manual.
 * - ✨ Quitar fondo automático con IA.
 * - 🧹 Borrador manual para limpiar sobrantes.
 */
export default function ImageSearchModal({ open, busy = false, onClose, onSearch }) {
  const fileRef = useRef(null);
  const dropRef = useRef(null);
  const imgRef = useRef(null);
  const canvasRef = useRef(null);
  const dragRef = useRef(null);
  const lastErasePosRef = useRef(null);

  const [preview, setPreview] = useState("");
  const [originalPreview, setOriginalPreview] = useState("");
  const [pendingFile, setPendingFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [hint, setHint] = useState("");
  const [sel, setSel] = useState(null); // {x,y,w,h} normalizado 0..1
  const [draft, setDraft] = useState(null);

  const [tool, setTool] = useState("crop"); // 'crop' | 'eraser'
  const [brushSize, setBrushSize] = useState(24);
  const [displayWidth, setDisplayWidth] = useState(null);

  // Enlarge tiny screenshots for precise edits, preserving the search pixels.
  useEffect(() => {
    let cancelled = false;
    setDisplayWidth(null);
    if (!preview) return;
    const image = new Image();
    image.onload = () => {
      if (!cancelled && Math.max(image.width, image.height) < 120) {
        setDisplayWidth(Math.round(image.width * Math.min(4, 240 / Math.max(image.width, image.height))));
      }
    };
    image.src = preview;
    return () => { cancelled = true; };
  }, [preview]);
  const [isRemovingBg, setIsRemovingBg] = useState(false);

  // Sync canvas with preview when in eraser mode
  useEffect(() => {
    if (!preview || tool !== "eraser") return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const img = new Image();
    img.onload = () => {
      canvas.width = img.naturalWidth || img.width;
      canvas.height = img.naturalHeight || img.height;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
    };
    img.src = preview;
  }, [preview, tool]);

  const acceptFile = useCallback(async (file) => {
    if (!file || !String(file.type || "").startsWith("image/")) {
      setHint("Eso no parece una imagen.");
      return;
    }
    try {
      const dataUrl = await readFileAsDataUrl(file);
      setPendingFile(file);
      setPreview(dataUrl);
      setOriginalPreview(dataUrl);
      setSel(null);
      setDraft(null);
      setTool("crop");
      setHint("Marcá el objeto con un recuadro o tocá «Quitar fondo» para aislarlo.");
    } catch (err) {
      setHint(err.message || "No se pudo cargar");
    }
  }, []);

  useEffect(() => {
    if (!open) {
      setPreview("");
      setOriginalPreview("");
      setPendingFile(null);
      setDragOver(false);
      setHint("");
      setSel(null);
      setDraft(null);
      setTool("crop");
      setIsRemovingBg(false);
      return undefined;
    }

    const onPaste = async (e) => {
      const file = await imageFromClipboardEvent(e);
      if (!file) return;
      e.preventDefault();
      await acceptFile(file);
    };

    const onKey = (e) => {
      if (e.key === "Escape" && !busy && !isRemovingBg) onClose?.();
    };

    window.addEventListener("paste", onPaste);
    window.addEventListener("keydown", onKey);
    const t = setTimeout(() => dropRef.current?.focus?.(), 50);
    return () => {
      clearTimeout(t);
      window.removeEventListener("paste", onPaste);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, busy, isRemovingBg, onClose, acceptFile]);

  if (!open) return null;

  // --- Crop Handlers ---
  const onCropPointerDown = (e) => {
    if (busy || isRemovingBg || tool !== "crop") return;
    const img = imgRef.current;
    if (!img) return;
    e.preventDefault();
    e.stopPropagation();
    img.setPointerCapture?.(e.pointerId);
    const p = clientToNorm(img, e.clientX, e.clientY);
    dragRef.current = { ...p, pointerId: e.pointerId };
    setDraft({ x: p.x, y: p.y, w: 0, h: 0 });
  };

  const onCropPointerMove = (e) => {
    if (tool !== "crop") return;
    const start = dragRef.current;
    const img = imgRef.current;
    if (!start || !img) return;
    const p = clientToNorm(img, e.clientX, e.clientY);
    setDraft({
      x: Math.min(start.x, p.x),
      y: Math.min(start.y, p.y),
      w: Math.abs(p.x - start.x),
      h: Math.abs(p.y - start.y),
    });
  };

  const onCropPointerUp = () => {
    if (tool !== "crop" || !dragRef.current) return;
    dragRef.current = null;
    setDraft((cur) => {
      if (cur && cur.w > 0.04 && cur.h > 0.04) {
        setSel(cur);
        setHint("Zona marcada. Podés buscar directo o tocar «Quitar fondo» para aislar el objeto.");
      }
      return null;
    });
  };

  // --- Eraser Handlers ---
  const onEraserPointerDown = (e) => {
    if (busy || isRemovingBg || tool !== "eraser") return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    e.preventDefault();
    e.stopPropagation();
    canvas.setPointerCapture?.(e.pointerId);

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;
    const r = (brushSize * scaleX) / 2;

    const ctx = canvas.getContext("2d");
    ctx.globalCompositeOperation = "destination-out";
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();

    lastErasePosRef.current = { x, y, pointerId: e.pointerId };
  };

  const onEraserPointerMove = (e) => {
    if (tool !== "eraser" || !lastErasePosRef.current) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;
    const lw = brushSize * scaleX;

    const ctx = canvas.getContext("2d");
    ctx.globalCompositeOperation = "destination-out";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = lw;
    ctx.beginPath();
    ctx.moveTo(lastErasePosRef.current.x, lastErasePosRef.current.y);
    ctx.lineTo(x, y);
    ctx.stroke();

    lastErasePosRef.current = { x, y, pointerId: e.pointerId };
  };

  const onEraserPointerUp = () => {
    if (tool !== "eraser" || !lastErasePosRef.current) return;
    lastErasePosRef.current = null;
    const canvas = canvasRef.current;
    if (canvas) {
      try {
        const updated = canvas.toDataURL("image/png");
        setPreview(updated);
        setPendingFile(null);
      } catch (_) {}
    }
  };

  // --- Auto Remove Background ---
  const handleRemoveBackground = async (mode = "smart") => {
    if (!preview || busy || isRemovingBg) return;
    setIsRemovingBg(true);
    setHint(mode === "ai" ? "Analizando y quitando fondo con IA neuronal (RMBG-1.4)…" : "Analizando y quitando fondo de sprite…");
    try {
      let targetDataUrl = preview;
      // Si hay un recorte activo, primero recortamos esa zona específica
      if (sel && sel.w > 0.04 && sel.h > 0.04) {
        targetDataUrl = await cropDataUrl(preview, sel);
        setSel(null);
        setDraft(null);
      }
      const res = await api.removeBackground({ dataUrl: targetDataUrl, mode });
      if (res.ok && res.data_url) {
        setPreview(res.data_url);
        setPendingFile(null);
        setHint("¡Fondo eliminado! Podés retocar con el Borrador o Buscar directamente.");
      } else {
        setHint(res.error || "No se pudo quitar el fondo.");
      }
    } catch (err) {
      setHint(err.message || "Error al procesar el fondo.");
    } finally {
      setIsRemovingBg(false);
    }
  };

  // --- Restore Original ---
  const handleRestoreOriginal = () => {
    if (!originalPreview) return;
    setPreview(originalPreview);
    setSel(null);
    setDraft(null);
    setTool("crop");
    setHint("Imagen restaurada al estado original.");
  };

  const onFileChange = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) await acceptFile(file);
  };

  const onDrop = async (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) await acceptFile(file);
  };

  const tryClipboardButton = async () => {
    const file = await imageFromClipboardApi();
    if (file) {
      await acceptFile(file);
      return;
    }
    setHint("Copiá una imagen y pegá acá con Ctrl+V.");
  };

  const submit = async () => {
    if (!preview || busy || isRemovingBg) return;
    let dataUrl = preview;
    if (sel && sel.w > 0.04 && sel.h > 0.04) {
      try {
        dataUrl = await cropDataUrl(preview, sel);
      } catch (_) {
        /* usa full */
      }
    }
    // Always search the edited pixels, never the originally uploaded file.
    await onSearch?.({ dataUrl });
  };

  const box = draft || sel;

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => e.target === e.currentTarget && !busy && !isRemovingBg && onClose?.()}
    >
      <div className="modal-card image-search-modal app-no-drag">
        <div className="modal-title">Buscar por imagen</div>
        <div className="modal-sub">
          Pegá una captura con <kbd>Ctrl</kbd>+<kbd>V</kbd>. Podés <strong>quitar el fondo automáticamente</strong> o marcar la zona del objeto.
        </div>

        <input ref={fileRef} type="file" accept="image/*" hidden onChange={onFileChange} />

        {/* Toolbar superior para recortar, borrar fondo y pincel */}
        {preview && (
          <div className="image-toolbar">
            <div className="image-toolbar-group">
              <button
                type="button"
                className={`btn btn-sm ${tool === "crop" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setTool("crop")}
                title="Marcar recuadro del objeto"
                disabled={isRemovingBg}
              >
                <Crop size={14} />
                Recortar
              </button>
              <button
                type="button"
                className={`btn btn-sm ${tool === "eraser" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => {
                  setTool("eraser");
                  setSel(null);
                  setDraft(null);
                  setHint("Pasa el mouse sobre las partes que quieras borrar (anteojos, pelo sobrante, etc.).");
                }}
                title="Borrar partes manualmente"
                disabled={isRemovingBg}
              >
                <Eraser size={14} />
                Borrador
              </button>
            </div>

            {tool === "eraser" && (
              <div className="image-brush-control">
                <span style={{ fontSize: 11, color: "var(--muted)" }}>Tamaño:</span>
                <input
                  type="range"
                  min="1"
                  max="50"
                  value={brushSize}
                  onChange={(e) => setBrushSize(Number(e.target.value))}
                  style={{ width: 80 }}
                />
                <span style={{ fontSize: 11, color: "#fff", minWidth: 20 }}>{brushSize}px</span>
              </div>
            )}

            <div className="image-toolbar-group" style={{ marginLeft: "auto" }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => handleRemoveBackground("smart")}
                disabled={isRemovingBg}
                title="Quitar fondo rápido de sprites y gráficos de juegos"
              >
                {isRemovingBg ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />}
                {isRemovingBg ? "Quitando fondo…" : "Sacar fondo"}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => handleRemoveBackground("ai")}
                disabled={isRemovingBg}
                title="Quitar fondo con Red Neuronal RMBG-1.4"
                style={{ color: "#a78bfa" }}
              >
                {isRemovingBg ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />}
                Fondo con IA
              </button>
              {originalPreview && originalPreview !== preview && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={handleRestoreOriginal}
                  title="Restaurar a la imagen original"
                  disabled={isRemovingBg}
                >
                  <RotateCcw size={14} />
                  Restaurar
                </button>
              )}
            </div>
          </div>
        )}

        {/* Dropzone / Preview Stage */}
        <div
          ref={dropRef}
          tabIndex={0}
          role="button"
          className={`image-dropzone ${dragOver ? "dragover" : ""} ${preview ? "has-preview" : ""}`}
          onDragEnter={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => !preview && fileRef.current?.click()}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === " ") && !preview) {
              e.preventDefault();
              fileRef.current?.click();
            }
          }}
        >
          {preview ? (
            <div className={`image-crop-stage ${tool === "eraser" ? "eraser-mode" : ""}`}>
              {tool === "eraser" ? (
                <canvas
                  ref={canvasRef}
                  className="image-dropzone-canvas"
                  style={{ width: displayWidth || undefined, height: "auto" }}
                  onPointerDown={onEraserPointerDown}
                  onPointerMove={onEraserPointerMove}
                  onPointerUp={onEraserPointerUp}
                  onPointerCancel={onEraserPointerUp}
                />
              ) : (
                <img
                  ref={imgRef}
                  src={preview}
                  alt=""
                  className="image-dropzone-preview"
                  style={{ width: displayWidth || undefined, height: "auto" }}
                  draggable={false}
                  onPointerDown={onCropPointerDown}
                  onPointerMove={onCropPointerMove}
                  onPointerUp={onCropPointerUp}
                  onPointerCancel={onCropPointerUp}
                />
              )}

              {tool === "crop" && box && box.w > 0.01 && box.h > 0.01 ? (
                <div
                  className="image-crop-box"
                  style={{
                    left: `${box.x * 100}%`,
                    top: `${box.y * 100}%`,
                    width: `${box.w * 100}%`,
                    height: `${box.h * 100}%`,
                  }}
                />
              ) : null}
            </div>
          ) : (
            <div className="image-dropzone-empty">
              <div className="image-dropzone-title">Pegá acá tu imagen</div>
              <div className="image-dropzone-sub">o hacé clic para elegir un archivo</div>
            </div>
          )}
        </div>

        {hint ? <div className="warn-text">{hint}</div> : null}

        <div className="modal-actions image-search-modal-actions">
          <button type="button" className="btn btn-ghost" disabled={busy || isRemovingBg} onClick={tryClipboardButton}>
            Pegar portapapeles
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy || isRemovingBg}
            onClick={() => fileRef.current?.click()}
          >
            Elegir archivo
          </button>
          {preview ? (
            <button
              type="button"
              className="btn btn-ghost"
              disabled={busy || isRemovingBg}
              onClick={() => {
                setPreview("");
                setOriginalPreview("");
                setPendingFile(null);
                setSel(null);
                setDraft(null);
                setHint("");
              }}
            >
              Quitar
            </button>
          ) : null}
          {sel ? (
            <button
              type="button"
              className="btn btn-ghost"
              disabled={busy || isRemovingBg}
              onClick={() => {
                setSel(null);
                setHint("Arrastrá sobre la imagen para marcar el objeto.");
              }}
            >
              Quitar marca
            </button>
          ) : null}
          <div className="grow" />
          <button type="button" className="btn btn-ghost" disabled={busy || isRemovingBg} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!preview || busy || isRemovingBg}
            onClick={submit}
          >
            {busy ? "Buscando…" : "Buscar"}
          </button>
        </div>
      </div>
    </div>
  );
}
