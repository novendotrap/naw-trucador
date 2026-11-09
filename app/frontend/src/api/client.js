import { describeLolaPayload, isDeliverableItem } from "../look/lolaPayload";
async function request(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    const err = new Error(data.error || `HTTP ${res.status}`);
    err.data = data;
    throw err;
  }
  if (opts.method && opts.method !== "GET" && /^\/api\/(payload\/set|behaviors\/activate|tiendas\/activate|trucar\/|effects\/|quick-start)/.test(path)) {
    window.dispatchEvent(new Event("naw:lola-changed"));
  }
  return data;
}

export const api = {
  status: () => request("/api/status"),
  logs: (n = 80) => request(`/api/logs?n=${n}`),

  proxyStart: () => request("/api/proxy/start", { method: "POST", body: "{}" }),
  proxyStop: () => request("/api/proxy/stop", { method: "POST", body: "{}" }),

  quickStart: (body = {}) =>
    request("/api/quick-start", { method: "POST", body: JSON.stringify(body) }),
  launchGame: (clean_cache = true) =>
    request("/api/game/launch", {
      method: "POST",
      body: JSON.stringify({ clean_cache }),
    }),
  killGame: () => request("/api/game/kill", { method: "POST", body: "{}" }),
  cleanCache: () =>
    request("/api/game/clean-cache", { method: "POST", body: "{}" }),

  getPayload: async () => {
    const data = await request("/api/payload/get");
    return { ...data, active: data.active || describeLolaPayload(data.payload || "") };
  },
  setPayload: (payload) =>
    request("/api/payload/set", {
      method: "POST",
      body: JSON.stringify({ raw: payload }),
    }),
  setPayloadItems: (items) => {
    const deliverable = items.filter(isDeliverableItem);
    if (!deliverable.length) return Promise.reject(new Error("No hay objetos para enviar: las variantes _so están excluidas."));
    return request("/api/payload/set", {method:"POST", body:JSON.stringify({items:deliverable})});
  },

  listSwfs: (q = "", theme = "") => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (theme) params.set("theme", theme);
    const qs = params.toString();
    return request(`/api/swfs${qs ? `?${qs}` : ""}`);
  },
  listThemes: () => request("/api/themes"),
  inspectSwf: (name) =>
    request(`/api/swf/inspect?name=${encodeURIComponent(name)}`),
  thumbUrl: (pack, name) =>
    `/api/assets/thumb?pack=${encodeURIComponent(pack)}&name=${encodeURIComponent(name)}`,
  cachedThumbUrl: (pack, name) =>
    `/api/thumbs/file?pack=${encodeURIComponent(pack)}&name=${encodeURIComponent(name)}&v=2`,

  thumbsStats: () => request("/api/thumbs/stats"),
  thumbsCoverage: (include_stale = false) =>
    request(`/api/thumbs/coverage${include_stale ? "?include_stale=1" : ""}`),
  thumbsReindex: () => request("/api/thumbs/reindex", { method: "POST", body: "{}" }),
  thumbsExport: () => request("/api/thumbs/export", { method: "POST", body: "{}" }),
  thumbsExportStatus: () => request("/api/thumbs/export/status"),
  thumbsExportUrl: () => "/api/thumbs/export/file",
  thumbsImport: async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/thumbs/import", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    return data;
  },
  searchByKeyword: (q = "", theme = "", limit = 80) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (theme) params.set("theme", theme);
    params.set("limit", String(limit));
    return request(`/api/search/by-keyword?${params.toString()}`);
  },
  removeBackground: async ({ dataUrl, file, mode = "smart" } = {}) => {
    if (file && !dataUrl) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mode", mode);
      const res = await fetch("/api/image/remove-background", { method: "POST", body: fd });
      return await res.json();
    }
    return request("/api/image/remove-background", {
      method: "POST",
      body: JSON.stringify({ data_url: dataUrl, mode }),
    });
  },
  searchByImage: async ({ file, dataUrl, theme = "", top_k = 40, exclude_pack = "", exclude_name = "" } = {}) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 90000);
    try {
      if (file && !dataUrl) {
        const fd = new FormData();
        fd.append("file", file);
        if (theme) fd.append("theme", theme);
        fd.append("top_k", String(top_k));
        if (exclude_pack) fd.append("exclude_pack", exclude_pack);
        if (exclude_name) fd.append("exclude_name", exclude_name);
        const res = await fetch("/api/search/by-image", { method: "POST", body: fd, signal: ctrl.signal });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.ok === false) {
          const err = new Error(
            data.loading
              ? "Índice visual cargando… reintentá en unos segundos"
              : data.error || `HTTP ${res.status}`
          );
          err.data = data;
          throw err;
        }
        return data;
      }
      const res = await fetch("/api/search/by-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          png: dataUrl,
          theme,
          top_k,
          exclude_pack,
          exclude_name,
        }),
        signal: ctrl.signal,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        const err = new Error(
          data.loading
            ? "Índice visual cargando… reintentá en unos segundos"
            : data.error || `HTTP ${res.status}`
        );
        err.data = data;
        throw err;
      }
      return data;
    } catch (e) {
      if (e?.name === "AbortError") {
        throw new Error("La búsqueda tardó demasiado. Reintentá.");
      }
      throw e;
    } finally {
      clearTimeout(timer);
    }
  },

  listTricks: () => request("/api/trucar/list"),
  listClasses: () => request("/api/trucar/clases"),
  changeClass: (body) =>
    request("/api/trucar/clase", { method: "POST", body: JSON.stringify(body) }),
  trucarRopa: (body) =>
    request("/api/trucar/ropa", { method: "POST", body: JSON.stringify(body) }),
  deleteTrick: (pack, obj) =>
    request(`/api/trucar/${encodeURIComponent(pack)}/${encodeURIComponent(obj)}`, {
      method: "DELETE",
    }),
  queueTricks: (body) =>
    request("/api/trucar/queue", { method: "POST", body: JSON.stringify(body) }),

  listActions: () => request("/api/actions"),
  listEffects: () => request("/api/effects"),
  saveEffect: (body) =>
    request("/api/effects/save", { method: "POST", body: JSON.stringify(body) }),
  deleteEffect: (id) =>
    request("/api/effects/delete", { method: "POST", body: JSON.stringify({ id }) }),
  queueEffectsToLola: (body = {}) =>
    request("/api/effects/queue-lola", { method: "POST", body: JSON.stringify(body) }),

  listBehaviors: (q = "", type = "") => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (type) params.set("type", type);
    const qs = params.toString();
    return request(`/api/behaviors${qs ? `?${qs}` : ""}`);
  },
  listTiendas: (q = "") =>
    request(`/api/behaviors${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  activateBehavior: ({ catalog = "", behavior = "", script = "" } = {}) =>
    request("/api/behaviors/activate", {
      method: "POST",
      body: JSON.stringify({ catalog, behavior, script }),
    }),
  activateTienda: (catalog) =>
    request("/api/behaviors/activate", {
      method: "POST",
      body: JSON.stringify({ catalog }),
    }),

  listOverrides: () => request("/api/overrides"),
  deleteOverride: (filename) =>
    request(`/api/overrides/${encodeURIComponent(filename)}`, { method: "DELETE" }),

  libraryStatus: () => request("/api/library/status"),
  libraryReview: () => request("/api/library/review", { method: "POST", body: "{}" }),
  libraryDownload: () =>
    request("/api/library/download", { method: "POST", body: "{}" }),
  libraryZip: () => request("/api/library/zip", { method: "POST", body: "{}" }),
  libraryDumpMmo: () =>
    request("/api/library/dump-mmo", { method: "POST", body: "{}" }),
  libraryJob: () => request("/api/library/job"),
};
