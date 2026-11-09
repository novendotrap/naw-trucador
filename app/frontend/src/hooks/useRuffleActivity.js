import { useEffect } from "react";

export function watchRuffleActivity(player, suspended = false) {
  const sync = () => {
    if (document.hidden || suspended) player.pause?.();
    else player.play?.();
  };
  document.addEventListener("visibilitychange", sync);
  sync();
  return () => document.removeEventListener("visibilitychange", sync);
}

export function useRuffleActivity(playerRef, suspended = false, readyRef, active = true) {
  useEffect(() => {
    if (!active) return;
    let release;
    let cancelled = false;
    const attach = () => {
      if (cancelled) return;
      if (playerRef.current && (!readyRef || readyRef.current)) release = watchRuffleActivity(playerRef.current, suspended);
      else timer = setTimeout(attach, 100);
    };
    let timer;
    attach();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      release?.();
    };
  }, [playerRef, suspended, readyRef, active]);
}
