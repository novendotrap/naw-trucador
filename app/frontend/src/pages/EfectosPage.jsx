import { useEffect, useState, useMemo } from "react";
import {
  Sparkles,
  Zap,
  Trash2,
  Check,
  Search,
  Package,
  Home,
  Briefcase,
  Flame,
  Layers,
  Info,
  RefreshCw,
  Plus,
} from "lucide-react";
import { api } from "../api/client";
import { useToast } from "../hooks/useToast";
import ItemThumb from "../components/ItemThumb";
import AnimPreviewStage from "../components/AnimPreviewStage";

const POPULAR_BASES = [
  { item: "food.banana", label: "Banana", pack: "food", obj: "banana" },
  { item: "food.apple", label: "Manzana", pack: "food", obj: "apple" },
  { item: "giftStore.carbon", label: "Carbón", pack: "giftStore", obj: "carbon" },
  { item: "giftStore.sprayRosa", label: "Spray Rosa", pack: "giftStore", obj: "sprayRosa" },
  { item: "toys.pelota", label: "Pelota", pack: "toys", obj: "pelota" },
  { item: "food.pizza", label: "Pizza", pack: "food", obj: "pizza" },
];

const POPULAR_PROPS = [
  "mundialClothes.petardo",
  "toys.pelota",
  "food.pizza",
  "food.banana",
  "catalogoRock.guitarra",
  "tools.rod",
  "paint.aerosol",
  "mundialClothes.bandera",
];

