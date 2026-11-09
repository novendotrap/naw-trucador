import { describeLolaPayload } from "./look/lolaPayload";
import { useState, useEffect, useRef } from "react";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import HomePage from "./pages/HomePage";
import LolaPage from "./pages/LolaPage";
import ObjetosPage from "./pages/ObjetosPage";
import TrucarPage from "./pages/TrucarPage";
import TiendasPage from "./pages/TiendasPage";
import ArchivosPage from "./pages/ArchivosPage";
import LogsPage from "./pages/LogsPage";
import ErrorBoundary from "./components/ErrorBoundary";
import FloatingLookPill from "./components/FloatingLookPill";
import QuickLookModal from "./components/QuickLookModal";
import QtyModal from "./components/QtyModal";
import ThumbAutoIndexer from "./components/ThumbAutoIndexer";
import { useStatus } from "./hooks/useStatus";
import { useToast } from "./hooks/useToast";
import { api } from "./api/client";
import { emptyLook, lookHasContent } from "./look/slots";
import { emptyEffect, effectHasContent } from "./look/effects";
import FloatingEffectPill from "./components/FloatingEffectPill";
import QuickEffectModal from "./components/QuickEffectModal";

export default function App() {
  const [tab, setTab] = useState("home");
  const [collapsed, setCollapsed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [look, setLook] = useState(emptyLook());
  const [effectDraft, setEffectDraft] = useState(emptyEffect());
  const [quickEffectOpen, setQuickEffectOpen] = useState(false);
  const [actions, setActions] = useState([]);

  useEffect(() => {
    api.listActions().then((res) => {
      if (res?.actions) setActions(res.actions);
    }).catch(() => {});
  }, []);
  const [quickOpen, setQuickOpen] = useState(false);
  const [quantityRequest, setQuantityRequest] = useState(null);
  const [saving, setSaving] = useState(null);
  const saveLock = useRef(false);
  const requestLookSave = () => {
    if (!saveLock.current) setQuantityRequest({ kind: "look" });
  };
  const requestEffectSave = (effect = effectDraft) => {
    if (!saveLock.current) setQuantityRequest({ kind: "effect", effect: { ...effect } });
  };
  const { status, refresh } = useStatus(2000);
  const toast = useToast();
  const proxyOn = !!status?.proxy?.running;

  const withBusy = async (fn, okMsg) => {
    if (busy) return;
    setBusy(true);
    try {
      const data = await fn();
      if (data && data.ok === false) throw new Error(data.error || "Falló");
      if (okMsg) toast.success(typeof okMsg === "function" ? okMsg(data) : okMsg);
      await refresh();
      return data;
    } catch (e) {
      toast.error(e.message || "Error");
    } finally {
      setBusy(false);
    }
  };

  const saveEffectDraft = async (dataToSave) => {
    const eff = dataToSave || effectDraft;
    const baseItem = eff.baseItem || eff.base_item || (eff.basePack && eff.baseObj ? `${eff.basePack}.${eff.baseObj}` : "");
    if (!baseItem) {
      toast.error("Falta el objeto base del efecto (mochila)");
      return;
    }
    const subItem = eff.subItem || eff.sub_item || (eff.subPack && eff.subObj ? `${eff.subPack}.${eff.subObj}` : "");
    if (saveLock.current) return;
    saveLock.current = true;
    setSaving("effect");
    try {
      const res = await api.saveEffect({
        base_item: baseItem,
        action: eff.action || "kick",
        sub_item: subItem,
        destination: eff.destination || "default",
        uses: eff.uses || 9999,
        qty: eff.qty || 1,
        queue_lola: true,
      });
      if (!res.ok) throw new Error(res.error || "No se pudo guardar");
      toast.success(res.message || "Efecto guardado y activado en Lola!");
      setQuickEffectOpen(false);
      setEffectDraft(emptyEffect());
    } catch (e) {
      toast.error(e.message || "Error al guardar el efecto");
    } finally {
      saveLock.current = false;
      setSaving(null);
    }
  };

  const onQuickStart = () =>
    withBusy(() => api.quickStart({}), (d) => d.message || "MG abierto con proxy");
  const onToggleProxy = () =>
    withBusy(
      () => (proxyOn ? api.proxyStop() : api.proxyStart()),
      () => (proxyOn ? "Proxy detenido" : "Proxy iniciado")
    );
  const onCleanCache = () => withBusy(() => api.cleanCache(), "Caché limpiada");
  const onLaunch = () => withBusy(() => api.launchGame(false), "Juego lanzado");

  const saveLook = async (qty) => {
    setQuantityRequest(null);
    if (!look.baseSwf || !look.baseObj) {
      toast.error("Primero elegí el objeto base");
      return;
    }
    if (!Object.keys(look.parts || {}).length) {
      toast.error("Agregá al menos una parte al look");
      return;
    }
    if (saveLock.current) return;
    saveLock.current = true;
    setSaving("look");
    try {
      const data = await api.trucarRopa({
        base_swf: look.baseSwf,
        base_object: look.baseObj,
        parts: look.parts,
        parts_info: look.partsInfo,
        auto_queue: true,
        qty,
      });
      if (!data.ok) throw new Error(data.error || "No se pudo guardar");
      toast.success(data.message || `Truco guardado · x${qty}`);
      setLook(emptyLook());
      setQuickOpen(false);
    } catch (e) {
      toast.error(e.message || "Error al guardar el truco");
    } finally {
      saveLock.current = false;
      setSaving(null);
    }
  };

  return (
    <>
      <ThumbAutoIndexer />
      <div className="titlebar-spacer app-drag">naw</div>
      <div className="app-shell">
        <Sidebar
          active={tab}
          onNavigate={setTab}
          collapsed={collapsed}
          onToggle={() => setCollapsed((c) => !c)}
          proxyOn={proxyOn}
          tricksCount={status?.tricks_count ?? 0}
          lolaCount={describeLolaPayload(status?.payload || "").items.length}
        />
        <div className="main-column">
          <Topbar
            status={status}
            busy={busy}
            onQuickStart={onQuickStart}
            onToggleProxy={onToggleProxy}
            onCleanCache={onCleanCache}
            onLaunch={onLaunch}
          />
          <main className="content app-no-drag">
            <ErrorBoundary key={tab}>
              {tab === "home" && (
                <HomePage
                  status={status}
                  busy={busy}
                  onQuickStart={onQuickStart}
                  onToggleProxy={onToggleProxy}
                />
              )}
              {tab === "lola" && <LolaPage />}
              {tab === "objetos" && (
                <ObjetosPage
                  look={look}
                  setLook={setLook}
                  effectDraft={effectDraft}
                  setEffectDraft={setEffectDraft}
                  onNavigateTab={setTab}
                  onOpenEffectModal={() => setQuickEffectOpen(true)}
                  actions={actions}
                  onSaveEffect={requestEffectSave}
                  saveBlocked={!!saving}
                  effectSaving={saving === "effect"}
                  previewSuspended={quickOpen || quickEffectOpen || !!quantityRequest}
                />
              )}
              {tab === "trucar" && (
                <TrucarPage
                  look={look}
                  setLook={setLook}
                  onOpenQuick={() => setQuickOpen(true)}
                  onTricksChange={refresh}
                />
              )}
              {tab === "tiendas" && <TiendasPage />}
              {tab === "archivos" && <ArchivosPage />}
              {tab === "logs" && <LogsPage />}
            </ErrorBoundary>
          </main>
        </div>
      </div>

      <FloatingLookPill
        look={look}
        busy={saving === "look"}
        disabled={!!saving}
        onOpen={() => setQuickOpen(true)}
        onSave={requestLookSave}
      />
      <FloatingEffectPill
        effect={effectDraft}
        busy={saving === "effect"}
        disabled={!!saving}
        onOpen={() => setQuickEffectOpen(true)}
        onSave={() => requestEffectSave()}
        hasLookPill={lookHasContent(look)}
      />
      <QuickEffectModal
        open={quickEffectOpen && !quantityRequest}
        effect={effectDraft}
        actions={actions}
        onClose={() => setQuickEffectOpen(false)}
        onSave={requestEffectSave}
        onClear={() => {
          setEffectDraft(emptyEffect());
          toast.info("Efecto vaciado");
        }}
        onClearBase={() => setEffectDraft((prev) => ({ ...prev, baseItem: "", basePack: "", baseObj: "" }))}
        onClearProp={() => setEffectDraft((prev) => ({ ...prev, subItem: "", subPack: "", subObj: "" }))}
        onSetAction={(act) => setEffectDraft((prev) => ({ ...prev, action: act }))}
        onSetDestination={(dest) => setEffectDraft((prev) => ({ ...prev, destination: dest }))}
        onSetUses={(u) => setEffectDraft((prev) => ({ ...prev, uses: u }))}
        busy={!!saving}
      />
      <QuickLookModal
        open={quickOpen && !quantityRequest}
        look={look}
        busy={!!saving}
        onClose={() => setQuickOpen(false)}
        onSave={requestLookSave}
        onClear={() => {
          setLook(emptyLook());
          toast.info("Look vaciado");
        }}
        onClearBase={() => setLook((L) => ({ ...L, baseSwf: "", baseObj: "", baseThumb: "" }))}
        onRemovePart={(slot) =>
          setLook((L) => {
            const parts = { ...L.parts };
            const partsInfo = { ...L.partsInfo };
            delete parts[slot];
            delete partsInfo[slot];
            return { ...L, parts, partsInfo };
          })
        }
      />
      <QtyModal
        open={!!quantityRequest}
        title="¿Cuántos querés?"
        message={`Lola te va a dar ${quantityRequest?.kind === "effect" ? "el objeto con efecto" : look.baseObj || "el objeto"} xN. Recomendado: 1.`}
        onCancel={() => setQuantityRequest(null)}
        onConfirm={(qty) => {
          if (quantityRequest?.kind === "effect") {
            const effect = quantityRequest.effect;
            setQuantityRequest(null);
            saveEffectDraft({ ...effect, qty });
          } else if (quantityRequest?.kind === "look") saveLook(qty);
        }}
      />
    </>
  );
}
