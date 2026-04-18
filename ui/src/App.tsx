import { useState } from "react";
import Header from "./components/Header";
import ActivityBar, { type ActivityView } from "./components/ActivityBar";
import AgentCard from "./components/AgentCard";
import TaskList from "./components/TaskList";
import ChatInput from "./components/ChatInput";
import LogFeed from "./components/LogFeed";
import TerminalGrid, { type TerminalData } from "./components/TerminalGrid";
import AgentList from "./pages/AgentList";
import MessengerSettings, { type TabKey } from "./pages/MessengerSettings";
import useOrchestrator from "./hooks/useOrchestrator";
import {
  useAgents,
  useLogs,
  useTasks,
  type AgentState,
} from "./store/agentStore";

function SectionHeader({ title }: { title: string }) {
  return (
    <h2 className="text-text-muted uppercase text-xs tracking-widest px-4 pt-4 pb-2">
      {title}
    </h2>
  );
}

const MESSENGER_ITEMS: Array<{ key: TabKey; icon: string; label: string }> = [
  { key: "telegram", icon: "📱", label: "Telegram" },
  { key: "discord", icon: "🎮", label: "Discord" },
  { key: "webhook", icon: "🔗", label: "Webhook" },
];

function SidebarContent({
  view,
  agents,
  messengerTab,
  onMessengerTabChange,
}: {
  view: ActivityView;
  agents: AgentState[];
  messengerTab: TabKey;
  onMessengerTabChange: (tab: TabKey) => void;
}) {
  const tasks = useTasks();
  switch (view) {
    case "agents":
      return (
        <>
          <SectionHeader title="Agents" />
          <div className="px-3 space-y-2">
            {agents.map((agent) => (
              <AgentCard
                key={agent.name}
                name={agent.name}
                role={agent.role}
                status={agent.status}
                currentAction={agent.currentAction}
                currentTask={agent.currentTask}
                model={agent.model}
              />
            ))}
          </div>
        </>
      );
    case "tasks":
      return (
        <>
          <SectionHeader title="Backlog" />
          <TaskList tasks={tasks.backlog} />
          <SectionHeader title="Current" />
          <TaskList tasks={tasks.current} />
          <SectionHeader title="Done" />
          <TaskList tasks={tasks.done} />
        </>
      );
    case "messengers":
      return (
        <>
          <SectionHeader title="Messengers" />
          <ul className="px-2 space-y-0.5">
            {MESSENGER_ITEMS.map((item) => {
              const active = item.key === messengerTab;
              return (
                <li key={item.key}>
                  <button
                    type="button"
                    onClick={() => onMessengerTabChange(item.key)}
                    aria-pressed={active}
                    className={
                      active
                        ? "w-full flex items-center gap-2 px-3 py-2 rounded text-sm bg-bg-secondary text-accent-primary font-medium"
                        : "w-full flex items-center gap-2 px-3 py-2 rounded text-sm text-text-secondary hover:bg-bg-secondary hover:text-text-primary"
                    }
                  >
                    <span className="text-base leading-none">{item.icon}</span>
                    <span>{item.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      );
    case "settings":
      return (
        <>
          <SectionHeader title="Settings" />
          <div className="text-text-muted text-sm px-4 space-y-2 leading-relaxed">
            <div>
              Модели агентов:{" "}
              <span className="text-text-code">config.yml</span>
            </div>
            <div>
              WebSocket:{" "}
              <span className="text-text-code">localhost:8765</span>
            </div>
            <div>
              Тема: <span className="text-text-code">Light</span>
            </div>
            <div>
              Версия:{" "}
              <span className="text-text-code">ClaudeOrch v0.1.0</span>
            </div>
            <div>
              GitHub:{" "}
              <a
                href="https://github.com/nnenoix/orck"
                target="_blank"
                rel="noreferrer"
                className="text-accent-primary hover:underline"
              >
                nnenoix/orck
              </a>
            </div>
          </div>
        </>
      );
  }
}

function App() {
  const [activeView, setActiveView] = useState<ActivityView>("agents");
  const [messengerTab, setMessengerTab] = useState<TabKey>("telegram");
  const { status, sendMessage } = useOrchestrator();
  const agents = useAgents();
  const logs = useLogs();

  const terminals: TerminalData[] = agents.map((a) => ({
    agent: a.name,
    status: a.status,
    lines: a.terminalOutput,
  }));

  const logEntries = logs.map((l) => ({
    id: l.id,
    timestamp: l.timestamp,
    agent: l.agent,
    action: l.action,
  }));

  function handleChatSubmit(text: string): boolean {
    return sendMessage({
      type: "message",
      from: "ui",
      to: "opus",
      content: text,
    });
  }

  const isPageView = activeView === "agents" || activeView === "messengers";

  return (
    <div className="h-screen flex flex-col bg-bg-primary text-text-primary overflow-hidden">
      <Header agentCount={agents.length} connectionStatus={status} />
      <div className="flex-1 flex overflow-hidden">
        <ActivityBar activeView={activeView} onSelect={setActiveView} />
        <aside className="w-64 h-full bg-bg-sidebar border-r border-border overflow-y-auto shrink-0">
          <SidebarContent
            view={activeView}
            agents={agents}
            messengerTab={messengerTab}
            onMessengerTabChange={setMessengerTab}
          />
        </aside>
        <main className="flex-1 flex flex-col overflow-hidden min-w-0">
          {isPageView ? (
            <div className="flex-1 overflow-hidden">
              {activeView === "agents" ? (
                <AgentList />
              ) : (
                <MessengerSettings
                  tab={messengerTab}
                  onTabChange={setMessengerTab}
                />
              )}
            </div>
          ) : (
            <>
              <div className="flex-1 overflow-hidden flex flex-col">
                <h2 className="text-text-muted uppercase text-xs tracking-widest px-6 pt-4 pb-2">
                  Terminals
                </h2>
                <div className="flex-1 overflow-hidden">
                  <TerminalGrid terminals={terminals} />
                </div>
              </div>
              <div className="h-56 border-t border-border flex bg-bg-secondary shrink-0">
                <div className="w-[40%] border-r border-border">
                  <ChatInput onSubmit={handleChatSubmit} />
                </div>
                <div className="flex-1 min-w-0">
                  <LogFeed entries={logEntries} />
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
