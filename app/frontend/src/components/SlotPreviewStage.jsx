import { useRuffleActivity } from "../hooks/useRuffleActivity";
import { showPreviewObject, showPreviewLook } from "../look/previewPlayer";
import { useEffect, useRef, useState } from "react";
import {
  lookWearAttrs,
  remapWearAttrsForPreview,
  toClothesOnValue,
  wearKeyForLookSlot,
  previewVisualSlot,
} from "../look/slots";

let scriptPromise = null;

function ensureRuffle() {
  if (window.RufflePlayer?.newest) return Promise.resolve(window.RufflePlayer);
  if (scriptPromise) return scriptPromise;
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
  scriptPromise = new Promise((resolve, reject) => {
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
  return scriptPromise;
}

/**
 * Un solo player Ruffle para el modal de slots (objeto + puesto),
 * aislado del visor principal — misma idea que slotVizPlayer del panel web.
 */
export default function SlotPreviewStage({
  item, // { pack, name }
  mode, // object | worn
  look,
  pickSlot, // slot key or null
  withLook,
}) {
  const hostRef = useRef(null);
  const playerRef = useRef(null);
  const readyRef = useRef(false);
  useRuffleActivity(playerRef, false, readyRef);
  const seededPacksRef = useRef(new Set());
  const genRef = useRef(0);
  const [msg, setMsg] = useState("Cargando…");

  // Mount once: create dedicated player, destroy on unmount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await ensureRuffle();
        if (cancelled || !hostRef.current) return;
        hostRef.current.innerHTML = "";
        const ruffle = window.RufflePlayer.newest();
        const player = ruffle.createPlayer();
        player.style.width = "100%";
        player.style.height = "100%";
        hostRef.current.appendChild(player);
        playerRef.current = player;
        await player.load({
          url: "/preview.swf?v=43-json",
          allowScriptAccess: true,
          autoplay: "on",
          unmuteOverlay: "hidden",
          splashScreen: false,
          letterbox: "on",
          wmode: "transparent",
        });
        for (let i = 0; i < 90; i++) {
          if (
            typeof player.previewAsset === "function" &&
            typeof player.changeAttr === "function"
          ) {
            break;
          }
          await new Promise((r) => setTimeout(r, 80));
        }
        readyRef.current = typeof player.previewAsset === "function";
        if (!readyRef.current && !cancelled) setMsg("No se pudo abrir el visualizer.");
      } catch (e) {
        console.warn(e);
        if (!cancelled) setMsg("No se pudo abrir el visualizer.");
      }
    })();
    return () => {
      cancelled = true;
      readyRef.current = false;
      seededPacksRef.current.clear();
      playerRef.current = null;
      if (hostRef.current) hostRef.current.innerHTML = "";
    };
  }, []);

  useEffect(() => {
    if (!item?.pack || !item?.name) return;
    const gen = ++genRef.current;
    let cancelled = false;

    (async () => {
      for (let i = 0; i < 50 && (!playerRef.current || !readyRef.current); i++) {
        await new Promise((r) => setTimeout(r, 100));
      }
      if (cancelled || gen !== genRef.current || !playerRef.current) return;
      await new Promise((resolve) => setTimeout(resolve, 100));
      if (cancelled || gen !== genRef.current) return;
      const player = playerRef.current;
      const leaf = String(item.name).replace(/_on$/, "");
      const seed = `${item.pack}.${leaf}`;

      if (mode === "object") {
        setMsg("Cargando el objeto…");
        try {
          if (typeof player.previewAsset !== "function") {
            setMsg("No se pudo mostrar el objeto.");
            return;
          }
          showPreviewObject(player, seed);
          setMsg("");
        } catch (e) {
          console.warn(e);
          setMsg("No se pudo mostrar el objeto.");
        }
        return;
      }

      // worn
      if (!pickSlot) {
        setMsg("Tocá una parte para verla puesta");
        return;
      }
      if (typeof player.clearAsset === "function") {
        try {
          player.clearAsset();
        } catch (_) {}
      }
      setMsg("Cargando el gaturro…");
      try {
        const value = toClothesOnValue(item.pack, leaf);
        const attrs = withLook ? lookWearAttrs(look, null) : {};
        attrs[wearKeyForLookSlot(previewVisualSlot(pickSlot))] = value;
        const remapped = remapWearAttrsForPreview(attrs);
        const json = JSON.stringify(remapped);

        // Preload/seed any packs that Flash has not yet loaded into ApplicationDomain
        const neededPacks = new Set();
        if (item.pack) neededPacks.add(item.pack);
        for (const v of Object.values(attrs)) {
          if (typeof v === "string" && v.includes(".")) {
            const p = v.split(".")[0];
            if (p) neededPacks.add(p);
          }
        }

        let seededAny = false;
        for (const p of neededPacks) {
          if (!seededPacksRef.current.has(p)) {
            seededPacksRef.current.add(p);
            seededAny = true;
            try {
              if (typeof player.searchAssets === "function") {
                player.searchAssets(p);
              } else if (typeof player.previewAsset === "function") {
                showPreviewObject(player, `${p}.${leaf}`);
              }
            } catch (_) {}
          }
        }

        if (seededAny) {
          await new Promise((r) => setTimeout(r, 800));
          if (cancelled || gen !== genRef.current) return;
        }

        if (typeof player.clearAsset === "function") {
          try {
            player.clearAsset();
          } catch (_) {}
        }

        if (typeof player.changeAttr !== "function") {
          setMsg("No se pudo vestir al gaturro.");
          return;
        }
        showPreviewLook(player, json);
        setMsg("");
      } catch (e) {
        console.warn(e);
        setMsg("No se pudo vestir al gaturro.");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [item?.pack, item?.name, mode, pickSlot, withLook, look]);

  return (
    <div className="slot-preview-stage">
      <div ref={hostRef} className="slot-preview-host" style={{ opacity: msg ? 0.4 : 1 }} />
      {msg ? <div className="slot-preview-msg">{msg}</div> : null}
    </div>
  );
}
