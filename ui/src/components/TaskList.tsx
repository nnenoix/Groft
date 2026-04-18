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

const ICON_CLASSES: Record<TaskStatus, string> = {
  done: "text-status-active",
  active: "text-accent-primary",
  pending: "text-text-dim",
};

function TaskList({ tasks }: TaskListProps) {
  return (
    <ul className="space-y-1">
      {tasks.map((task) => (
        <li
          key={task.id}
          className="flex items-center gap-2 px-3 py-2 rounded hover:bg-bg-card transition-colors"
        >
          <span className={`font-mono ${ICON_CLASSES[task.status]}`}>
            {ICONS[task.status]}
          </span>
          <div className="flex flex-col">
            <span className="text-text-primary text-sm">{task.title}</span>
            <span className="text-text-muted text-xs">{task.stage}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default TaskList;
