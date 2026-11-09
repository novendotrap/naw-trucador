import ItemThumb from "./ItemThumb";
import { getCachedThumb } from "../thumbs/bridge";
import { api } from "../api/client";
import { lookHasContent } from "../look/slots";

export default function FloatingLookPill({ look, busy, disabled = false, onOpen, onSave }) {
  if (!lookHasContent(look)) return null;

  const parts = Object.keys(look.parts || {});
  const count = (look.baseObj ? 1 : 0) + parts.length;
  const thumbs = [];
  if (look.baseSwf && look.baseObj) {
    thumbs.push({
      pack: look.baseSwf,
      name: look.baseObj,
      src: look.baseThumb || getCachedThumb(look.baseSwf, look.baseObj) || api.thumbUrl(look.baseSwf, look.baseObj),
    });
  }
  for (const slot of parts.slice(0, 5)) {
    const info = look.partsInfo?.[slot] || {};
    const pack = info.pack || String(look.parts[slot]).split(".")[0];
    const name = info.name || String(look.parts[slot]).split(".").slice(1).join(".");
    if (!name) continue;
    thumbs.push({
      pack,
      name,
      src: info.thumb || getCachedThumb(pack, name) || api.thumbUrl(pack, name),
    });
  }

  return (
    <div className="floating-look-pill app-no-drag" onClick={onOpen} title="Ver look">
      <div className="floating-pill-thumbs">
        {thumbs.map((t, i) => (
          <div key={`${t.pack}.${t.name}-${i}`} className="floating-pill-avatar" title={`${t.pack}.${t.name}`}>
            <ItemThumb pack={t.pack} name={t.name} size={26} />
          </div>
        ))}
      </div>
      <div className="floating-pill-text-wrap">
        <span className="floating-pill-text">Look activo ({count})</span>
        <span className="floating-pill-sub">Ver detalle</span>
      </div>
      <button
        type="button"
        className="floating-pill-btn"
        disabled={disabled || busy || !look.baseObj || !parts.length}
        onClick={(e) => {
          e.stopPropagation();
          onSave?.();
        }}
      >
        {busy ? "Guardando..." : "Guardar"}
      </button>
    </div>
  );
}
