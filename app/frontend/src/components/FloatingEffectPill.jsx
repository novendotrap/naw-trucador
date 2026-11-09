import ItemThumb from "./ItemThumb";
import { effectHasContent, parseItemParts } from "../look/effects";
import { Sparkles } from "lucide-react";

export default function FloatingEffectPill({ effect, busy, disabled = false, onOpen, onSave, hasLookPill = false }) {
  if (!effectHasContent(effect)) return null;

  const baseItem = effect.baseItem || (effect.basePack && effect.baseObj ? `${effect.basePack}.${effect.baseObj}` : "");
  const { pack: basePack, obj: baseObj } = parseItemParts(baseItem);

  const subItem = effect.subItem || (effect.subPack && effect.subObj ? `${effect.subPack}.${effect.subObj}` : "");
  const { pack: subPack, obj: subObj } = parseItemParts(subItem);

  const action = effect.action || "kick";

  const thumbs = [];
  if (basePack && baseObj) {
    thumbs.push({ pack: basePack, name: baseObj, title: `Base: ${baseObj}` });
  }
  if (subPack && subObj) {
    thumbs.push({ pack: subPack, name: subObj, title: `Prop: ${subObj}` });
  }

  // If FloatingLookPill is also visible, position this pill higher
  const bottomOffset = hasLookPill ? 84 : 22;

  return (
    <div
      className="floating-effect-pill app-no-drag"
      style={{ bottom: `${bottomOffset}px` }}
      onClick={onOpen}
      title="Ver configurador de efecto"
    >
      <div className="floating-pill-sparkle">
        <Sparkles size={16} />
      </div>

      <div className="floating-pill-thumbs">
        {thumbs.map((t, i) => (
          <div key={`${t.pack}.${t.name}-${i}`} className="floating-pill-avatar" title={t.title}>
            <ItemThumb pack={t.pack} name={t.name} size={26} />
          </div>
        ))}
      </div>

      <div className="floating-pill-text-wrap">
        <span className="floating-pill-text" style={{ color: "#fbbf24" }}>
          Efecto: {baseObj || "Sin base"} + {action}
        </span>
        <span className="floating-pill-sub">
          {subObj ? `Prop: ${subObj}` : "Click para configurar"}
        </span>
      </div>

      <button
        type="button"
        className="floating-pill-btn"
        style={{
          background: "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
          color: "#fff",
          borderColor: "#b45309",
        }}
        disabled={disabled || busy || !baseObj}
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
