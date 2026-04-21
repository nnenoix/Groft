import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Icon } from "../components/icons";
import { MODEL_OPTIONS } from "../data/models";

const NAME_RE = /^[a-z][a-z0-9-]{1,30}$/;
const AVAILABLE_TOOLS = ["Read", "Write", "Edit", "Bash", "Grep", "Glob"] as const;
const MODELS_URL = "http://localhost:8766/agents/models";

interface AgentEntry {
  filename: string;
  name: string;
  content: string;
}

function buildContent(input: {
  name: string;
  role: string;
  model: string;
  tools: string[];
  prompt: string;
}): string {
  const tools = input.tools.length > 0 ? input.tools.join(", ") : "—";
  return [
    `# ${input.name}`,
    "",
    "## Роль",
    input.role,
    "",
    "## Модель",
    input.model,
    "",
    "## Инструменты",
    tools,
    "",
    "## Промпт",
    input.prompt,
    "",
  ].join("\n");
}

function errorToString(e: unknown): string {
  if (typeof e === "string") return e;
  if (e instanceof Error) return e.message;
  return String(e);
}

function parseAgentEntry(raw: string): AgentEntry | null {
  const sepIdx = raw.indexOf("|");
  if (sepIdx < 0) return null;
  const filename = raw.slice(0, sepIdx);
  const content = raw.slice(sepIdx + 1);
  const name = filename.replace(/\.md$/, "");
  return { filename, name, content };
}

async function loadAgents(): Promise<AgentEntry[]> {
  try {
    const raws = await invoke<string[]>("list_agent_files");
    return raws.map(parseAgentEntry).filter((e): e is AgentEntry => e !== null);
  } catch {
    return [];
  }
}

