import GaturroVisualizer from "./GaturroVisualizer";
import ItemThumb from "./ItemThumb";

export default function QuickLookModal({
  open,
  look,
  onClose,
  onSave,
  onClear,
  onRemovePart,
  onClearBase,
  busy,
}) {
  if (!open) return null;
  const parts = Object.entries(look.parts || {});
  const hasBase = !!(look.baseSwf && look.baseObj);

  return (
    <div className="modal-backdrop quick-look-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="quick-look-card app-no-drag">
        <div className="quick-look-header">
          <div>
            <div className="modal-title">Look activo</div>
            <div className="modal-sub">
              {hasBase ? "1 base" : "0 base"} · {parts.length} parte{parts.length === 1 ? "" : "s"}
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="quick-look-body">
          <div className="quick-look-viz">
            <div className="card-title" style={{ fontSize: 12 }}>Gaturro</div>
            <GaturroVisualizer look={look} height={300} />
          </div>

          <div className="quick-look-list">
            <div className="card-sub" style={{ marginBottom: 8 }}>Base</div>
            {hasBase ? (
              <div className="quick-look-row">
                <ItemThumb pack={look.baseSwf} name={look.baseObj} size={44} />
                <div className="grow">
                  <span className="badge badge-accent">BASE</span>
                  <div className="mono" style={{ fontSize: 12, marginTop: 4 }}>
                    {look.baseSwf}.{look.baseObj}
                  </div>
                </div>
                <button type="button" className="btn btn-ghost btn-sm" onClick={onClearBase}>
                  ×
                </button>
              </div>
            ) : (
              <div className="empty" style={{ padding: 12 }}>Sin base. En Objetos → Usar de base.</div>
            )}

            <div className="card-sub" style={{ margin: "14px 0 8px" }}>Partes</div>
            {!parts.length ? (
              <div className="empty" style={{ padding: 12 }}>Sin partes. En Objetos → Poner en el look.</div>
            ) : (
              parts.map(([slot, val]) => {
                const info = look.partsInfo?.[slot] || {};
                const pack = info.pack || String(val).split(".")[0];
                const name = info.name || String(val).split(".").slice(1).join(".");
                return (
                  <div key={slot} className="quick-look-row">
                    <ItemThumb pack={pack} name={name} size={40} />
                    <div className="grow">
                      <span className="badge">{slot}</span>
                      <div className="mono" style={{ fontSize: 12, marginTop: 4 }}>
                        {pack}.{name}
                      </div>
                    </div>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => onRemovePart(slot)}>
                      ×
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="modal-actions" style={{ justifyContent: "space-between" }}>
          <button type="button" className="btn btn-secondary" onClick={onClear}>
            Vaciar look
          </button>
          <div className="row">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cerrar
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !hasBase || !parts.length}
              onClick={onSave}
            >
              {busy ? "Guardando..." : "Guardar truco"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
