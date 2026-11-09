import { portalDestinations, buildPortalPayload } from "../look/lolaPayload";
import { useEffect, useState, useMemo, useRef } from "react";
import {
  Store,
  ShoppingBag,
  DoorOpen,
  Image as ImageIcon,
  User,
  Sparkles,
  Code2,
  Copy,
  Check,
  Search,
  Zap,
  X,
  SlidersHorizontal,
  RotateCcw,
  Terminal,
  ExternalLink,
  Layers,
  FileCode,
  Tag,
  Package,
} from "lucide-react";
import { api } from "../api/client";
import { useToast } from "../hooks/useToast";
import Field from "../components/Field";

const TYPE_CONFIG = {
  catalog: { label: "Catálogos", icon: ShoppingBag, color: "#38bdf8", badge: "badge-cyan" },
  vendor: { label: "Vendedores", icon: Store, color: "#34d399", badge: "badge-green" },
  npc: { label: "NPCs", icon: User, color: "#818cf8", badge: "badge-blue" },
  portal: { label: "Portales", icon: DoorOpen, color: "#c084fc", badge: "badge-purple" },
  banner: { label: "Banners", icon: ImageIcon, color: "#fbbf24", badge: "badge-amber" },
};

const hasPortalDestination = (item) => item?.type === "portal" && portalDestinations(item.script || "").length > 0;
const canActivateInLola = (item) => item?.type !== "npc" && (item?.type !== "portal" || hasPortalDestination(item));

