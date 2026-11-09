import LolaActiveSummary from "../components/LolaActiveSummary";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useToast } from "../hooks/useToast";
import QtyModal from "../components/QtyModal";
import ConfirmModal from "../components/ConfirmModal";
import ItemThumb from "../components/ItemThumb";
import { requestPackThumbs } from "../components/RuffleStage";
import { emptyLook, SLOT_FAMILIES } from "../look/slots";

function normalizePartsInfo(t) {
  const fromApi = t?.parts_info && typeof t.parts_info === "object" ? { ...t.parts_info } : {};
  const parts = t?.parts || {};
  const rows = Array.isArray(t?.part_rows) ? t.part_rows : [];

  for (const row of rows) {
    if (!row?.slot) continue;
    if (fromApi[row.slot]?.name) continue;
    fromApi[row.slot] = {
      pack: row.pack || "",
      name: row.name || "",
      thumb: row.thumb || "",
    };
  }

  for (const [slot, val] of Object.entries(parts)) {
    if (fromApi[slot]?.name) continue;
    const raw = String(val || "");
    const bits = raw.split(".");
    const pack = bits.length > 1 ? bits[0] : t.pack || "";
    let name = bits.length > 1 ? bits.slice(1).join(".") : raw;
    if (name.endsWith("_on")) name = name.slice(0, -3);
    fromApi[slot] = { pack, name, thumb: "" };
  }
  return fromApi;
}

function ItemIdentity({ pack, name, size = 40 }) {
  return <div className="trucar-identity">
    <ItemThumb pack={pack} name={name} size={size} />
    <div className="trucar-item-text">
      <strong title={name}>{name || "Sin objeto"}</strong>
      <span>Archivo SWF <code title={pack}>{pack}.swf</code></span>
    </div>
  </div>;
}

function slotTitle(slot) {
  const family = SLOT_FAMILIES.find((f) => f.layers.includes(slot));
  return family ? `${family.label} · capa ${family.layers.indexOf(slot) + 1}` : slot;
}