export function SubagentsView() {
  const [agents, setAgents] = useState<AgentEntry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const list = await loadAgents();
    setAgents(list);
    setLoaded(true);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selectedAgent = useMemo(
    () => agents.find((a) => a.name === selected) ?? null,
    [agents, selected],
  );

  async function handleDelete(agent: AgentEntry) {
    const confirmed = window.confirm(`Удалить субагента «${agent.name}»?`);
    if (!confirmed) return;
    try {
      await invoke<void>("delete_agent_file", { name: agent.name });
      if (selected === agent.name) setSelected(null);
      await refresh();
    } catch (err) {
      window.alert(`Не удалось удалить: ${errorToString(err)}`);
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <header
        className="shrink-0 flex items-center justify-between px-[var(--pad-5)] py-[var(--pad-3)]"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div>
          <div
            className="text-[11px] uppercase tracking-[0.2em] font-semibold"
            style={{ color: "var(--text-muted)" }}
          >
            Субагенты
          </div>
          <h2 className="font-display font-semibold text-[18px] tracking-tight">
            .claude/agents
          </h2>
        </div>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="btn btn-primary text-[12px]"
        >
          <Icon.Plus size={14} />
          <span>Создать</span>
        </button>
      </header>

      <div className="flex-1 min-h-0 flex">
        <aside
          className="shrink-0 overflow-y-auto"
          style={{
            width: 260,
            borderRight: "1px solid var(--border)",
            background: "var(--bg-secondary)",
          }}
        >
          {!loaded && (
            <div
              className="p-[var(--pad-4)] text-[12px]"
              style={{ color: "var(--text-muted)" }}
            >
              Загружаю…
            </div>
          )}
          {loaded && agents.length === 0 && (
            <div
              className="p-[var(--pad-4)] text-[12px] leading-relaxed"
              style={{ color: "var(--text-muted)" }}
            >
              Субагентов ещё нет. Нажмите <b>Создать</b>, чтобы сделать первого.
            </div>
          )}
          <ul>
            {agents.map((a) => {
              const active = a.name === selected;
              return (
                <li key={a.filename}>
                  <button
                    type="button"
                    onClick={() => setSelected(a.name)}
                    className="w-full text-left px-[var(--pad-4)] py-2 flex items-center gap-2 transition-colors"
                    style={{
                      background: active ? "var(--accent-light)" : "transparent",
                      color: active ? "var(--accent-hover)" : "var(--text-primary)",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <Icon.Users size={12} />
                    <span className="font-mono text-[12.5px]">{a.name}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        <main className="flex-1 min-h-0 overflow-y-auto p-[var(--pad-5)]">
          {!selectedAgent && (
            <div
              className="text-[12.5px] leading-relaxed max-w-[480px]"
              style={{ color: "var(--text-muted)" }}
            >
              <p>
                Субагенты — это шаблоны в <span className="font-mono">.claude/agents/*.md</span>,
                которые Opus использует через <span className="font-mono">Task tool</span>.
                Каждый шаблон задаёт роль, модель, набор инструментов и системный промпт.
              </p>
              <p className="mt-3">Выберите субагента слева или создайте нового.</p>
            </div>
          )}
          {selectedAgent && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-display font-semibold text-[15px]">
                  {selectedAgent.name}
                </h3>
                <button
                  type="button"
                  onClick={() => handleDelete(selectedAgent)}
                  className="btn btn-ghost text-[11.5px]"
                  style={{ color: "var(--status-stuck)" }}
                >
                  <Icon.Trash size={12} />
                  <span>Удалить</span>
                </button>
              </div>
              <pre
                className="whitespace-pre-wrap font-mono text-[12px] p-[var(--pad-4)] rounded-md"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                }}
              >
                {selectedAgent.content}
              </pre>
            </div>
          )}
        </main>
      </div>

      {showCreate && (
        <CreateAgentModal
          onClose={() => setShowCreate(false)}
          onCreated={async (name) => {
            setShowCreate(false);
            await refresh();
            setSelected(name);
          }}
        />
      )}
    </div>
  );
}

interface CreateAgentModalProps {
  onClose: () => void;
  onCreated: (name: string) => void;
}

function CreateAgentModal({ onClose, onCreated }: CreateAgentModalProps) {
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [role, setRole] = useState("");
  const [models, setModels] = useState<string[]>([...MODEL_OPTIONS]);
  const [model, setModel] = useState<string>(MODEL_OPTIONS[0]);
  const [prompt, setPrompt] = useState("");
  const [tools, setTools] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  const nameInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const id = requestAnimationFrame(() => {
      if (!cancelled) setMounted(true);
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(id);
    };
  }, []);

  useEffect(() => {
    nameInputRef.current?.focus();
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    (async () => {
      try {
        const res = await fetch(MODELS_URL, { signal: ac.signal });
        if (!res.ok) return;
        const body: unknown = await res.json();
        if (
          body &&
          typeof body === "object" &&
          Array.isArray((body as { models?: unknown }).models)
        ) {
          const list = (body as { models: unknown[] }).models.filter(
            (m): m is string => typeof m === "string",
          );
          if (list.length > 0) {
            setModels(list);
            setModel((prev) => (list.includes(prev) ? prev : list[0]));
          }
        }
      } catch {
        // network/parse errors → keep hardcoded fallback
      }
    })();
    return () => ac.abort();
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) {
        e.stopPropagation();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  const nameValid = NAME_RE.test(name);
  const nameError = nameTouched && !nameValid
    ? "Только строчные латинские буквы, цифры и дефис; 2–31 символов, начинается с буквы."
    : null;

  const canSubmit = useMemo(() => {
    return nameValid && role.trim().length > 0 && prompt.trim().length > 0 && !submitting;
  }, [nameValid, role, prompt, submitting]);

  function toggleTool(t: string) {
    setTools((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const content = buildContent({ name, role: role.trim(), model, tools, prompt: prompt.trim() });
      await invoke<void>("write_agent_file", { name, content });
      onCreated(name);
    } catch (err) {
      setFormError(errorToString(err));
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center p-[var(--pad-5)]"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div className="absolute inset-0" style={{ background: "rgba(15, 22, 20, 0.45)" }} />
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        className="relative flex flex-col rounded-[var(--radius-lg)] overflow-hidden"
        style={{
          width: 560,
          maxWidth: "100%",
          maxHeight: "90vh",
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-lg)",
          opacity: mounted ? 1 : 0,
          transform: mounted ? "translateY(0) scale(1)" : "translateY(8px) scale(0.98)",
          transition: "opacity 220ms ease-out, transform 280ms cubic-bezier(0.2, 0.9, 0.3, 1)",
        }}
      >
        <div className="shrink-0 p-[var(--pad-5)] flex items-start gap-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="flex-1 min-w-0">
            <div className="text-[11px] uppercase tracking-[0.2em] font-semibold mb-1" style={{ color: "var(--text-muted)" }}>
              Новый субагент
            </div>
            <h2 className="font-display font-semibold text-[18px] tracking-tight">Создать субагента</h2>
            <p className="text-[12px] mt-0.5" style={{ color: "var(--text-muted)" }}>
              Файл сохранится в <span className="font-mono" style={{ color: "var(--text-code)" }}>.claude/agents/{name || "<name>"}.md</span>
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="btn btn-ghost !p-1"
            aria-label="Закрыть"
          >
            <Icon.X size={14} />
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-[var(--pad-5)] space-y-[var(--pad-4)]">
          {formError && (
            <div
              className="px-3 py-2 rounded-md text-[12px]"
              style={{
                background: "var(--tint-danger)",
                color: "var(--status-stuck)",
                border: "1px solid var(--status-stuck)",
              }}
              role="alert"
            >
              {formError}
            </div>
          )}

          <label className="block space-y-1.5">
            <span className="text-[10.5px] uppercase tracking-[0.16em] font-semibold" style={{ color: "var(--text-muted)" }}>
              Имя
            </span>
            <input
              ref={nameInputRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => setNameTouched(true)}
              placeholder="security-auditor"
              spellCheck={false}
              autoComplete="off"
              className="w-full px-3 py-2 rounded-md text-[13px] font-mono focus:outline-none"
              style={{
                background: "var(--bg-secondary)",
                border: `1px solid ${nameError ? "var(--status-stuck)" : "var(--border)"}`,
                color: "var(--text-primary)",
              }}
            />
            {nameError && (
              <span className="text-[11px]" style={{ color: "var(--status-stuck)" }}>
                {nameError}
              </span>
            )}
          </label>

          <label className="block space-y-1.5">
            <span className="text-[10.5px] uppercase tracking-[0.16em] font-semibold" style={{ color: "var(--text-muted)" }}>
              Роль
            </span>
            <input
              type="text"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="Security auditor"
              className="w-full px-3 py-2 rounded-md text-[13px] focus:outline-none"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-[10.5px] uppercase tracking-[0.16em] font-semibold" style={{ color: "var(--text-muted)" }}>
              Модель
            </span>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full px-3 py-2 rounded-md text-[12px] font-mono focus:outline-none"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            >
              {models.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </label>

          <div className="space-y-1.5">
            <span className="text-[10.5px] uppercase tracking-[0.16em] font-semibold block" style={{ color: "var(--text-muted)" }}>
              Инструменты
            </span>
            <div className="flex flex-wrap gap-2">
              {AVAILABLE_TOOLS.map((t) => {
                const active = tools.includes(t);
                return (
                  <button
                    type="button"
                    key={t}
                    onClick={() => toggleTool(t)}
                    aria-pressed={active}
                    className="px-2.5 py-1 rounded-full text-[11.5px] font-medium transition-colors"
                    style={{
                      background: active ? "var(--accent-light)" : "var(--bg-secondary)",
                      color: active ? "var(--accent-hover)" : "var(--text-secondary)",
                      border: `1px solid ${active ? "var(--accent-dim)" : "var(--border)"}`,
                    }}
                  >
                    {t}
                  </button>
                );
              })}
            </div>
          </div>

          <label className="block space-y-1.5">
            <span className="text-[10.5px] uppercase tracking-[0.16em] font-semibold" style={{ color: "var(--text-muted)" }}>
              Промпт
            </span>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={8}
              placeholder="Ты агент, который проверяет код на уязвимости…"
              className="w-full px-3 py-2 rounded-md text-[12px] font-mono focus:outline-none"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
                resize: "vertical",
                minHeight: "8rem",
              }}
            />
          </label>
        </div>

        <div className="shrink-0 p-[var(--pad-5)] flex justify-end gap-2" style={{ borderTop: "1px solid var(--border)" }}>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="btn btn-outline text-[12px]"
          >
            Отмена
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="btn btn-primary text-[12px]"
            style={{ opacity: canSubmit ? 1 : 0.55, cursor: canSubmit ? "pointer" : "not-allowed" }}
          >
            {submitting ? "Создаю…" : "Создать субагента"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default SubagentsView;
