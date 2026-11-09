/**
 * Indexa TODOS los packs en background con un Ruffle propio (no el del visor).
 * Se pausa solo cuando el usuario está explorando un SWF.
 *
 * Espera adaptativa: corta cuando el pack deja de mandar thumbs (mucho más
 * rápido que un sleep fijo de 1.8–3s por pack).
 */

import { api } from "../api/client";
import {
  bindFlashThumbBridge,
  getIndexerThumbStats,
  setIndexerSearchPack,
  viewerHoldRemainingMs,
  viewerIsHolding,
} from "./bridge";

const listeners = new Set();
const state = {
  running: false,
  paused: false,
  done: false,
  current: "",
  index: 0,
  total: 0,
  thumbs: 0,
  packsDone: 0,
  message: "",
};

let player = null;
let hostEl = null;
let loopPromise = null;
let stopFlag = false;
let ruffleScriptPromise = null;
let wantHdUpgrade = false;

function emit() {
  const snap = { ...state };
  for (const fn of listeners) {
    try {
      fn(snap);
    } catch (_) {}
  }
}

export function subscribeIndexer(fn) {
  listeners.add(fn);
  fn({ ...state });
  return () => listeners.delete(fn);
}

export function getIndexerState() {
  return { ...state };
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function ensureRuffleScript() {
  if (window.RufflePlayer?.newest) return Promise.resolve(window.RufflePlayer);
  if (ruffleScriptPromise) return ruffleScriptPromise;
  window.RufflePlayer = window.RufflePlayer || {};
  window.RufflePlayer.config = {
    publicPath: "/static/ruffle/",
    polyfills: false,
    wmode: "transparent",
    allowScriptAccess: true,
    allowNetworking: "all",
    contextMenu: "off",
    splashScreen: false,
    logLevel: "error",
    unmuteOverlay: "hidden",
  };
  ruffleScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-naw-ruffle="1"]');
    if (existing) {
      existing.addEventListener("load", () => resolve(window.RufflePlayer));
      existing.addEventListener("error", reject);
      return;
    }
    const s = document.createElement("script");
    s.src = "/static/ruffle/ruffle.js";
    s.dataset.nawRuffle = "1";
    s.onload = () => resolve(window.RufflePlayer);
    s.onerror = reject;
    document.head.appendChild(s);
  });
  return ruffleScriptPromise;
}

async function ensurePlayer() {
  bindFlashThumbBridge();
  if (player && typeof player.searchAssets === "function") return player;
  await ensureRuffleScript();
  if (!hostEl) {
    hostEl = document.createElement("div");
    hostEl.id = "naw-thumb-indexer-host";
    hostEl.setAttribute("aria-hidden", "true");
    Object.assign(hostEl.style, {
      position: "fixed",
      left: "-200px",
      top: "-200px",
      width: "160px",
      height: "160px",
      opacity: "0",
      pointerEvents: "none",
      overflow: "hidden",
      zIndex: "-1",
    });
    document.body.appendChild(hostEl);
  }
  hostEl.innerHTML = "";
  const ruffle = window.RufflePlayer.newest();
  const p = ruffle.createPlayer();
  p.style.width = "100%";
  p.style.height = "100%";
  hostEl.appendChild(p);
  await p.load({
    url: "/preview.swf?v=43-json",
    allowScriptAccess: true,
    autoplay: "on",
    unmuteOverlay: "hidden",
    splashScreen: false,
    letterbox: "off",
    wmode: "transparent",
  });
  for (let i = 0; i < 100; i++) {
    if (typeof p.searchAssets === "function") break;
    await sleep(100);
  }
  player = p;
  return player;
}

async function waitWhileViewerBusy() {
  while (!stopFlag && (viewerIsHolding() || document.hidden || document.querySelector(".modal-backdrop, .slot-modal-backdrop"))) {
    player?.pause?.();
    state.paused = true;
    const left = Math.max(1, Math.ceil(viewerHoldRemainingMs() / 1000));
    state.message = `Pausado por exploración · retoma en ~${left}s`;
    emit();
    await sleep(400);
  }
  if (!stopFlag) player?.play?.();
  state.paused = false;
}

function packMaxWaitMs(pack, expected) {
  const n = Number(expected) || 0;
  if (n >= 80) return 2800;
  if (n >= 30) return 2000;
  if (n >= 12) return 1500;
  if (/greek|halloween|christmas|navidad|virtualGoods|clothesZero/i.test(pack || "")) {
    return 2000;
  }
  return 1100;
}

/**
 * Espera hasta que el pack deje de emitir thumbs (quiet) o se cumpla el techo.
 * Packs vacíos/chicos salen en ~0.4–0.7s en vez de 1.8s fijos.
 */
