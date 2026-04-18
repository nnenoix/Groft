import { useEffect, useRef } from "react";
import type { LogEntry } from "../store/agentStore";

interface LogFeedProps {
  logs: LogEntry[];
  dense?: boolean;
}

function LogFeed({ logs, dense = false }: LogFeedProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [logs]);
  return (
    <div
      ref={ref}
      className={`h-full overflow-y-auto px-[var(--pad-4)] py-[var(--pad-3)] font-mono space-y-1 ${dense ? "text-[10.5px]" : "text-[11.5px]"}`}
      style={{ color: "var(--text-secondary)" }}
    >
      {logs.map((l, i) => (
        <div key={l.id ?? i} className="flex gap-2 whitespace-pre-wrap fade-up">
          <span style={{ color: "var(--text-muted)" }}>[{l.timestamp}]</span>
          <span className="font-semibold" style={{ color: "var(--accent-primary)" }}>{l.agent}</span>
          <span style={{ color: "var(--text-muted)" }}>›</span>
          <span style={{ color: "var(--text-primary)" }}>{l.action}</span>
        </div>
      ))}
    </div>
  );
}

export default LogFeed;
