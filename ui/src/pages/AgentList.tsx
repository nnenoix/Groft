import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import AgentCreate, { type AgentFormValues } from "./AgentCreate";

// read_agent_files returns Vec<String>, where each entry is encoded as
// "<filename>|<content>" (filename is basename including .md; content is
// the full file body including the YAML frontmatter fenced by ---).
// The split is on the FIRST '|' only — file contents may contain '|'.

const PROJECT_AGENTS_DIR = "/mnt/d/orchkerstr/.claude/agents";

interface ParsedAgent {
  filename: string;
  path: string;
  name: string;
  description: string;
  values: AgentFormValues | null;
}

function splitOnFirst(s: string, sep: string): [string, string] | null {
  const i = s.indexOf(sep);
  if (i === -1) return null;
  return [s.slice(0, i), s.slice(i + 1)];
}

function extractFrontmatter(content: string): Record<string, string> | null {
  const lines = content.split(/\r?\n/);
  if (lines[0] !== "---") return null;
  const endIdx = lines.findIndex((line, i) => i > 0 && line === "---");
  if (endIdx === -1) return null;
  const result: Record<string, string> = {};
  for (let i = 1; i < endIdx; i += 1) {
    const line = lines[i];
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    result[key] = value;
  }
  return result;
}

function extractBody(content: string): string {
  const lines = content.split(/\r?\n/);
  if (lines[0] !== "---") return content;
  const endIdx = lines.findIndex((line, i) => i > 0 && line === "---");
  if (endIdx === -1) return content;
  return lines
    .slice(endIdx + 1)
    .join("\n")
    .replace(/^\n+/, "")
    .replace(/\n+$/, "");
}

function parseEntry(entry: string): ParsedAgent {
  const split = splitOnFirst(entry, "|");
  if (!split) {
    return {
      filename: entry,
      path: `${PROJECT_AGENTS_DIR}/${entry}`,
      name: entry,
      description: "",
      values: null,
    };
  }
  const [filename, content] = split;
  const fm = extractFrontmatter(content);
  if (!fm) {
    return {
      filename,
      path: `${PROJECT_AGENTS_DIR}/${filename}`,
      name: filename.replace(/\.md$/, ""),
      description: "",
      values: null,
    };
  }
  const name = fm.name ?? filename.replace(/\.md$/, "");
  const description = fm.description ?? "";
  const body = extractBody(content);
  const toolsRaw = fm.tools ?? "";
  const tools = toolsRaw
    .split(",")
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
  const model = fm.model && fm.model !== "inherit" ? fm.model : "";
  const values: AgentFormValues = {
    name,
    role: description,
    model: model || "claude-sonnet-4-6",
    systemPrompt: body,
    tools,
    scope: "project",
  };
  return {
    filename,
    path: `${PROJECT_AGENTS_DIR}/${filename}`,
    name,
    description,
    values,
  };
}

function AgentList() {
  const [agents, setAgents] = useState<ParsedAgent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<
    | { kind: "idle" }
    | { kind: "create" }
    | { kind: "edit"; initial: AgentFormValues }
  >({ kind: "idle" });

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const entries = await invoke<string[]>("read_agent_files", {
        dir: PROJECT_AGENTS_DIR,
      });
      setAgents(entries.map(parseEntry));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function handleDelete(agent: ParsedAgent) {
    const ok = window.confirm(`Удалить агента ${agent.name}?`);
    if (!ok) return;
    try {
      await invoke<void>("delete_agent_file", { path: agent.path });
      await refetch();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    }
  }

  function closeModal() {
    setMode({ kind: "idle" });
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-bg-primary text-text-primary">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-semibold">Агенты</h1>
        <button
          type="button"
          onClick={() => setMode({ kind: "create" })}
          className="w-8 h-8 flex items-center justify-center rounded-full bg-accent-primary text-white hover:bg-accent-hover text-lg leading-none"
          aria-label="Новый агент"
        >
          +
        </button>
      </div>

      {error && (
        <div className="mb-3 text-sm text-status-stuck border border-status-stuck rounded px-3 py-2 bg-bg-secondary">
          {error}
        </div>
      )}

      {loading && agents.length === 0 && (
        <div className="text-text-muted text-sm">Загрузка...</div>
      )}

      {!loading && agents.length === 0 && !error && (
        <div className="text-text-muted text-sm">
          Пока нет агентов. Нажмите "+" чтобы создать.
        </div>
      )}

      <ul className="space-y-2">
        {agents.map((agent) => (
          <li
            key={agent.filename}
            className="bg-bg-card border border-border rounded-md p-3 flex items-center gap-3"
          >
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold truncate">
                {agent.name}
              </div>
              <div className="text-xs text-text-muted truncate">
                {agent.description || agent.filename}
              </div>
            </div>
            <button
              type="button"
              onClick={() =>
                agent.values &&
                setMode({ kind: "edit", initial: agent.values })
              }
              disabled={!agent.values}
              className="px-3 py-1.5 rounded text-xs border border-border text-text-secondary hover:bg-bg-secondary disabled:opacity-40"
            >
              Редактировать
            </button>
            <button
              type="button"
              onClick={() => handleDelete(agent)}
              className="px-3 py-1.5 rounded text-xs border border-status-stuck text-status-stuck hover:bg-accent-light"
            >
              Удалить
            </button>
          </li>
        ))}
      </ul>

      {mode.kind !== "idle" && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-6"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeModal();
          }}
        >
          <AgentCreate
            onClose={closeModal}
            onSaved={refetch}
            initialValues={
              mode.kind === "edit" ? mode.initial : undefined
            }
          />
        </div>
      )}
    </div>
  );
}

export default AgentList;
