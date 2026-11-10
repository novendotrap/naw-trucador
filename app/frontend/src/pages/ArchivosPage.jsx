import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useToast } from "../hooks/useToast";
import ConfirmModal from "../components/ConfirmModal";

export default function ArchivosPage() {
  const toast = useToast();
  const [overrides, setOverrides] = useState([]);
  const [lib, setLib] = useState(null);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState(null);

  const refresh = async () => {
    try {
      const [o, s, j] = await Promise.all([
        api.listOverrides(),
        api.libraryStatus(),
        api.libraryJob().catch(() => null),
      ]);
      setOverrides(o.overrides || o.files || []);
      setLib(s);
      setJob(j);
    } catch (e) {
      toast.error(e.message || "Error al cargar archivos");
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(async () => {
      try {
        const j = await api.libraryJob();
        setJob(j);
      } catch {
        /* ignore */
      }
    }, 2000);
    return () => clearInterval(id);
  }, []);

  const run = async (fn, label) => {
    setBusy(true);
    try {
      const data = await fn();
      toast.success(data.message || `${label} ok`);
      await refresh();
    } catch (e) {
      toast.error(e.message || `Falló ${label}`);
    } finally {
      setBusy(false);
    }
  };

  const remove = (filename) => setConfirmDel(filename);

  const doRemove = async () => {
    const filename = confirmDel;
    setConfirmDel(null);
    if (!filename) return;
    try {
      await api.deleteOverride(filename);
      toast.success("Override eliminado");
      refresh();
    } catch (e) {
      toast.error(e.message || "No se pudo borrar");
    }
  };

  return (
    <div className="stack">
      <div>
        <div className="page-title">Archivos</div>
        <div className="page-sub">Overrides SWF y librería de assets.</div>
      </div>

      <div className="card">
        <div className="card-title">Librería</div>
        <div className="card-sub">
          {lib
            ? `Estado: ${lib.message || lib.status || "ok"} · assets: ${lib.count ?? lib.assets ?? "—"}`
            : "Cargando…"}
          {job?.running ? ` · Job: ${job.phase || job.message || "trabajando…"}` : ""}
        </div>
        <div className="home-actions">
          <button className="btn btn-secondary" disabled={busy} onClick={() => run(api.libraryReview, "Review")}>
            Revisar
          </button>
          <button className="btn btn-secondary" disabled={busy || job?.running} onClick={() => run(api.libraryDownload, "Download")}>
            Descargar faltantes
          </button>
          <button className="btn btn-secondary" disabled={busy} onClick={() => run(api.libraryDumpMmo, "Dump MMO")}>
            Dump MMO
          </button>
          <button className="btn btn-primary" disabled={busy} onClick={() => run(api.libraryZip, "Zip")}>
            Generar ZIP
          </button>
          <a className="btn btn-secondary" href="/api/library/zip/file">
            Descargar ZIP
          </a>
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <span>Overrides</span>
          <button className="btn btn-secondary btn-sm" onClick={refresh}>
            Actualizar
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Archivo</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {!overrides.length ? (
                <tr>
                  <td colSpan={2} className="empty">
                    No hay overrides.
                  </td>
                </tr>
              ) : (
                overrides.map((f) => {
                  const name = typeof f === "string" ? f : f.name || f.filename;
                  return (
                    <tr key={name}>
                      <td className="mono">{name}</td>
                      <td>
                        <button className="btn btn-danger btn-sm" onClick={() => remove(name)}>
                          Borrar
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <ConfirmModal
        open={!!confirmDel}
        title="Borrar override"
        message={confirmDel ? `¿Borrar override ${confirmDel}?` : ""}
        confirmLabel="Borrar"
        danger
        onCancel={() => setConfirmDel(null)}
        onConfirm={doRemove}
      />
    </div>
  );
}
