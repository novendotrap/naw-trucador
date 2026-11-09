import { isDeliverableItem } from "../look/lolaPayload";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { useToast } from "../hooks/useToast";
import QtyModal from "../components/QtyModal";
import ImageSearchModal from "../components/ImageSearchModal";
import RuffleStage, { refreshSharedStage } from "../components/RuffleStage";
import Field from "../components/Field";
import ErrorBoundary from "../components/ErrorBoundary";
import ItemThumb from "../components/ItemThumb";
import {
  clearViewerPack,
  getCachedThumb,
  noteViewerActivity,
  releaseViewerHold,
} from "../thumbs/bridge";
import {
  prioritizePackThumbs,
  resumeAutoIndexer,
  stopAutoIndexer,
  subscribeIndexer,
} from "../thumbs/autoIndexer";
import { emptyLook } from "../look/slots";
import { emptyEffect, effectHasContent } from "../look/effects";
import { THEMES, packMatchesTheme, itemMatchesTheme } from "../look/themes";
import SlotSelectorModal from "../components/SlotSelectorModal";

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("No se pudo leer la imagen"));
    reader.readAsDataURL(file);
  });
}

/** Memoized card to eliminate lag on large packs with 100+ items */
const ItemGridCard = memo(
  function ItemGridCard({ item, pack, sel, active, onSelect, onToggleCheck }) {
    return (
      <button
        type="button"
        className={`item-card ${sel ? "selected" : ""} ${active ? "active-preview" : ""}`}
        onClick={(e) => onSelect(item, e)}
      >
        <span
          className={`item-select-check ${sel ? "checked" : ""}`}
          title={sel ? "Deseleccionar" : "Seleccionar"}
          onClick={(e) => {
            e.stopPropagation();
            onToggleCheck(item);
          }}
        >
          {sel ? "✓" : ""}
        </span>
        <ItemThumb pack={pack} name={item.name} />
        <div className="name">{item.name}</div>
      </button>
    );
  },
  (prev, next) =>
    prev.pack === next.pack &&
    prev.item?.name === next.item?.name &&
    prev.sel === next.sel &&
    prev.active === next.active
);

