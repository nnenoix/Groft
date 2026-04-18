export type TaskStatus = "done" | "active" | "pending";

export interface Task {
  id: string;
  title: string;
  stage: string;
  status: TaskStatus;
}

export interface TaskListProps {
  tasks: Task[];
}

const ICONS: Record<TaskStatus, string> = {
  done: "✓",
  active: "▶",
  pending: "○",
};

const ICON_COLORS: Record<TaskStatus, string> = {
  done: "#00ff88",
  active: "#00ff88",
  pending: "#666666",
};

function TaskList({ tasks }: TaskListProps) {
  return (
    <ul className="flex flex-col gap-2">
      {tasks.map((task) => (
        <li
          key={task.id}
          className="flex items-start gap-2 text-sm text-white"
        >
          <span
            className="mt-0.5 font-mono"
            style={{ color: ICON_COLORS[task.status] }}
          >
            {ICONS[task.status]}
          </span>
          <div className="flex flex-col">
            <span>{task.title}</span>
            <span className="text-[10px] text-[#666]">{task.stage}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default TaskList;
