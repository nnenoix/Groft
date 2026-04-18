import { Icon } from "../components/icons";
import { StatusDot, STATUS_COLOR, Avatar, Chip, StatusLabel } from "../components/primitives";
import { TerminalBlock } from "../components/TerminalBlock";
import type { AgentState } from "../store/agentStore";

function GridIcon({ n }: { n: number }) {
  if (n === 1)
    return (
      <svg width="12" height="12" viewBox="0 0 12 12">
        <rect x="1.5" y="1.5" width="9" height="9" rx="1" fill="none" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    );
  if (n === 2)
    return (
      <svg width="12" height="12" viewBox="0 0 12 12">
        <rect x="1.5" y="1.5" width="4" height="9" rx="1" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <rect x="6.5" y="1.5" width="4" height="9" rx="1" fill="none" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    );
  return (
    <svg width="12" height="12" viewBox="0 0 12 12">
      <rect x="1.5" y="1.5" width="4" height="4" rx="0.8" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <rect x="6.5" y="1.5" width="4" height="4" rx="0.8" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <rect x="1.5" y="6.5" width="4" height="4" rx="0.8" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <rect x="6.5" y="6.5" width="4" height="4" rx="0.8" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

interface TerminalsViewProps {
  agents: AgentState[];
  focusAgent: string | null;
  onFocus: (name: string) => void;
  gridMode: number | "all";
  setGridMode: (v: number | "all") => void;
}

export function TerminalsView({
  agents,
  focusAgent,
  onFocus,
  gridMode,
  setGridMode,
}: TerminalsViewProps) {
  const activeName = focusAgent ?? agents[0]?.name;
  const agent = agents.find((a) => a.name === activeName) ?? agents[0];

  const visibleAgents =
    gridMode === "all"
      ? agents
      : gridMode === 1
      ? [agent]
      : (() => {
          const rest = agents.filter((a) => a.name !== activeName);
          return [agent, ...rest].slice(0, gridMode as number);
        })();

  const gridClass =
    gridMode === 1
      ? "grid-cols-1"
      : gridMode === 2
      ? "grid-cols-2"
      : gridMode === 4
      ? "grid-cols-2 grid-rows-2"
      : agents.length <= 2
      ? "grid-cols-1"
      : agents.length <= 4
      ? "grid-cols-2"
      : agents.length <= 6
      ? "grid-cols-3"
      : "grid-cols-4";

  return (
    <div className="h-full overflow-hidden flex flex-col p-[var(--pad-6)]">
      {/* Header */}
      <div className="mb-[var(--pad-4)] flex items-end justify-between gap-[var(--pad-3)] shrink-0 flex-wrap">
        <div className="min-w-0">
          <div
            className="text-[11px] uppercase tracking-[0.2em] font-semibold mb-1"
            style={{ color: "var(--text-muted)" }}
          >
            Live feed
          </div>
          <h1 className="text-[28px] font-display font-semibold tracking-tight">Терминалы</h1>
          <p className="text-[12.5px] mt-1" style={{ color: "var(--text-muted)" }}>
            {gridMode === 1
              ? "Фокус на одном pty — остальные в табах."
              : gridMode === "all"
              ? `Все ${agents.length} агентов в одной сетке.`
              : `${gridMode} окна одновременно — переключай сеткой ниже.`}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Chip icon={<Icon.Activity size={11} />} tone="accent">
            {agents.filter((a) => a.status === "active").length} live
          </Chip>
          <div className="seg !p-0.5 shrink-0">
            <button aria-pressed={gridMode === 1} onClick={() => setGridMode(1)} className="!px-2" title="Один фокус">
              <GridIcon n={1} />
            </button>
            <button aria-pressed={gridMode === 2} onClick={() => setGridMode(2)} className="!px-2" title="Два рядом">
              <GridIcon n={2} />
            </button>
            <button aria-pressed={gridMode === 4} onClick={() => setGridMode(4)} className="!px-2" title="Сетка 2×2">
              <GridIcon n={4} />
            </button>
            <button
              aria-pressed={gridMode === "all"}
              onClick={() => setGridMode("all")}
              className="!px-2 !text-[10.5px] font-mono"
              title="Все"
            >
              all
            </button>
          </div>
          <button className="btn btn-outline text-[12px] shrink-0" title="Pause all">
            <Icon.Pause size={13} />
            <span className="hidden lg:inline"> Pause all</span>
          </button>
        </div>
      </div>

      {/* Tab strip — only in focus mode */}
      {gridMode === 1 && (
        <div
          className="shrink-0 relative mb-[var(--pad-3)]"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div className="flex gap-1 overflow-x-auto pb-0 scrollbar-thin" style={{ scrollbarWidth: "thin" }}>
            {agents.map((a) => {
              const active = a.name === activeName;
              return (
                <button
                  key={a.name}
                  onClick={() => onFocus(a.name)}
                  className="shrink-0 flex items-center gap-2 px-3 py-2 rounded-t-md text-[12px] transition-all relative"
                  style={{
                    background: active ? "var(--bg-terminal)" : "transparent",
                    border: `1px solid ${active ? "var(--border)" : "transparent"}`,
                    borderBottom: active ? "1px solid var(--bg-terminal)" : "1px solid transparent",
                    color: active ? "var(--text-primary)" : "var(--text-muted)",
                    marginBottom: -1,
                    fontWeight: active ? 600 : 400,
                  }}
                >
                  <StatusDot status={a.status} pulse size={6} />
                  <span>{a.name}</span>
                  {active && (
                    <span
                      className="absolute left-2 right-2 top-0 h-0.5"
                      style={{ background: STATUS_COLOR[a.status] }}
                    />
                  )}
                </button>
              );
            })}
          </div>
          <div
            className="pointer-events-none absolute left-0 top-0 bottom-0 w-6"
            style={{ background: "linear-gradient(90deg, var(--bg-primary), transparent)" }}
          />
          <div
            className="pointer-events-none absolute right-0 top-0 bottom-0 w-6"
            style={{ background: "linear-gradient(270deg, var(--bg-primary), transparent)" }}
          />
        </div>
      )}

      {/* Terminal area */}
      <div className={`flex-1 min-h-0 grid ${gridClass} gap-[var(--pad-3)]`}>
        {visibleAgents.map((a) => {
          if (!a) return null;
          const isFocused = gridMode !== 1 && a.name === activeName;
          return (
            <div
              key={a.name}
              className="min-h-0 flex flex-col rounded-[var(--radius-lg)] overflow-hidden transition-all cursor-pointer"
              style={{
                boxShadow: isFocused
                  ? "0 0 0 2px var(--accent-primary), var(--shadow-md)"
                  : gridMode === 1
                  ? "0 0 0 2px var(--accent-light), var(--shadow-md)"
                  : "var(--shadow-sm)",
                border: "1px solid var(--border)",
              }}
              onClick={() => gridMode !== 1 && onFocus(a.name)}
            >
              <TerminalBlock
                agent={a}
                live={a.status === "active"}
                lines={a.terminalOutput}
                expandable={false}
                heightClass="h-full"
              />
            </div>
          );
        })}
      </div>

      {/* Agent meta strip — only focus mode */}
      {gridMode === 1 && agent && (
        <div
          className="shrink-0 mt-[var(--pad-3)] card p-[var(--pad-3)] flex items-center gap-[var(--pad-3)] text-[12px]"
          style={{ minHeight: 56 }}
        >
          <Avatar name={agent.name} letter={agent.avatar} size={28} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-semibold truncate">{agent.name}</span>
              <StatusLabel status={agent.status} />
            </div>
            <div
              className="text-[11.5px] mt-0.5 truncate"
              style={{ color: "var(--text-muted)" }}
            >
              {agent.currentAction}
            </div>
          </div>
          <div
            className="hidden md:flex items-center gap-3 font-mono text-[11.5px] shrink-0"
            style={{ color: "var(--text-muted)" }}
          >
            <span>{agent.model}</span>
            <span style={{ opacity: 0.4 }}>·</span>
            <span>{agent.uptime}</span>
            <span style={{ opacity: 0.4 }}>·</span>
            <span>{agent.cycles}c</span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button className="btn btn-outline text-[11px] whitespace-nowrap">
              <Icon.Pause size={11} /> Stop
            </button>
            <button className="btn btn-outline text-[11px] whitespace-nowrap">
              <Icon.Activity size={11} /> Restart
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
