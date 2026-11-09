/**
 * Flash ↔ React thumbnail bridge (same protocol as legacy app.js).
 * preview.swf calls window.receiveThumb / receiveAssets after searchAssets(pack).
 * También persiste thumbs en el backend para búsqueda por imagen.
 *
 * Soporta dos orígenes: visor (usuario) e indexador en background.
 * Si el usuario está mirando un pack, el indexador se pausa unos segundos.
 */

const cache = new Map();
const MAX_CACHE_ENTRIES = 512;
const MAX_CACHE_CHARS = 16 * 1024 * 1024;
let cacheChars = 0;
function cacheThumb(key, src) {
  cacheChars -= cache.get(key)?.length || 0;
  cache.delete(key);
  cache.set(key, src);
  cacheChars += src.length;
  while (cache.size > MAX_CACHE_ENTRIES || cacheChars > MAX_CACHE_CHARS) {
    const oldest = cache.keys().next().value;
    cacheChars -= cache.get(oldest).length;
    cache.delete(oldest);
  }
} // "pack.name" -> dataURL
const idToName = new Map();
const ingestPending = new Map(); // key -> {pack, name, png}
const INGESTED = new Set();

let viewerPack = "";
let indexerPack = "";
let bridgeMode = "viewer"; // "viewer" | "indexer"
let viewerHoldUntil = 0;
let bound = false;
let ingestTimer = null;
let ingestInFlight = false;
let indexerThumbCount = 0;
let indexerLastThumbAt = 0;
let indexerStartedAt = 0;

function cleanAssetName(raw) {
  if (!raw) return "";
  let s = String(raw).trim();
  if (s.includes(":")) s = s.split(":").pop();
  if (s.includes(".")) s = s.split(".").pop();
  return s.trim();
}

function cleanPack(pack) {
  return String(pack || "")
    .replace(/\.swf$/i, "")
    .trim();
}

const keyListeners = new Map();
const wildcardListeners = new Set();

function notify(key, src) {
  const specific = keyListeners.get(key);
  if (specific) {
    for (const fn of specific) {
      try {
        fn(key, src);
      } catch (_) {}
    }
  }
  for (const fn of wildcardListeners) {
    try {
      fn(key, src);
    } catch (_) {}
  }
}

export function thumbKey(pack, name) {
  return `${pack}.${name}`;
}

export function getCachedThumb(pack, name) {
  if (!pack || !name) return "";
  const key = thumbKey(pack, name);
  const src = cache.get(key) || "";
  if (src) { cache.delete(key); cache.set(key, src); }
  return src;
}

export function subscribeThumbs(fn, key) {
  if (key) {
    let set = keyListeners.get(key);
    if (!set) {
      set = new Set();
      keyListeners.set(key, set);
    }
    set.add(fn);
    return () => {
      set.delete(fn);
      if (set.size === 0) keyListeners.delete(key);
    };
  }
  wildcardListeners.add(fn);
  return () => wildcardListeners.delete(fn);
}

const VIEWER_HOLD_MS = 1000;

/** Pack del visor / exploración manual. Pausa el indexador unos segundos. */
export function setThumbSearchPack(pack) {
  viewerPack = cleanPack(pack);
  bridgeMode = "viewer";
  viewerHoldUntil = Date.now() + VIEWER_HOLD_MS;
  idToName.clear();
}

/** Pack del indexador automático (solo cuando el visor no está activo). */
export function setIndexerSearchPack(pack) {
  indexerPack = cleanPack(pack);
  bridgeMode = "indexer";
  idToName.clear();
  indexerThumbCount = 0;
  indexerStartedAt = Date.now();
  indexerLastThumbAt = indexerStartedAt;
}

/** Stats del pack que está indexando ahora (para espera adaptativa). */
export function getIndexerThumbStats() {
  return {
    pack: indexerPack,
    count: indexerThumbCount,
    lastAt: indexerLastThumbAt,
    startedAt: indexerStartedAt,
    pending: ingestPending.size + Number(ingestInFlight),
  };
}

export function noteViewerActivity(ms = VIEWER_HOLD_MS) {
  viewerHoldUntil = Date.now() + ms;
}

export function clearViewerPack() {
  viewerPack = "";
  viewerHoldUntil = 0;
}

