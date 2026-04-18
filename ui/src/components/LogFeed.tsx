import { useEffect, useRef } from "react";

export interface LogEntry {
  id: string;
  timestamp: string;
  agent: string;
  action: string;
}

export interface LogFeedProps {
  entries: LogEntry[];
}

function LogFeed({ entries }: LogFeedProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [entries]);

  return (
    <div
      ref={ref}
      className="bg-bg-secondary h-full overflow-y-auto p-4 font-mono text-xs space-y-1"
    >
      {entries.map((entry) => (
        <div key={entry.id} className="flex gap-2 whitespace-pre-wrap">
          <span className="text-text-muted">[{entry.timestamp}]</span>
          <span className="text-accent-primary font-semibold">
            {entry.agent}:
          </span>
          <span className="text-text-primary">{entry.action}</span>
        </div>
      ))}
    </div>
  );
}

export default LogFeed;
