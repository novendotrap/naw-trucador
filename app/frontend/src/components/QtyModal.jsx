import { useEffect, useState } from "react";
import Field from "./Field";

export default function QtyModal({
  open,
  title = "¿Cuántos querés?",
  message = "Lola te va a dar esta cantidad. Recomendado: 1.",
  defaultQty = 1,
  onCancel,
  onConfirm,
}) {
  const [qty, setQty] = useState(defaultQty);

  useEffect(() => {
    if (open) setQty(defaultQty || 1);
  }, [open, defaultQty]);

  if (!open) return null;

  const n = Math.max(1, Math.min(99, parseInt(qty, 10) || 1));

  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onCancel?.()}>
      <div className="modal-card app-no-drag">
        <div className="modal-title">{title}</div>
        <div className="modal-sub">{message}</div>
        <Field
          label="Cantidad"
          type="number"
          min={1}
          max={99}
          value={n}
          autoFocus
          onChange={(e) => setQty(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onConfirm?.(n);
            if (e.key === "Escape") onCancel?.();
          }}
        />
        {n > 10 && (
          <div className="warn-text">Más de 10 puede generar lag o tirarte la conexión.</div>
        )}
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            Cancelar
          </button>
          <button type="button" className="btn btn-primary" onClick={() => onConfirm?.(n)}>
            Continuar
          </button>
        </div>
      </div>
    </div>
  );
}
