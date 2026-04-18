import { useMemo } from "react";
import type { AgentState } from "../../store/agentStore";
import { Icon } from "../icons";
import { StatusDot } from "./StatusDot";

interface PulseBarProps {
  agents: AgentState[];
}

export function PulseBar({ agents }: PulseBarProps) {
  const count = useMemo(() => {
    const out = { active: 0, idle: 0, stuck: 0, restarting: 0 };
    agents.forEach((a) => {
      const s = a.status as keyof typeof out;
      if (s in out) out[s] = (out[s] || 0) + 1;
    });
    return out;
  }, [agents]);

  const totalTokens = agents.reduce((s, a) => s + ((a.tokensIn ?? 0) + (a.tokensOut ?? 0)), 0);

  return (
    <div className="flex items-center gap-[var(--pad-5)] text-[12px]" style={{ color: "var(--text-secondary)" }}>
      <div className="flex items-center gap-2">
        <StatusDot status="active" pulse />
        <span className="font-medium">{count.active} active</span>
      </div>
      <div className="flex items-center gap-2">
        <StatusDot status="idle" />
        <span>{count.idle} idle</span>
      </div>
      {count.stuck > 0 && (
        <div className="flex items-center gap-2">
          <StatusDot status="stuck" pulse />
          <span style={{ color: "var(--status-stuck)" }}>{count.stuck} stuck</span>
        </div>
      )}
      {count.restarting > 0 && (
        <div className="flex items-center gap-2">
          <StatusDot status="restarting" pulse />
          <span>{count.restarting} restart</span>
        </div>
      )}
      <div className="w-px h-4" style={{ background: "var(--border)" }} />
      <div className="flex items-center gap-1.5 font-mono">
        <Icon.Zap size={12} />
        <span>{(totalTokens / 1000).toFixed(1)}k tokens</span>
      </div>
    </div>
  );
}
