import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

export function useStatus(pollMs = 2000) {
  const [status, setStatus] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.status();
      setStatus(data);
      return data;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, pollMs);
    window.addEventListener("naw:lola-changed", refresh);
    return () => { clearInterval(id); window.removeEventListener("naw:lola-changed", refresh); };
  }, [refresh, pollMs]);

  return { status, refresh };
}
