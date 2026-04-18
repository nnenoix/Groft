import type { AgentState } from "../store/agentStore";
import { AgentCard } from "../components/primitives";
import { Icon } from "../components/icons";
import { EmptyState } from "../components/EmptyState";

interface AgentsViewProps {
  agents: AgentState[];
  onOpenAgent: (name: string) => void;
  onOpenTerminal: (name: string) => void;
}

export function AgentsView({ agents, onOpenAgent, onOpenTerminal }: AgentsViewProps) {
  if (!agents || agents.length === 0) {
    return (
      <div className="h-full overflow-y-auto p-[var(--pad-6)]">
        <div className="max-w-[1100px] mx-auto h-full">
          <EmptyState
            icon={Icon.Users}
            title="Пока нет агентов"
            desc="Создайте первого агента — backend, frontend, tester или docs. opus их оркестрирует."
            action={
              <button className="btn btn-primary">
                <Icon.Plus size={14} /> Создать агента
              </button>
            }
          />
        </div>
      </div>
    );
  }
  return (
    <div className="h-full overflow-y-auto p-[var(--pad-6)]">
      <div className="max-w-[1100px] mx-auto">
        <div className="flex items-end justify-between mb-[var(--pad-5)]">
          <div>
            <div className="text-[11px] uppercase tracking-[0.2em] font-semibold mb-1" style={{ color: "var(--text-muted)" }}>Roster</div>
            <h1 className="text-[28px] font-display font-semibold tracking-tight">Агенты команды</h1>
            <p className="text-[13px] mt-1" style={{ color: "var(--text-muted)" }}>
              Клик по карточке — откроет состояние и настройки. Кнопка «терминал» — перенесёт в live-feed.
            </p>
          </div>
          <button className="btn btn-primary">
            <Icon.Plus size={14} /> Новый агент
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-[var(--pad-4)]">
          {agents.map((a) => (
            <div
              key={a.name}
              onClick={() => onOpenAgent(a.name)}
              className="cursor-pointer hover:translate-y-[-1px] transition-transform relative group"
            >
              <AgentCard agent={a} />
              <button
                onClick={(e) => { e.stopPropagation(); onOpenTerminal(a.name); }}
                className="absolute top-2 right-2 btn btn-outline !px-2 !py-1 text-[10.5px] opacity-0 group-hover:opacity-100 transition-opacity"
                title="Открыть терминал агента"
              >
                <Icon.Terminal size={11} />
              </button>
            </div>
          ))}
          <button
            className="rounded-[var(--radius-lg)] border-2 border-dashed flex flex-col items-center justify-center gap-2 py-10 hover:bg-[var(--bg-secondary)] transition-colors"
            style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
          >
            <Icon.Plus size={22} />
            <span className="text-[13px] font-medium">Создать агента</span>
            <span className="text-[11px]">backend-dev / docs / custom…</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default AgentsView;
