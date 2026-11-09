import { Zap, Shield, Gamepad2, Radio } from "lucide-react";

export default function HomePage({ status, busy, onQuickStart, onToggleProxy }) {
  const proxy = status?.proxy || {};
  const game = status?.game || {};

  return (
    <div className="home-hero">
      <div>
        <div className="page-title">Panel</div>
        <div className="page-sub">
          Proxy, Lola y trucos en una app de escritorio. Abrí el juego ya aplicado con un click.
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <span>Arranque rápido</span>
          <Zap size={16} color="var(--accent-light)" />
        </div>
        <div className="card-sub">
          Prende el proxy, limpia caché y abre Mundo Gaturro con lo que tengas listo en Lola.
        </div>
        <div className="home-actions">
          <button className="btn btn-primary" disabled={busy} onClick={onQuickStart}>
            Abrir MG aplicado
          </button>
          <button className="btn btn-secondary" disabled={busy} onClick={onToggleProxy}>
            {proxy.running ? "Parar proxy" : "Iniciar proxy"}
          </button>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">Proxy</div>
          <div className="stat-value" style={{ color: proxy.running ? "var(--ok)" : undefined }}>
            {proxy.running ? "Activo" : "Apagado"}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">PAC Windows</div>
          <div className="stat-value">{proxy.system_proxy_enabled ? "Aplicado" : "Libre"}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Mundo Gaturro</div>
          <div className="stat-value">{game.running ? "Abierto" : "Cerrado"}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Puerto</div>
          <div className="stat-value mono">{proxy.port || 8080}</div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title">
            <span>Flujo tipico</span>
            <Shield size={15} color="var(--muted)" />
          </div>
          <div className="card-sub" style={{ marginBottom: 0, lineHeight: 1.6 }}>
            1. En Objetos armá el look o cambiá clase.
            <br />
            2. Guardá el truco (te pide cantidad para Lola).
            <br />
            3. Tocá Abrir MG aplicado y hablale a Lola.
          </div>
        </div>
        <div className="card">
          <div className="card-title">
            <span>Estado del cliente</span>
            <Gamepad2 size={15} color="var(--muted)" />
          </div>
          <div className="card-sub" style={{ marginBottom: 0 }}>
            {game.executable_found
              ? `Detectado: ${game.executable_path || "MundoGaturro.exe"}`
              : "No se encontró el ejecutable de Mundo Gaturro."}
          </div>
          <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8, color: "var(--muted)", fontSize: 12 }}>
            <Radio size={14} />
            Los logs en vivo están en la pestaña Logs.
          </div>
        </div>
      </div>
    </div>
  );
}
