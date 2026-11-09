import { useEffect, useState } from "react";
import { api } from "../api/client";

export default function LogsPage() {
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const data = await api.logs(120);
        if (alive) setLogs(data.logs || data.recent_logs || []);
      } catch {
        /* ignore */
      }
    };
    tick();
    const id = setInterval(tick, 1500);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="stack">
      <div>
        <div className="page-title">Logs</div>
        <div className="page-sub">Actividad del proxy, trucos y Lola en vivo.</div>
      </div>
      <div className="logs-box">
        {!logs.length && <div className="empty">Sin logs todavía.</div>}
        {logs.map((line, i) => {
          const text = typeof line === "string" ? line : line.message || JSON.stringify(line);
          const level =
            typeof line === "object" && line.level
              ? line.level
              : text.includes("[ERROR]")
                ? "ERROR"
                : text.includes("[TRUCO]")
                  ? "TRUCO"
                  : text.includes("[WARN]")
                    ? "WARN"
                    : "";
          return (
            <div key={i} className={`log-line ${level}`}>
              {text}
            </div>
          );
        })}
      </div>
    </div>
  );
}
