import type { Task } from "../../store/agentStore";
import { Avatar } from "./Avatar";

interface TaskCardProps {
  task: Task;
  draggable?: boolean;
}

const PRIORITY_COLOR: Record<string, string> = {
  high: "var(--status-stuck)",
  med: "var(--accent-primary)",
  low: "var(--text-dim)",
};

export function TaskCard({ task }: TaskCardProps) {
  const priorityColor = PRIORITY_COLOR[task.priority ?? "med"] ?? "var(--accent-primary)";
  const isDone = task.status === "done";
  return (
    <div
      className="card-flat p-[var(--pad-3)] cursor-grab hover:shadow-sm transition-shadow active:cursor-grabbing"
      style={{ opacity: isDone ? 0.72 : 1 }}
    >
      <div className="flex items-start gap-2">
        <span
          className="mt-1 inline-block w-1 h-1 rounded-full shrink-0"
          style={{ background: priorityColor, boxShadow: `0 0 0 3px ${priorityColor}22` }}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-[10.5px] font-mono tracking-wider" style={{ color: "var(--text-code)" }}>{task.id}</span>
            <span
              className="text-[13px] font-medium leading-snug"
              style={{ color: isDone ? "var(--text-muted)" : "var(--text-primary)", textDecoration: isDone ? "line-through" : "none" }}
            >
              {task.title}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1.5 text-[11px]" style={{ color: "var(--text-muted)" }}>
            {task.owner && <Avatar name={task.owner} letter={task.owner[0]?.toUpperCase()} size={14} />}
            <span>{task.owner ?? "—"}</span>
            {task.deps && task.deps.length > 0 && (
              <>
                <span>·</span>
                <span className="font-mono">↳ {task.deps.join(", ")}</span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
