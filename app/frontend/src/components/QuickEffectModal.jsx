import { useState, useMemo, useEffect } from "react";
import ItemThumb from "./ItemThumb";
import AnimPreviewStage from "./AnimPreviewStage";
import { Sparkles, Zap, Package, X, Check, HelpCircle } from "lucide-react";
import { parseItemParts } from "../look/effects";

export default function QuickEffectModal({
  open,
  effect = {},
  actions = [],
  onClose,
  onSave,
  busy = false,
  onClearBase,
  onClearSub,
  onClearProp,
  onSelectAction,
  onSetAction,
}) {
  const [searchAct, setSearchAct] = useState("");
  const [propFilter, setPropFilter] = useState("all"); // "all" | "with_prop" | "no_prop"
  const [selectedAction, setSelectedAction] = useState(effect.action || "kick");

  useEffect(() => {
    if (effect.action) {
      setSelectedAction(effect.action);
    }
  }, [effect.action]);

  const handleSelectAction = (actId) => {
    setSelectedAction(actId);
    onSelectAction?.(actId);
    onSetAction?.(actId);
  };

  const handleClearSub = () => {
    onClearSub?.();
    onClearProp?.();
  };

  const baseItem = effect.baseItem || (effect.basePack && effect.baseObj ? `${effect.basePack}.${effect.baseObj}` : "");
  const basePack = effect.basePack || (baseItem ? parseItemParts(baseItem).pack : "");
  const baseObj = effect.baseObj || (baseItem ? parseItemParts(baseItem).name : "");

  const subItem = effect.subItem || (effect.subPack && effect.subObj ? `${effect.subPack}.${effect.subObj}` : "");
  const subPack = effect.subPack || (subItem ? parseItemParts(subItem).pack : "");
  const subObj = effect.subObj || (subItem ? parseItemParts(subItem).name : "");

  const currentAction = actions.find((a) => a.id === selectedAction) || {
    id: selectedAction || "kick",
    name: selectedAction || "kick",
    label: selectedAction || "kick",
    takes_prop: Boolean(subItem),
  };

  const withPropCount = useMemo(() => actions.filter((a) => a.takes_prop).length, [actions]);
  const noPropCount = useMemo(() => actions.filter((a) => !a.takes_prop).length, [actions]);

  const filteredActions = useMemo(() => {
    let list = actions;
    if (propFilter === "with_prop") {
      list = list.filter((a) => a.takes_prop);
    } else if (propFilter === "no_prop") {
      list = list.filter((a) => !a.takes_prop);
    }

    if (searchAct.trim()) {
      const q = searchAct.toLowerCase().trim();
      list = list.filter(
        (a) =>
          (a.name && a.name.toLowerCase().includes(q)) ||
          (a.id && a.id.toLowerCase().includes(q)) ||
          (a.category && a.category.toLowerCase().includes(q))
      );
    }
    return list;
  }, [actions, propFilter, searchAct]);

  // Hooks must run in the same order when opening and closing the modal.
  if (!open) return null;

  const handleSave = () => {
    if (!baseItem) return;
    onSave?.({
      baseItem: baseItem,
      base_item: baseItem,
      basePack: basePack,
      baseObj: baseObj,
      action: selectedAction || effect.action || "kick",
      // Si la acción no lleva prop (sin manito), no enviamos objeto secundario
      subItem: currentAction.takes_prop ? subItem : "",
      sub_item: currentAction.takes_prop ? subItem : "",
      destination: "default",
      uses: effect.uses || 9999,
    });
  };

  return (
    <div
      className="modal-backdrop quick-look-backdrop"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="quick-look-card app-no-drag" style={{ maxWidth: 880, width: "95vw" }}>
        {/* Header */}
        <div className="quick-look-header" style={{ borderBottomColor: "rgba(251, 191, 36, 0.2)" }}>
          <div className="row" style={{ gap: 8 }}>
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: 8,
                background: "rgba(251, 191, 36, 0.15)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fbbf24",
              }}
            >
              <Sparkles size={16} />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, color: "#fff" }}>
                Configurar Efecto en Objeto
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>
                Crear consumible con animación y prop para mochila · by pika
              </div>
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        {/* Modal Body: 2 Columns */}
        <div
          className="quick-look-body"
          style={{
            display: "grid",
            gridTemplateColumns: "310px 1fr",
            gap: 16,
            maxHeight: "75vh",
            overflowY: "auto",
            padding: 16,
          }}
        >
          {/* Columna Izquierda: Visor de Animación + Objeto Base + Cantidad */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* Visor de Animación con Ruffle */}
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)", marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
                <span>VISTA PREVIA ANIMADA</span>
                <span style={{ color: "#818cf8", fontWeight: 700 }}>{currentAction.name || selectedAction}</span>
              </div>
              <AnimPreviewStage
                action={selectedAction}
                propItem={currentAction.takes_prop ? subItem : null}
                height={230}
              />
            </div>

            {/* 1. Objeto Base */}
            <div className="card" style={{ padding: 12, background: "rgba(255, 255, 255, 0.02)" }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                <span className="badge badge-accent" style={{ background: "rgba(245, 158, 11, 0.2)", color: "#fbbf24" }}>
                  1. OBJETO BASE (MOCHILA)
                </span>
                {baseObj && (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={onClearBase} style={{ fontSize: 11, height: 22, padding: "0 6px" }}>
                    Cambiar
                  </button>
                )}
              </div>
              {baseObj ? (
                <div className="quick-look-row" style={{ background: "rgba(0,0,0,0.3)", borderRadius: 10, padding: "10px 12px" }}>
                  <ItemThumb pack={basePack} name={baseObj} size={48} />
                  <div className="grow" style={{ marginLeft: 10 }}>
                    <div style={{ fontWeight: 600, color: "#fff" }}>{baseObj}</div>
                    <div className="mono" style={{ fontSize: 12, color: "var(--muted)" }}>
                      {basePack}.{baseObj}
                    </div>
                  </div>
                  <span className="badge" style={{ color: "#34d399", background: "rgba(16, 185, 129, 0.15)" }}>
                    Base 🎒
                  </span>
                </div>
              ) : (
                <div className="empty" style={{ padding: 10, textAlign: "left", fontSize: 11.5 }}>
                  ⚠️ Sin objeto base seleccionado. Tocá <strong>✨ Base Efecto</strong> en Objetos.
                </div>
              )}
            </div>

            {/* Destino Mochila & Cantidad */}
            <div className="card" style={{ padding: 10, background: "rgba(255, 255, 255, 0.02)" }}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <span style={{ fontSize: 10.5, color: "var(--muted)", display: "block" }}>Destino del truco:</span>
                  <div style={{ marginTop: 4 }}>
                    <span
                      className="badge"
                      style={{
                        background: "rgba(99, 102, 241, 0.16)",
                        color: "#a5b4fc",
                        border: "1px solid rgba(99, 102, 241, 0.3)",
                        fontSize: 11.5,
                        padding: "3px 10px",
                        fontWeight: 600,
                        gap: 5,
                      }}
                    >
                      🎒 Mochila
                    </span>
                  </div>
                </div>

              </div>
            </div>
          </div>

          {/* Columna Derecha: Selector de Acciones con Filtro + Prop (Punto 3 solo si lleva prop) */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* 2. Selector de Acción */}
            <div className="card" style={{ padding: 12, background: "rgba(255, 255, 255, 0.02)" }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                <span className="badge badge-accent" style={{ background: "rgba(99, 102, 241, 0.2)", color: "#a5b4fc" }}>
                  2. ACCIÓN O ANIMACIÓN
                </span>
                <span style={{ fontSize: 11, color: "var(--muted)" }}>
                  {filteredActions.length} de {actions.length} acciones
                </span>
              </div>

              {/* Botones de Filtrado: Todos / Con prop en mano / Sin prop */}
              <div className="row" style={{ gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  className={`btn btn-sm ${propFilter === "all" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setPropFilter("all")}
                  style={{
                    fontSize: 11,
                    height: 26,
                    padding: "0 10px",
                    background: propFilter === "all" ? "#4f46e5" : "rgba(255,255,255,0.05)",
                  }}
                >
                  Todos ({actions.length})
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${propFilter === "with_prop" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setPropFilter("with_prop")}
                  style={{
                    fontSize: 11,
                    height: 26,
                    padding: "0 10px",
                    background: propFilter === "with_prop" ? "#d97706" : "rgba(255,255,255,0.05)",
                    borderColor: propFilter === "with_prop" ? "#f59e0b" : "transparent",
                    color: propFilter === "with_prop" ? "#fff" : "#fbbf24",
                  }}
                >
                  🖐 Con prop en mano ({withPropCount})
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${propFilter === "no_prop" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setPropFilter("no_prop")}
                  style={{
                    fontSize: 11,
                    height: 26,
                    padding: "0 10px",
                    background: propFilter === "no_prop" ? "#0284c7" : "rgba(255,255,255,0.05)",
                    borderColor: propFilter === "no_prop" ? "#38bdf8" : "transparent",
                    color: propFilter === "no_prop" ? "#fff" : "#7dd3fc",
                  }}
                >
                  ⚡ Solo animación ({noPropCount})
                </button>
              </div>

              <div style={{ marginBottom: 8 }}>
                <input
                  type="text"
                  className="input input-sm"
                  placeholder="Buscar acción por nombre... ej: kick, football, eat, guitar, rayos..."
                  value={searchAct}
                  onChange={(e) => setSearchAct(e.target.value)}
                  style={{ width: "100%", fontSize: 12 }}
                />
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))",
                  gap: 6,
                  maxHeight: 180,
                  overflowY: "auto",
                  padding: 4,
                }}
              >
                {filteredActions.map((a) => {
                  const isSel = selectedAction === a.id;
                  const actionName = a.name || a.label || a.id;
                  return (
                    <button
                      key={a.id}
                      type="button"
                      className={`btn btn-sm ${isSel ? "btn-primary" : "btn-secondary"}`}
                      onClick={() => handleSelectAction(a.id)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        textAlign: "left",
                        fontSize: 11.5,
                        padding: "5px 8px",
                        position: "relative",
                        borderColor: isSel ? "#6366f1" : undefined,
                        background: isSel ? "#4f46e5" : undefined,
                      }}
                      title={`${actionName} (${a.category || ""}) ${a.takes_prop ? "- Permite objeto en mano" : ""}`}
                    >
                      <span className="grow" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: isSel ? 700 : 400 }}>
                        {actionName}
                      </span>
                      {a.takes_prop && (
                        <span title="Lleva objeto secundario en mano" style={{ fontSize: 12, marginLeft: 4 }}>
                          🖐
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 3. Prop / Objeto Secundario en Mano (SOLO SI LA ACCIÓN LLEVA PROP) */}
            {currentAction.takes_prop ? (
              <div className="card" style={{ padding: 12, background: "rgba(255, 255, 255, 0.02)" }}>
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                  <span className="badge badge-accent" style={{ background: "rgba(16, 185, 129, 0.2)", color: "#34d399" }}>
                    3. OBJETO EN MANO (PROP SECUNDARIO) 🖐
                  </span>
                  {subObj && (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={handleClearSub} style={{ fontSize: 11, height: 22, padding: "0 6px" }}>
                      Quitar
                    </button>
                  )}
                </div>
                {subObj ? (
                  <div className="quick-look-row" style={{ background: "rgba(0,0,0,0.3)", borderRadius: 10, padding: "10px 12px" }}>
                    <ItemThumb pack={subPack} name={subObj} size={48} />
                    <div className="grow" style={{ marginLeft: 10 }}>
                      <div style={{ fontWeight: 600, color: "#fff" }}>{subObj}</div>
                      <div className="mono" style={{ fontSize: 12, color: "var(--muted)" }}>
                        Pack: {subPack} · Se mostrará al ejecutar la acción
                      </div>
                    </div>
                    <span className="badge" style={{ color: "#a78bfa", background: "rgba(167, 139, 250, 0.15)" }}>
                      Prop en mano
                    </span>
                  </div>
                ) : (
                  <div className="empty" style={{ padding: 12, textAlign: "left", fontSize: 11.5 }}>
                    👉 Esta acción permite sostener un objeto secundario. Podés elegir uno en Objetos y tocar <strong>🖐 Prop Acción</strong>.
                  </div>
                )}
              </div>
            ) : null}

            {/* Resumen del Efecto */}
            <div
              style={{
                padding: "8px 12px",
                borderRadius: 8,
                background: "rgba(99, 102, 241, 0.08)",
                border: "1px solid rgba(99, 102, 241, 0.2)",
                fontSize: 12,
              }}
            >
              <div style={{ color: "var(--muted)", fontSize: 10.5, marginBottom: 2 }}>Resultado final:</div>
              <div className="mono" style={{ color: "#a5b4fc", fontWeight: 600 }}>
                {baseItem || "item"} → anim: <strong>{selectedAction}</strong>
                {currentAction.takes_prop && subItem ? ` + prop: ${subItem}` : ""}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="quick-look-footer" style={{ borderTopColor: "rgba(255,255,255,0.06)", display: "flex", justifyContent: "space-between" }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancelar
          </button>
          <div className="row" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!baseItem || busy}
              onClick={handleSave}
              style={{ background: "#4f46e5" }}
            >
              <Zap size={14} style={{ marginRight: 6 }} />
              Guardar y elegir cantidad
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
