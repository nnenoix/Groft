import { useCallback, useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ErrorBox } from "../components/ErrorBox";

const HEADING_RE = /^##\s+(.+)$/;

interface DecisionEntry {
  title: string;
  body: string;
}

function parseDecisions(raw: string): DecisionEntry[] {
  const lines = raw.split(/\r?\n/);
  const entries: DecisionEntry[] = [];
  let current: DecisionEntry | null = null;
  for (const line of lines) {
    const m = line.match(HEADING_RE);
    if (m) {
      if (current) entries.push(current);
      current = { title: m[1].trim(), body: "" };
      continue;
    }
    if (current) {
      current.body += (current.body ? "\n" : "") + line;
    }
  }
  if (current) entries.push(current);
  return entries;
}

export function DecisionsView() {
  const [raw, setRaw] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const refresh = useCallback(() => {
    setLoading(true);
    invoke<string>("read_architecture_file", { name: "decisions.md" })
      .then((c) => {
        setRaw(c);
        setError(null);
      })
      .catch((e) => {
        setRaw("");
        setError(String(e));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const entries = useMemo(() => parseDecisions(raw), [raw]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) =>
        e.title.toLowerCase().includes(q) ||
        e.body.toLowerCase().includes(q),
    );
  }, [entries, query]);

  return (
    <div className="flex-1 overflow-auto">
      <header
        className="px-[var(--pad-6)] py-[var(--pad-5)] flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div>
          <h1 className="font-display text-[20px] font-semibold tracking-tight">Решения</h1>
          <div className="text-[11.5px] mt-0.5" style={{ color: "var(--text-muted)" }}>
            architecture/decisions.md · {entries.length} записей
          </div>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск…"
            className="px-3 py-1.5 text-[12px] rounded-md"
            style={{
              background: "var(--bg-sidebar)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
              width: 200,
            }}
          />
          <button onClick={refresh} className="btn btn-outline text-[11.5px]" title="Обновить">
            ↻
          </button>
        </div>
      </header>

      {error && <ErrorBox message={error} />}

      <div className="px-[var(--pad-6)] py-[var(--pad-5)] space-y-[var(--pad-4)]">
        {loading ? (
          <div className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
            Загрузка…
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
            {query ? "Ничего не нашлось по запросу." : "В decisions.md пока нет записей."}
          </div>
        ) : (
          filtered.map((e, i) => <DecisionCard key={`${i}-${e.title}`} entry={e} />)
        )}
      </div>
    </div>
  );
}

function DecisionCard({ entry }: { entry: DecisionEntry }) {
  return (
    <article
      className="rounded-lg p-[var(--pad-4)]"
      style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
    >
      <h2 className="font-display text-[13.5px] font-semibold tracking-tight mb-2">
        {entry.title}
      </h2>
      <pre
        className="text-[12.5px] font-mono whitespace-pre-wrap leading-relaxed"
        style={{ color: "var(--text-secondary)" }}
      >
        {entry.body.trim()}
      </pre>
    </article>
  );
}
