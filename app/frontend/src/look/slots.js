export const LOOK_SLOTS = [
  "hats", "hats2", "hairs", "hairs2", "mouths", "mouths2",
  "neck", "neck2", "accesories", "accesories2",
  "cloth", "cloth2", "clothBack", "clothBack2",
  "leg", "leg2", "arm", "arm2", "foot", "foot2",
  "grip", "grip2", "transport", "transport2",
  "effect", "effect2",
];

export const SLOT_FAMILIES = [
  { id: "hats", label: "Sombrero", layers: ["hats", "hats2"] },
  { id: "hairs", label: "Pelo", layers: ["hairs", "hairs2"] },
  { id: "mouths", label: "Boca", layers: ["mouths", "mouths2"] },
  { id: "neck", label: "Cuello", layers: ["neck", "neck2"] },
  { id: "accesories", label: "Accesorio", layers: ["accesories", "accesories2"] },
  { id: "cloth", label: "Ropa", layers: ["cloth", "cloth2"] },
  { id: "clothBack", label: "Capa", layers: ["clothBack", "clothBack2"] },
  { id: "leg", label: "Pantalón", layers: ["leg", "leg2"] },
  { id: "foot", label: "Calzado", layers: ["foot", "foot2"] },
  { id: "arm", label: "Brazo", layers: ["arm", "arm2"] },
  { id: "grip", label: "Mano", layers: ["grip", "grip2"] },
  { id: "transport", label: "Transporte", layers: ["transport", "transport2"] },
  { id: "effect", label: "Efecto", layers: ["effect", "effect2"] },
];

export const SLOT_GROUPS = [
  { id: "head", label: "Cabeza", families: ["hats", "hairs"] },
  { id: "face", label: "Cara", families: ["mouths", "neck"] },
  { id: "body", label: "Cuerpo", families: ["cloth", "clothBack"] },
  { id: "legs", label: "Piernas", families: ["leg", "foot"] },
  { id: "hands", label: "Manos", families: ["arm", "grip"] },
  { id: "extra", label: "Otros", families: ["accesories", "transport", "effect"], wide: true },
];

/** Iconos SVG por familia (mismo set que la UI web vieja). */
export const SLOT_FAMILY_ICONS = {
  hats: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2"><path d="M2 17h14c3.3 0 6-2.7 6-6 0-.6-.5-1-1-1h-6C10 5 4 8 2 17z"/></svg>`,
  hairs: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#c084fc" stroke-width="2"><path d="M4 16c0-6 3-12 8-12s8 6 8 12c-1.5-1-3-2-4-1-2 2-3 2-4 0-1-1-3-1-4 1-1.5 2-4 1-4 0z"/></svg>`,
  mouths: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f472b6" stroke-width="2"><path d="M4 11c2.5 3.5 5 5 8 5s5.5-1.5 8-5c-2.5-2-5.5-3-8-3s-5.5 1-8 3z"/></svg>`,
  neck: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2dd4bf" stroke-width="2"><path d="M5 6c2-2 12-2 14 0 2 2 1 6-3 7-4 1-8 1-11-7z"/></svg>`,
  accesories: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fb7185" stroke-width="2"><path d="M3 10l1 5c0 2 2 3 4 3s4-1 4-3l1-5H3z"/></svg>`,
  cloth: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2"><path d="M6 2L3 6l3 2v13h12V8l3-2-3-4-3 2a4 4 0 01-6 0L6 2z"/></svg>`,
  clothBack: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><path d="M7 4h10l3 16-8-3-8 3 3-16z"/></svg>`,
  leg: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><path d="M5 4h14v4l-2 13h-4l-1-10-1 10H7L5 8V4z"/></svg>`,
  foot: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fb923c" stroke-width="2"><path d="M2 17h20v-3c-3-1-5-3-7-3h-4l-3-4H4v7l-2 3z"/></svg>`,
  arm: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#a3e635" stroke-width="2"><path d="M4 14v4a2 2 0 002 2h4c3 0 6-2 7-5l1-4a3 3 0 00-3-3h-3c-2 0-3 1-4 2l-4 4z"/></svg>`,
  grip: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2"><path d="M19 3l2 2-10 10-3-1 1-3 10-8z"/><path d="M6 18l-3 3"/></svg>`,
  transport: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#818cf8" stroke-width="2"><path d="M3 11c3-2 15-2 18 0l1 2H2l1-2z"/><circle cx="6" cy="16" r="2"/><circle cx="18" cy="16" r="2"/></svg>`,
  effect: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#facc15" stroke-width="2"><path d="M12 2l2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5L12 2z"/></svg>`,
};

