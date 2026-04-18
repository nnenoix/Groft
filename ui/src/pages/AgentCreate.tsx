import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { homeDir } from "@tauri-apps/api/path";

export type AgentScope = "project" | "user";

export interface AgentFormValues {
  name: string;
  role: string;
  model: string;
  systemPrompt: string;
  tools: string[];
  scope: AgentScope;
}

export interface AgentCreateProps {
  onClose: () => void;
  onSaved?: () => void;
  initialValues?: AgentFormValues;
}

// Hardcoded for now — the integrator will wire a real project-root
// source (config.yml / tauri state) later.
const PROJECT_ROOT = "/mnt/d/orchkerstr";

const MODEL_OPTIONS = [
  "claude-opus-4-7",
  "claude-sonnet-4-6",
  "claude-haiku-4-5-20251001",
];

const TOOL_OPTIONS = ["Read", "Write", "Edit", "Bash"];

const NAME_REGEX = /^[a-z][a-z0-9-]*[a-z0-9]$/;

const EMPTY_VALUES: AgentFormValues = {
  name: "",
  role: "",
  model: MODEL_OPTIONS[1],
  systemPrompt: "",
  tools: ["Read", "Write", "Edit", "Bash"],
  scope: "project",
};

interface Errors {
  name?: string;
  role?: string;
  systemPrompt?: string;
}

function validate(values: AgentFormValues): Errors {
  const errors: Errors = {};
  if (values.name.length < 2) {
    errors.name = "Минимум 2 символа";
  } else if (!NAME_REGEX.test(values.name)) {
    errors.name = "Только a-z, 0-9 и дефис; начинается с буквы";
  }
  if (values.role.trim().length < 5) {
    errors.role = "Минимум 5 символов";
  }
  if (values.systemPrompt.trim().length < 20) {
    errors.systemPrompt = "Минимум 20 символов";
  }
  return errors;
}

function buildMarkdown(values: AgentFormValues): string {
  const toolsLine = values.tools.join(", ");
  return `---
name: ${values.name}
description: ${values.role}
model: ${values.model}
tools: ${toolsLine}
---
${values.systemPrompt}
`;
}

async function resolvePath(values: AgentFormValues): Promise<string> {
  if (values.scope === "user") {
    const home = await homeDir();
    const trimmed = home.endsWith("/") ? home.slice(0, -1) : home;
    return `${trimmed}/.claude/agents/${values.name}.md`;
  }
  return `${PROJECT_ROOT}/.claude/agents/${values.name}.md`;
}

