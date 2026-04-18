import { useState } from "react";
import Header from "./components/Header";
import ActivityBar, { type ActivityView } from "./components/ActivityBar";
import AgentCard from "./components/AgentCard";
import TaskList from "./components/TaskList";
import ChatInput from "./components/ChatInput";
import LogFeed from "./components/LogFeed";
import TerminalGrid, { type TerminalData } from "./components/TerminalGrid";
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

function SidebarContent({
  view,
  agents,
}: {
  view: ActivityView;
  agents: AgentState[];
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
    case "logs":
      return (
        <>
          <SectionHeader title="Logs" />
          <div className="text-text-muted text-sm px-4 leading-relaxed">
            Последние события — в нижней панели под терминалами.
          </div>
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
            <div className="text-text-dim">Редактирование — скоро</div>
          </div>
        </>
      );
  }
}

function App() {
  const [activeView, setActiveView] = useState<ActivityView>("agents");
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

  return (
    <div className="h-screen flex flex-col bg-bg-primary text-text-primary overflow-hidden">
      <Header agentCount={agents.length} connectionStatus={status} />
      <div className="flex-1 flex overflow-hidden">
        <ActivityBar activeView={activeView} onSelect={setActiveView} />
        <aside className="w-64 h-full bg-bg-sidebar border-r border-border overflow-y-auto shrink-0">
          <SidebarContent view={activeView} agents={agents} />
        </aside>
        <main className="flex-1 flex flex-col overflow-hidden min-w-0">
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
        </main>
      </div>
    </div>
  );
}

export default App;
