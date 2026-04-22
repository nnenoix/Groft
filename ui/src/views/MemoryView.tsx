import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ErrorBox } from "../components/ErrorBox";

type Source = "repo" | "auto";

const PINNED_ORDER = ["MEMORY.md", "shared.md", "current-plan.md", "session-log.md"];

function sortFiles(files: string[]): string[] {
  const pinned: string[] = [];
  const rest: string[] = [];
  const pinnedSet = new Set(PINNED_ORDER);
  for (const f of files) {
    if (pinnedSet.has(f)) continue;
    rest.push(f);
  }
  for (const name of PINNED_ORDER) {
    if (files.includes(name)) pinned.push(name);
  }
  rest.sort();
  return [...pinned, ...rest];
}

function humanLabel(filename: string): string {
  return filename.replace(/\.md$/, "");
}

type Category = "pinned" | "feedback" | "project" | "user" | "reference" | "other";

function classifyFile(filename: string): Category {
  if (PINNED_ORDER.includes(filename)) return "pinned";
  if (filename.startsWith("feedback_")) return "feedback";
  if (filename.startsWith("project_")) return "project";
  if (filename.startsWith("user_")) return "user";
  if (filename.startsWith("reference_")) return "reference";
  return "other";
}

const CATEGORY_LABEL: Record<Category, string> = {
  pinned: "Главное",
  feedback: "Feedback rules",
  project: "Project",
  user: "User",
  reference: "References",
  other: "Прочее",
};

const CATEGORY_ORDER: Category[] = [
  "pinned",
  "feedback",
  "project",
  "user",
  "reference",
  "other",
];

const SOURCE_META: Record<Source, { list: string; read: string; label: string; hint: string; pathPrefix: string }> = {
  repo: {
    list: "list_memory_files",
    read: "read_memory_file",
    label: "Репо",
    hint: "memory/*.md — grepается через MCP",
    pathPrefix: "memory/",
  },
  auto: {
    list: "list_auto_memory_files",
    read: "read_auto_memory_file",
    label: "Auto",
    hint: "~/.claude/projects/<slug>/memory — кросс-сессионная",
    pathPrefix: "~/.claude/…/memory/",
  },
};

export function MemoryView() {
  const [source, setSource] = useState<Source>("repo");
  const [files, setFiles] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const list = await invoke<string[]>(SOURCE_META[source].list);
      setFiles(sortFiles(list));
      setError(null);
    } catch (e) {
      setFiles([]);
      setError(String(e));
    }
  }, [source]);

  useEffect(() => {
    // Clear everything on source flip — otherwise a stale `selected` from the
    // other source can race the auto-pick effect and trigger a read against
    // a file that doesn't exist in the new source (→ os error 123 on Windows
    // if the stale name contains characters invalid in the other namespace).
    setFiles([]);
    setSelected(null);
    setContent("");
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (files.length === 0) return;
    if (selected === null || !files.includes(selected)) {
      setSelected(files[0]);
    }
  }, [files, selected]);

  useEffect(() => {
    if (!selected) {
      setContent("");
      return;
    }
    setLoading(true);
    invoke<string>(SOURCE_META[source].read, { name: selected })
      .then((c) => {
        setContent(c);
        setError(null);
      })
      .catch((e) => {
        setContent("");
        setError(String(e));
      })
      .finally(() => setLoading(false));
  }, [selected, source]);

  const grouped: Partial<Record<Category, string[]>> = {};
  for (const f of files) {
    const cat = classifyFile(f);
    (grouped[cat] ||= []).push(f);
  }

  const meta = SOURCE_META[source];

  return (
    <div className="flex-1 flex overflow-hidden">
      <aside
        className="w-64 shrink-0 overflow-y-auto"
        style={{ borderRight: "1px solid var(--border)", background: "var(--bg-sidebar)" }}
      >
        <header
          className="px-[var(--pad-4)] pt-[var(--pad-4)] pb-[var(--pad-3)] sticky top-0"
          style={{ background: "var(--bg-sidebar)", borderBottom: "1px solid var(--border)" }}
        >
          <h1 className="font-display text-[14px] font-semibold tracking-tight">Память</h1>
          <div className="text-[10.5px] mt-0.5" style={{ color: "var(--text-muted)" }}>
            {meta.hint}
          </div>
          <SourceToggle source={source} onChange={setSource} />
        </header>

        <div className="py-2">
          {CATEGORY_ORDER.map((cat) => {
            const items = grouped[cat];
            if (!items || items.length === 0) return null;
            return (
              <div key={cat} className="mb-3">
                <div
                  className="px-[var(--pad-4)] py-1 text-[10px] font-mono uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  {CATEGORY_LABEL[cat]}
                </div>
                {items.map((f) => (
                  <button
                    key={f}
                    onClick={() => setSelected(f)}
                    className="w-full text-left px-[var(--pad-4)] py-1.5 text-[12px] transition-colors"
                    style={{
                      background: selected === f ? "var(--accent-light)" : "transparent",
                      color:
                        selected === f ? "var(--accent-hover)" : "var(--text-secondary)",
                      fontWeight: selected === f ? 600 : 400,
                    }}
                  >
                    {humanLabel(f)}
                  </button>
                ))}
              </div>
            );
          })}
          {files.length === 0 && (
            <div className="px-[var(--pad-4)] py-4 text-[12px]" style={{ color: "var(--text-muted)" }}>
              Пусто.
            </div>
          )}
        </div>
      </aside>

      <main className="flex-1 min-w-0 overflow-auto">
        <header
          className="px-[var(--pad-6)] py-[var(--pad-4)] flex items-center justify-between"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div>
            <h2 className="font-display text-[15px] font-semibold tracking-tight">
              {selected ? humanLabel(selected) : "Нет выбранного файла"}
            </h2>
            {selected && (
              <div className="text-[10.5px] mt-0.5 font-mono" style={{ color: "var(--text-muted)" }}>
                {meta.pathPrefix}{selected}
              </div>
            )}
          </div>
          <button
            onClick={() => void refresh()}
            className="btn btn-outline text-[11.5px]"
            title="Обновить список"
          >
            ↻
          </button>
        </header>

        {error && <ErrorBox message={error} />}

        <div className="px-[var(--pad-6)] py-[var(--pad-5)]">
          {loading ? (
            <div className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
              Загрузка…
            </div>
          ) : selected ? (
            <pre
              className="text-[12.5px] font-mono whitespace-pre-wrap leading-relaxed"
              style={{ color: "var(--text-secondary)" }}
            >
              {content}
            </pre>
          ) : (
            <div className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
              Выбери файл слева.
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function SourceToggle({
  source,
  onChange,
}: {
  source: Source;
  onChange: (s: Source) => void;
}) {
  const sources: Source[] = ["repo", "auto"];
  return (
    <div
      className="mt-3 flex rounded-md overflow-hidden text-[11px]"
      style={{ border: "1px solid var(--border)" }}
    >
      {sources.map((s) => {
        const active = source === s;
        return (
          <button
            key={s}
            onClick={() => onChange(s)}
            className="flex-1 py-1.5 font-mono transition-colors"
            style={{
              background: active ? "var(--accent-light)" : "transparent",
              color: active ? "var(--accent-hover)" : "var(--text-muted)",
              fontWeight: active ? 600 : 400,
            }}
          >
            {SOURCE_META[s].label}
          </button>
        );
      })}
    </div>
  );
}