function AgentCreate({ onClose, onSaved, initialValues }: AgentCreateProps) {
  const [values, setValues] = useState<AgentFormValues>(
    initialValues ?? EMPTY_VALUES,
  );
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<{
    kind: "ok" | "err";
    text: string;
  } | null>(null);

  useEffect(() => {
    if (!toast) return;
    if (toast.kind !== "ok") return;
    const id = setTimeout(() => setToast(null), 2000);
    return () => clearTimeout(id);
  }, [toast]);

  const errors = validate(values);
  const canSubmit = Object.keys(errors).length === 0 && !submitting;

  function patch<K extends keyof AgentFormValues>(
    key: K,
    value: AgentFormValues[K],
  ) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function toggleTool(tool: string) {
    setValues((prev) => {
      const has = prev.tools.includes(tool);
      const nextTools = has
        ? prev.tools.filter((t) => t !== tool)
        : [...prev.tools, tool];
      return { ...prev, tools: nextTools };
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setToast(null);
    try {
      const path = await resolvePath(values);
      const content = buildMarkdown(values);
      await invoke<void>("write_agent_file", { path, content });
      setToast({ kind: "ok", text: "Агент создан" });
      onSaved?.();
      setTimeout(() => onClose(), 600);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setToast({ kind: "err", text: msg });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-bg-card border border-border rounded-md p-5 w-full max-w-[560px] space-y-4 text-text-primary"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">
          {initialValues ? "Редактировать агента" : "Новый агент"}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="text-text-muted hover:text-text-primary text-sm"
        >
          ✕
        </button>
      </div>

      <label className="block space-y-1">
        <span className="text-xs uppercase tracking-widest text-text-muted">
          Имя (slug)
        </span>
        <input
          type="text"
          value={values.name}
          onChange={(e) => patch("name", e.target.value)}
          disabled={Boolean(initialValues)}
          className="w-full px-3 py-2 rounded bg-bg-secondary border border-border text-sm focus:outline-none focus:border-accent-primary disabled:opacity-60"
          placeholder="my-agent"
        />
        {errors.name && (
          <span className="text-xs text-status-stuck">{errors.name}</span>
        )}
      </label>

      <label className="block space-y-1">
        <span className="text-xs uppercase tracking-widest text-text-muted">
          Роль
        </span>
        <input
          type="text"
          value={values.role}
          onChange={(e) => patch("role", e.target.value)}
          className="w-full px-3 py-2 rounded bg-bg-secondary border border-border text-sm focus:outline-none focus:border-accent-primary"
          placeholder="Короткое описание"
        />
        {errors.role && (
          <span className="text-xs text-status-stuck">{errors.role}</span>
        )}
      </label>

      <label className="block space-y-1">
        <span className="text-xs uppercase tracking-widest text-text-muted">
          Модель
        </span>
        <select
          value={values.model}
          onChange={(e) => patch("model", e.target.value)}
          className="w-full px-3 py-2 rounded bg-bg-secondary border border-border text-sm focus:outline-none focus:border-accent-primary"
        >
          {MODEL_OPTIONS.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>

      <label className="block space-y-1">
        <span className="text-xs uppercase tracking-widest text-text-muted">
          Системный промпт
        </span>
        <textarea
          value={values.systemPrompt}
          onChange={(e) => patch("systemPrompt", e.target.value)}
          rows={6}
          className="w-full px-3 py-2 rounded bg-bg-secondary border border-border text-sm font-mono focus:outline-none focus:border-accent-primary"
          placeholder="Ты ..."
        />
        {errors.systemPrompt && (
          <span className="text-xs text-status-stuck">
            {errors.systemPrompt}
          </span>
        )}
      </label>

      <div className="space-y-1">
        <span className="text-xs uppercase tracking-widest text-text-muted block">
          Инструменты
        </span>
        <div className="flex gap-4 flex-wrap">
          {TOOL_OPTIONS.map((tool) => (
            <label key={tool} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={values.tools.includes(tool)}
                onChange={() => toggleTool(tool)}
                className="accent-accent-primary"
              />
              <span>{tool}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="space-y-1">
        <span className="text-xs uppercase tracking-widest text-text-muted block">
          Scope
        </span>
        <div className="flex gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="scope"
              value="project"
              checked={values.scope === "project"}
              onChange={() => patch("scope", "project")}
              className="accent-accent-primary"
            />
            <span>Этот проект</span>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="scope"
              value="user"
              checked={values.scope === "user"}
              onChange={() => patch("scope", "user")}
              className="accent-accent-primary"
            />
            <span>Все проекты</span>
          </label>
        </div>
      </div>

      {toast && (
        <div
          className={
            toast.kind === "ok"
              ? "rounded border border-status-active text-status-active bg-accent-light px-3 py-2 text-sm"
              : "rounded border border-status-stuck text-status-stuck bg-bg-secondary px-3 py-2 text-sm"
          }
        >
          {toast.text}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onClose}
          className="px-4 py-2 rounded text-sm border border-border text-text-secondary hover:bg-bg-secondary"
        >
          Отмена
        </button>
        <button
          type="submit"
          disabled={!canSubmit}
          className="px-4 py-2 rounded text-sm bg-accent-primary text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? "Сохранение..." : "Сохранить"}
        </button>
      </div>
    </form>
  );
}

export default AgentCreate;
