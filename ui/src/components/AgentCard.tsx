export type AgentStatus = "active" | "idle" | "stuck" | "restarting";

export interface AgentCardProps {
  name: string;
  role: string;
  status: AgentStatus;
  currentAction: string;
  currentTask: string;
  model: string;
}

const STATUS_CLASSES: Record<AgentStatus, string> = {
  active: "bg-status-active",
  idle: "bg-status-idle",
  stuck: "bg-status-stuck",
  restarting: "bg-status-restarting",
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
    <div className="bg-bg-card border border-border rounded-lg p-4 hover:border-accent-primary transition-colors space-y-2">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block rounded-full w-2 h-2 ${STATUS_CLASSES[status]}`}
        />
        <span className="text-text-primary font-semibold">{name}</span>
        <span className="text-text-muted text-sm">· {role}</span>
      </div>
      <div className="space-y-1">
        <div className="text-text-primary text-sm">{currentAction}</div>
        <div className="text-text-muted text-xs truncate">{currentTask}</div>
      </div>
      <div className="text-accent-primary text-xs font-medium">{model}</div>
    </div>
  );
}

export default AgentCard;