/** True solo mientras hay actividad reciente en el visor (no mientras el pack quede abierto). */
export function viewerIsHolding() {
  return Date.now() < viewerHoldUntil;
}

export function viewerHoldRemainingMs() {
  return Math.max(0, viewerHoldUntil - Date.now());
}

/** Liberar pausa del indexador ya (el pack puede seguir abierto en la UI). */
export function releaseViewerHold() {
  viewerHoldUntil = 0;
}

export function getBridgePack() {
  return bridgeMode === "indexer" ? indexerPack : viewerPack;
}

function resolvePack(parsed) {
  const fromMsg = cleanPack(parsed?.pack || "");
  if (fromMsg) return fromMsg;
  if (bridgeMode === "indexer" && indexerPack) return indexerPack;
  if (viewerPack) return viewerPack;
  return indexerPack || "";
}

function queueIngest(pack, name, dataUrl) {
  const key = thumbKey(pack, name);
  if (INGESTED.has(key)) return;
  ingestPending.set(key, { pack, name, png: dataUrl });
  if (ingestTimer || ingestInFlight) return;
  // Indexador: flush casi inmediato. Visor: debounce un poco más.
  const delay = bridgeMode === "indexer" ? 80 : 350;
  ingestTimer = setTimeout(flushIngest, delay);
}

async function flushIngest() {
  ingestTimer = null;
  if (!ingestPending.size) return;
  const batch = Array.from(ingestPending.values()).slice(0, 80);
  ingestInFlight = true;
  for (const row of batch) {
    ingestPending.delete(thumbKey(row.pack, row.name));
  }
  try {
    const res = await fetch("/api/thumbs/ingest-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: batch }),
    });
    if (res.ok) {
      for (const row of batch) INGESTED.add(thumbKey(row.pack, row.name));
    }
  } catch (_) {
    // silencioso
  }
  ingestInFlight = false;
  if (ingestPending.size) {
    ingestTimer = setTimeout(flushIngest, bridgeMode === "indexer" ? 60 : 250);
  }
}

let lastAttributes = {};

export function getLastAttributes() {
  return lastAttributes;
}

export function bindFlashThumbBridge() {
  if (bound || typeof window === "undefined") return;
  bound = true;

  window.receiveAttributes = (raw) => {
    try {
      const parsed = typeof raw === "string" ? JSON.parse(raw) : (raw || {});
      lastAttributes = parsed && typeof parsed === "object" ? parsed : {};
    } catch (_) {
      lastAttributes = {};
    }
  };

  window.receiveAssets = (raw) => {
    try {
      const list = typeof raw === "string" ? JSON.parse(raw) : raw;
      const rows = Array.isArray(list) ? list : [];
      if (!rows.length) return;

      const incomingPack = cleanPack(rows[0]?.pack || "");
      const active = resolvePack({ pack: incomingPack });
      if (incomingPack && active && incomingPack !== active) return;

      for (const row of rows) {
        if (!row) continue;
        const clean = cleanAssetName(row.name || row.id);
        if (!clean || clean.endsWith("_on") || clean.endsWith("MamboAsset") || clean.startsWith("_")) {
          continue;
        }
        if (row.id != null) idToName.set(String(row.id), clean);
      }
    } catch (err) {
      console.warn("[ThumbBridge] receiveAssets:", err);
    }
  };

  window.receiveThumb = (raw) => {
    try {
      const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
      if (!parsed) return;
      const png = parsed.thumb || parsed.png || parsed.image;
      if (!png) return;
      const src = png.startsWith("data:") ? png : `data:image/png;base64,${png}`;

      let targetName = "";
      if (parsed.id != null) targetName = idToName.get(String(parsed.id)) || "";
      if (!targetName && parsed.name) targetName = cleanAssetName(parsed.name);
      if (!targetName) return;

      const pack = resolvePack(parsed);
      if (!pack) return;

      if (bridgeMode === "indexer" && pack === indexerPack) {
        indexerThumbCount += 1;
        indexerLastThumbAt = Date.now();
      }

      const key = thumbKey(pack, targetName);
      cacheThumb(key, src);
      notify(key, src);
      queueIngest(pack, targetName, src);
    } catch (err) {
      console.warn("[ThumbBridge] receiveThumb:", err);
    }
  };

  if (!window.receiveError) {
    window.receiveError = (raw) => console.warn("[FlashBridge] receiveError:", raw);
  }
}
