import { useRuffleActivity } from "../hooks/useRuffleActivity";
import { showPreviewObject, showPreviewLook } from "../look/previewPlayer";
import { useEffect, useRef, useState } from "react";
import { lookWearAttrs, remapWearAttrsForPreview } from "../look/slots";
import { bindFlashThumbBridge } from "../thumbs/bridge";

bindFlashThumbBridge();

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
      if (window.RufflePlayer?.newest) return resolve(window.RufflePlayer);
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
 * Shows the gaturro wearing look parts via preview.swf changeAttr.
 */
export default function GaturroVisualizer({ look, onlySlot = null, height = 280 }) {
  const hostRef = useRef(null);
  const playerRef = useRef(null);
  const readyRef = useRef(false);
  useRuffleActivity(playerRef, false, readyRef);
  const seededPacksRef = useRef(new Set());
  const genRef = useRef(0);
  const [msg, setMsg] = useState("Cargando el gaturro…");

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
            typeof player.changeAttr === "function" &&
            typeof player.previewAsset === "function"
          ) {
            break;
          }
          await new Promise((r) => setTimeout(r, 80));
        }
        if (cancelled) return;
        readyRef.current = typeof player.changeAttr === "function";
        if (!readyRef.current) setMsg("No se pudo abrir el visualizer.");
      } catch (e) {
        console.warn("GaturroVisualizer mount error:", e);
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
    const curGen = ++genRef.current;
    let cancelled = false;

    (async () => {
      const attrs = lookWearAttrs(look, onlySlot);
      if (!Object.keys(attrs).length) {
        setMsg("Agregá alguna parte para verla en el gaturro.");
        return;
      }

      setMsg("Cargando el gaturro…");

      // Wait until player and changeAttr are fully ready
      for (let i = 0; i < 60; i++) {
        if (
          playerRef.current &&
          readyRef.current &&
          typeof playerRef.current.changeAttr === "function"
        ) {
          break;
        }
        await new Promise((r) => setTimeout(r, 100));
        if (cancelled || curGen !== genRef.current) return;
      }

      const player = playerRef.current;
      if (!player || typeof player.changeAttr !== "function") {
        setMsg("No se pudo vestir al gaturro.");
        return;
      }

      try {
        const remapped = remapWearAttrsForPreview(attrs);
        const json = JSON.stringify(remapped);

        // Preload/seed all needed packs into Flash ApplicationDomain
        const neededPacks = new Set();
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
                showPreviewObject(player, `${p}.dummy`);
              }
            } catch (_) {}
          }
        }

        if (seededAny) {
          await new Promise((r) => setTimeout(r, 750));
          if (cancelled || curGen !== genRef.current) return;
        }

        if (typeof player.clearAsset === "function") {
          try {
            player.clearAsset();
          } catch (_) {}
        }

        showPreviewLook(player, json);
        if (!cancelled && curGen === genRef.current) {
          setMsg("");
        }
      } catch (e) {
        console.warn("GaturroVisualizer changeAttr error:", e);
        if (!cancelled && curGen === genRef.current) {
          setMsg("No se pudo vestir al gaturro.");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [look, onlySlot]);

  return (
    <div className="gaturro-stage" style={{ height }}>
      <div ref={hostRef} className="gaturro-host" style={{ opacity: msg ? 0.35 : 1 }} />
      {msg ? <div className="gaturro-msg">{msg}</div> : null}
    </div>
  );
}
