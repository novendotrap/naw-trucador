import { useEffect, useMemo, useState } from "react";
import ItemThumb from "./ItemThumb";
import SlotPreviewStage from "./SlotPreviewStage";
import { SLOT_FAMILIES, SLOT_GROUPS, SLOT_FAMILY_ICONS } from "../look/slots";

/**
 * Dos paneles flotantes: preview (izq) + selector de parte (der).
 * Un solo Ruffle dedicado — no toca el visor principal.
 */
export default function SlotSelectorModal({
  open,
  item, // { pack, name }
  look,
  onClose,
  onConfirm,
}) {
  const [pick, setPick] = useState(null); // { slot, familyId, label, layer }
  const [vizMode, setVizMode] = useState("object"); // object | worn
  const [withLook, setWithLook] = useState(true);

  useEffect(() => {
    if (!open) return;
    setPick(null);
    setVizMode("object");
    setWithLook(true);
  }, [open, item?.pack, item?.name]);

  const taken = look?.parts || {};
  const byId = useMemo(
    () => Object.fromEntries(SLOT_FAMILIES.map((f) => [f.id, f])),
    []
  );

  if (!open || !item) return null;

  const caption =
    vizMode === "object"
      ? "Así se ve el objeto"
      : pick
        ? withLook
          ? `En ${pick.label}${pick.layer > 1 ? ` · capa ${pick.layer}` : ""}, con el look`
          : `Solo en ${pick.label}${pick.layer > 1 ? ` · capa ${pick.layer}` : ""}`
        : "Tocá una parte para verla puesta";

  const selectSlot = (slot, familyId, label, layer) => {
    setPick({ slot, familyId, label, layer: Number(layer) || 1 });
    setVizMode("worn");
  };

  return (
    <div
      className="slot-modal-backdrop active app-no-drag"
      onClick={(e) => e.target === e.currentTarget && onClose?.()}
    >
      <div className="slot-dual">
        {/* Panel izquierdo: preview */}
        <aside className="slot-float slot-float-viz">
          <div className="slot-float-viz-head">
            <ItemThumb pack={item.pack} name={item.name} size={36} />
            <div className="slot-float-viz-meta">
              <div className="slot-float-viz-name mono">
                {item.pack}.{item.name}
              </div>
              <div className="slot-float-viz-hint">Preview</div>
            </div>
          </div>

          <div className="slot-preview-frame">
            <SlotPreviewStage
              item={item}
              mode={vizMode}
              look={look}
              pickSlot={pick?.slot || null}
              withLook={withLook}
            />
          </div>

          <div className="slot-viz-modes">
            <button
              type="button"
              className={`slot-viz-mode ${vizMode === "object" ? "active" : ""}`}
              onClick={() => setVizMode("object")}
            >
              Objeto
            </button>
            <button
              type="button"
              className={`slot-viz-mode ${vizMode === "worn" ? "active" : ""}`}
              onClick={() => {
                if (!pick) return;
                setVizMode("worn");
              }}
            >
              Puesto
            </button>
          </div>
          <div className="slot-viz-mix">
            <button
              type="button"
              className={`slot-viz-mode ${withLook ? "active" : ""}`}
              onClick={() => setWithLook(true)}
            >
              Con el look
            </button>
            <button
              type="button"
              className={`slot-viz-mode ${!withLook ? "active" : ""}`}
              onClick={() => setWithLook(false)}
            >
              Solo esto
            </button>
          </div>
          <div className="slot-viz-caption">{caption}</div>
        </aside>

        {/* Panel derecho: selector */}
        <section className="slot-float slot-float-picker">
          <div className="slot-modal-header">
            <div className="slot-modal-heading">
              <div>
                <div className="slot-modal-title">¿Dónde lo ponemos?</div>
                <div className="slot-modal-sub">
                  Poner “{item.name}”. Tocá la parte o el 1 / 2. Confirmá para dejarlo.
                </div>
              </div>
            </div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} style={{ fontSize: 20 }}>
              ×
            </button>
          </div>

          <div className="slot-grid-picker">
            {SLOT_GROUPS.map((group) => (
              <section
                key={group.id}
                className={`slot-family-group${group.wide ? " wide" : ""}`}
              >
                <div className="slot-family-group-title">{group.label}</div>
                <div className="slot-family-group-grid">
                  {group.families.map((famId) => {
                    const fam = byId[famId];
                    if (!fam) return null;
                    const previewing = pick?.familyId === fam.id;
                    return (
                      <div
                        key={fam.id}
                        className={`slot-pick-row${previewing ? " previewing" : ""}`}
                        onClick={() => selectSlot(fam.layers[0], fam.id, fam.label, 1)}
                      >
                        <div className="slot-pick-top">
                          <div
                            className={`slot-icon-badge ${fam.id}`}
                            dangerouslySetInnerHTML={{ __html: SLOT_FAMILY_ICONS[fam.id] || "" }}
                          />
                          <div className="slot-info">
                            <span className="slot-pick-code">{fam.label}</span>
                          </div>
                        </div>
                        <div className="slot-pick-actions">
                          <div className="slot-layer-group">
                            {fam.layers.map((slot, i) => {
                              const used = !!taken[slot];
                              const selected = pick?.slot === slot;
                              const tip = used
                                ? `Ya tiene ${String(taken[slot]).split(".").pop()}`
                                : `Probar capa ${i + 1}`;
                              return (
                                <button
                                  key={slot}
                                  type="button"
                                  className={`slot-layer-chip${used ? " used" : ""}${selected ? " selected" : ""}`}
                                  title={tip}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    selectSlot(slot, fam.id, fam.label, i + 1);
                                  }}
                                >
                                  {i + 1}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>

          <div className="slot-modal-footer">
            <span className="slot-modal-footer-hint">
              {pick
                ? `Listo para poner en ${pick.label}${pick.layer > 1 ? ` · capa ${pick.layer}` : ""}.`
                : "Tocá una parte para verla puesta."}
            </span>
            <div className="slot-modal-footer-actions">
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Cancelar
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!pick?.slot}
                onClick={() => onConfirm?.(pick)}
              >
                Confirmar
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
