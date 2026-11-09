import { removePreparedItems, withoutSceneDeliveries, isDeliverableItem } from "../look/lolaPayload";
import LolaActiveSummary from "../components/LolaActiveSummary";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useToast } from "../hooks/useToast";
import ItemThumb from "../components/ItemThumb";

export default function LolaPage() {
  const toast = useToast();
  const [active, setActive] = useState(null);
  const [queue, setQueue] = useState([]);
  const [name, setName] = useState("");
  const [qty, setQty] = useState(1);
  const [payload, setPayload] = useState("");
  const [busy, setBusy] = useState(false);

  const loadPayload = async (syncEditor = true) => {
    try {
      let data = await api.getPayload();
      const clean = withoutSceneDeliveries(data.payload || "");
      if (clean !== data.payload) {
        await api.setPayload(clean);
        data = await api.getPayload();
      }
      setActive(data.active || null);
      if (syncEditor) setPayload(data.payload || "");
    } catch (e) {
      toast.error(e.message || "No se pudo cargar Lola");
    }
  };

  useEffect(() => {
    loadPayload();
    const changed = () => loadPayload(false);
    window.addEventListener("naw:lola-changed", changed);
    const timer = setInterval(() => { if (!document.hidden) loadPayload(false); }, 5000);
    return () => { clearInterval(timer); window.removeEventListener("naw:lola-changed", changed); };
  }, []);

  const removeActiveItems = async (itemName = null) => {
    if (busy) return;
    setBusy(true);
    try {
      // Work from the actual server payload, not the editable script/draft.
      const current = await api.getPayload();
      const next = removePreparedItems(current.payload || "", itemName ? (Array.isArray(itemName) ? itemName : [itemName]) : null);
      if (next !== current.payload) await api.setPayload(next);
      await loadPayload();
      toast.success(itemName ? "Objeto quitado de Lola" : "Objetos preparados vaciados");
    } catch (e) {
      toast.error(e.message || "No se pudieron quitar los objetos preparados");
    } finally {
      setBusy(false);
    }
  };

  const addItem = () => {
    const item = name.trim();
    if (!item || !item.includes(".")) {
      toast.error("Usá el formato pack.objeto");
      return;
    }
    if (!isDeliverableItem(item)) {
      toast.error("Las variantes _so están excluidas. Elegí el objeto sin ese sufijo.");
      return;
    }
    const amount = Math.max(1, parseInt(qty, 10) || 1);
    setQueue((q) => {
      const i = q.findIndex((x) => x.name === item);
      if (i >= 0) {
        const next = [...q];
        next[i] = { ...next[i], qty: next[i].qty + amount };
        return next;
      }
      const [swf, ...rest] = item.split(".");
      return [...q, { name: item, swf, item: rest.join("."), qty: amount }];
    });
    setName("");
    setQty(1);
    toast.success(`Agregado ${item}`);
  };

  const applyQueue = async () => {
    if (!queue.length) {
      toast.error("La cola está vacía");
      return;
    }
    setBusy(true);
    try {
      await api.setPayloadItems(queue);
      await loadPayload();
      toast.success("Cola lista en Lola");
    } catch (e) {
      toast.error(e.message || "Error al aplicar");
    } finally {
      setBusy(false);
    }
  };

  const saveRaw = async () => {
    setBusy(true);
    try {
      await api.setPayload(payload);
      await loadPayload();
      toast.success("Script guardado");
    } catch (e) {
      toast.error(e.message || "Error al guardar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <div>
        <div className="page-title">Lola</div>
        <div className="page-sub">Armá lo que te da Lola cuando le hablás en el juego.</div>
      </div>

      <LolaActiveSummary active={active} busy={busy} onRemoveItem={removeActiveItems} onClearItems={() => removeActiveItems()} onRemoveGroup={removeActiveItems} />
      <div className="grid-2">
        <div className="card">
          <div className="card-title">
            <span>Borrador de objetos</span>
            <span className="badge badge-accent">{queue.length}</span>
          </div>
          <div className="card-sub">Este borrador reemplaza la acción activa al pulsar Dejar listo para Lola. Formato: pack.objeto</div>

          <div className="lola-add-row">
            <div className="field-shell lola-name">
              <input
                className="field-control"
                placeholder="pack.objeto"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addItem()}
              />
            </div>
            <div className="field-shell lola-qty" title="Cantidad">
              <input
                className="field-control"
                type="number"
                min={1}
                max={99}
                value={qty}
                aria-label="Cantidad"
                onChange={(e) => setQty(e.target.value)}
              />
            </div>
            <button type="button" className="btn btn-secondary lola-add-btn" onClick={addItem}>
              + Agregar
            </button>
          </div>
          <div className="field-hint" style={{ marginBottom: 10 }}>
            SWF + nombre del símbolo
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Objeto</th>
                  <th>Cant.</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {!queue.length ? (
                  <tr>
                    <td colSpan={3} className="empty">
                      Todavía no hay nada.
                    </td>
                  </tr>
                ) : (
                  queue.map((it) => (
                    <tr key={it.name}>
                      <td>
                        <div className="row" style={{ gap: 10 }}>
                          <ItemThumb pack={it.swf} name={it.item} size={36} />
                          <span className="mono">{it.name}</span>
                        </div>
                      </td>
                      <td>x{it.qty}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => setQueue((q) => q.filter((x) => x.name !== it.name))}
                        >
                          Quitar
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="row" style={{ marginTop: 12, justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setQueue([])}>
              Vaciar
            </button>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={applyQueue}>
              Dejar listo para Lola
            </button>
          </div>
        </div>

        <div className="card">
          <div className="card-title">
            <span>Script activo</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={loadPayload}>
              Recargar
            </button>
          </div>
          <div className="card-sub">Casi nunca hace falta editarlo a mano.</div>
          <div className="field-shell" style={{ alignItems: "stretch" }}>
            <textarea
              className="field-control"
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
              rows={16}
            />
          </div>
          <div className="row" style={{ marginTop: 12, justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={saveRaw}>
              Guardar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
