import { useState, useEffect, useRef, useMemo } from "react";
import { Icon } from "./icons";
import { useAgents, useTasks } from "../store/agentStore";
import { COMMANDS } from "../data/commands";
import type { CommandCenterState } from "./CommandCenterLayout";

interface CmdKProps {
  open: boolean;
  onClose: () => void;
  setState: (patch: Partial<CommandCenterState>) => void;
}

type IconKind = "Agent" | "Task" | "Nav" | "Cmd";

interface Item {
  id: string;
  label: string;
  hint: string;
  kbd?: string;
  icon: IconKind;
  color?: string;
  action: () => void;
}

interface Group {
  label: string;
  items: Item[];
}

export function CmdK({ open, onClose, setState }: CmdKProps) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const ref = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const agents = useAgents();
  const tasks = useTasks();

  useEffect(() => {
    if (open) {
      setTimeout(() => ref.current?.focus(), 10);
      setQ("");
      setSel(0);
    }
  }, [open]);

  const query = q.trim().toLowerCase();
  const match = (s: string) => !query || s.toLowerCase().includes(query);

  const groups = useMemo<Group[]>(() => {
    const g: Group[] = [];

    const ags: Item[] = agents
      .filter((a) => match(a.name) || match(a.status) || match(a.model))
      .slice(0, 6)
      .map((a) => ({
        id: `agent-${a.name}`,
        label: a.name,
        hint: `${a.model} · ${a.status}`,
        icon: "Agent" as const,
        action: () => { setState({ selectedAgent: a.name }); onClose(); },
      }));
    if (ags.length) g.push({ label: "Агенты", items: ags });

    const allTasks = [
      ...(tasks.backlog ?? []),
      ...(tasks.current ?? []),
      ...(tasks.done ?? []),
    ];
    const tks: Item[] = allTasks
      .filter((t) => match(t.title) || match(t.owner ?? "") || match(t.status))
      .slice(0, 5)
      .map((t) => ({
        id: `task-${t.id}`,
        label: t.title,
        hint: `${t.owner ?? "—"} · ${t.status}`,
        icon: "Task" as const,
        action: () => { setState({ view: "tasks" }); onClose(); },
      }));
    if (tks.length) g.push({ label: "Задачи", items: tks });

    const cmds: Item[] = COMMANDS
      .filter((c) => match(c.label) || match(c.hint))
      .map((c) => ({
        id: c.id,
        label: c.label,
        hint: c.hint,
        kbd: c.kbd,
        icon: "Cmd" as const,
        action: () => {
          if (c.id === "new-agent") setState({ view: "agents" });
          else if (c.id === "new-task") setState({ view: "tasks" });
          else if (c.id === "settings") setState({ view: "settings" });
          else if (c.id === "go-terminals") setState({ view: "terminals" });
          onClose();
        },
      }));
    if (cmds.length) g.push({ label: "Команды", items: cmds });

    const views: Item[] = ([
      { id: "view-agents",    label: "Agents",    hint: "Обзор всех агентов", kbd: "1", icon: "Nav" as IconKind, action: () => { setState({ view: "agents" });    onClose(); } },
      { id: "view-tasks",     label: "Tasks",     hint: "Backlog и план",     kbd: "2", icon: "Nav" as IconKind, action: () => { setState({ view: "tasks" });     onClose(); } },
      { id: "view-terminals", label: "Terminals", hint: "Live терминалы",     kbd: "3", icon: "Nav" as IconKind, action: () => { setState({ view: "terminals" }); onClose(); } },
      { id: "view-settings",  label: "Settings",  hint: "Настройки",          kbd: ",", icon: "Nav" as IconKind, action: () => { setState({ view: "settings" });  onClose(); } },
    ] as Item[]).filter((v) => match(v.label) || match(v.hint));
    if (views.length) g.push({ label: "Навигация", items: views });

    return g;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, agents, tasks, onClose, setState]);

  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups]);

  useEffect(() => {
    if (sel >= flat.length) setSel(0);
  }, [flat.length, sel]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, flat.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
      else if (e.key === "Enter") { e.preventDefault(); flat[sel]?.action(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, flat, sel]);

  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector(`[data-idx="${sel}"]`);
    if (el) (el as HTMLElement).scrollIntoView({ block: "nearest" });
  }, [sel]);

  if (!open) return null;

  const iconFor = (kind: IconKind, color?: string) => {
    const C = color ?? "var(--accent-hover)";
    if (kind === "Agent")
      return <div className="w-7 h-7 rounded-md flex items-center justify-center text-[11px] font-bold text-white" style={{ background: C }}>A</div>;
    if (kind === "Task")
      return <div className="w-7 h-7 rounded-md flex items-center justify-center" style={{ background: "var(--bg-secondary)", color: "var(--text-muted)" }}><Icon.Check size={13} /></div>;
    if (kind === "Nav")
      return <div className="w-7 h-7 rounded-md flex items-center justify-center" style={{ background: "var(--accent-light)", color: "var(--accent-hover)" }}><Icon.ArrowRight size={13} /></div>;
    return <div className="w-7 h-7 rounded-md flex items-center justify-center" style={{ background: "var(--bg-secondary)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}><Icon.Command size={12} /></div>;
  };

  let idx = -1;

  return (
    <div
      className="fixed inset-0 z-40 cmdk-backdrop flex items-start justify-center pt-[12vh]"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-[620px] max-w-[94vw] card overflow-hidden fade-up" style={{ boxShadow: "var(--shadow-lg)" }}>
        <div className="flex items-center gap-2 px-[var(--pad-4)] py-[var(--pad-3)] border-b" style={{ borderColor: "var(--border)" }}>
          <Icon.Search size={16} style={{ color: "var(--text-muted)" }} />
          <input
            ref={ref}
            value={q}
            onChange={(e) => { setQ(e.target.value); setSel(0); }}
            placeholder="Поиск агентов, задач, команд…"
            className="flex-1 bg-transparent focus:outline-none text-[14px]"
            style={{ color: "var(--text-primary)" }}
          />
          <kbd>Esc</kbd>
        </div>

        <div ref={listRef} className="max-h-[55vh] overflow-y-auto">
          {groups.length === 0 && (
            <div className="px-[var(--pad-4)] py-[var(--pad-6)] text-center text-[13px]" style={{ color: "var(--text-muted)" }}>
              Ничего не найдено для «{q}»
            </div>
          )}
          {groups.map((g) => (
            <div key={g.label}>
              <div
                className="px-[var(--pad-4)] pt-[var(--pad-3)] pb-[var(--pad-1)] text-[10px] uppercase"
                style={{ color: "var(--text-muted)", letterSpacing: "0.08em" }}
              >
                {g.label}
              </div>
              {g.items.map((it) => {
                idx++;
                const active = idx === sel;
                const my = idx;
                return (
                  <button
                    key={it.id}
                    data-idx={my}
                    onClick={it.action}
                    onMouseEnter={() => setSel(my)}
                    className="w-full flex items-center gap-3 px-[var(--pad-4)] py-[var(--pad-2)] text-left transition-colors"
                    style={{ background: active ? "var(--accent-light)" : "transparent" }}
                  >
                    {iconFor(it.icon, it.color)}
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium truncate" style={{ color: active ? "var(--accent-hover)" : "var(--text-primary)" }}>
                        {it.label}
                      </div>
                      <div className="text-[11px] truncate" style={{ color: "var(--text-muted)" }}>{it.hint}</div>
                    </div>
                    {it.kbd && <kbd>{it.kbd}</kbd>}
                    {active && <Icon.ArrowRight size={13} style={{ color: "var(--accent-hover)" }} />}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <div
          className="px-[var(--pad-4)] py-[var(--pad-2)] text-[10.5px] flex items-center gap-4"
          style={{ borderTop: "1px solid var(--border)", color: "var(--text-muted)" }}
        >
          <span className="flex items-center gap-1"><kbd>↑</kbd><kbd>↓</kbd> навигация</span>
          <span className="flex items-center gap-1"><kbd>↵</kbd> выполнить</span>
          <span className="flex items-center gap-1"><kbd>Esc</kbd> закрыть</span>
          <span className="ml-auto">{flat.length} результата</span>
        </div>
      </div>
    </div>
  );
}
