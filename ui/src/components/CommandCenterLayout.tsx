import React from "react";
import { Avatar, EyebrowLabel, StatusDot } from "./primitives";
import { Icon } from "./icons";
import { SidebarPulse } from "./SidebarPulse";
import { ComposerDock } from "./ComposerDock";
import { ComposerModal } from "./ComposerModal";
import { AgentDrawer } from "./AgentDrawer";
import LogFeed from "./LogFeed";
import { AgentsView } from "../views/AgentsView";
import { TasksView } from "../views/TasksView";
import { TerminalsView } from "../views/TerminalsView";
import { SettingsView, type UISettings } from "../views/SettingsView";
import { useAgents, useLogs, useTasks } from "../store/agentStore";

export type NavView = "agents" | "tasks" | "terminals" | "settings";

export interface CommandCenterState {
  view: NavView;
  focusAgent: string | null;
  selectedAgent: string | null;
  composerOpen: boolean;
  gridMode: number | "all";
  uiSettings: UISettings;
}

export const INITIAL_CMD_STATE: CommandCenterState = {
  view: "agents",
  focusAgent: null,
  selectedAgent: null,
  composerOpen: false,
  gridMode: 1,
  uiSettings: {
    theme: "dark",
    font: "inter",
    density: "normal",
    accent: "default",
    backdrop: "none",
  },
};

export const NAV_ITEMS: Array<{ key: NavView; label: string; Icon: (p: { size?: number }) => React.ReactElement }> = [
  { key: "agents",    label: "Agents",    Icon: Icon.Users },
  { key: "tasks",     label: "Tasks",     Icon: Icon.Check },
  { key: "terminals", label: "Terminals", Icon: Icon.Terminal },
  { key: "settings",  label: "Settings",  Icon: Icon.Cog },
];

interface CommandCenterLayoutProps {
  state: CommandCenterState;
  setState: (patch: Partial<CommandCenterState>) => void;
  openCmdK?: () => void;
}

