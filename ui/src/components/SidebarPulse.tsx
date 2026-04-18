import React from "react";
import type { AgentState } from "../store/agentStore";
import { STATUS_COLOR } from "./primitives/StatusDot";
import type { Status } from "./primitives/StatusDot";

interface PulseStatProps {
  label: string;
  value: number;
  tone: Status;
}

function PulseStat({ label, value, tone }: PulseStatProps) {
  const color = STATUS_COLOR[tone] ?? "var(--text-dim)";
  const dim = !value;
  return (
    <div
      className="flex flex-col items-start px-1.5 py-1 rounded"
      style={{ background: dim ? "transparent" : "var(--bg-secondary)", opacity: dim ? 0.45 : 1 }}
    >
      <span className="text-[8.5px] uppercase tracking-[0.12em]" style={{ color: "var(--text-dim)" }}>
        {label}
      </span>
      <span
        className="text-[13px] font-mono font-semibold"
        style={{ color: value ? color : "var(--text-dim)" }}
      >
        {value}
      </span>
    </div>
  );
}

interface SidebarPulseProps {
  agents: AgentState[];
}

export function SidebarPulse({ agents }: SidebarPulseProps) {
  const counts = agents.reduce<Record<string, number>>((acc, a) => {
    acc[a.status] = (acc[a.status] ?? 0) + 1;
    return acc;
  }, {});
  const totalTokens = agents.reduce((s, a) => s + ((a.tokensIn ?? 0) + (a.tokensOut ?? 0)), 0);
  const totalCycles = agents.reduce((s, a) => s + (a.cycles ?? 0), 0);

  return (
    <div className="space-y-[var(--pad-2)]">
      <div className="flex items-center justify-between">
        <span
          className="text-[9.5px] uppercase tracking-[0.2em] font-semibold"
          style={{ color: "var(--text-muted)" }}
        >
          Pulse
        </span>
        <span
          className="flex items-center gap-1 text-[9px] font-mono"
          style={{ color: "var(--status-active)" }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full pulse-dot"
            style={
              {
                background: "var(--status-active)",
                "--accent-glow": "oklch(0.72 0.14 150 / 0.25)",
              } as React.CSSProperties
            }
          />
          healthy
        </span>
      </div>

      <div className="grid grid-cols-4 gap-1">
        <PulseStat label="Live" value={counts.active ?? 0} tone="active" />
        <PulseStat label="Idle" value={counts.idle ?? 0} tone="idle" />
        <PulseStat label="Stuck" value={counts.stuck ?? 0} tone="stuck" />
        <PulseStat label="Restart" value={counts.restarting ?? 0} tone="restarting" />
      </div>

      <div
        className="pt-[var(--pad-2)] grid grid-cols-2 gap-2 text-[10.5px]"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <div>
          <div
            className="text-[9px] uppercase tracking-[0.16em]"
            style={{ color: "var(--text-dim)" }}
          >
            Tokens
          </div>
          <div className="font-mono font-semibold" style={{ color: "var(--text-primary)" }}>
            {(totalTokens / 1000).toFixed(1)}k
          </div>
        </div>
        <div>
          <div
            className="text-[9px] uppercase tracking-[0.16em]"
            style={{ color: "var(--text-dim)" }}
          >
            Cycles
          </div>
          <div className="font-mono font-semibold" style={{ color: "var(--text-primary)" }}>
            {totalCycles}
          </div>
        </div>
      </div>
    </div>
  );
}
