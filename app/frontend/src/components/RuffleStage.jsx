import { useRuffleActivity } from "../hooks/useRuffleActivity";
import { showPreviewObject, showPreviewLook } from "../look/previewPlayer";
import { useEffect, useRef, useState } from "react";
import {
  bindFlashThumbBridge,
  setThumbSearchPack,
} from "../thumbs/bridge";
import {
  getWornAttrsForItem,
  remapWearAttrsForPreview,
} from "../look/slots";
import { api } from "../api/client";

let ruffleScriptPromise = null;
let sharedPlayer = null;
let sharedReady = false;

bindFlashThumbBridge();

/** Trigger thumbnail extraction for a pack (safe to call anytime). */
let coveragePromise = null;
let coverageAt = 0;
let thumbRequest = 0;
const searchedPacks = new WeakMap();
export async function requestPackThumbs(pack) {
  const clean = (pack || "").replace(/\.swf$/i, "").trim();
  if (!clean) return;
  const request = ++thumbRequest;
  try {
    if (!coveragePromise || Date.now() - coverageAt > 30000) {
      coverageAt = Date.now();
      coveragePromise = api.thumbsCoverage(false);
    }
    const coverage = await coveragePromise;
    if (request !== thumbRequest || !coverage.missing?.includes(clean)) return;
    const player = sharedPlayer;
    if (!player || typeof player.searchAssets !== "function" || searchedPacks.get(player) === clean) return;
    setThumbSearchPack(clean);
    player.searchAssets(clean);
    searchedPacks.set(player, clean);
  } catch (error) {
    coveragePromise = null;
    console.warn("Could not prepare pack thumbnails", error);
  }
}

