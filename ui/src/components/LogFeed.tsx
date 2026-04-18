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
      className="h-full max-h-full overflow-y-auto font-mono text-xs text-[#ccc] p-3 bg-[#0d0d0d] border-l border-[#222]"
    >
      {entries.map((entry) => (
        <div key={entry.id} className="whitespace-pre-wrap">
          <span className="text-[#666]">[{entry.timestamp}]</span>{" "}
          <span className="text-accent">{entry.agent}</span>:{" "}
          <span>{entry.action}</span>
        </div>
      ))}
    </div>
  );
}

export default LogFeed;
