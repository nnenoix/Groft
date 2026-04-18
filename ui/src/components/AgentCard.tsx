export type AgentStatus = "active" | "idle" | "stuck" | "restarting";

export interface AgentCardProps {
  name: string;
  role: string;
  status: AgentStatus;
  currentAction: string;
  currentTask: string;
  model: string;
}

const STATUS_BORDER_COLOR: Record<AgentStatus, string> = {
  active: "#2d7a4f",
  idle: "#999999",
  stuck: "#c0392b",
  restarting: "#d97757",
};

function AgentCard({
  name,
  role,
  status,
  currentAction,
  currentTask,
  model,
}: AgentCardProps) {
  return (
    <div
      className="bg-bg-card border border-border border-l-2 rounded-md p-3 shadow-sm hover:shadow-md transition-shadow space-y-1"
      style={{ borderLeftColor: STATUS_BORDER_COLOR[status] }}
    >
      <div className="flex items-baseline gap-2">
        <span className="text-text-primary font-semibold text-sm">{name}</span>
        <span className="text-text-muted text-xs">· {role}</span>
      </div>
      <div className="text-text-secondary text-xs italic">{currentAction}</div>
      <div className="text-text-dim text-xs truncate">{currentTask}</div>
      <div className="text-text-code text-xs font-medium">{model}</div>
    </div>
  );
}

export default AgentCard;
