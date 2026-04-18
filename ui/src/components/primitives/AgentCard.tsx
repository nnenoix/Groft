import type { AgentState } from "../../store/agentStore";
import { Sparkline } from "./Sparkline";
import { StatusDot, STATUS_COLOR } from "./StatusDot";
import { Avatar } from "./Avatar";

interface AgentCardProps {
  agent: AgentState;
  compact?: boolean;
}

export function AgentCard({ agent, compact = false }: AgentCardProps) {
  const { name, role, status, currentAction, currentTask, model, spark, uptime, cycles, mode, tokensIn, tokensOut } = agent;
  const tokensK = (((tokensIn ?? 0) + (tokensOut ?? 0)) / 1000).toFixed(1);
  return (
    <div
      className="relative card p-[var(--pad-4)] hover:shadow-md transition-all duration-200 overflow-hidden"
      style={{ borderLeftWidth: 3, borderLeftStyle: "solid", borderLeftColor: STATUS_COLOR[status] }}
    >
      <div className="flex items-start gap-[var(--pad-3)]">
        <Avatar name={name} letter={agent.avatar} size={compact ? 30 : 38} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-[14px] font-display" style={{ color: "var(--text-primary)" }}>{name}</span>
            <StatusDot status={status} pulse />
            <span className="text-[11px] font-mono uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{mode}</span>
          </div>
          <div className="text-[12px] mt-0.5" style={{ color: "var(--text-muted)" }}>{role}</div>
        </div>
      </div>

      {!compact && (
        <div className="mt-[var(--pad-3)] space-y-1">
          <div className="text-[12px] leading-snug" style={{ color: "var(--text-secondary)" }}>
            <span style={{ color: "var(--text-muted)" }}>Action · </span>{currentAction}
          </div>
          <div className="text-[11px] font-mono truncate" style={{ color: "var(--text-code)" }}>
            {currentTask}
          </div>
        </div>
      )}

      {!compact && (
        <div className="mt-[var(--pad-3)] flex items-end justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-[9.5px] uppercase tracking-[0.18em] font-semibold mb-1" style={{ color: "var(--text-dim)" }}>
              Tokens · {cycles ?? 0}c cycles
            </div>
            <div style={{ color: "var(--accent-primary)" }}>
              <Sparkline values={spark ?? []} width={170} height={26} />
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-[13px] font-mono font-semibold" style={{ color: "var(--text-primary)" }}>{tokensK}k</div>
            <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>{uptime}</div>
          </div>
        </div>
      )}

      {!compact && (
        <div className="mt-[var(--pad-3)] pt-[var(--pad-2)] flex items-center gap-2 text-[10.5px] font-mono" style={{ color: "var(--text-muted)", borderTop: "1px dashed var(--border)" }}>
          <span>{model}</span>
        </div>
      )}

      {compact && (
        <div className="mt-[var(--pad-2)] flex items-center gap-2" style={{ color: "var(--accent-primary)" }}>
          <Sparkline values={spark ?? []} width={84} height={18} />
          <span className="text-[10px] font-mono ml-auto" style={{ color: "var(--text-muted)" }}>{tokensK}k · {cycles ?? 0}c</span>
        </div>
      )}
    </div>
  );
}
