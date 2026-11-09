/**
 * effects.js - Helper functions and initial state for interactive Effect Tricks draft.
 */

export function parseItemParts(itemStr) {
  const clean = String(itemStr || "").replace(/\.swf$/i, "").trim();
  if (!clean) return { pack: "", obj: "" };
  if (clean.includes(".")) {
    const [pack, ...rest] = clean.split(".");
    return { pack, obj: rest.join(".") };
  }
  return { pack: clean, obj: clean };
}

export function emptyEffect() {
  return {
    baseItem: "",
    basePack: "",
    baseObj: "",
    action: "kick",
    subItem: "",
    subPack: "",
    subObj: "",
    destination: "default", // "default" (mochila) | "house" (casa)
    uses: 9999,
  };
}

export function effectHasContent(eff) {
  if (!eff) return false;
  return Boolean(eff.baseObj || eff.baseItem || eff.subObj || eff.subItem);
}