export const SPECIAL_WEAR_MAPPINGS = {
  "costumes.peloMorti": "costumes.peloMorticia_on",
  "costumes.peloMorticia": "costumes.peloMorticia_on",
  "costumesHalloween.costumeDiablo": "costumesHalloween.vestidoDiablo_on",
  "costumesHalloween.disfrazDiablo": "costumesHalloween.vestidoDiablo_on",
  "aesthetic.CamisaColores": "aesthetic.Camisacolores_on",
  "anime.Anime_kimono": "anime.Anime_Kimono_on",
  "anime.Kpop_CamisaCuadrille": "anime.Kpop_Camisacuadrille_on",
  "anime.Anime_UniformeH": "anime.Anime_uniformeH_on",
  "anteojos2019.anteojos2019_fla.MainTimeline": "anteojos2019.anteojos2_on",
  "arcor.premio1": "arcor.premio11_on",
  "ba.ba_fla.bolaanimadaobelisco_5": "ba.ba_on",
  "ba.ba_fla.bolaanimadaplanetario_8": "ba.ba_on",
  "ba.baReciclable": "ba.ba_on",
  "ba.ba_fla.empty_70": "ba.ba_on",
  "escuela.uniformeMujer": "escuela.uniformeMujerRojo_on",
  "escuela.uniformeVaron": "escuela.uniformeVaronRojo_brazo_on",
  "escuela.pelota2": "escuela.pelota_on",
  "escuelaNueva.pantalonGimnasia": "escuelaNueva.pantalonGimnasiaInvierno_on",
  "fashion2017.MusculosaBlancaA": "fashion2017.musculosaBlancaA_on",
  "fashion2017.MusculosaBlancaB": "fashion2017.musculosaBlancaB_on",
  "fashion2017.MusculosaNaranjaA": "fashion2017.musculosaNaranjaA_on",
  "fashion2017.MusculosaNaranjaB": "fashion2017.musculosaNaranjaB_on",
  "fashion2017.MusculosaRojaA": "fashion2017.musculosaRojaA_on",
  "fashion2017.MusculosaRojaB": "fashion2017.musculosaRojaB_on",
  "fashion2017.MusculosaVerdeA": "fashion2017.musculosaVerdeA_on",
  "fashion2017.MusculosaVerdeB": "fashion2017.musculosaVerdeB_on",
  "fashion2017.RemeraAmarillaA": "fashion2017.remeraAmarillaA_on",
  "fashion2017.RemeraAmarillaB": "fashion2017.remeraAmarillaB_on",
  "fashion2017.RemeraCelesteA": "fashion2017.remeraCelesteA_on",
  "fashion2017.RemeraCelesteB": "fashion2017.remeraCelesteB_on",
  "fashion2017.RemeraPurpuraA": "fashion2017.remeraPurpuraA_on",
  "fashion2017.RemeraPurpuraB": "fashion2017.remeraPurpuraB_on",
  "fashion2017.RemeraVerdeA": "fashion2017.remeraVerdeA_on",
  "fashion2017.RemeraVerdeB": "fashion2017.remeraVerdeB_on",
  "gigante.bota": "gigante.botaBrocoli_on",
  "hairs1.pelucaFrozen": "hairs1.pelucaFrozenHombre_on",
  "heartStop.mochila": "heartStop.mochila1_front_on",
  "islandClothes.pulseraFlores": "islandClothes.pulseraFlores_brazo_on",
  "mounstruos.remeraJardineroVerde": "mounstruos.remeraJardineroVerde_brazo_on",
  "mundial.pelota1": "mundial.pelota_on",
  "mundial.pelota2": "mundial.pelota_on",
  "mundialClothes.papelPicado2": "mundialClothes.papelPicado_on",
  "princeClothes.vestidoCenicienta2": "princeClothes.vestidoCenicienta_on",
  "serenito.hatSerenitoChocolate": "serenito.HatSerenitoChocolate_on",
  "serenito.hatSerenitoDulceDeLeche": "serenito.HatSerenitoDulceDeLeche_on",
  "serenito.hatSerenitoFlan": "serenito.HatSerenitoFlan_on",
  "serenito.hatSerenitoRocklets": "serenito.HatSerenitoRocklets_on",
  "serenito.hatSerenitoVainilla": "serenito.HatSerenitoVainilla_on",
  "serenito.remeraS": "serenito.remeraS_brazo_on",
  "serenito.tabletPremio": "serenito.tablet_on",
  "transport.bicicletaPaseo_on_shape": "transport.bicicletaPaseo_on",
  "transport.caballoAzul2": "transport.caballoAzul_on",
  "transport.caballoRojo2": "transport.caballoRojo_on",
  "transport.caballoVioleta2": "transport.caballoVioleta_on",
  "transport.escoba1": "transport.escoba1Active_on",
  "trenFantasma.gorro": "trenFantasma.gorroFantasma_on",
};

