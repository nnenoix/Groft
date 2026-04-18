export type ActivityView = "agents" | "tasks" | "messengers" | "settings";

export interface ActivityBarProps {
  activeView: ActivityView;
  onSelect: (view: ActivityView) => void;
}

interface ActivityItem {
  view: ActivityView;
  icon: string;
  label: string;
}

const ITEMS: ActivityItem[] = [
  { view: "agents", icon: "👥", label: "Agents" },
  { view: "tasks", icon: "✓", label: "Tasks" },
  { view: "messengers", icon: "💬", label: "Messengers" },
  { view: "settings", icon: "⚙", label: "Settings" },
];

function ActivityBar({ activeView, onSelect }: ActivityBarProps) {
  return (
    <nav className="w-12 h-full bg-bg-sidebar border-r border-border flex flex-col items-center py-3 gap-1 shrink-0">
      {ITEMS.map((item) => {
        const isActive = item.view === activeView;
        const base =
          "w-10 h-10 rounded-lg flex items-center justify-center text-lg transition-colors select-none";
        const stateClasses = isActive
          ? "bg-accent-primary text-bg-card font-semibold"
          : "text-text-muted hover:bg-bg-secondary hover:text-text-primary";
        return (
          <button
            key={item.view}
            type="button"
            aria-label={item.label}
            aria-pressed={isActive}
            title={item.label}
            onClick={() => onSelect(item.view)}
            className={`${base} ${stateClasses}`}
          >
            {item.icon}
          </button>
        );
      })}
    </nav>
  );
}

export default ActivityBar;
