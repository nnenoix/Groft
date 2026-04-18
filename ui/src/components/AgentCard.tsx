export type AgentStatus = "active" | "idle" | "stuck" | "restarting";

export interface AgentCardProps {
  name: string;
  role: string;
  status: AgentStatus;
  currentAction: string;
  currentTask: string;
  model: string;
}

const STATUS_COLORS: Record<AgentStatus, string> = {
  active: "#00ff88",
  idle: "#666666",
  stuck: "#ff5555",
  restarting: "#ffaa00",
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
    <div className="bg-card rounded-lg p-3 text-sm text-white">
      <div className="flex items-center gap-2 mb-1">
        <span
          className="inline-block rounded-full"
          style={{
            width: "8px",
            height: "8px",
            backgroundColor: STATUS_COLORS[status],
          }}
        />
        <span className="font-semibold">{name}</span>
        <span className="text-[#888] text-xs">· {role}</span>
      </div>
      <div className="text-[#bbb] text-xs mb-0.5">{currentAction}</div>
      <div className="text-[#888] text-xs mb-0.5 truncate">{currentTask}</div>
      <div className="text-[#555] text-[10px] uppercase tracking-wide">
        {model}
      </div>
    </div>
  );
}

export default AgentCard;
