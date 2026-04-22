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
  const [addOpen, setAddOpen] = useState(false);

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
          <button onClick={() => setAddOpen(true)} className="btn btn-primary text-[11.5px]">
            + Новое
          </button>
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

      {addOpen && (
        <AddDecisionModal
          onClose={() => setAddOpen(false)}
          onSaved={() => {
            setAddOpen(false);
            refresh();
          }}
        />
      )}
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

function AddDecisionModal({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [category, setCategory] = useState("");
  const [chosen, setChosen] = useState("");
  const [why, setWhy] = useState("");
  const [alternatives, setAlternatives] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const disabled =
    busy || category.trim() === "" || chosen.trim() === "" || why.trim() === "";

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await invoke<void>("append_decision_entry", {
        category: category.trim(),
        chosen: chosen.trim(),
        why: why.trim(),
        alternatives: alternatives.trim() === "" ? null : alternatives.trim(),
      });
      onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0, 0, 0, 0.6)" }}
      onClick={onClose}
    >
      <div
        className="max-w-xl w-full mx-8 rounded-xl p-6"
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between mb-4">
          <h2 className="font-display text-[16px] font-semibold tracking-tight">
            Новое решение
          </h2>
          <button
            onClick={onClose}
            className="text-[14px]"
            style={{ color: "var(--text-muted)" }}
          >
            ✕
          </button>
        </header>

        <div className="space-y-3">
          <Field
            label="Категория"
            hint="одна-две слова: например, packaging / memory / ui"
            value={category}
            onChange={setCategory}
          />
          <Field
            label="Выбрано"
            hint="короткое название принятого варианта"
            value={chosen}
            onChange={setChosen}
          />
          <TextArea
            label="Почему"
            hint="основное обоснование — 1–3 предложения"
            value={why}
            onChange={setWhy}
            rows={3}
          />
          <TextArea
            label="Альтернативы (опционально)"
            hint="что рассматривали и почему отвергли"
            value={alternatives}
            onChange={setAlternatives}
            rows={2}
          />
        </div>

        {error && (
          <div className="mt-3">
            <ErrorBox message={error} inset={false} />
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button onClick={onClose} className="btn btn-outline text-[12px]">
            Отмена
          </button>
          <button
            onClick={save}
            disabled={disabled}
            className="btn btn-primary text-[12px]"
            style={{ opacity: disabled ? 0.5 : 1 }}
          >
            {busy ? "Сохраняю…" : "Добавить"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="block text-[11.5px] uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>
        {label}
      </label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 text-[13px] rounded-md"
        style={{
          background: "var(--bg-sidebar)",
          border: "1px solid var(--border)",
          color: "var(--text-primary)",
        }}
      />
      {hint && (
        <div className="text-[10.5px] mt-1" style={{ color: "var(--text-muted)" }}>
          {hint}
        </div>
      )}
    </div>
  );
}

function TextArea({
  label,
  hint,
  value,
  onChange,
  rows = 3,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <div>
      <label className="block text-[11.5px] uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>
        {label}
      </label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        className="w-full px-3 py-2 text-[13px] rounded-md resize-y"
        style={{
          background: "var(--bg-sidebar)",
          border: "1px solid var(--border)",
          color: "var(--text-primary)",
        }}
      />
      {hint && (
        <div className="text-[10.5px] mt-1" style={{ color: "var(--text-muted)" }}>
          {hint}
        </div>
      )}
    </div>
  );
}
