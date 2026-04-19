import { useEffect, useState } from "react";
import type { UsageWindow } from "../store/agentStore";

interface SidebarUsageProps {
  rolling5h: UsageWindow | null;
  weekly: UsageWindow | null;
}

function formatTokens(total: number): string {
  if (total >= 1_000_000) {
    return `${(total / 1_000_000).toFixed(1)}M`;
  }
  return `${(total / 1000).toFixed(1)}k`;
}

function formatCountdown(resetAt: string, now: number): string {
  const target = Date.parse(resetAt);
  if (Number.isNaN(target)) return "—";
  const diffMs = target - now;
  if (diffMs <= 0) return "—";
  const totalMinutes = Math.floor(diffMs / 60_000);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  if (days >= 1) return `${days}d ${hours}h`;
  return `${hours}h ${minutes}m`;
}

interface UsageRowProps {
  label: string;
  window: UsageWindow | null;
  now: number;
}

function UsageRow({ label, window, now }: UsageRowProps) {
  const dim = !window;
  const tokensText = window ? formatTokens(window.total) : "—";
  const countdownText = window ? formatCountdown(window.resetAt, now) : "—";
  return (
    <div
      className="flex items-center justify-between px-1.5 py-1 rounded"
      style={{
        background: dim ? "transparent" : "var(--bg-secondary)",
        opacity: dim ? 0.45 : 1,
      }}
    >
      <span
        className="text-[9px] uppercase tracking-[0.16em]"
        style={{ color: "var(--text-dim)" }}
      >
        {label}
      </span>
      <div className="flex items-center gap-2">
        <span
          className="text-[11px] font-mono font-semibold"
          style={{
            color: dim ? "var(--text-dim)" : "var(--text-primary)",
          }}
        >
          {tokensText}
        </span>
        <span
          className="text-[10px] font-mono"
          style={{ color: "var(--text-dim)" }}
        >
          {countdownText}
        </span>
      </div>
    </div>
  );
}

export function SidebarUsage({ rolling5h, weekly }: SidebarUsageProps) {
  const [now, setNow] = useState<number>(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="space-y-[var(--pad-2)]">
      <div className="flex items-center justify-between">
        <span
          className="text-[9.5px] uppercase tracking-[0.2em] font-semibold"
          style={{ color: "var(--text-muted)" }}
        >
          Usage
        </span>
      </div>
      <div className="space-y-1">
        <UsageRow label="5h" window={rolling5h} now={now} />
        <UsageRow label="Week" window={weekly} now={now} />
      </div>
    </div>
  );
}