async function waitForPackThumbs(pack, expected) {
  const maxMs = packMaxWaitMs(pack, expected);
  const minMs = 220;
  const quietMs = 140;
  const start = Date.now();

  await sleep(minMs);
  while (!stopFlag && Date.now() - start < maxMs) {
    if (viewerIsHolding()) return;
    const st = getIndexerThumbStats();
    if (st.pack !== pack) return;

    const silentFor = Date.now() - st.lastAt;
    const gotEnough =
      expected > 0 && st.count >= Math.max(1, Math.floor(expected * 0.9));

    if (gotEnough && silentFor >= quietMs && st.pending === 0) {
      return;
    }
    // Sin thumbs: no conviene esperar el max entero
    if (st.count === 0 && Date.now() - start >= 450 && silentFor >= quietMs) {
      return;
    }
    // Con thumbs y silencio: listo
    if (st.count > 0 && silentFor >= quietMs && st.pending === 0) {
      return;
    }
    await sleep(50);
  }
}

async function indexLoop() {
  state.running = true;
  state.done = false;
  state.message = "Preparando índice…";
  emit();

  try {
    const hd = wantHdUpgrade;
    wantHdUpgrade = false;
    const cov = await api.thumbsCoverage(hd);
    const missing = cov.missing || [];
    const expectedMap = cov.expected || {};
    state.total = cov.total_packs || 0;
    state.packsDone = cov.done_packs || 0;
    state.thumbs = cov.thumbs || 0;
    state.index = state.packsDone;

    if (!missing.length) {
      state.done = true;
      const staleN = cov.stale_packs || 0;
      state.message = staleN
        ? `Índice listo · ${state.thumbs} thumbs (${staleN} packs podrían subir a HD)`
        : `Índice completo · ${state.thumbs} thumbs`;
      state.running = false;
      emit();
      return;
    }

    await waitWhileViewerBusy();
    if (stopFlag) return;
    await ensurePlayer();

    const never = cov.never_indexed || 0;
    const incomplete = cov.incomplete_packs || 0;
    const stale = cov.stale_packs || 0;
    if (hd && stale) {
      state.message = `Mejorando thumbs HD (${cov.capture_max || 120}px) · ${missing.length} packs…`;
    } else if (never) {
      state.message = `Indexando ${never} packs nuevos primero…`;
    } else if (incomplete) {
      state.message = `Completando ${incomplete} packs parciales…`;
    } else {
      state.message = `Indexando ${missing.length} packs pendientes…`;
    }
    emit();

    for (let i = 0; i < missing.length; i++) {
      if (stopFlag) break;
      await waitWhileViewerBusy();
      if (stopFlag) break;

      const pack = missing[i];
      const expected = Number(expectedMap[pack] || 0);
      state.current = pack;
      state.index = state.packsDone + i + 1;
      state.message = `${state.index}/${state.total} · ${pack}`;
      emit();

      setIndexerSearchPack(pack);
      try {
        if (player && typeof player.searchAssets === "function") {
          player.searchAssets(pack);
        }
      } catch (e) {
        console.warn("[AutoIndexer] searchAssets", pack, e);
      }

      await waitForPackThumbs(pack, expected);

      if (i % 12 === 11) {
        try {
          const st = await api.thumbsStats();
          state.thumbs = st.thumbs || state.thumbs;
          emit();
        } catch (_) {}
      }
    }

    try {
      await api.thumbsReindex();
      const st = await api.thumbsStats();
      state.thumbs = st.thumbs || 0;
    } catch (_) {}

    state.done = !stopFlag;
    state.current = "";
    state.message = stopFlag
      ? `Indexado detenido · ${state.thumbs} thumbs`
      : `Índice listo · ${state.thumbs} thumbs`;
  } catch (e) {
    state.message = e.message || "Error indexando";
    console.warn("[AutoIndexer]", e);
  } finally {
    // A finished index must not leave an invisible Flash runtime consuming CPU/RAM.
    player = null;
    hostEl?.remove();
    hostEl = null;
    state.running = false;
    state.paused = false;
    emit();
    loopPromise = null;
  }
}

/** Arranca indexado de packs faltantes (vacíos/incompletos). No resetea lo ya capturado. */
export function startAutoIndexer({ hd = false } = {}) {
  stopFlag = false;
  wantHdUpgrade = !!hd;
  if (loopPromise) return loopPromise;
  loopPromise = indexLoop();
  return loopPromise;
}

export function stopAutoIndexer() {
  stopFlag = true;
}

/** Re-scan de faltantes reales (no vuelve a pasar todos los packs viejos). */
export function resumeAutoIndexer(opts = {}) {
  stopFlag = false;
  if (loopPromise) return loopPromise;
  return startAutoIndexer(opts);
}