export default function TrucarPage({ look, setLook, onOpenQuick, onTricksChange }) {
  const toast = useToast();
  const [activeLola, setActiveLola] = useState(null);
  const [tricks, setTricks] = useState([]);
  const [classes, setClasses] = useState([]);
  const [effects, setEffects] = useState([]);
  const [busy, setBusy] = useState(false);
  const [qtyOpen, setQtyOpen] = useState(false);
  const [confirmDel, setConfirmDel] = useState(null); // { pack, object, label, kind, effectId }

  const refresh = async () => {
    try {
      const [tricksRes, effectsRes, payloadRes] = await Promise.all([
        api.listTricks().catch(() => ({})),
        api.listEffects().catch(() => ({})),
        api.getPayload().catch(() => ({})),
      ]);
      setActiveLola(payloadRes.active || null);
      const nextTricks = tricksRes.tricks || [];
      const nextClasses = tricksRes.class_changes || [];
      const nextEffects = tricksRes.effects || effectsRes.effects || [];
      setTricks(nextTricks);
      setClasses(nextClasses);
      setEffects(nextEffects);
      onTricksChange?.();
      const packs = new Set();
      for (const t of nextTricks) if (t.pack) packs.add(t.pack);
      for (const c of nextClasses) if (c.pack) packs.add(c.pack);
      for (const e of nextEffects) if (e.pack) packs.add(e.pack);
      for (const p of packs) requestPackThumbs(p);
    } catch (e) {
      toast.error(e.message || "No se pudieron cargar trucos");
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const saveLook = async (qty) => {
    setQtyOpen(false);
    if (!look.baseSwf || !look.baseObj) {
      toast.error("Elegí un objeto base en Objetos");
      return;
    }
    if (!Object.keys(look.parts || {}).length) {
      toast.error("Agregá al menos una parte");
      return;
    }
    setBusy(true);
    try {
      const data = await api.trucarRopa({
        base_swf: look.baseSwf,
        base_object: look.baseObj,
        parts: look.parts,
        parts_info: look.partsInfo,
        auto_queue: true,
        qty,
      });
      if (!data.ok) throw new Error(data.error || "No se pudo guardar");
      toast.success(data.message || `Guardado · x${qty}`);
      setLook(emptyLook());
      await refresh();
    } catch (e) {
      toast.error(e.message || "Error al guardar");
    } finally {
      setBusy(false);
    }
  };

  const askDelete = (pack, obj, kind = "truco", effectId = null) => {
    setConfirmDel({
      pack,
      object: obj,
      label: `${pack}.${obj}`,
      kind,
      effectId,
    });
  };

  const doDelete = async () => {
    const row = confirmDel;
    setConfirmDel(null);
    if (!row) return;
    try {
      if (row.kind === "effect") {
        await api.deleteEffect(row.effectId || `${row.pack}.${row.object}`);
        toast.success("Efecto eliminado");
      } else if (row.kind === "class") {
        await api.deleteTrick(row.pack, row.object);
        toast.success("Cambio de clase sacado");
      } else {
        await api.deleteTrick(row.pack, row.object);
        toast.success("Truco eliminado");
      }
      refresh();
    } catch (e) {
      toast.error(e.message || "No se pudo borrar");
    }
  };

  const queueAll = async () => {
    setBusy(true);
    try {
      const data = await api.queueTricks({ all: true });
      await api.queueEffectsToLola().catch(() => {});
      toast.success(data.message || "Todo listo en Lola (ropa, clases y efectos)");
    } catch (e) {
      toast.error(e.message || "Error");
    } finally {
      setBusy(false);
    }
  };

  const loadTrick = (t) => {
    setLook({
      baseSwf: t.pack,
      baseObj: t.object,
      parts: t.parts || {},
      partsInfo: normalizePartsInfo(t),
      baseThumb: api.thumbUrl(t.pack, t.object),
    });
    toast.info(`Cargado ${t.item}`);
  };

  const openDetail = (t) => {
    loadTrick(t);
    onOpenQuick?.();
  };

  const total = tricks.length + effects.length + classes.length;
  const parts = Object.entries(look.parts || {});
  return (
    <div className="stack trucar-page">
      <header className="trucar-heading">
        <div><div className="page-title">Trucar <span className="badge badge-accent">{total} guardados</span></div>
          <div className="page-sub">Armá tu look y administrá la ropa, los efectos y los cambios de clase.</div></div>
        <button className="btn btn-secondary btn-sm" onClick={onOpenQuick} disabled={!look.baseObj && !parts.length}>Vista del look</button>
      </header>
      <div className="trucar-layout">
        <section className="card trucar-editor">
          <div className="card-title"><span>Look en edición</span><span className="badge">{parts.length} partes</span></div>
          <div className="card-sub">Elegí la base y agregá las partes desde Objetos.</div>
          <div className="trucar-base">
            <span className="stat-label">Objeto base</span>
            {look.baseObj ? <ItemIdentity pack={look.baseSwf} name={look.baseObj} size={48} /> : <div className="trucar-muted">Todavía no elegiste una base.</div>}
          </div>
          <div className="table-wrap trucar-parts-wrap">
            <table className="trucar-parts">
              <thead><tr><th>Parte del look</th><th>Objeto</th><th>Archivo SWF</th></tr></thead>
              <tbody>{!parts.length ? <tr><td colSpan={3} className="empty">Agregá una parte desde Objetos → Poner en look.</td></tr> : parts.map(([slot, value]) => {
                const info = look.partsInfo?.[slot] || {};
                const raw = String(value).split(".");
                const pack = info.pack || (raw.length > 1 ? raw[0] : look.baseSwf);
                const name = (info.name || (raw.length > 1 ? raw.slice(1).join(".") : raw[0])).replace(/_on$/, "");
                return <tr key={slot}><td><span className="trucar-slot">{slotTitle(slot)}</span></td>
                  <td><div className="trucar-part-object"><ItemThumb pack={pack} name={name} size={34}/><span title={name}>{name}</span></div></td>
                  <td><code title={pack}>{pack}.swf</code></td></tr>;
              })}</tbody>
            </table>
          </div>
          <footer className="trucar-editor-footer"><span className="trucar-muted">Guardalo para prepararlo en Lola.</span>
            <button className="btn btn-primary btn-sm" disabled={busy || !look.baseObj || !parts.length} onClick={() => setQtyOpen(true)}>{busy ? "Guardando..." : "Guardar truco"}</button></footer>
        </section>
        <section className="card trucar-saved">
          <div className="card-title"><span>Tus trucos <span className="badge">{total}</span></span><div className="row">
            <button className="btn btn-secondary btn-sm" disabled={busy || !total} onClick={queueAll}>Preparar todos en Lola</button>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={refresh}>Actualizar</button></div></div>
          <section className="trucar-group"><div className="trucar-group-heading"><h3>Looks de ropa</h3><span className="badge">{tricks.length}</span></div>
            {!tricks.length ? <div className="trucar-empty">Tus looks guardados van a aparecer acá.</div> : tricks.map((t) => <div className="trucar-saved-row" key={t.id || t.item}>
              <button className="trucar-load" onClick={() => loadTrick(t)} title="Cargar en el editor"><ItemIdentity pack={t.pack} name={t.object}/></button>
              <div className="trick-row-meta"><span className="badge">{t.parts_count || Object.keys(t.parts || {}).length} partes</span><span className="badge badge-accent">×{t.qty || 1}</span></div>
              <div className="trick-row-actions"><button className="btn btn-secondary btn-sm" onClick={() => openDetail(t)}>Ver</button><button className="btn btn-danger btn-sm" onClick={() => askDelete(t.pack,t.object)}>Borrar</button></div>
            </div>)}</section>
          <section className="trucar-group"><div className="trucar-group-heading"><h3>Objetos con efecto <span className="trucar-credit">by pika</span></h3><span className="badge">{effects.length}</span></div>
            {!effects.length ? <div className="trucar-empty">Creá uno desde Objetos → Base Efecto.</div> : effects.map((e) => {
              const pack = e.pack || String(e.item || "").split(".")[0]; const name = e.object || String(e.item || "").split(".").pop();
              return <div className="trucar-saved-row" key={e.id || e.item}><div className="trucar-item-text"><ItemIdentity pack={pack} name={name}/>
                <div className="trucar-effect-meta"><span>Acción <code>{e.action}</code></span>{e.sub_item && <span>Objeto en mano <code>{e.sub_item}</code></span>}</div></div>
                <span className="badge badge-accent">×{e.qty || 1}</span><button className="btn btn-danger btn-sm" onClick={() => askDelete(pack,name,"effect",e.id)}>Borrar</button></div>;
            })}</section>
          <section className="trucar-group"><div className="trucar-group-heading"><h3>Cambios de clase</h3><span className="badge">{classes.length}</span></div>
            {!classes.length ? <div className="trucar-empty">Todavía no cambiaste la clase de un objeto.</div> : classes.map((c) => <div className="trucar-saved-row" key={c.id || c.item}><div className="trucar-item-text"><ItemIdentity pack={c.pack} name={c.object || String(c.item || "").split(".").pop()}/><div className="trucar-effect-meta"><span>Clase <code>{c.mambo_class}</code></span>{c.inventory_label && <span>{c.inventory_label}</span>}</div></div>
              <span className="badge badge-accent">×{c.qty || 1}</span><button className="btn btn-danger btn-sm" onClick={() => askDelete(c.pack,c.object,"class")}>Borrar</button></div>)}</section>
        </section>
      </div>

      <LolaActiveSummary active={activeLola} />
      <QtyModal
        open={qtyOpen}
        title="¿Cuántos querés?"
        message={`Lola te va a dar ${look.baseObj || "el objeto"} xN. Recomendado: 1.`}
        onCancel={() => setQtyOpen(false)}
        onConfirm={saveLook}
      />
      <ConfirmModal
        open={!!confirmDel}
        title={
          confirmDel?.kind === "class"
            ? "Sacar cambio de clase"
            : confirmDel?.kind === "effect"
            ? "Borrar truco de efecto"
            : "Borrar truco"
        }
        message={
          confirmDel
            ? confirmDel.kind === "class"
              ? `¿Sacar ${confirmDel.label}? Vuelve a la clase original del pack.`
              : confirmDel.kind === "effect"
              ? `¿Borrar el efecto de ${confirmDel.label}?`
              : `¿Borrar ${confirmDel.label}?`
            : ""
        }
        confirmLabel="Borrar"
        danger
        onCancel={() => setConfirmDel(null)}
        onConfirm={doDelete}
      />
    </div>
  );
}