export default function EfectosPage({ effectDraft, setEffectDraft, onNavigateTab }) {
  const toast = useToast();
  const [actions, setActions] = useState([]);
  const [effects, setEffects] = useState([]);
  const [busy, setBusy] = useState(false);

  // Form states
  const [baseItem, setBaseItem] = useState("food.banana");
  const [selectedAction, setSelectedAction] = useState("kick");
  const [subItem, setSubItem] = useState("");
  const [destination, setDestination] = useState("default");
  const [uses, setUses] = useState(9999);
  const [autoOn, setAutoOn] = useState(true);
  const [qty, setQty] = useState(1);

  // Filters for action selector
  const [actionQuery, setActionQuery] = useState("");
  const [actionCategory, setActionCategory] = useState("all");
  const [propFilter, setPropFilter] = useState("all"); // "all" | "with_prop" | "no_prop"

  useEffect(() => {
    if (effectDraft?.baseItem) {
      setBaseItem(effectDraft.baseItem);
    }
    if (effectDraft?.action) {
      setSelectedAction(effectDraft.action);
    }
    if (effectDraft?.subItem !== undefined) {
      setSubItem(effectDraft.subItem);
    }
    if (effectDraft?.destination) {
      setDestination(effectDraft.destination);
    }
  }, [effectDraft]);

  const loadData = async () => {
    try {
      const [actData, effData] = await Promise.all([
        api.listActions().catch(() => ({ actions: [] })),
        api.listEffects().catch(() => ({ effects: [] })),
      ]);
      setActions(actData.actions || []);
      setEffects(effData.effects || []);
    } catch (e) {
      toast.error(e.message || "Error al cargar datos");
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Filter actions
  const categories = useMemo(() => {
    const cats = new Set(["all"]);
    actions.forEach((a) => {
      if (a.category) cats.add(a.category);
    });
    return Array.from(cats);
  }, [actions]);

  const withPropCount = useMemo(() => actions.filter((a) => a.takes_prop).length, [actions]);
  const noPropCount = useMemo(() => actions.filter((a) => !a.takes_prop).length, [actions]);

  const filteredActions = useMemo(() => {
    const q = actionQuery.toLowerCase().trim();
    return actions.filter((a) => {
      if (propFilter === "with_prop" && !a.takes_prop) return false;
      if (propFilter === "no_prop" && a.takes_prop) return false;
      if (actionCategory !== "all" && a.category !== actionCategory) return false;
      if (q && !a.name.toLowerCase().includes(q) && !(a.category || "").toLowerCase().includes(q))
        return false;
      return true;
    });
  }, [actions, actionQuery, actionCategory, propFilter]);

  const currentActionObj = useMemo(() => {
    return actions.find((a) => a.id === selectedAction) || { id: selectedAction, name: selectedAction };
  }, [actions, selectedAction]);

  // Compute full_action in real time
  const fullAction = useMemo(() => {
    const act = (selectedAction || "").trim();
    if (!currentActionObj.takes_prop) return act;
    let sub = (subItem || "").trim();
    if (!sub) return act;
    if (autoOn && !sub.endsWith("_on") && !sub.endsWith("_so")) {
      sub = `${sub}_on`;
    }
    return act.includes(".") ? act : `${act}.${sub}`;
  }, [selectedAction, subItem, autoOn, currentActionObj.takes_prop]);

  // Compute base parts
  const [basePack, baseObj] = useMemo(() => {
    const parts = (baseItem || "").split(".");
    return [parts[0] || "food", parts[1] || baseItem];
  }, [baseItem]);

  const handleSave = async (queueLola = true) => {
    if (!baseItem.trim() || !baseItem.includes(".")) {
      toast.error("El objeto base debe tener el formato pack.objeto (ej: food.banana)");
      return;
    }
    if (!selectedAction.trim()) {
      toast.error("Seleccioná una acción");
      return;
    }

    setBusy(true);
    try {
      const data = await api.saveEffect({
        base_item: baseItem.trim(),
        action: selectedAction.trim(),
        sub_item: currentActionObj.takes_prop ? subItem.trim() : "",
        destination: "default", // Siempre solo Mochila
        uses,
        qty,
        auto_on: autoOn,
        queue_lola: queueLola,
      });

      if (!data.ok) throw new Error(data.error || "No se pudo guardar el efecto");

      const lolaMsg = queueLola ? " ¡Listo para hablar con Lola!" : "";
      toast.success((data.message || "Efecto guardado.") + lolaMsg);
      await loadData();
    } catch (e) {
      toast.error(e.message || "Error al guardar el efecto");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (id) => {
    setBusy(true);
    try {
      const data = await api.deleteEffect(id);
      if (!data.ok) throw new Error(data.error || "No se pudo borrar");
      toast.success("Efecto eliminado");
      await loadData();
    } catch (e) {
      toast.error(e.message || "Error al borrar");
    } finally {
      setBusy(false);
    }
  };

  const handleQueueAll = async () => {
    setBusy(true);
    try {
      const data = await api.queueEffectsToLola();
      toast.success(data.message || "Efectos listos en Lola");
    } catch (e) {
      toast.error(e.message || "Error al sincronizar con Lola");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="page-title flex items-center gap-2">
            <Sparkles size={22} className="text-amber-400" />
            <span>Trucar Efectos</span>
            <span
              style={{
                fontSize: 12,
                color: "var(--muted)",
                fontWeight: 400,
                opacity: 0.75,
                marginLeft: 2,
              }}
            >
              by pika
            </span>
            <span className="badge badge-amber" style={{ fontSize: 12, verticalAlign: "middle" }}>
              {effects.length} creados
            </span>
          </div>
          <div className="page-sub">
            Crea consumibles con animaciones, bailes y props interactivos para la mochila o tu casa.
          </div>
        </div>
      </div>

      <div className="grid-2">
        {/* Editor Card */}
        <div className="card">
          <div className="card-title flex items-center gap-2">
            <Flame size={16} className="text-amber-400" />
            <span>Creador de Efecto</span>
          </div>
          <div className="card-sub">
            Combina un consumible base, la animación del avatar y un prop visual en mano.
          </div>

          <div className="stack" style={{ gap: 16, marginTop: 14 }}>
            {/* Visor de Animación SWF Ruffle */}
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)", marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
                <span>VISTA PREVIA ANIMADA</span>
                <span style={{ color: "#818cf8" }}>{selectedAction}</span>
              </div>
              <AnimPreviewStage
                action={selectedAction}
                propItem={currentActionObj.takes_prop ? subItem : null}
                height={220}
              />
            </div>

            {/* 1. Objeto Base */}
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#fff", display: "block", marginBottom: 6 }}>
                1. Objeto Base (Consumible en Mochila)
              </label>
              <div className="flex items-center gap-3">
                <ItemThumb pack={basePack} name={baseObj} size={42} />
                <div style={{ flex: 1 }}>
                  <input
                    type="text"
                    className="field-control mono"
                    placeholder="pack.objeto (ej: food.banana)"
                    value={baseItem}
                    onChange={(e) => {
                      setBaseItem(e.target.value);
                      setEffectDraft?.((prev) => ({ ...prev, baseItem: e.target.value }));
                    }}
                  />
                  {onNavigateTab && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      style={{ height: 38, fontSize: 12, padding: "0 10px", whiteSpace: "nowrap" }}
                      onClick={() => {
                        onNavigateTab("objetos");
                        toast.info("Elegí un objeto en el visor y tocá '✨ Base Efecto'");
                      }}
                      title="Explorar assets visualmente con miniaturas en el buscador"
                    >
                      🔍 Ver en Objetos
                    </button>
                  )}
                </div>
              </div>
              {/* Quick base pills */}
              <div className="flex flex-wrap gap-1" style={{ marginTop: 6 }}>
                <span style={{ fontSize: 11, color: "var(--muted)", alignSelf: "center", marginRight: 4 }}>
                  Sugeridos:
                </span>
                {POPULAR_BASES.map((b) => (
                  <button
                    key={b.item}
                    type="button"
                    className={`badge cursor-pointer ${baseItem === b.item ? "badge-amber" : ""}`}
                    onClick={() => setBaseItem(b.item)}
                    style={{ fontSize: 11, padding: "2px 6px" }}
                  >
                    {b.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 2. Selector de Acción */}
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#fff", display: "block", marginBottom: 6 }}>
                2. Acción del Avatar (de las 99 disponibles)
              </label>

              {/* Category pills */}
              <div className="flex flex-wrap gap-1" style={{ marginBottom: 8 }}>
                {categories.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`filter-pill ${actionCategory === c ? "active" : "inactive"}`}
                    onClick={() => setActionCategory(c)}
                    style={{ fontSize: 10, padding: "3px 8px" }}
                  >
                    {c === "all" ? "Todas" : c}
                  </button>
                ))}
              </div>

              {/* Action Search and Select */}
              <div className="flex gap-2">
                <input
                  type="text"
                  className="field-control"
                  placeholder="Buscar acción (kick, rayos, pedo, throw, etc.)..."
                  value={actionQuery}
                  onChange={(e) => setActionQuery(e.target.value)}
                  style={{ flex: 1, fontSize: 12 }}
                />
                <select
                  className="field-control mono"
                  value={selectedAction}
                  onChange={(e) => setSelectedAction(e.target.value)}
                  style={{ flex: 1.2, fontSize: 12 }}
                >
                  {filteredActions.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.category})
                    </option>
                  ))}
                </select>
              </div>

              {currentActionObj.takes_prop && (
                <div style={{ fontSize: 11, color: "#38bdf8", marginTop: 4 }} className="flex items-center gap-1">
                  <Info size={12} />
                  <span>Esta acción soporta prop/objeto en mano (paso 3).</span>
                </div>
              )}
            </div>

            {/* 3. Sub-Item / Prop (SOLO SI LA ACCIÓN LLEVA PROP) */}
            {currentActionObj.takes_prop && (
              <div style={{ padding: 12, background: "rgba(16, 185, 129, 0.04)", border: "1px solid rgba(16, 185, 129, 0.2)", borderRadius: 8 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#6ee7b7", display: "block", marginBottom: 6 }}>
                  3. Sub-Item / Prop dentro de la acción 🖐 (Requerido para esta acción)
                </label>
                <input
                  type="text"
                  className="field-control mono"
                  placeholder="pack.objeto (ej: mundialClothes.petardo o toys.pelota)"
                  value={subItem}
                  onChange={(e) => setSubItem(e.target.value)}
                />

                <div className="flex items-center justify-between" style={{ marginTop: 6 }}>
                  <div className="flex flex-wrap gap-1">
                    <span style={{ fontSize: 11, color: "var(--muted)", alignSelf: "center", marginRight: 4 }}>
                      Props sugeridos:
                    </span>
                    {POPULAR_PROPS.slice(0, 4).map((p) => (
                      <button
                        key={p}
                        type="button"
                        className={`badge cursor-pointer ${subItem === p ? "badge-cyan" : ""}`}
                        onClick={() => setSubItem(p)}
                        style={{ fontSize: 10, padding: "2px 6px" }}
                      >
                        {p.split(".")[1]}
                      </button>
                    ))}
                  </div>

                  <label className="flex items-center gap-1 cursor-pointer" style={{ fontSize: 11, color: "#94a3b8" }}>
                    <input
                      type="checkbox"
                      checked={autoOn}
                      onChange={(e) => setAutoOn(e.target.checked)}
                    />
                    <span>Auto "_on"</span>
                  </label>
                </div>
              </div>
            )}

            {/* Destino y Opciones */}
            <div className="grid-2" style={{ gap: 12 }}>
              <div>
                <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 4 }}>
                  Destino
                </label>
                <div style={{ marginTop: 4 }}>
                  <span
                    className="badge"
                    style={{
                      background: "rgba(99, 102, 241, 0.16)",
                      color: "#a5b4fc",
                      border: "1px solid rgba(99, 102, 241, 0.3)",
                      fontSize: 11.5,
                      padding: "4px 12px",
                      fontWeight: 600,
                      gap: 6,
                    }}
                  >
                    <Briefcase size={13} />
                    <span>Mochila</span>
                  </span>
                </div>
              </div>

              <div>
                <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 4 }}>
                  Cantidad para Lola
                </label>
                <input
                  type="number"
                  className="field-control"
                  min="1"
                  max="99"
                  value={qty}
                  onChange={(e) => setQty(Number(e.target.value) || 1)}
                />
              </div>
            </div>

            {/* Live Result Box */}
            <div
              style={{
                background: "rgba(0,0,0,0.35)",
                border: "1px solid rgba(251, 191, 36, 0.2)",
                borderRadius: 8,
                padding: "10px 14px",
              }}
            >
              <div style={{ fontSize: 11, color: "#fbbf24", fontWeight: 600, marginBottom: 4 }}>
                Atributo generado (full_action):
              </div>
              <div className="mono text-cyan-400" style={{ fontSize: 13, wordBreak: "break-all" }}>
                {fullAction}
              </div>
              <div style={{ fontSize: 10, color: "#64748b", marginTop: 4 }}>
                Lola inyectará:{" "}
                <code>
                  inventory.addOptions "{baseItem}" {qty} " " &#123;"{destination === "house" ? "useAction" : "attr_action"}":"{fullAction}", "uses":"9999"&#125;
                </code>
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-2" style={{ marginTop: 6 }}>
              <button
                type="button"
                className="btn btn-primary flex-1 flex items-center justify-center gap-2"
                disabled={busy}
                onClick={() => handleSave(true)}
              >
                <Zap size={14} />
                <span>Guardar y Dejar en Lola</span>
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => handleSave(false)}
              >
                Solo guardar
              </button>
            </div>
          </div>
        </div>

        {/* Saved Effects List */}
        <div className="card">
          <div className="card-title flex items-center justify-between">
            <span>Tus Efectos Guardados</span>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn btn-secondary btn-sm flex items-center gap-1"
                disabled={busy || !effects.length}
                onClick={handleQueueAll}
                title="Pone todos los efectos en la lista de entrega de Lola"
              >
                <Zap size={12} />
                <span>Dar todos a Lola</span>
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={loadData}>
                <RefreshCw size={12} />
              </button>
            </div>
          </div>
          <div className="card-sub">
            Hablá con Lola en el juego para recibir cualquiera de estos efectos.
          </div>

          <div className="list-scroll" style={{ maxHeight: 520, marginTop: 12 }}>
            {!effects.length ? (
              <div className="empty" style={{ padding: "40px 20px" }}>
                <Sparkles size={28} style={{ opacity: 0.3, margin: "0 auto 8px" }} />
                <div>Todavía no guardaste ningún efecto.</div>
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                  Configurá uno a la izquierda y hacé clic en "Guardar y Dejar en Lola".
                </div>
              </div>
            ) : (
              effects.map((eff) => {
                const bPack = eff.pack || "food";
                const bObj = eff.object || "banana";
                return (
                  <div key={eff.id} className="trick-row flex items-center justify-between" style={{ padding: 10 }}>
                    <div className="flex items-center gap-3" style={{ minWidth: 0, flex: 1 }}>
                      <ItemThumb pack={bPack} name={bObj} size={40} />
                      <div style={{ minWidth: 0 }}>
                        <div className="flex items-center gap-2">
                          <span className="mono" style={{ fontWeight: 600, color: "#fff", fontSize: 13 }}>
                            {eff.item}
                          </span>
                          <span className="badge badge-amber" style={{ fontSize: 10, padding: "1px 5px" }}>
                            {eff.inventory === "house" ? "Casa" : "Mochila"}
                          </span>
                          <span className="badge badge-accent" style={{ fontSize: 10, padding: "1px 5px" }}>
                            x{eff.qty || 1}
                          </span>
                        </div>
                        <div
                          className="mono text-cyan-400"
                          style={{ fontSize: 11, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                          title={eff.full_action}
                        >
                          ⚡ {eff.full_action}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        disabled={busy}
                        onClick={() => handleDelete(eff.id)}
                        title="Eliminar efecto"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