export function CommandCenterLayout({ state, setState, openCmdK }: CommandCenterLayoutProps) {
  const agents = useAgents();
  const tasks = useTasks();
  const logs = useLogs();

  const { view, focusAgent, selectedAgent, composerOpen, gridMode, uiSettings } = state;
  const selectedAgentData = selectedAgent
    ? (agents.find((a) => a.name === selectedAgent) ?? null)
    : null;

  function openTerminal(name: string) {
    setState({ view: "terminals", focusAgent: name, selectedAgent: null });
  }

  function openAgent(name: string) {
    setState({ selectedAgent: name });
  }

  function setUISettings(patch: Partial<UISettings>) {
    setState({ uiSettings: { ...uiSettings, ...patch } });
  }

  return (
    <div className="h-full flex" style={{ background: "var(--bg-primary)" }}>
      {/* LEFT RAIL */}
      <aside
        className="shrink-0 flex flex-col"
        style={{ width: 280, borderRight: "1px solid var(--border)", background: "var(--bg-sidebar)" }}
      >
        {/* Logo */}
        <div className="px-[var(--pad-4)] pt-[var(--pad-5)] pb-[var(--pad-4)] flex items-center gap-2.5">
          <div style={{ color: "var(--accent-primary)" }}>
            <Icon.Logo size={26} />
          </div>
          <div className="min-w-0">
            <div className="font-display font-semibold text-[15px] leading-tight tracking-tight">
              Groft
            </div>
            <div className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
              orchestrator · v0.1.0
            </div>
          </div>
        </div>

        {/* Search / CmdK */}
        <div className="px-[var(--pad-4)] pb-[var(--pad-3)]">
          <button
            onClick={openCmdK}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-[12px] transition-colors"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border)",
              color: "var(--text-muted)",
            }}
          >
            <Icon.Search size={12} /> Поиск и команды
            <span className="ml-auto flex items-center gap-0.5">
              <kbd>⌘</kbd>
              <kbd>K</kbd>
            </span>
          </button>
        </div>

        {/* Nav */}
        <nav className="px-[var(--pad-3)] space-y-0.5">
          {NAV_ITEMS.map((n) => {
            const active = view === n.key;
            return (
              <button
                key={n.key}
                onClick={() => setState({ view: n.key })}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] text-left transition-colors"
                style={{
                  background: active ? "var(--accent-light)" : "transparent",
                  color: active ? "var(--accent-hover)" : "var(--text-secondary)",
                  fontWeight: active ? 600 : 400,
                }}
              >
                <n.Icon size={14} /> {n.label}
                {n.key === "tasks" && tasks.current.length > 0 && (
                  <span
                    className="ml-auto text-[10px] font-mono"
                    style={{ color: active ? "var(--accent-hover)" : "var(--text-dim)" }}
                  >
                    {tasks.current.length}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Pulse block */}
        <div
          className="mt-[var(--pad-3)] mx-[var(--pad-3)] px-[var(--pad-3)] py-[var(--pad-3)] rounded-[var(--radius-md)]"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
        >
          <SidebarPulse agents={agents} />
        </div>

        {/* Agent roster */}
        <div className="mt-[var(--pad-3)] px-[var(--pad-4)] flex-1 min-h-0 overflow-y-auto">
          <EyebrowLabel count={agents.length} className="mb-[var(--pad-2)]">
            Roster
          </EyebrowLabel>
          <div className="space-y-1">
            {agents.map((a) => {
              const active =
                (focusAgent === a.name && view === "terminals") || selectedAgent === a.name;
              return (
                <button
                  key={a.name}
                  onClick={() => {
                    if (view === "terminals") setState({ focusAgent: a.name });
                    else openAgent(a.name);
                  }}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors text-left"
                  style={{
                    background: active ? "var(--accent-light)" : "transparent",
                    borderLeft: `2px solid ${active ? "var(--accent-primary)" : "transparent"}`,
                  }}
                >
                  <Avatar name={a.name} letter={a.avatar} size={22} />
                  <div className="min-w-0 flex-1">
                    <div
                      className="text-[12px] font-medium truncate"
                      style={{ color: active ? "var(--accent-hover)" : "var(--text-primary)" }}
                    >
                      {a.name}
                    </div>
                    <div
                      className="text-[10px] font-mono truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {a.currentAction}
                    </div>
                  </div>
                  <StatusDot status={a.status} pulse size={6} />
                </button>
              );
            })}
          </div>
        </div>

        {/* Composer dock */}
        <div className="shrink-0 p-[var(--pad-3)]" style={{ borderTop: "1px solid var(--border)" }}>
          <ComposerDock onOpen={() => setState({ composerOpen: true })} />
        </div>
      </aside>

      {/* MAIN */}
      <main className="flex-1 min-w-0 overflow-hidden flex flex-col">
        {view === "agents" ? (
          <AgentsView agents={agents} onOpenAgent={openAgent} onOpenTerminal={openTerminal} />
        ) : view === "tasks" ? (
          <TasksView tasks={tasks} />
        ) : view === "settings" ? (
          <SettingsView state={uiSettings} setState={setUISettings} />
        ) : (
          <TerminalsView
            agents={agents}
            focusAgent={focusAgent}
            onFocus={(n) => setState({ focusAgent: n })}
            gridMode={gridMode}
            setGridMode={(v) => setState({ gridMode: v })}
          />
        )}
      </main>

      {/* RIGHT: activity log (xl+) */}
      {view !== "settings" && (
        <aside
          className="shrink-0 hidden xl:flex flex-col min-h-0"
          style={{
            width: 300,
            borderLeft: "1px solid var(--border)",
            background: "var(--bg-sidebar)",
          }}
        >
          <div className="px-[var(--pad-4)] pt-[var(--pad-4)] pb-[var(--pad-2)] shrink-0">
            <EyebrowLabel count={logs.length}>Activity</EyebrowLabel>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">
            <LogFeed logs={logs} />
          </div>
        </aside>
      )}

      <AgentDrawer
        agent={selectedAgentData}
        onClose={() => setState({ selectedAgent: null })}
        onOpenTerminal={openTerminal}
      />

      {composerOpen && <ComposerModal onClose={() => setState({ composerOpen: false })} />}
    </div>
  );
}
