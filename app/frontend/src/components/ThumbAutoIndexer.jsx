import { useEffect } from "react";
import { startAutoIndexer } from "../thumbs/autoIndexer";

/**
 * Arranca el indexado completo de thumbs al montar la app.
 * El trabajo corre en un Ruffle oculto (ver autoIndexer.js).
 */
export default function ThumbAutoIndexer() {
  useEffect(() => {
    const t = setTimeout(() => {
      startAutoIndexer().catch(() => {});
    }, 1200);
    return () => clearTimeout(t);
  }, []);

  return null;
}
