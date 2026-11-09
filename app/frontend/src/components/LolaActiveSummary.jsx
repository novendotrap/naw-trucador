import ItemThumb from "./ItemThumb";

export default function LolaActiveSummary({ active, onRemoveItem, onClearItems, onRemoveGroup, busy = false }) {
  if (!active) return null;
  const groups = new Map();
  for (const item of active.items || []) {
    if (!groups.has(item.swf)) groups.set(item.swf, []);
    groups.get(item.swf).push(item);
  }
  const unitCount = (active.items || []).reduce((sum, item) => sum + item.qty, 0);
  return <section className="card lola-active-summary">
    <div className="card-title"><span>Preparado en Lola</span><div className="row"><span className="badge badge-accent">{active.label}</span>{onClearItems && !!active.items?.length && <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={onClearItems}>Vaciar preparados</button>}</div></div>
    <div className="card-sub">Abrí un archivo para ver o quitar sus objetos preparados.</div>
    {!!active.items?.length && <div className="trucar-muted">{groups.size} SWF · {active.items.length} objetos · {unitCount} unidades</div>}
    {active.actions?.map((action, i) => <div className="lola-active-action" key={i}><strong>{action.label}</strong><code>{action.target}</code></div>)}
    {[...groups].map(([swf, items]) => <div className="lola-pack" key={swf}>
      <details><summary><strong>{swf}.swf</strong><span className="trucar-muted">{items.length} objetos · {items.reduce((sum, item) => sum + item.qty, 0)} unidades</span><span className="lola-pack-hint btn btn-secondary btn-sm"><span className="lola-pack-show">Ver objetos</span><span className="lola-pack-hide">Ocultar objetos</span></span></summary>
        <div className="lola-pack-items">{items.map((item, i) => <div className="lola-active-item" key={item.name + i}><ItemThumb pack={item.swf} name={item.item} size={36}/><div className="grow"><strong>{item.item}</strong></div><span className="badge">×{item.qty}</span>{onRemoveItem && <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onRemoveItem(item.name)} aria-label={`Quitar ${item.name}`}>Quitar</button>}</div>)}</div>
      </details>
      {onRemoveGroup && <button type="button" className="btn btn-secondary btn-sm lola-pack-remove" disabled={busy} onClick={() => onRemoveGroup(items.map(item => item.name))} aria-label={`Quitar ${swf}.swf`}>Quitar SWF</button>}
    </div>)}
    {!active.items?.length && !active.actions?.length && <div className="trucar-muted">{active.kind === "behavior" ? "NPC con diálogo o lógica propia. Consultá el script en Lola." : "No hay objetos preparados. Podés consultar el script en Lola."}</div>}
  </section>;
}
