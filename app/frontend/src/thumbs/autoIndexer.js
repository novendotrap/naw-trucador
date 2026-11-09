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

/**
 * Give Ruffle time to load the SWF and deliver the first thumbnail, even
 * when rendering takes longer on a cold cache or a slower computer.
 */
async function waitForPackThumbs(pack, expected) {
  const maxMs = expected >= 80 ? 12000 : 6000;
  const start = Date.now();

  while (!stopFlag && Date.now() - start < maxMs) {
    if (viewerIsHolding()) return;
    const st = getIndexerThumbStats();
    if (st.pack !== pack) return;

    const quietMs = expected > st.count ? 750 : 250;
    if (st.count > 0 && Date.now() - st.lastAt >= quietMs && st.pending === 0) return;
    await sleep(50);
  }
}

async function indexLoop({ hd, pack: targetPack }) {
  state.running = true;
  state.done = false;
  state.message = "Preparando índice…";
  emit();

  try {
    const cov = await api.thumbsCoverage(hd);
    const missing = (cov.missing || []).filter((pack) => !targetPack || pack === targetPack);
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
      state.index = i + 1;
      state.message = `${hd ? "Mejorando miniaturas" : "Indexando"} · ${state.index}/${missing.length} · ${pack}`;
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
      if (viewerIsHolding() && !stopFlag) {
        i -= 1;
        continue;
      }

      if (i % 12 === 11) {
        try {
          const st = await api.thumbsStats();
          state.thumbs = st.thumbs || state.thumbs;
          emit();
        } catch (_) {}
      }
    }

    try {
      if (!targetPack) await api.thumbsReindex();
      const st = await api.thumbsStats();
      state.thumbs = st.thumbs || 0;
    } catch (_) {}

    state.done = !stopFlag;
    state.current = "";
    const updated = hd && !stopFlag ? await api.thumbsCoverage(true) : null;
    const remaining = updated?.stale_packs || 0;
    state.message = stopFlag
      ? `Indexado detenido · ${state.thumbs} thumbs`
      : targetPack && updated?.missing?.includes(targetPack)
        ? `Quedan miniaturas por actualizar en ${targetPack}`
        : remaining
          ? `Quedan ${remaining} packs con miniaturas antiguas`
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
export function startAutoIndexer({ hd = false, pack = "" } = {}) {
  if (loopPromise) return loopPromise;
  stopFlag = false;
  loopPromise = indexLoop({ hd, pack });
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
