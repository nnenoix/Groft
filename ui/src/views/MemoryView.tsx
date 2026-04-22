import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ErrorBox } from "../components/ErrorBox";

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

function classifyFile(filename: string): "pinned" | "feedback" | "project" | "user" | "reference" | "other" {
  if (PINNED_ORDER.includes(filename)) return "pinned";
  if (filename.startsWith("feedback_")) return "feedback";
  if (filename.startsWith("project_")) return "project";
  if (filename.startsWith("user_")) return "user";
  if (filename.startsWith("reference_")) return "reference";
  return "other";
}

const CATEGORY_LABEL: Record<ReturnType<typeof classifyFile>, string> = {
  pinned: "Главное",
  feedback: "Feedback rules",
  project: "Project",
  user: "User",
  reference: "References",
  other: "Прочее",
};

const CATEGORY_ORDER: Array<ReturnType<typeof classifyFile>> = [
  "pinned",
  "feedback",
  "project",
  "user",
  "reference",
  "other",
];

export function MemoryView() {
  const [files, setFiles] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const list = await invoke<string[]>("list_memory_files");
      setFiles(sortFiles(list));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Auto-select the first file once the list arrives, and re-pick the head
  // if the previously-selected file disappeared after a refresh.
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
    invoke<string>("read_memory_file", { name: selected })
      .then((c) => {
        setContent(c);
        setError(null);
      })
      .catch((e) => {
        setContent("");
        setError(String(e));
      })
      .finally(() => setLoading(false));
  }, [selected]);

  const grouped: Partial<Record<ReturnType<typeof classifyFile>, string[]>> = {};
  for (const f of files) {
    const cat = classifyFile(f);
    (grouped[cat] ||= []).push(f);
  }

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
            memory/*.md — grepается через MCP
          </div>
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
                memory/{selected}
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