export function toClothesOnValue(pack, name) {
  const cleanPack = String(pack || "").replace(/\.swf$/i, "").trim();
  let cleanName = String(name || "").trim();
  if (cleanName.includes(".")) {
    const bits = cleanName.split(".");
    cleanName = bits[bits.length - 1];
  }

  const fullKey = cleanPack ? `${cleanPack}.${cleanName}` : cleanName;
  if (SPECIAL_WEAR_MAPPINGS[fullKey]) {
    return SPECIAL_WEAR_MAPPINGS[fullKey];
  }

  // Prefix heuristic for Morticia / mortis
  if (cleanName.toLowerCase().startsWith("pelomorti")) {
    return cleanPack ? `${cleanPack}.peloMorticia_on` : "peloMorticia_on";
  }

  if (!cleanName.endsWith("_on")) cleanName += "_on";
  return cleanPack ? `${cleanPack}.${cleanName}` : cleanName;
}

export function wearKeyForLookSlot(slot) {
  return `wear_${String(slot || "").trim()}`;
}

export function previewVisualSlot(slot) {
  return String(slot || "").trim();
}

export function remapWearAttrsForPreview(rawAttrs) {
  const out = {};
  const attrs = { ...(rawAttrs || {}) };

  const getVal = (slot) => attrs[`wear_${slot}`] || attrs[slot] || null;

  // 1. Head slots mapping
  // Available physical head containers in Gaturro's Head (Sprite 79): 'hats', 'hairs', 'accesories'
  let hat1 = getVal("hats");
  let hat2 = getVal("hats2");
  let hair1 = getVal("hairs");
  let hair2 = getVal("hairs2");
  let acc1 = getVal("accesories");
  let acc2 = getVal("accesories2");

  let assignedHats = hat1;
  let assignedHairs = hair1;
  let assignedAcc = acc1;

  // If hat2 is provided, find where to put it
  if (hat2) {
    const isHairLike = /pelo|peluca|hair|peinado/i.test(String(hat2));
    if (isHairLike && !assignedHairs) {
      assignedHairs = hat2;
    } else if (!assignedAcc) {
      assignedAcc = hat2;
    } else if (!assignedHairs) {
      assignedHairs = hat2;
    }
  }

  // If hair2 is provided, find where to put it
  if (hair2) {
    const isHatLike = /sombrero|gorro|hat|corona|casco|adorno|tiara|vincha/i.test(String(hair2));
    if (isHatLike && !assignedHats) {
      assignedHats = hair2;
    } else if (!assignedAcc) {
      assignedAcc = hair2;
    } else if (!assignedHats) {
      assignedHats = hair2;
    }
  }

  // If acc2 is provided, find where to put it
  if (acc2) {
    if (!assignedHats) {
      assignedHats = acc2;
    } else if (!assignedHairs) {
      assignedHairs = acc2;
    }
  }

  if (assignedHats) {
    out.wear_hats = assignedHats;
    out.hats = assignedHats;
  }
  if (assignedHairs) {
    out.wear_hairs = assignedHairs;
    out.hairs = assignedHairs;
  }
  if (assignedAcc) {
    out.wear_accesories = assignedAcc;
    out.accesories = assignedAcc;
  }

  // 2. Body slots mapping
  let cloth1 = getVal("cloth");
  let cloth2 = getVal("cloth2");
  let cape1 = getVal("clothBack");
  let cape2 = getVal("clothBack2");

  let assignedCloth = cloth1;
  let assignedBack = cape1;
  let assignedFront = null;

  if (cloth2) {
    if (!assignedFront) assignedFront = cloth2;
    else if (!assignedBack) assignedBack = cloth2;
  }
  if (cape2) {
    if (!assignedFront) assignedFront = cape2;
  }

  if (assignedCloth) { out.wear_cloth = assignedCloth; out.cloth = assignedCloth; }
  if (assignedBack) { out.wear_clothBack = assignedBack; out.clothBack = assignedBack; }
  if (assignedFront) { out.wear_clothFront = assignedFront; out.clothFront = assignedFront; }

  // 3. Face / Mouth / Neck
  let mouth1 = getVal("mouths");
  let mouth2 = getVal("mouths2");
  let neck1 = getVal("neck");
  let neck2 = getVal("neck2");

  if (mouth1) { out.wear_mouths = mouth1; out.mouths = mouth1; }
  if (mouth2) {
    if (!out.accesories) {
      out.wear_accesories = mouth2;
      out.accesories = mouth2;
    }
  }

  if (neck1) { out.wear_neck = neck1; out.neck = neck1; }
  if (neck2) {
    if (!out.accesories) {
      out.wear_accesories = neck2;
      out.accesories = neck2;
    }
  }

  // 4. Other slots (leg, foot, arm, grip, transport, effect)
  const handledSlots = [
    "hats", "hats2", "hairs", "hairs2", "accesories", "accesories2",
    "cloth", "cloth2", "clothBack", "clothBack2",
    "mouths", "mouths2", "neck", "neck2",
  ];

  for (const [key, value] of Object.entries(attrs)) {
    if (!value) continue;
    const base = key.startsWith("wear_") ? key.slice(5) : key;
    if (handledSlots.includes(base)) continue;

    const clean = base.replace(/2$/, "");
    out[`wear_${clean}`] = value;
    out[clean] = value;
  }

  return out;
}

