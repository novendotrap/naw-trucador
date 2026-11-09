import { useRuffleActivity } from "../hooks/useRuffleActivity";
import { useEffect, useRef, useState, useCallback } from "react";
import { Play, Pause, RotateCcw, Repeat } from "lucide-react";

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

export default function AnimPreviewStage({
  action = "standBy",
  propItem = null, // { pack, obj } or string "pack.obj"
  look = null,
  height = 240,
  loop = true,
}) {
  const hostRef = useRef(null);
  const playerRef = useRef(null);
  const readyRef = useRef(false);
  useRuffleActivity(playerRef, false, readyRef);
  const [isReady, setIsReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const [isLooping, setIsLooping] = useState(loop);
  const [statusMsg, setStatusMsg] = useState("Cargando visor...");

  // Mount Ruffle Player with /anim_preview.swf
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
          url: "/anim_preview.swf?v=" + Date.now(),
          allowScriptAccess: true,
          autoplay: "on",
          unmuteOverlay: "hidden",
          splashScreen: false,
          letterbox: "on",
          wmode: "transparent",
        });

        for (let i = 0; i < 60; i++) {
          if (typeof player.playAction === "function") break;
          await new Promise((r) => setTimeout(r, 80));
        }

        readyRef.current = typeof player.playAction === "function";
        if (readyRef.current && !cancelled) {
          setIsReady(true);
          setStatusMsg("");
        } else if (!cancelled) {
          setStatusMsg("No se pudo iniciar el reproductor SWF.");
        }
      } catch (err) {
        console.warn("AnimPreviewStage mount error:", err);
        if (!cancelled) setStatusMsg("Error al cargar Ruffle.");
      }
    })();

    return () => {
      cancelled = true;
      readyRef.current = false;
      setIsReady(false);
      playerRef.current = null;
      if (hostRef.current) hostRef.current.innerHTML = "";
    };
  }, []);

  // Update Action and Loop
  useEffect(() => {
    if (!isReady || !playerRef.current) return;
    const player = playerRef.current;
    const act = action || "standBy";
    try {
      if (typeof player.playAction === "function") {
        player.playAction(act, isLooping);
        setIsPlaying(true);
      }
    } catch (err) {
      console.warn("playAction error:", err);
    }
  }, [action, isLooping, isReady]);

  // Update Prop
  useEffect(() => {
    if (!isReady || !playerRef.current) return;
    const player = playerRef.current;
    let pack = "";
    let obj = "";
    if (propItem) {
      if (typeof propItem === "string" && propItem.includes(".")) {
        const parts = propItem.split(".");
        pack = parts[0];
        obj = parts[1];
      } else if (typeof propItem === "object") {
        pack = propItem.pack || "";
        obj = propItem.obj || propItem.name || "";
      }
    }

    try {
      if (pack && obj) {
        if (typeof player.setProp === "function") {
          player.setProp(pack, obj);
        }
      } else {
        if (typeof player.clearProp === "function") {
          player.clearProp();
        }
      }
    } catch (err) {
      console.warn("setProp error:", err);
    }
  }, [propItem, isReady]);

  // Update Look (if available)
  useEffect(() => {
    if (!isReady || !playerRef.current) return;
    const player = playerRef.current;
    try {
      if (look && typeof look === "object" && typeof player.wearLook === "function") {
        const partsMap = {};
        if (look.parts && typeof look.parts === "object") {
          for (const [slot, item] of Object.entries(look.parts)) {
            if (typeof item === "string" && item.includes(".")) {
              const [p, o] = item.split(".");
              partsMap[slot] = { pack: p, leaf: o };
            }
          }
        }
        player.wearLook(JSON.stringify(partsMap));
      }
    } catch (err) {
      console.warn("wearLook error:", err);
    }
  }, [look, isReady]);

  // Controls
  const togglePlay = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    try {
      if (isPlaying) {
        player.stopAction?.();
        setIsPlaying(false);
      } else {
        player.resumeAction?.();
        setIsPlaying(true);
      }
    } catch (err) {
      console.warn("togglePlay error:", err);
    }
  }, [isPlaying]);

  const restart = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    try {
      player.restartAction?.();
      setIsPlaying(true);
    } catch (err) {
      console.warn("restart error:", err);
    }
  }, []);

  const toggleLoop = useCallback(() => {
    setIsLooping((prev) => !prev);
  }, []);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height,
        background: "radial-gradient(ellipse at center, rgba(30, 41, 59, 0.4) 0%, rgba(15, 23, 42, 0.7) 100%)",
        borderRadius: 12,
        border: "1px solid rgba(255, 255, 255, 0.08)",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Ruffle Host */}
      <div
        ref={hostRef}
        style={{
          flex: 1,
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      />

      {/* Loading / Status Overlay */}
      {statusMsg && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(10, 12, 18, 0.8)",
            color: "var(--muted)",
            fontSize: 12,
            pointerEvents: "none",
          }}
        >
          {statusMsg}
        </div>
      )}

      {/* Current Action Badge */}
      <div
        style={{
          position: "absolute",
          top: 8,
          left: 8,
          padding: "2px 8px",
          background: "rgba(0, 0, 0, 0.55)",
          backdropFilter: "blur(4px)",
          borderRadius: 6,
          border: "1px solid rgba(255, 255, 255, 0.1)",
          fontSize: 11,
          fontWeight: 600,
          color: "#a5b4fc",
          pointerEvents: "none",
        }}
      >
        {action}
      </div>

      {/* Playback Controls Floating Bar */}
      <div
        style={{
          position: "absolute",
          bottom: 8,
          right: 8,
          display: "flex",
          gap: 4,
          padding: "3px 6px",
          background: "rgba(0, 0, 0, 0.65)",
          backdropFilter: "blur(6px)",
          borderRadius: 8,
          border: "1px solid rgba(255, 255, 255, 0.1)",
        }}
      >
        <button
          type="button"
          onClick={togglePlay}
          className="btn btn-ghost btn-sm"
          style={{ padding: "4px 6px", height: "auto" }}
          title={isPlaying ? "Pausar" : "Reproducir"}
        >
          {isPlaying ? <Pause size={12} /> : <Play size={12} />}
        </button>
        <button
          type="button"
          onClick={restart}
          className="btn btn-ghost btn-sm"
          style={{ padding: "4px 6px", height: "auto" }}
          title="Reiniciar animación"
        >
          <RotateCcw size={12} />
        </button>
        <button
          type="button"
          onClick={toggleLoop}
          className="btn btn-ghost btn-sm"
          style={{
            padding: "4px 6px",
            height: "auto",
            color: isLooping ? "#818cf8" : "var(--muted)",
          }}
          title={isLooping ? "Bucle activado" : "Bucle desactivado"}
        >
          <Repeat size={12} />
        </button>
      </div>
    </div>
  );
}