export default function TiendasPage() {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [activeType, setActiveType] = useState("all");
  const [behaviors, setBehaviors] = useState([]);
  const [counts, setCounts] = useState({ all: 0, catalog: 0, vendor: 0, npc: 0, portal: 0, banner: 0 });
  const [busy, setBusy] = useState(false);
  const [scriptModal, setScriptModal] = useState(null);
  const [modalScriptText, setModalScriptText] = useState("");
  const [originalScriptText, setOriginalScriptText] = useState("");
  const [copied, setCopied] = useState(false);

  const textareaRef = useRef(null);
  const gutterRef = useRef(null);

  const load = async (query = q, type = activeType) => {
    try {
      const data = await api.listBehaviors(query, type === "all" ? "" : type);
      setBehaviors(data.behaviors || data.tiendas || []);
      if (data.counts) {
        setCounts(data.counts);
      }
    } catch (e) {
      toast.error(e.message || "No se pudieron cargar los behaviors");
    }
  };

  useEffect(() => {
    load(q, activeType);
  }, [activeType]);

  const handleSearchSubmit = (e) => {
    e?.preventDefault();
    load(q, activeType);
  };

  const activateCatalog = async (catalogName, label) => {
    setBusy(true);
    try {
      const data = await api.activateBehavior({ catalog: catalogName });
      if (!data.ok) throw new Error(data.error || "Falló la activación");
      toast.success(data.message);
    } catch (e) {
      toast.error(e.message || "Error al activar catálogo");
    } finally {
      setBusy(false);
    }
  };

  const activateFullBehavior = async (item) => {
    if (!canActivateInLola(item)) return;
    setBusy(true);
    try {
      const body = item.type === "portal"
        ? { script: buildPortalPayload(item.script) }
        : { behavior: item.behavior || item.id, catalog: item.catalogs?.[0] || "" };
      const data = await api.activateBehavior(body);
      if (!data.ok) throw new Error(data.error || "Falló la activación");
      toast.success(item.type === "portal" ? "Portal preparado. Abrí MG aplicado y hablá con Lola para viajar." : data.message || `Behavior "${item.title || item.behavior}" listo en Lola.`);
    } catch (e) {
      toast.error(e.message || "Error al activar behavior");
    } finally {
      setBusy(false);
    }
  };

  const openScriptViewer = (item) => {
    let script = item.script || "";
    if (!script && item.catalogs?.length) {
      const primary = item.catalogs[0];
      script = `initial: DO\r\n    on activate openCat\r\n\r\nINICIO: DO\r\n    on activate openCat\r\n\r\nopenCat: DO\r\n    catalog ${primary}\r\n    goto initial\r\n`;
    }
    setModalScriptText(script);
    setOriginalScriptText(script);
    setScriptModal(item);
    setCopied(false);
  };

  const handleCopyScript = () => {
    if (!modalScriptText) return;
    navigator.clipboard?.writeText(modalScriptText);
    setCopied(true);
    toast.success("Script copiado al portapapeles");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleResetScript = () => {
    setModalScriptText(originalScriptText);
    toast.info("Script restablecido al original");
  };

  const handleInjectCustomScript = async () => {
    if (!modalScriptText.trim() || !canActivateInLola(scriptModal)) return;
    setBusy(true);
    try {
      const data = await api.activateBehavior({ script: modalScriptText });
      if (!data.ok) throw new Error(data.error || "Falló la inyección");
      toast.success(data.message);
      setScriptModal(null);
    } catch (e) {
      toast.error(e.message || "Error al inyectar script");
    } finally {
      setBusy(false);
    }
  };

  // Sync scrolling between code textarea and line gutter
  const handleTextareaScroll = () => {
    if (textareaRef.current && gutterRef.current) {
      gutterRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  };

  const lineCount = useMemo(() => {
    if (!modalScriptText) return 1;
    return modalScriptText.split("\n").length;
  }, [modalScriptText]);

  return (
    <div className="stack">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="page-title flex items-center gap-2">
            <span>Behaviors & Tiendas</span>
            <span className="badge badge-cyan" style={{ fontSize: 12, verticalAlign: "middle" }}>
              {counts.all || behaviors.length} disponibles
            </span>
          </div>
          <div className="page-sub">
            Activá una acción, abrí MG aplicado y hablá con Lola. El look en edición no se guarda. Los portales con destino explícito preparan un viaje al hablar con Lola. Los NPCs y los portales sin destino conocido quedan para consulta.
          </div>
        </div>
      </div>

      {/* Main card */}
      <div className="card">
        {/* Type Filter Pills */}
        <div className="filter-pills-bar">
          <button
            type="button"
            className={`filter-pill ${activeType === "all" ? "active" : "inactive"}`}
            onClick={() => setActiveType("all")}
          >
            Todos ({counts.all || behaviors.length})
          </button>
          {Object.entries(TYPE_CONFIG).map(([tKey, cfg]) => {
            const Icon = cfg.icon;
            const active = activeType === tKey;
            const count = counts[tKey] ?? 0;
            return (
              <button
                key={tKey}
                type="button"
                className={`filter-pill ${active ? "active" : "inactive"}`}
                onClick={() => setActiveType(tKey)}
                style={active ? {} : { color: cfg.color }}
              >
                <Icon size={14} style={{ marginRight: 4 }} />
                {cfg.label} ({count})
              </button>
            );
          })}
        </div>

        {/* Search Toolbar */}
        <form onSubmit={handleSearchSubmit} className="row" style={{ marginBottom: 14, alignItems: "center" }}>
          <div style={{ flex: 1 }}>
            <Field
              type="search"
              icon="search"
              placeholder="Buscar por catálogo, behavior, nombre, temática o ítem (ej: zero3, crumbl, aesthetic, barbijo)..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-secondary" style={{ height: 40, whiteSpace: "nowrap" }}>
            Buscar
          </button>
          {q && (
            <button
              type="button"
              className="btn btn-ghost"
              style={{ height: 40 }}
              onClick={() => {
                setQ("");
                load("", activeType);
              }}
            >
              Limpiar
            </button>
          )}
        </form>

        {/* Table */}
        <div className="table-wrap" style={{ maxHeight: "calc(100vh - 280px)" }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 110 }}>Tipo</th>
                <th>Nombre / Descripción</th>
                <th>Behavior (.npc)</th>
                <th>Catálogo(s)</th>
                <th style={{ width: 220, textAlign: "right" }}>Acción</th>
              </tr>
            </thead>
            <tbody>
              {!behaviors.length ? (
                <tr>
                  <td colSpan={5} className="empty" style={{ padding: "40px 20px", textAlign: "center" }}>
                    No se encontraron behaviors con ese criterio.
                  </td>
                </tr>
              ) : (
                behaviors.map((b) => {
                  const btype = b.type || "catalog";
                  const cfg = TYPE_CONFIG[btype] || TYPE_CONFIG.catalog;
                  const TypeIcon = cfg.icon;
                  const primaryCat = b.catalogs && b.catalogs[0];

                  return (
                    <tr key={b.id || b.behavior}>
                      {/* Tipo */}
                      <td>
                        <span
                          className={`badge ${cfg.badge} flex items-center gap-1`}
                          style={{ width: "fit-content", padding: "3px 7px", fontSize: 11 }}
                        >
                          <TypeIcon size={12} />
                          {cfg.label}
                        </span>
                      </td>

                      {/* Nombre y descripción */}
                      <td>
                        <div style={{ fontWeight: 600, color: "#fff", fontSize: 13 }} className="flex items-center gap-2">
                          <span>{b.title || b.name || b.behavior}</span>
                          {b.items_count > 0 && (
                            <span
                              className="badge badge-purple"
                              style={{ fontSize: 10, padding: "1px 6px", fontWeight: 500 }}
                              title={`${b.items_count} ítems en este catálogo`}
                            >
                              {b.items_count} ítems
                            </span>
                          )}
                        </div>
                        {b.desc && (
                          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                            {b.desc}
                          </div>
                        )}
                        {b.category && (
                          <span
                            style={{
                              display: "inline-block",
                              fontSize: 10,
                              color: "#94a3b8",
                              background: "rgba(255,255,255,0.05)",
                              padding: "1px 6px",
                              borderRadius: 4,
                              marginTop: 4,
                            }}
                          >
                            {b.category}
                          </span>
                        )}
                      </td>

                      {/* Behavior path */}
                      <td>
                        <code className="mono text-cyan-400 behavior-copyable" style={{ fontSize: 11 }}>
                          {b.behavior}
                        </code>
                      </td>

                      {/* Catálogos */}
                      <td>
                        {b.catalogs && b.catalogs.length > 0 ? (
                          <div className="flex flex-wrap gap-2">
                            {b.catalogs.map((cat) => (
                              <button
                                key={cat}
                                type="button"
                                className="badge badge-cyan mono cursor-pointer hover:bg-cyan-900/60 transition"
                                title={`Hacer clic para activar catálogo "${cat}" en Lola`}
                                disabled={busy || !canActivateInLola(b)}
                                onClick={() => activateCatalog(cat, b.title)}
                                style={{ border: "1px solid rgba(56, 189, 248, 0.3)", padding: "3px 8px", fontSize: 11 }}
                              >
                                {cat}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <span style={{ fontSize: 11, color: "var(--muted)" }}>—</span>
                        )}
                      </td>

                      {/* Acciones */}
                      <td style={{ textAlign: "right" }}>
                        <div className="flex items-center justify-end gap-1">
                          {canActivateInLola(b) && (primaryCat ? (
                            <button
                              type="button"
                              className="btn btn-primary btn-sm flex items-center gap-1"
                              disabled={busy}
                              onClick={() => activateCatalog(primaryCat, b.title)}
                              title={`Activar catálogo "${primaryCat}" para abrirlo hablando con Lola`}
                            >
                              <Zap size={12} />
                              Activar en Lola
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="btn btn-primary btn-sm flex items-center gap-1"
                              disabled={busy}
                              onClick={() => activateFullBehavior(b)}
                              title={`Activar script completo de "${b.title || b.behavior}" en Lola`}
                            >
                              <Zap size={12} />
                              {b.type === "portal" ? "Preparar portal en Lola" : "Cargar en Lola"}
                            </button>
                          ))}

                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => openScriptViewer(b)}
                            title="Ver script ActionScript / Trucar behavior"
                          >
                            <Code2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal Script Viewer / Inspector Futurista */}
      {scriptModal && (
        <div className="slot-modal-backdrop" onClick={() => setScriptModal(null)}>
          <div
            className="cyber-modal-card"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Top Glowing Cyber Line */}
            <div className="cyber-modal-top-accent" />

            {/* Header */}
            <div className="cyber-modal-header">
              <div>
                <div className="cyber-badge-engine">
                  <span className="cyber-badge-dot" />
                  <span>MG ENGINE // AS3.0 NPC PROTOCOL</span>
                </div>
                <h3 className="cyber-modal-title">
                  {scriptModal.title || scriptModal.behavior}
                </h3>
                <div className="cyber-modal-sub">
                  {canActivateInLola(scriptModal) ? (scriptModal.type === "portal" ? "Prepara el salto directo a las salas indicadas, sin condiciones de misión. Si hay varios destinos, Lola te permite elegir." : "Consultá, copiá o editá el script del behavior.") : "Solo consulta y copia. Este NPC o portal depende del contexto del juego y no se activa desde Lola."}
                </div>
              </div>

              {/* Close Button */}
              <button
                type="button"
                className="cyber-btn-close"
                onClick={() => setScriptModal(null)}
                title="Cerrar modal"
              >
                <X size={15} />
              </button>
            </div>

            {/* Meta Strip */}
            <div className="cyber-meta-strip">
              {/* Type pill */}
              {(() => {
                const cfg = TYPE_CONFIG[scriptModal.type] || TYPE_CONFIG.catalog;
                const Icon = cfg.icon;
                return (
                  <span className={`badge ${cfg.badge} flex items-center gap-1`} style={{ fontSize: 11 }}>
                    <Icon size={12} />
                    {cfg.label}
                  </span>
                );
              })()}

              {/* Behavior code */}
              <span className="badge badge-neutral mono behavior-copyable" style={{ fontSize: 11, color: "#38bdf8" }}>
                {scriptModal.behavior}
              </span>

              {/* Catalogs info */}
              {scriptModal.catalogs?.length > 0 && (
                <span className="badge badge-cyan mono" style={{ fontSize: 11 }}>
                  Catálogo: {scriptModal.catalogs.join(", ")}
                </span>
              )}

              {/* Items count */}
              {scriptModal.items_count > 0 && (
                <span className="badge badge-purple" style={{ fontSize: 11 }}>
                  {scriptModal.items_count} ítems disponibles
                </span>
              )}

              {/* Category */}
              {scriptModal.category && (
                <span
                  style={{
                    fontSize: 10,
                    color: "#94a3b8",
                    background: "rgba(255,255,255,0.06)",
                    padding: "2px 8px",
                    borderRadius: 4,
                  }}
                >
                  {scriptModal.category}
                </span>
              )}
            </div>

            {/* Futuristic Terminal IDE Frame */}
            <div className="cyber-terminal">
              {/* Terminal Chrome Bar */}
              <div className="cyber-terminal-header">
                <div className="flex items-center">
                  <div className="cyber-traffic-lights">
                    <span className="cyber-light" style={{ background: "#ef4444" }} />
                    <span className="cyber-light" style={{ background: "#eab308" }} />
                    <span className="cyber-light" style={{ background: "#22c55e" }} />
                  </div>
                  <span className="cyber-terminal-file">
                    {scriptModal.behavior.split("/").pop()}.npc
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 10,
                      color: "#64748b",
                      padding: "2px 6px",
                      borderRadius: 4,
                      background: "rgba(255,255,255,0.04)",
                    }}
                  >
                    {lineCount} líneas
                  </span>

                  {modalScriptText !== originalScriptText && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm flex items-center gap-1"
                      onClick={handleResetScript}
                      style={{ height: 26, fontSize: 11, padding: "0 8px" }}
                      title="Restablecer script original"
                    >
                      <RotateCcw size={11} />
                      <span>Resetear</span>
                    </button>
                  )}

                  <button
                    type="button"
                    className="btn btn-ghost btn-sm flex items-center gap-1"
                    onClick={handleCopyScript}
                    style={{ height: 26, fontSize: 11, padding: "0 8px" }}
                  >
                    {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                    <span>{copied ? "Copiado" : "Copiar"}</span>
                  </button>
                </div>
              </div>

              {/* Code Editor Body with Line Numbers */}
              <div className="cyber-code-body">
                <div ref={gutterRef} className="cyber-code-gutter">
                  {Array.from({ length: lineCount }, (_, i) => (
                    <div key={i + 1}>{i + 1}</div>
                  ))}
                </div>

                <textarea
                  ref={textareaRef}
                  value={modalScriptText}
                  onChange={(e) => setModalScriptText(e.target.value)}
                  onScroll={handleTextareaScroll}
                  rows={Math.max(10, Math.min(lineCount, 18))}
                  className="cyber-code-textarea"
                  spellCheck={false}
                  placeholder="Código ActionScript / NPC..."
                />
              </div>
            </div>

            {/* Sample items preview if catalog items are known */}
            {scriptModal.items_sample && scriptModal.items_sample.length > 0 && (
              <div
                style={{
                  padding: "4px 22px 14px",
                  display: "flex",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: 8,
                }}
              >
                <span style={{ fontSize: 11, color: "var(--muted)", marginRight: 4 }}>
                  Ítems de muestra:
                </span>
                {scriptModal.items_sample.map((item) => (
                  <span
                    key={item}
                    className="badge badge-neutral mono behavior-copyable"
                    style={{ fontSize: 10, padding: "2px 7px" }}
                  >
                    {item}
                  </span>
                ))}
                {scriptModal.items_count > scriptModal.items_sample.length && (
                  <span style={{ fontSize: 10, color: "var(--muted)", marginLeft: 2 }}>
                    +{scriptModal.items_count - scriptModal.items_sample.length} más...
                  </span>
                )}
              </div>
            )}

            {/* Footer */}
            <div className="cyber-modal-footer">
              <div className="cyber-status-text">
                <span className="cyber-status-dot" />
                <span>{canActivateInLola(scriptModal) ? "LOLA PROXY // SCRIPT" : "NPC / PORTAL // SOLO CONSULTA"}</span>
              </div>

              <div className="cyber-modal-actions">
                <button
                  type="button"
                  className="cyber-btn-secondary"
                  onClick={() => setScriptModal(null)}
                >
                  Cerrar
                </button>
                {canActivateInLola(scriptModal) && <button
                  type="button"
                  className="cyber-btn-inject"
                  disabled={busy}
                  onClick={() => scriptModal.type === "portal" ? activateFullBehavior(scriptModal) : handleInjectCustomScript()}
                >
                  <Zap size={14} />
                  <span>{scriptModal.type === "portal" ? "Preparar portal en Lola" : "Inyectar este script en Lola"}</span>
                </button>}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}