export function lookWearAttrs(look, onlySlot) {
  const attrs = {};
  const slots = onlySlot ? [onlySlot] : Object.keys(look?.parts || {});
  for (const slot of slots) {
    const raw = look.parts[slot];
    if (raw == null || raw === "") continue;
    const info = look.partsInfo?.[slot] || {};
    const pack = info.pack || (String(raw).includes(".") ? String(raw).split(".")[0] : "");
    let name = info.name || (String(raw).includes(".") ? String(raw).split(".").slice(1).join(".") : String(raw));
    if (!name) continue;
    if (name.endsWith("_on")) name = name.slice(0, -3);
    attrs[wearKeyForLookSlot(slot)] = toClothesOnValue(pack, name);
  }
  return attrs;
}

export function guessSlotFromName(name) {
  const n = String(name || "").toLowerCase();
  if (/sombrero|gorro|hat|corona|casco|adorno|tiara|vincha|visera|cap|boina|turbante/.test(n)) return "hats";
  if (/pelo|peluca|hair|peinado|cresta|trenza|afro|copete/.test(n)) return "hairs";
  if (/boca|mouth|labio|bigote|barba|chupete|diente|pipa/.test(n)) return "mouths";
  if (/cuello|bufanda|neck|collar|gargantilla|panuelo|corbata|chalina|babero/.test(n)) return "neck";
  if (/anteojo|lente|gafa|accesor|antifaz|monoculo|mascara|parche|careta|maquillaje|make_?up|pintura|tatuaje|cara|face|rubor|cicatriz|lagrima/.test(n)) return "accesories";
  if (/capa|espalda|back|alas|mochila|caparazon/.test(n)) return "clothBack";
  if (/pantalon|short|leg|pollera|calza|falda|jean|traje_bano|malla|bermuda/.test(n)) return "leg";
  if (/zapa|bota|foot|zapato|calzado|ojota|patin|pantufla|chinela|sandalia/.test(n)) return "foot";
  if (/brazo|arm|guante|manga|reloj|pulsera/.test(n)) return "arm";
  if (/espada|katana|grip|varita|arma|cetro|globo|escudo|vara|baston|antorcha|hacha|pala|pistola/.test(n)) return "grip";
  if (/auto|moto|transport|tabla|skate|bici|patineta|nave|nube|trineo|alfombra|avion|bote/.test(n)) return "transport";
  return "cloth";
}