/** Re-apply pending search + preview on the shared player. */
export function refreshSharedStage() {
  if (sharedPlayer && typeof sharedPlayer.previewAsset === "function") {
    // Stage is already mounted and active
  }
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
    logLevel: "warn",
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

async function createPlayerInHost(host) {
  await ensureRuffleScript();
  if (!window.RufflePlayer?.newest || !host) return null;
  host.innerHTML = "";
  const ruffle = window.RufflePlayer.newest();
  const player = ruffle.createPlayer();
  player.style.width = "100%";
  player.style.height = "100%";
  host.appendChild(player);
  try {
    await player.load({
      url: "/preview.swf?v=43-json",
      allowScriptAccess: true,
      autoplay: "on",
      unmuteOverlay: "hidden",
      splashScreen: false,
      letterbox: "on",
      wmode: "transparent",
    });
  } catch (err) {
    console.warn("preview.swf load failed:", err);
  }
  for (let i = 0; i < 90; i++) {
    if (
      typeof player.searchAssets === "function" &&
      typeof player.previewAsset === "function" &&
      typeof player.changeAttr === "function"
    ) {
      break;
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  return player;
}

/**
 * Visor Stage: Vector Flash preview in HD (both Objeto and Puesto modes).
 * - "object" mode: calls player.previewAsset(`${pack}.${leaf}`) for 100% crisp vector HD graphics.
 * - "worn" mode: seeds asset domain, waits, and calls showPreviewLook(player, payload) once to dress Gaturro.
 * - Non-wearable items (room objects / consumables) display an informative banner.
 */
export default function RuffleStage({
  pack,
  name,
  item = null,
  mode = "object",
  onSwitchMode,
  suspended = false,
}) {
  const hostRef = useRef(null);
  const playerRef = useRef(null);
  const readyRef = useRef(false);
  useRuffleActivity(playerRef, suspended, readyRef, !!(pack && name));
  const seededSeedRef = useRef("");
  const genRef = useRef(0);

  const [loadingMsg, setLoadingMsg] = useState("");
  const [stageError, setStageError] = useState(false);

  const isHouseObject = Boolean(
    item?.so ||
      item?.category === "house" ||
      (name && (name.endsWith("_so") || name.includes("_so_")))
  );
  const isConsumable = Boolean(
    item?.class === "ConsumableMamboAsset" ||
      item?.category === "consumable" ||
      item?.category === "food" ||
      (name && /^jugo|^comida|^pocion|^torta|^helado/i.test(name))
  );
  const isCloth = Boolean(
    item?.class === "ClothMamboAsset" ||
      item?.category === "visualizer" ||
      (!isHouseObject && !isConsumable && item?.inventory === "visualizer")
  );
  const isWearable = !isHouseObject && !isConsumable;

  const hasSelection = !!(pack && name);

  // Allocate Flash only when there is an actual object to display.
  useEffect(() => {
    if (!hasSelection) return;
    let cancelled = false;
    (async () => {
      try {
        if (!hostRef.current) return;
        setLoadingMsg("Iniciando visor…");
        const player = await createPlayerInHost(hostRef.current);
        if (cancelled || !player) {
          if (!cancelled) setStageError(true);
          return;
        }
        playerRef.current = player;
        sharedPlayer = player;
        sharedReady = true;
        readyRef.current = true;
        setLoadingMsg("");
      } catch (err) {
        console.warn("Stage player init error:", err);
        if (!cancelled) setStageError(true);
      }
    })();

    return () => {
      cancelled = true;
      readyRef.current = false;
      sharedReady = false;
      sharedPlayer = null;
      playerRef.current = null;
      if (hostRef.current) hostRef.current.innerHTML = "";
    };
  }, [hasSelection]);

  // Sync mode and selected item
  useEffect(() => {
    if (!pack || !name) {
      setLoadingMsg("");
      return;
    }

    const gen = ++genRef.current;
    let cancelled = false;

    (async () => {
      // Wait for player to be ready
      for (let i = 0; i < 60 && (!playerRef.current || !readyRef.current); i++) {
        await new Promise((r) => setTimeout(r, 100));
      }
      if (cancelled || gen !== genRef.current || !playerRef.current) return;

      await new Promise((resolve) => setTimeout(resolve, 100));
      if (cancelled || gen !== genRef.current) return;
      const player = playerRef.current;
      const leaf = String(name).replace(/_on$/, "").trim();
      const seed = `${pack}.${leaf}`;

      if (mode === "object") {
        setLoadingMsg("Cargando objeto…");
        setStageError(false);
        try {
          if (typeof player.clearAsset === "function") {
            try {
              player.clearAsset();
            } catch (_) {}
          }
          if (typeof player.previewAsset !== "function") {
            setStageError(true);
            setLoadingMsg("");
            return;
          }
          showPreviewObject(player, seed);
          seededSeedRef.current = seed;
          if (!cancelled && gen === genRef.current) {
            setLoadingMsg("");
          }
        } catch (e) {
          console.warn("previewAsset failed:", e);
          if (!cancelled && gen === genRef.current) {
            setStageError(true);
            setLoadingMsg("");
          }
        }
        return;
      }

      // mode === "worn"
      if (!isWearable) {
        setLoadingMsg("");
        return;
      }

      setLoadingMsg("Cargando personaje…");
      setStageError(false);
      try {
        // Seed asset into Flash if not already seeded
        if (typeof player.previewAsset === "function" && seededSeedRef.current !== seed) {
          try {
            showPreviewObject(player, seed);
          } catch (_) {}
          await new Promise((r) => setTimeout(r, 850));
          if (cancelled || gen !== genRef.current) return;
          seededSeedRef.current = seed;
        }

        if (typeof player.changeAttr !== "function") {
          setStageError(true);
          setLoadingMsg("");
          return;
        }

        // Global Flash callbacks can belong to the indexer or a modal player.
        // Derive this preview from the selected item, never another player's attrs.
        const baseAttrs = getWornAttrsForItem(pack, leaf, item);
        const remappedAttrs = remapWearAttrsForPreview(baseAttrs);
        const payload = JSON.stringify(remappedAttrs);

        if (typeof player.clearAsset === "function") {
          try {
            player.clearAsset();
          } catch (_) {}
        }

        // Apply attributes to Gaturro
        showPreviewLook(player, payload);
        if (!cancelled && gen === genRef.current) {
          setLoadingMsg("");
        }
      } catch (err) {
        console.warn("Worn preview failed:", err);
        if (!cancelled && gen === genRef.current) {
          setStageError(true);
          setLoadingMsg("");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pack, name, mode, isWearable]);

  const categoryLabel = isHouseObject
    ? "Casa / Sala"
    : isConsumable
      ? "Consumible"
      : isCloth
        ? "Ropa / Prenda"
        : item?.inventory_label || item?.category || "Objeto";

  const frameCount = item?.frameCount || (item?.animated ? "Multi-frame" : null);

  return (
    <div className="stage-box">
      {/* Empty State */}
      {!pack && <div className="stage-overlay empty">Tocá un objeto para ver el visor</div>}

      {/* Ruffle Host (Always mounted for instant response and vector rendering) */}
      <div
        ref={hostRef}
        className="stage-host"
        style={{
          display: !pack || (mode === "worn" && !isWearable) ? "none" : "block",
          opacity: loadingMsg ? 0.4 : 1,
          transition: "opacity 0.2s ease",
        }}
      />

      {/* Loading Overlay */}
      {pack && loadingMsg && (
        <div className="stage-overlay" style={{ fontSize: 12, color: "var(--muted)" }}>
          {loadingMsg}
        </div>
      )}

      {/* Error Fallback */}
      {pack && stageError && !loadingMsg && (
        <div className="stage-fallback">
          <div style={{ fontSize: 12, color: "var(--muted)", textAlign: "center" }}>
            No se pudo cargar la vista del objeto.
          </div>
          {onSwitchMode && mode === "worn" && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => onSwitchMode("object")}
            >
              Volver a objeto
            </button>
          )}
        </div>
      )}

      {/* Worn Mode: Non-wearable item notice */}
      {pack && name && mode === "worn" && !isWearable && (
        <div className="stage-fallback" style={{ textAlign: "center", padding: 18 }}>
          <div style={{ fontSize: 28, marginBottom: 6 }}>{isHouseObject ? "🏠" : "🥤"}</div>
          <div style={{ fontWeight: 650, color: "#fff", fontSize: 13 }}>
            {isHouseObject ? "Objeto de sala / casa" : "Objeto consumible"}
          </div>
          <div
            style={{
              color: "var(--muted)",
              fontSize: 11.5,
              maxWidth: 220,
              lineHeight: 1.4,
              marginTop: 4,
            }}
          >
            {isHouseObject
              ? "Los objetos de casa (_so) son mobiliario de salas y no se pueden vestir en el personaje."
              : "Este ítem es un consumible/objeto y no se puede vestir en el personaje."}
          </div>
          {onSwitchMode && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ marginTop: 12 }}
              onClick={() => onSwitchMode("object")}
            >
              Ver como objeto
            </button>
          )}
        </div>
      )}

      {/* Badges strip on the bottom */}
      {pack && name && (
        <div className="stage-badges-bar">
          <span className={`stage-chip ${isHouseObject ? "so" : "accent"}`}>
            {categoryLabel}
          </span>
          {frameCount && (
            <span className="stage-chip">
              {typeof frameCount === "number" ? `${frameCount} frames` : frameCount}
            </span>
          )}
          {item?.class && (
            <span className="stage-chip" style={{ opacity: 0.85 }}>
              {item.class.replace("MamboAsset", "")}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
