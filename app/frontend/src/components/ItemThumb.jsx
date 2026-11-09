import { memo, useEffect, useState } from "react";
import { api } from "../api/client";
import { getCachedThumb, subscribeThumbs, thumbKey } from "../thumbs/bridge";

/**
 * Flash cache → disco (/api/thumbs/file) → JPEG embebido → iniciales.
 * Memoizado para evitar re-renderizados innecesarios en grillas grandes.
 */
function ItemThumb({ pack, name, size = 64, srcOverride = "" }) {
  const key = thumbKey(pack, name);
  const [src, setSrc] = useState(() => srcOverride || getCachedThumb(pack, name));
  const [diskFailed, setDiskFailed] = useState(false);
  const [apiFailed, setApiFailed] = useState(false);

  useEffect(() => {
    if (srcOverride) {
      setSrc(srcOverride);
      return undefined;
    }
    setSrc(getCachedThumb(pack, name));
    setDiskFailed(false);
    setApiFailed(false);
    return subscribeThumbs((k, dataUrl) => {
      setSrc(dataUrl);
      setDiskFailed(false);
      setApiFailed(false);
    }, key);
  }, [pack, name, key, srcOverride]);

  const initials = (name || "?").slice(0, 2).toUpperCase();
  const diskUrl = !src && !srcOverride && pack && name ? api.cachedThumbUrl(pack, name) : "";
  const apiUrl =
    !src && !srcOverride && diskFailed && pack && name ? api.thumbUrl(pack, name) : "";

  return (
    <div className="item-thumb" style={{ width: size, height: size }}>
      {src ? (
        <img src={src} alt="" draggable={false} loading="lazy" decoding="async" />
      ) : diskUrl && !diskFailed ? (
        <img
          src={diskUrl}
          alt=""
          draggable={false}
          loading="lazy"
          decoding="async"
          onError={() => setDiskFailed(true)}
        />
      ) : apiUrl && !apiFailed ? (
        <img
          src={apiUrl}
          alt=""
          draggable={false}
          loading="lazy"
          decoding="async"
          onLoad={(e) => {
            if (!e.currentTarget.naturalWidth) setApiFailed(true);
          }}
          onError={() => setApiFailed(true)}
        />
      ) : (
        <span className="avatar">{initials}</span>
      )}
    </div>
  );
}

export default memo(ItemThumb);