export default function ObjetosPage({
  look,
  setLook,
  effectDraft,
  setEffectDraft,
  onNavigateTab,
  onOpenEffectModal,
  actions = [],
  onSaveEffect,
  previewSuspended = false,
  saveBlocked = false,
  effectSaving = false,
}) {
  const toast = useToast();
  const [swfs, setSwfs] = useState([]);
  const [swfQ, setSwfQ] = useState("");
  const [theme, setTheme] = useState("");
  const [showThemes, setShowThemes] = useState(() => {
    try {
      return localStorage.getItem("naw_show_themes") !== "false";
    } catch {
      return true;
    }
  });
  const [themeStats, setThemeStats] = useState([]);
  const [pack, setPack] = useState("");
  const [items, setItems] = useState([]);
  const [rightTab, setRightTab] = useState("look");
  const [localActions, setLocalActions] = useState([]);

  useEffect(() => {
    if (actions && actions.length > 0) {
      setLocalActions(actions);
    } else {
      api.listActions().then((res) => {
        if (res?.actions) setLocalActions(res.actions);
      }).catch(() => {});
    }
  }, [actions]);

  const setEffectBase = () => {
    if (!preview) return;
    const full = `${preview.pack}.${preview.name}`;
    if (setEffectDraft) {
      setEffectDraft((prev) => ({
        ...prev,
        baseItem: full,
        basePack: preview.pack,
        baseObj: preview.name,
      }));
    }
    setRightTab("effect");
    toast.success(`Base de efecto: ${preview.name} (mochila)`);
  };

  const setEffectProp = () => {
    if (!preview) return;
    const full = `${preview.pack}.${preview.name}`;
    if (setEffectDraft) {
      setEffectDraft((prev) => ({
        ...prev,
        subItem: full,
        subPack: preview.pack,
        subObj: preview.name,
      }));
    }
    setRightTab("effect");
    toast.success(`Prop en mano: ${preview.name}`);
  };
  const [itemQ, setItemQ] = useState("");
  const [selected, setSelected] = useState([]);
  const [preview, setPreview] = useState(null);
  const [visorMode, setVisorMode] = useState("object");
  const [mambo, setMambo] = useState(null);
  const [classModal, setClassModal] = useState(false);
  const [mamboClass, setMamboClass] = useState("NpcMamboAsset");
  const [qtyOpen, setQtyOpen] = useState(false);
  const [lolaQtyOpen, setLolaQtyOpen] = useState(false);
  const [slotPick, setSlotPick] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadingPack, setLoadingPack] = useState(false);
  const [imageHits, setImageHits] = useState(null);
  const [imageQuery, setImageQuery] = useState("");
  const [imageBusy, setImageBusy] = useState(false);
  const [imageModalOpen, setImageModalOpen] = useState(false);
  const [objectQ, setObjectQ] = useState("");
  const [keywordHits, setKeywordHits] = useState(null);
  const [keywordBusy, setKeywordBusy] = useState(false);
  const [hitMode, setHitMode] = useState(null); // 'image' | 'keyword' | null
  const [ioBusy, setIoBusy] = useState(false);
  const [ioStatus, setIoStatus] = useState("");
  const importRef = useRef(null);
  const [thumbStats, setThumbStats] = useState({ thumbs: 0, indexed: 0, packs: 0 });
  const [coverageData, setCoverageData] = useState(null);
  const [displayLimit, setDisplayLimit] = useState(80);
  const [indexer, setIndexer] = useState({
    running: false,
    paused: false,
    done: false,
    message: "",
    thumbs: 0,
    index: 0,
    total: 0,
  });

  const isIndex100Percent = useMemo(() => {
    if (!coverageData) return false;
    const missing = coverageData.missing || [];
    return missing.length === 0 && coverageData.done_packs > 0;
  }, [coverageData]);

  const refreshThumbStats = () => {
    api
      .thumbsStats()
      .then((d) =>
        setThumbStats({
          thumbs: d.thumbs || 0,
          indexed: d.indexed || d.thumbs || 0,
          packs: d.packs || 0,
        })
      )
      .catch(() => {});

    api
      .thumbsCoverage(false)
      .then((cov) => setCoverageData(cov))
      .catch(() => {});
  };

  useEffect(() => {
    api
      .listSwfs()
      .then((d) => setSwfs(d.swfs || d.items || []))
      .catch(() => toast.error("No se pudieron cargar los SWF"));
    api.listClasses().then(setMambo).catch(() => {});
    api
      .listThemes()
      .then((d) => setThemeStats(d.themes || []))
      .catch(() => setThemeStats(THEMES.map((t) => ({ ...t, pack_count: 0 }))));
    refreshThumbStats();
    const t = setInterval(refreshThumbStats, 10000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => subscribeIndexer(setIndexer), []);

  useEffect(() => () => clearViewerPack(), []);

  // Búsqueda cross-pack por palabra → objetos (no archivos SWF).
  useEffect(() => {
    const q = objectQ.trim();
    if (q.length < 2) {
      setKeywordHits(null);
      setKeywordBusy(false);
      setHitMode((m) => (m === "keyword" ? null : m));
      return undefined;
    }
    let cancelled = false;
    setKeywordBusy(true);
    const t = setTimeout(() => {
      api
        .searchByKeyword(q, theme, 80)
        .then((d) => {
          if (cancelled) return;
          const hits = d.hits || [];
          setKeywordHits(hits);
          setImageHits(null);
          setImageQuery("");
          setHitMode("keyword");
        })
        .catch(() => {
          if (cancelled) return;
          setKeywordHits([]);
          setHitMode("keyword");
        })
        .finally(() => {
          if (!cancelled) setKeywordBusy(false);
        });
    }, 280);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [objectQ, theme]);

  // Al cerrar el modal de slots, refrescar el visor compartido.
  useEffect(() => {
    if (slotPick) return undefined;
    if (!pack) return undefined;
    const t = setTimeout(() => {
      refreshSharedStage();
    }, 250);
    return () => clearTimeout(t);
  }, [slotPick, pack]);

  const needsPackThumbs = !!pack && (
    coverageData?.missing?.includes(pack) || coverageData?.stale?.includes(pack)
  );
  useEffect(() => {
    if (!needsPackThumbs) return undefined;
    const timer = setTimeout(() => prioritizePackThumbs(pack), 200);
    return () => clearTimeout(timer);
  }, [pack, needsPackThumbs]);

  const filteredSwfs = useMemo(() => {
    const q = swfQ.trim().toLowerCase();
    let list = swfs
      .map((s) => (typeof s === "string" ? s : s.name || s.pack || ""))
      .filter(Boolean)
      .map((n) => n.replace(/\.swf$/i, ""));
    if (theme) list = list.filter((n) => packMatchesTheme(n, theme));
    if (q) list = list.filter((n) => n.toLowerCase().includes(q));
    return list;
  }, [swfs, swfQ, theme]);

  const filteredItems = useMemo(() => {
    const q = itemQ.trim().toLowerCase();
    let list = items.filter(isDeliverableItem);
    if (theme) list = list.filter((it) => itemMatchesTheme(pack, it.name, theme));
    if (q) list = list.filter((it) => (it.name || "").toLowerCase().includes(q));
    return list;
  }, [items, itemQ, theme, pack]);

  const selectedPacks = useMemo(() => {
    const set = new Set((selected || []).map((s) => s.pack).filter(Boolean));
    return Array.from(set);
  }, [selected]);
  const selectedPacksCount = selectedPacks.length;

  // Set O(1) para lookups instantáneos sin lag en grillas grandes
  const selectedKeySet = useMemo(() => {
    const set = new Set();
    const arr = selected || [];
    for (let i = 0; i < arr.length; i++) {
      const s = arr[i];
      if (s && s.pack && s.name) set.add(`${s.pack}.${s.name}`);
    }
    return set;
  }, [selected]);

  const allVisibleSelected = useMemo(() => {
    if (!pack || !filteredItems.length) return false;
    for (let i = 0; i < filteredItems.length; i++) {
      if (!selectedKeySet.has(`${pack}.${filteredItems[i].name}`)) return false;
    }
    return true;
  }, [filteredItems, selectedKeySet, pack]);

  const toggleSelectVisibles = () => {
    if (!pack || !filteredItems.length) return;
    if (allVisibleSelected) {
      const visibleNames = new Set(filteredItems.map((it) => it.name));
      setSelected((prev) =>
        prev.filter((s) => !(s.pack === pack && visibleNames.has(s.name)))
      );
    } else {
      setSelected((prev) => {
        const map = new Map();
        for (let i = 0; i < prev.length; i++) {
          const it = prev[i];
          map.set(`${it.pack}.${it.name}`, it);
        }
        for (let i = 0; i < filteredItems.length; i++) {
          const it = filteredItems[i];
          map.set(`${pack}.${it.name}`, { ...it, pack, name: it.name });
        }
        return Array.from(map.values());
      });
    }
  };

  const toggleItemSelection = useCallback(
    (it) => {
      if (!it?.name || !pack) return;
      const fullItem = { ...it, pack, name: it.name };
      const key = `${pack}.${it.name}`;
      setSelected((prev) =>
        selectedKeySet.has(key)
          ? prev.filter((s) => !(s.pack === pack && s.name === it.name))
          : [...prev, fullItem]
      );
    },
    [pack, selectedKeySet]
  );

  const themeCountMap = useMemo(() => {
    const map = Object.fromEntries((themeStats || []).map((t) => [t.id, t.pack_count || 0]));
    return map;
  }, [themeStats]);

  const activeThemeObj = useMemo(() => THEMES.find((t) => t.id === theme) || null, [theme]);

  const clearCrossSearch = () => {
    setImageHits(null);
    setImageQuery("");
    setKeywordHits(null);
    setObjectQ("");
    setHitMode(null);
  };

  const openPack = async (name, opts = {}) => {
    const clean = String(name || "").replace(/\.swf$/i, "").trim();
    if (!clean) return;
    if (!opts.keepSearch) clearCrossSearch();
    setPack(clean);
    setDisplayLimit(80);
    // Persist multi-SWF selection across packs
    if (!opts.keepPreview) setPreview(null);
    setItems([]);
    setLoadingPack(true);
    try {
      const data = await api.inspectSwf(clean);
      if (!data.ok) throw new Error(data.error || "No se pudo leer");
      const classes = data.classes || data.items || [];
      const parsed = classes
        .map((c) => {
          if (typeof c === "string") return { name: c };
          const leaf = c.name || c.id || c.class || "";
          return { ...c, name: leaf };
        })
        .filter((c) => c.name);
      setItems(parsed);
      if (opts.selectName) {
        const found = parsed.find((x) => x.name === opts.selectName);
        setPreview(found ? { ...found, pack: clean, name: opts.selectName } : { pack: clean, name: opts.selectName });
      }
    } catch (e) {
      toast.error(e.message || "Error al inspeccionar");
      setItems([]);
    } finally {
      setLoadingPack(false);
    }
  };

  const runImageSearch = async ({ file, dataUrl, exclude } = {}) => {
    setImageBusy(true);
    try {
      if (file && !dataUrl) {
        dataUrl = await fileToDataUrl(file);
      }
      if (dataUrl) setImageQuery(dataUrl);
      const data = await api.searchByImage({
        file: dataUrl ? undefined : file,
        dataUrl,
        theme,
        top_k: 48,
        exclude_pack: exclude?.pack || "",
        exclude_name: exclude?.name || "",
      });
      const hits = data.hits || [];
      setImageHits(hits);
      setKeywordHits(null);
      setObjectQ("");
      setHitMode("image");
      setImageModalOpen(false);
      if (!hits.length) {
        const indexed = data.indexed || thumbStats.indexed || 0;
        toast.error(
          indexed < 5
            ? "Todavía hay pocos thumbs. Dejá indexar en segundo plano un rato."
            : "Sin parecidos con el índice actual."
        );
      } else {
        toast.success(`${hits.length} parecidos · índice ${data.indexed || "—"}`);
      }
      refreshThumbStats();
    } catch (e) {
      toast.error(e.message || "Error en búsqueda por imagen");
    } finally {
      setImageBusy(false);
    }
  };

  const searchSimilarToPreview = async () => {
    if (!preview) return;
    const mem = getCachedThumb(preview.pack, preview.name);
    if (mem) {
      await runImageSearch({
        dataUrl: mem,
        exclude: { pack: preview.pack, name: preview.name },
      });
      return;
    }
    try {
      const url = api.cachedThumbUrl(preview.pack, preview.name);
      const res = await fetch(url);
      if (!res.ok) throw new Error("Sin thumb guardado de este objeto");
      const blob = await res.blob();
      const dataUrl = await fileToDataUrl(blob);
      await runImageSearch({
        dataUrl,
        exclude: { pack: preview.pack, name: preview.name },
      });
    } catch (e) {
      toast.error(e.message || "No hay imagen de este objeto todavía");
    }
  };

  const rawCrossHits = hitMode === "image" ? imageHits : hitMode === "keyword" ? keywordHits : null;
  const crossHits = rawCrossHits?.filter(isDeliverableItem) ?? null;

  const exportThumbsIndex = async () => {
    setIoBusy(true);
    setIoStatus("Preparando export…");
    try {
      const start = await api.thumbsExport();
      if (!start.ok) throw new Error(start.error || "No se pudo empezar el export");
      // Poll hasta que termine
      for (;;) {
        await new Promise((r) => setTimeout(r, 350));
        const st = await api.thumbsExportStatus();
        const job = st.job || {};
        const pct = Math.max(0, Math.min(100, Number(job.pct) || 0));
        const done = Number(job.done) || 0;
        const total = Number(job.total) || 0;
        setIoStatus(
          job.message ||
            (total ? `Exportando ${done}/${total} · ${pct}%` : `Exportando… ${pct}%`)
        );
        if (!job.running) {
          const result = job.result || {};
          if (!result.ok) {
            throw new Error(result.error || job.message || "Falló el export");
          }
          const msg =
            result.message ||
            `Índice exportado · ${result.files || "?"} archivos · ${result.size_mb ?? "?"} MB`;
          setIoStatus(msg);
          toast.success(msg);
          const a = document.createElement("a");
          a.href = api.thumbsExportUrl();
          a.download = "thumbs_index.zip";
          document.body.appendChild(a);
          a.click();
          a.remove();
          break;
        }
      }
    } catch (e) {
      setIoStatus("");
      toast.error(e.message || "Error al exportar");
    } finally {
      setIoBusy(false);
    }
  };

  const importThumbsIndex = async (file) => {
    if (!file) return;
    setIoBusy(true);
    setIoStatus(`Importando ${file.name}…`);
    try {
      const data = await api.thumbsImport(file);
      if (!data.ok) throw new Error(data.error || "No se pudo importar");
      const msg = data.message || "Índice importado";
      setIoStatus(msg);
      toast.success(msg);
      refreshThumbStats();
    } catch (e) {
      setIoStatus("");
      toast.error(e.message || "Error al importar");
    } finally {
      setIoBusy(false);
      if (importRef.current) importRef.current.value = "";
    }
  };

  const openImageHit = (hit) => {
    if (!hit?.pack || !hit?.name) return;
    setPreview({ ...hit, pack: hit.pack, name: hit.name });
    setVisorMode("object");
  };

  const goToSwf = async (targetPack, selectName) => {
    if (!targetPack) return;
    const cleanPack = String(targetPack).replace(/\.swf$/i, "").trim();
    clearCrossSearch();
    await openPack(cleanPack, {
      selectName: selectName || preview?.name,
      keepPreview: true,
    });
    setTimeout(() => {
      const el = document.querySelector(".swf-file-list button.active");
      if (el) {
        el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    }, 150);
  };

  const toggleSelect = useCallback(
    (it, ev) => {
      try {
        const id = it?.name;
        if (!id || !pack) return;
        noteViewerActivity();
        const fullItem = { ...it, pack, name: id };
        setPreview(fullItem);
        setVisorMode("object");

        if (ev?.ctrlKey || ev?.metaKey) {
          toggleItemSelection(it);
        } else if (selected.length <= 1) {
          setSelected([fullItem]);
        }
        // If selected.length > 1, regular click updates preview without discarding multi-pack selection
      } catch (e) {
        console.error(e);
        toast.error("No se pudo seleccionar el objeto");
      }
    },
    [pack, selected.length, toggleItemSelection, toast]
  );

  const setBase = () => {
    if (!preview) return;
    setLook((L) => ({
      ...L,
      baseSwf: preview.pack,
      baseObj: preview.name,
      baseThumb: api.thumbUrl(preview.pack, preview.name),
    }));
    toast.success(`Base: ${preview.name}`);
  };

  const addPart = (pick) => {
    const slot = typeof pick === "string" ? pick : pick?.slot;
    if (!preview || !slot) return;
    setLook((L) => ({
      ...L,
      parts: { ...L.parts, [slot]: `${preview.pack}.${preview.name}` },
      partsInfo: {
        ...L.partsInfo,
        [slot]: {
          pack: preview.pack,
          name: preview.name,
          thumb: api.thumbUrl(preview.pack, preview.name),
        },
      },
    }));
    setSlotPick(null);
    const label = typeof pick === "object" && pick?.label ? pick.label : slot;
    toast.success(`Parte asignada [${label}]: ${preview.name}`);
  };

  const handleOpenLolaQty = () => {
    if (!selected.length && !preview) {
      toast.error("Seleccioná al menos un objeto o abrí uno en el visor");
      return;
    }
    setLolaQtyOpen(true);
  };

  const handleLolaConfirm = async (qty) => {
    setLolaQtyOpen(false);
    const itemsToSend =
      selected.length > 0
        ? selected
        : preview
          ? [{ pack: preview.pack, name: preview.name }]
          : [];
    if (!itemsToSend.length) return;

    try {
      const n = Math.max(1, Math.min(99, parseInt(qty, 10) || 1));
      const payload = itemsToSend.filter(isDeliverableItem).map((it) => ({
        name: `${it.pack}.${it.name}`,
        swf: it.pack,
        item: it.name,
        qty: n,
      }));
      await api.setPayloadItems(payload);
      const packsCount = new Set(itemsToSend.map((s) => s.pack)).size;
      toast.success(
        payload.length === 1
          ? `Listo en Lola: ${payload[0].name} (x${n})`
          : `${payload.length} objetos listos en Lola (x${n}) · ${packsCount} pack(s)`
      );
    } catch (e) {
      toast.error(e.message || "No se pudo agregar a Lola");
    }
  };

  const applyClass = async (qty) => {
    setQtyOpen(false);
    if (!selected.length) return;
    setBusy(true);
    try {
      const byPack = {};
      for (const a of selected) {
        if (!byPack[a.pack]) byPack[a.pack] = [];
        byPack[a.pack].push(a.name);
      }
      let ok = 0;
      for (const p of Object.keys(byPack)) {
        const data = await api.changeClass({
          pack: p,
          classes: byPack[p],
          mambo_class: mamboClass,
          queue_lola: true,
          qty,
        });
        if (!data.ok) throw new Error(data.error || `Falló ${p}`);
        ok += data.count || byPack[p].length;
      }
      toast.success(`Clase aplicada · ${ok} objeto(s) · x${qty}`);
      setClassModal(false);
      if (pack) openPack(pack);
    } catch (e) {
      toast.error(e.message || "Error al cambiar clase");
    } finally {
      setBusy(false);
    }
  };

  const presets = mambo?.presets || [
    { id: "ClothMamboAsset", label: "Ropa (ClothMamboAsset)", inventory: "visualizer", inventory_label: "ropa puesta" },
    { id: "ConsumableMamboAsset", label: "Mochila (ConsumableMamboAsset)", inventory: "default", inventory_label: "mochila" },
    { id: "NpcMamboAsset", label: "Casa/NPC (recomendado)", inventory: "house", inventory_label: "casa" },
  ];

  const mamboOptions = mambo?.advanced?.length ? mambo.advanced : presets;

  const mamboOptionText = (a) => {
    const inv = a.inventory_label || ({ visualizer: "ropa puesta", default: "mochila", house: "casa" }[a.inventory] || "");
    const base = a.label || a.id;
    return inv ? `${base} · ${inv}` : base;
  };

  const selectedMamboMeta =
    mamboOptions.find((a) => a.id === mamboClass) ||
    presets.find((p) => p.id === mamboClass);

  return (
    <div className="stack" style={{ height: "100%" }}>
      <div>
        <div className="page-title">Objetos</div>
        <div className="page-sub">
          Temas · objetos por palabra · imagen. Thumbs: {thumbStats.thumbs || indexer.thumbs || 0}
          {coverageData?.total_packs
            ? ` · ${coverageData.total_packs} packs verificados`
            : thumbStats.packs
              ? ` · ${thumbStats.packs} packs`
              : ""}
          {indexer.running
            ? indexer.paused
              ? " · indexado en pausa"
              : " · indexando todos…"
            : isIndex100Percent
              ? " · índice listo (100% completo)"
              : indexer.done
                ? " · índice listo"
                : ""}
          .
        </div>
      </div>

      <div className="image-search-bar app-no-drag">
        <Field
          type="search"
          icon="search"
          placeholder='Buscar objetos… ej. halloween, mesa, fuego'
          value={objectQ}
          onChange={(e) => setObjectQ(e.target.value)}
          className="compact-field object-keyword-field"
        />
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={imageBusy}
          onClick={() => setImageModalOpen(true)}
        >
          {imageBusy ? "Buscando…" : "Buscar por imagen"}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={!preview || imageBusy}
          onClick={searchSimilarToPreview}
          title="Usa el thumb del objeto del visor"
        >
          Similares al visor
        </button>
        {crossHits ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={clearCrossSearch}>
            Limpiar búsqueda
          </button>
        ) : null}

        {imageQuery ? (
          <img className="image-search-query" src={imageQuery} alt="" />
        ) : null}
        {ioStatus ? <span className="image-search-status">{ioStatus}</span> : null}
        {keywordBusy ? (
          <span className="image-search-status">Buscando objetos…</span>
        ) : null}
        {(indexer.running || indexer.message) && (
          <span className="image-search-status">{indexer.message}</span>
        )}

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
          {indexer.running ? (
            indexer.paused ? (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  releaseViewerHold();
                  toast.info("Índice reanudado");
                }}
                title="El índice se pausa solo unos segundos al abrir un pack"
              >
                Reanudar índice
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => stopAutoIndexer()}
              >
                Detener índice
              </button>
            )
          ) : isIndex100Percent ? (
            <span
              className="badge"
              style={{
                background: "rgba(34, 197, 94, 0.12)",
                color: "#4ade80",
                border: "1px solid rgba(34, 197, 94, 0.25)",
                padding: "4px 8px",
                fontSize: "11px",
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
              }}
              title="Todos los packs disponibles tienen cobertura en el índice."
            >
              ✓ Índice completo
            </span>
          ) : (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                releaseViewerHold();
                resumeAutoIndexer();
                toast.info("Indexando solo packs faltantes (no borra lo ya guardado)…");
              }}
              title="Solo packs sin thumbs o incompletos. Los que ya están no se resetean."
            >
              Indexar faltantes
            </button>
          )}
          {!indexer.running && coverageData?.stale_packs > 0 && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={ioBusy}
              onClick={() => {
                releaseViewerHold();
                resumeAutoIndexer({ hd: true }).then(refreshThumbStats);
              }}
              title={`Recaptura hasta 120 px en ${coverageData.stale_packs} packs. El pack abierto tiene prioridad.`}
            >
              Mejorar todas las miniaturas
            </button>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={ioBusy || indexer.running}
            onClick={exportThumbsIndex}
            title="Exporta el índice y las miniaturas guardadas, incluidas las mejoradas"
          >
            Exportar
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={ioBusy || indexer.running}
            onClick={() => importRef.current?.click()}
            title="Importa un thumbs_index.zip (fusiona con lo local)"
          >
            Importar
          </button>
        </div>
        <input
          ref={importRef}
          type="file"
          accept=".zip,application/zip"
          style={{ display: "none" }}
          onChange={(e) => importThumbsIndex(e.target.files?.[0])}
        />
      </div>

      <div className={`theme-filter-box app-no-drag ${!showThemes ? "collapsed" : ""}`}>
        <div className="theme-filter-head">
          <div className="theme-filter-title">
            <span>🏷️ Temáticas ({THEMES.length})</span>
            {theme && activeThemeObj && !showThemes && (
              <span className="theme-active-pill">
                <span>{activeThemeObj.emoji} {activeThemeObj.label}</span>
                <button
                  type="button"
                  className="icon-btn-micro"
                  onClick={() => setTheme("")}
                  title="Quitar filtro"
                >
                  ✕
                </button>
              </span>
            )}
          </div>
          <div className="theme-filter-actions">
            {theme ? (
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                onClick={() => setTheme("")}
                title="Limpiar filtro de tema"
              >
                Limpiar filtro ✕
              </button>
            ) : null}
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              onClick={() => {
                setShowThemes((prev) => {
                  const next = !prev;
                  try {
                    localStorage.setItem("naw_show_themes", String(next));
                  } catch {}
                  return next;
                });
              }}
              title={showThemes ? "Ocultar panel de temáticas" : "Mostrar panel de temáticas"}
            >
              {showThemes ? "Ocultar filtros ▴" : "Mostrar filtros ▾"}
            </button>
          </div>
        </div>

        {showThemes && (
          <div className="theme-chip-row">
            <button
              type="button"
              className={`theme-chip ${!theme ? "active" : ""}`}
              onClick={() => setTheme("")}
            >
              Todos
            </button>
            {THEMES.map((t) => {
              const count = themeCountMap[t.id];
              return (
                <button
                  key={t.id}
                  type="button"
                  className={`theme-chip ${theme === t.id ? "active" : ""}`}
                  onClick={() => setTheme(theme === t.id ? "" : t.id)}
                  title={t.keywords.slice(0, 6).join(", ")}
                >
                  <span aria-hidden="true">{t.emoji}</span>
                  <span>{t.label}</span>
                  {typeof count === "number" ? <span className="theme-chip-count">{count}</span> : null}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="grid-3" style={{ minHeight: 520 }}>
        <div className="card" style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div className="card-title">
            <span>Archivos{theme ? " · tema" : ""}</span>
            <span className="badge">{filteredSwfs.length}</span>
          </div>
          <Field
            type="search"
            icon="search"
            placeholder={theme ? "Buscar dentro del tema..." : "Buscar archivo..."}
            value={swfQ}
            onChange={(e) => setSwfQ(e.target.value)}
            className="compact-field"
          />
          <div className="list-scroll swf-file-list" style={{ marginTop: 8 }}>
            {!filteredSwfs.length ? (
              <div className="empty" style={{ padding: 12 }}>
                {theme ? "Ningún pack de este tema." : "Sin archivos."}
              </div>
            ) : (
              filteredSwfs.map((n) => (
                <button
                  key={n}
                  type="button"
                  className={`list-item ${pack === n ? "active" : ""}`}
                  onClick={() => {
                    clearCrossSearch();
                    openPack(n);
                  }}
                >
                  {n}
                </button>
              ))
            )}
          </div>
        </div>

        <div className="card" style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div className="card-title">
            <span>
              {hitMode === "image"
                ? "Parecidos por imagen"
                : hitMode === "keyword"
                  ? (
                    <>
                      Objetos:{" "}
                      <strong style={{ color: "var(--accent-light)" }}>
                        {objectQ.trim() || "…"}
                      </strong>
                    </>
                  )
                  : (
                    <>
                      Adentro:{" "}
                      <strong style={{ color: "var(--accent-light)" }}>{pack || "ninguno"}</strong>
                    </>
                  )}
            </span>
            <span className="badge">{crossHits ? crossHits.length : filteredItems.length}</span>
          </div>
          {!crossHits ? (
            <div className="toolbar-row">
              <Field
                type="search"
                icon="search"
                placeholder={theme ? "Filtrar objetos del pack/tema..." : "Filtrar objetos del pack..."}
                value={itemQ}
                onChange={(e) => setItemQ(e.target.value)}
              />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={toggleSelectVisibles}
                disabled={!pack || !filteredItems.length}
                title={allVisibleSelected ? "Deseleccionar los objetos visibles de este pack" : "Agregar los objetos visibles de este pack a la selección"}
              >
                {allVisibleSelected ? "Desel. visibles" : "Sel. visibles"}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setSelected([])}
                disabled={!selected.length}
                title="Limpiar toda la selección"
              >
                Limpiar
              </button>
              <span
                className="badge badge-accent"
                title={selectedPacks.length > 0 ? `Packs seleccionados: ${selectedPacks.join(", ")}` : ""}
              >
                {selected.length === 0
                  ? "0 sel."
                  : selectedPacksCount > 1
                    ? `${selected.length} sel. (${selectedPacksCount} packs)`
                    : selected[0]?.pack && selected[0].pack !== pack
                      ? `${selected.length} sel. (${selected[0].pack})`
                      : `${selected.length} sel.`}
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={!selected.length && !preview}
                onClick={handleOpenLolaQty}
                title={
                  selected.length > 0
                    ? `Enviar ${selected.length} objeto(s) a Lola`
                    : "Enviar objeto del visor a Lola"
                }
              >
                Dar con Lola {selected.length ? `(${selected.length})` : ""}
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={!selected.length || busy}
                onClick={() => setClassModal(true)}
              >
                Cambiar clase {selected.length ? `(${selected.length})` : ""}
              </button>
            </div>
          ) : (
            <div className="toolbar-row" style={{ marginBottom: 8, justifyContent: "space-between" }}>
              <div className="card-sub" style={{ marginBottom: 0 }}>
                {hitMode === "keyword"
                  ? `Objetos que matchean “${objectQ.trim()}”${theme ? " · tema activo" : ""}. Tocá uno para ver el visor.`
                  : `Resultados cross-pack${theme ? " (filtrados por tema)" : ""}. Tocá uno para ver el visor.`}
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={clearCrossSearch}
                title="Cerrar búsqueda y volver a la vista normal"
              >
                Limpiar búsqueda ✕
              </button>
            </div>
          )}
          <div className="item-grid">
            {crossHits ? (
              crossHits.length ? (
                crossHits.map((hit) => {
                  const active = preview?.name === hit.name && preview?.pack === hit.pack;
                  const pct = Math.round((hit.score || 0) * 100);
                  return (
                    <button
                      type="button"
                      key={`${hit.pack}.${hit.name}`}
                      className={`item-card ${active ? "selected" : ""}`}
                      onClick={() => openImageHit(hit)}
                      title={`${hit.pack}.${hit.name} · ${pct}%`}
                    >
                      <ItemThumb
                        pack={hit.pack}
                        name={hit.name}
                        srcOverride={hit.thumb_url || ""}
                      />
                      <div className="name">{hit.name}</div>
                      <div className="name" style={{ opacity: 0.7 }}>
                        {hit.pack}
                        {hitMode === "image" ? ` · ${pct}%` : hit.match === "pack" ? " · pack" : ""}
                      </div>
                      <span
                        className="btn btn-secondary btn-sm"
                        style={{
                          fontSize: 10,
                          padding: "2px 8px",
                          marginTop: 4,
                          borderRadius: 6,
                          width: "100%",
                          fontWeight: 600,
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          goToSwf(hit.pack, hit.name);
                        }}
                        title={`Ir al SWF ${hit.pack}`}
                      >
                        Ir a SWF ➔
                      </span>
                    </button>
                  );
                })
              ) : (
                <div className="empty" style={{ gridColumn: "1/-1" }}>
                  {keywordBusy ? "Buscando…" : "Sin resultados."}
                </div>
              )
            ) : (
              <>
                {!pack && (
                  <div className="empty" style={{ gridColumn: "1/-1" }}>
                    Elegí un archivo o buscá objetos arriba.
                  </div>
                )}
                {pack && loadingPack && (
                  <div className="empty" style={{ gridColumn: "1/-1" }}>
                    Cargando objetos…
                  </div>
                )}
                {pack && !loadingPack && !filteredItems.length && (
                  <div className="empty" style={{ gridColumn: "1/-1" }}>
                    Sin objetos en este SWF.
                  </div>
                )}
                {filteredItems.slice(0, displayLimit).map((it) => {
                  const sel = selectedKeySet.has(`${pack}.${it.name}`);
                  const active = preview?.name === it.name && preview?.pack === pack;
                  return (
                    <ItemGridCard
                      key={it.name}
                      item={it}
                      pack={pack}
                      sel={sel}
                      active={active}
                      onSelect={toggleSelect}
                      onToggleCheck={toggleItemSelection}
                    />
                  );
                })}
                {filteredItems.length > displayLimit && (
                  <div
                    style={{
                      gridColumn: "1/-1",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 10,
                      padding: "14px 0",
                    }}
                  >
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setDisplayLimit((n) => n + 80)}
                    >
                      Mostrar más (+80)
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setDisplayLimit(filteredItems.length)}
                    >
                      Ver todos ({filteredItems.length})
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="card-title" style={{ justifyContent: "space-between" }}>
            <span>Visor</span>
            {preview ? (
              <span className="badge" style={{ fontSize: 10.5 }}>{preview.pack}</span>
            ) : null}
          </div>
          {preview ? (
            <>
              {Boolean(crossHits || (pack && preview.pack !== pack)) && (
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 6,
                    padding: "7px 12px",
                    fontWeight: 600,
                    fontSize: 12,
                    background: "linear-gradient(135deg, rgba(79, 142, 254, 0.25) 0%, rgba(59, 130, 246, 0.15) 100%)",
                    border: "1px solid rgba(79, 142, 254, 0.4)",
                    boxShadow: "0 2px 10px rgba(0, 0, 0, 0.25)",
                    width: "100%",
                  }}
                  onClick={() => goToSwf(preview.pack, preview.name)}
                  title={`Abrir ${preview.pack}.swf y ver todos sus objetos`}
                >
                  <span>Ir a este SWF</span>
                  <span className="badge badge-accent" style={{ fontSize: 10.5 }}>
                    {preview.pack}
                  </span>
                  <span>➔</span>
                </button>
              )}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 6,
                  padding: "6px 8px",
                  background: "rgba(255, 255, 255, 0.03)",
                  borderRadius: 8,
                  border: "1px solid var(--line)",
                }}
              >
                <div
                  className="mono"
                  style={{
                    fontSize: 11.5,
                    color: "#fff",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={`${preview.pack}.${preview.name}`}
                >
                  {preview.pack}.{preview.name}
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ padding: "2px 6px", height: 22, fontSize: 10.5 }}
                  onClick={() => {
                    navigator.clipboard.writeText(`${preview.pack}.${preview.name}`);
                    toast.success("Nombre copiado");
                  }}
                  title="Copiar nombre completo"
                >
                  Copiar
                </button>
              </div>
            </>
          ) : (
            <div className="card-sub" style={{ marginBottom: 0 }}>
              Tocá un objeto para ver el visor
            </div>
          )}
          {preview ? (
            <div className="visor-modes">
              <button
                type="button"
                className={`slot-viz-mode ${visorMode === "object" ? "active" : ""}`}
                onClick={() => setVisorMode("object")}
              >
                Objeto
              </button>
              <button
                type="button"
                className={`slot-viz-mode ${visorMode === "worn" ? "active" : ""}`}
                onClick={() => setVisorMode("worn")}
              >
                Puesto
              </button>
            </div>
          ) : null}
          <ErrorBoundary>
            <RuffleStage
              suspended={previewSuspended || !!slotPick || classModal || imageModalOpen || qtyOpen || lolaQtyOpen}
              pack={preview?.pack || ""}
              name={preview?.name || ""}
              item={preview}
              mode={visorMode}
              onSwitchMode={setVisorMode}
            />
          </ErrorBoundary>
          {/* Botones de acción del visor en cuadrícula 2x3 perfecta */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 4 }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!preview}
              onClick={() => setSlotPick(preview)}
              style={{ minWidth: 0, padding: "7px 8px", width: "100%" }}
            >
              Poner en look
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={!preview}
              onClick={setBase}
              style={{ minWidth: 0, padding: "7px 8px", width: "100%" }}
            >
              Usar de base
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={!preview && !selected.length}
              onClick={handleOpenLolaQty}
              title={
                selected.length > 1
                  ? `Enviar ${selected.length} objeto(s) seleccionados a Lola`
                  : "Enviar a Lola"
              }
              style={{ minWidth: 0, padding: "7px 8px", width: "100%" }}
            >
              Dar con Lola {selected.length > 1 ? `(${selected.length})` : ""}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={!preview || imageBusy}
              onClick={searchSimilarToPreview}
              style={{ minWidth: 0, padding: "7px 8px", width: "100%" }}
            >
              Similares
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={!preview}
              onClick={setEffectBase}
              title="Usar este objeto como base que irá a la mochila como consumible"
              style={{
                minWidth: 0,
                padding: "7px 8px",
                width: "100%",
                borderColor: "rgba(245, 158, 11, 0.4)",
                color: "#fef3c7",
                background: "rgba(245, 158, 11, 0.08)",
              }}
            >
              ✨ Base Efecto
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={!preview}
              onClick={setEffectProp}
              title="Usar este objeto dentro de la acción (objeto en mano o lanzado)"
              style={{
                minWidth: 0,
                padding: "7px 8px",
                width: "100%",
                borderColor: "rgba(245, 158, 11, 0.4)",
                color: "#fef3c7",
                background: "rgba(245, 158, 11, 0.08)",
              }}
            >
              🖐 Prop Acción
            </button>
          </div>

          {/* Selector de Pestañas: Look vs Efecto */}
          <div className="row" style={{ gap: 4, marginTop: 10, marginBottom: 6 }}>
            <button
              type="button"
              className={`btn btn-sm grow ${rightTab === "look" ? "btn-primary" : "btn-ghost"}`}
              style={{ fontSize: 11.5, padding: "5px 8px" }}
              onClick={() => setRightTab("look")}
            >
              👕 Look Ropa {Object.keys(look?.parts || {}).length > 0 ? `(${Object.keys(look.parts).length})` : ""}
            </button>
            <button
              type="button"
              className={`btn btn-sm grow ${rightTab === "effect" ? "btn-primary" : "btn-ghost"}`}
              style={{
                fontSize: 11.5,
                padding: "5px 8px",
                borderColor: rightTab === "effect" ? "#f59e0b" : "rgba(245, 158, 11, 0.3)",
                background: rightTab === "effect" ? "rgba(245, 158, 11, 0.2)" : "transparent",
                color: rightTab === "effect" ? "#fbbf24" : "var(--muted)",
              }}
              onClick={() => setRightTab("effect")}
            >
              ✨ Efecto {effectHasContent(effectDraft) ? "●" : ""}
            </button>
          </div>

          {rightTab === "look" ? (
            <div className="card" style={{ padding: 10, background: "rgba(0,0,0,0.25)" }}>
              <div className="card-title" style={{ fontSize: 12 }}>
                Look
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setLook(emptyLook())}
                >
                  Vaciar
                </button>
              </div>
              <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6 }}>
                Base:{" "}
                <strong style={{ color: "#fff" }}>
                  {look.baseObj ? `${look.baseSwf}.${look.baseObj}` : "—"}
                </strong>
              </div>
              {Object.keys(look.parts || {}).length === 0 ? (
                <div className="empty" style={{ padding: 8 }}>
                  Sin partes
                </div>
              ) : (
                Object.entries(look.parts).map(([slot, val]) => (
                  <div key={slot} className="row" style={{ fontSize: 11.5, marginBottom: 4 }}>
                    <span className="badge">{slot}</span>
                    <span className="grow mono">{val}</span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() =>
                        setLook((L) => {
                          const parts = { ...L.parts };
                          const partsInfo = { ...L.partsInfo };
                          delete parts[slot];
                          delete partsInfo[slot];
                          return { ...L, parts, partsInfo };
                        })
                      }
                    >
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="card" style={{ padding: 10, background: "rgba(0,0,0,0.25)", border: "1px solid rgba(245, 158, 11, 0.3)" }}>
              <div className="card-title" style={{ fontSize: 12, color: "#fbbf24" }}>
                <span>✨ Efecto / Acción</span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ fontSize: 11, padding: "2px 6px" }}
                  onClick={() => {
                    setEffectDraft?.(emptyEffect());
                    toast.info("Efecto vaciado");
                  }}
                >
                  Vaciar
                </button>
              </div>

              {/* Base */}
              <div style={{ marginTop: 6 }}>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 3, display: "flex", justifyContent: "space-between" }}>
                  <span>1. Objeto Base (Mochila):</span>
                  {preview && (!effectDraft?.baseObj || effectDraft?.baseObj !== preview.name) && (
                    <span
                      style={{ color: "#fbbf24", cursor: "pointer", textDecoration: "underline" }}
                      onClick={setEffectBase}
                    >
                      Usar visor
                    </span>
                  )}
                </div>
                {effectDraft?.baseObj ? (
                  <div className="row" style={{ fontSize: 11.5, background: "rgba(0,0,0,0.3)", padding: "4px 8px", borderRadius: 6 }}>
                    <ItemThumb pack={effectDraft.basePack} name={effectDraft.baseObj} size={28} />
                    <span className="grow mono" style={{ marginLeft: 6, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {effectDraft.basePack}.{effectDraft.baseObj}
                    </span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setEffectDraft?.((prev) => ({ ...prev, baseItem: "", basePack: "", baseObj: "" }))}
                    >
                      ×
                    </button>
                  </div>
                ) : (
                  <div className="empty" style={{ padding: 6, fontSize: 11 }}>
                    Sin base. Tocá <strong>✨ Base Efecto</strong> en el visor.
                  </div>
                )}
              </div>

              {/* Acción */}
              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 3 }}>
                  2. Acción del avatar:
                </div>
                <select
                  className="input input-sm"
                  style={{ width: "100%", fontSize: 11.5, height: 28, padding: "2px 6px" }}
                  value={effectDraft?.action || "kick"}
                  onChange={(e) => setEffectDraft?.((prev) => ({ ...prev, action: e.target.value }))}
                >
                  {localActions.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.category}){a.takes_prop ? " 🖐" : ""}
                    </option>
                  ))}
                </select>
              </div>

              {/* Prop (solo si la acción lleva prop 🖐) */}
              {localActions.find((a) => a.id === (effectDraft?.action || "kick"))?.takes_prop && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 3, display: "flex", justifyContent: "space-between" }}>
                    <span>3. Prop en mano 🖐:</span>
                    {preview && (!effectDraft?.subObj || effectDraft?.subObj !== preview.name) && (
                      <span
                        style={{ color: "#fbbf24", cursor: "pointer", textDecoration: "underline" }}
                        onClick={setEffectProp}
                      >
                        Usar visor
                      </span>
                    )}
                  </div>
                  {effectDraft?.subObj ? (
                    <div className="row" style={{ fontSize: 11.5, background: "rgba(0,0,0,0.3)", padding: "4px 8px", borderRadius: 6 }}>
                      <ItemThumb pack={effectDraft.subPack} name={effectDraft.subObj} size={28} />
                      <span className="grow mono" style={{ marginLeft: 6, overflow: "hidden", textOverflow: "ellipsis" }}>
                        {effectDraft.subPack}.{effectDraft.subObj}
                      </span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => setEffectDraft?.((prev) => ({ ...prev, subItem: "", subPack: "", subObj: "" }))}
                      >
                        ×
                      </button>
                    </div>
                  ) : (
                    <div className="empty" style={{ padding: 6, fontSize: 11 }}>
                      👉 Esta acción requiere prop. Buscá uno en la lista y tocá <strong>🖐 Prop Acción</strong>.
                    </div>
                  )}
                </div>
              )}

              {/* Botón Guardar directo */}
              <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  style={{
                    background: "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
                    borderColor: "#b45309",
                    color: "#fff",
                    fontWeight: 600,
                  }}
                  disabled={saveBlocked || !effectDraft?.baseObj}
                  onClick={() => onSaveEffect?.(effectDraft)}
                >
                  {effectSaving ? "Guardando..." : "✨ Guardar y dar con Lola"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ fontSize: 11.5, color: "#fbbf24" }}
                  onClick={() => onOpenEffectModal?.()}
                >
                  Abrir configurador completo ⚡
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {classModal && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setClassModal(false)}>
          <div className="modal-card">
            <div className="modal-title">Cambiar clase</div>
            <div className="modal-sub">
              {selected.length} objeto(s) · elegí a qué inventario va (ropa puesta / mochila / casa)
            </div>
            <div className="toolbar-row">
              {presets.map((p) => {
                const short =
                  p.id === "ClothMamboAsset"
                    ? "Ropa"
                    : p.id === "ConsumableMamboAsset"
                      ? "Mochila"
                      : p.id === "NpcMamboAsset"
                        ? "Casa/NPC"
                        : p.label || p.id;
                const inv =
                  p.inventory_label ||
                  ({ visualizer: "ropa puesta", default: "mochila", house: "casa" }[p.inventory] || "");
                return (
                  <button
                    key={p.id}
                    type="button"
                    className={`btn btn-sm ${mamboClass === p.id ? "btn-primary" : "btn-secondary"}`}
                    title={mamboOptionText(p)}
                    onClick={() => setMamboClass(p.id)}
                  >
                    {short}
                    {inv ? <span className="badge" style={{ marginLeft: 6 }}>{inv}</span> : null}
                  </button>
                );
              })}
            </div>
            <Field
              as="select"
              label="Clase Mambo"
              value={mamboClass}
              onChange={(e) => setMamboClass(e.target.value)}
              hint={
                selectedMamboMeta
                  ? `Va a: ${
                      selectedMamboMeta.inventory_label ||
                      ({ visualizer: "ropa puesta", default: "mochila", house: "casa" }[
                        selectedMamboMeta.inventory
                      ] || "inventario")
                    }`
                  : undefined
              }
            >
              {mamboOptions.map((a) => (
                <option key={a.id} value={a.id}>
                  {mamboOptionText(a)}
                </option>
              ))}
            </Field>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setClassModal(false)}>
                Cancelar
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => setQtyOpen(true)}>
                Aplicar
              </button>
            </div>
          </div>
        </div>
      )}

      <ImageSearchModal
        open={imageModalOpen}
        busy={imageBusy}
        onClose={() => !imageBusy && setImageModalOpen(false)}
        onSearch={runImageSearch}
      />

      <SlotSelectorModal
        open={!!slotPick}
        item={slotPick}
        look={look}
        onClose={() => setSlotPick(null)}
        onConfirm={addPart}
      />

      <QtyModal
        open={qtyOpen}
        title="¿Cuántos de cada uno?"
        message={`Lola te va a dar esta cantidad de cada objeto (${selected.length}). Recomendado: 1.`}
        onCancel={() => setQtyOpen(false)}
        onConfirm={applyClass}
      />

      <QtyModal
        open={lolaQtyOpen}
        title={
          selected.length > 1
            ? `¿Cuántos de cada uno? (${selected.length} objetos)`
            : `¿Cuántos querés de ${preview?.name || "este objeto"}?`
        }
        message={
          selected.length > 1
            ? `Lola te va a dar esta cantidad para cada uno de los ${selected.length} objetos seleccionados (${selectedPacksCount} pack${selectedPacksCount === 1 ? "" : "s"}). Recomendado: 1.`
            : `Lola te va a dar esta cantidad de ${preview?.pack || ""}.${preview?.name || ""}. Recomendado: 1.`
        }
        onCancel={() => setLolaQtyOpen(false)}
        onConfirm={handleLolaConfirm}
      />
    </div>
  );
}