/**
 * Returns wear attributes for a single item or full costume disguise.
 */
export function getWornAttrsForItem(pack, rawName, item = null) {
  const cleanPack = String(pack || "").replace(/\.swf$/i, "").trim();
  const leaf = String(rawName || "").replace(/_on$/, "").trim();
  const lower = leaf.toLowerCase();

  // Clothes may be a map of body parts, not a symbol string.
  const clothes = item?.clothes || item?.attributes?.clothes;
  if (clothes && typeof clothes === "object") {
    const attrs = {};
    for (const [slot, value] of Object.entries(clothes)) {
      if (typeof value !== "string" || !value) continue;
      const dot = value.indexOf(".");
      attrs[wearKeyForLookSlot(slot.replace(/^wear_/, ""))] =
        dot > 0 ? toClothesOnValue(value.slice(0, dot), value.slice(dot + 1)) : toClothesOnValue(cleanPack, value);
    }
    if (Object.keys(attrs).length) return attrs;
  } else if (typeof clothes === "string" && clothes) {
    const dot = clothes.indexOf(".");
    const symbol = dot > 0 ? clothes.slice(dot + 1) : clothes;
    return { [wearKeyForLookSlot(guessSlotFromName(symbol))]: toClothesOnValue(dot > 0 ? clothes.slice(0, dot) : cleanPack, symbol) };
  }

  // If disguise / costume (e.g. costumeDiablo, disfrazMax, trajeAngel, etc.)
  if (lower.startsWith("disfraz") || lower.startsWith("traje") || lower.startsWith("costume")) {
    const suffix = leaf.replace(/^(disfraz|traje|costume)/i, "");
    if (suffix) {
      const sLow = suffix.toLowerCase();
      const shirt = sLow === "diablo" ? `vestido${suffix}` : `remera${suffix}`;
      const shoes = (sLow === "diablo" || sLow === "payaso" || sLow === "invisible" || sLow.includes("llama") || sLow === "opera") ? `zapa${suffix}` : `bota${suffix}`;
      const hat = (sLow === "sam" || sLow === "clicker" || sLow === "ghost" || sLow === "ghostface" || sLow === "pinhead") ? `mascara${suffix}` : `gorro${suffix}`;
      return {
        wear_cloth: toClothesOnValue(pack, shirt),
        wear_leg: toClothesOnValue(pack, `pantalon${suffix}`),
        wear_foot: toClothesOnValue(pack, shoes),
        wear_hats: toClothesOnValue(pack, hat),
      };
    }
  }

  // If special wear mapping
  const fullKey = cleanPack ? `${cleanPack}.${leaf}` : leaf;
  if (SPECIAL_WEAR_MAPPINGS[fullKey]) {
    const mapped = SPECIAL_WEAR_MAPPINGS[fullKey];
    const leafMapped = mapped.includes(".") ? mapped.split(".").pop() : mapped;
    const slot = guessSlotFromName(leafMapped) || guessSlotFromName(leaf);
    return {
      [wearKeyForLookSlot(slot)]: mapped,
    };
  }

  const slot = guessSlotFromName(leaf);
  return {
    [wearKeyForLookSlot(slot)]: toClothesOnValue(pack, leaf),
  };
}

export function emptyLook() {
  return { baseSwf: "", baseObj: "", baseThumb: "", parts: {}, partsInfo: {} };
}

export function lookHasContent(look) {
  return !!(look?.baseSwf && look?.baseObj) || Object.keys(look?.parts || {}).length > 0;
}
