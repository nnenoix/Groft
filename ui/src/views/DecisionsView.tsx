import { useEffect, useState } from "react";
import { Icon } from "../components/icons";
import { EyebrowLabel } from "../components/primitives";
import { EmptyState } from "../components/EmptyState";

export interface Decision {
  id: number;
  ts: string;
  agent: string;
  category: string;
  chosen: string;
  alternatives: string[] | null;
  reason: string;
  task_id: string | null;
}

const REST_URL =
  (import.meta.env.VITE_REST_URL as string | undefined) ??
  "http://localhost:8766";

function formatTs(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function AgentBadge({ agent }: { agent: string }) {
  return (
    <span
      className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono font-medium"
      style={{ background: "var(--accent-light)", color: "var(--accent-hover)" }}
    >
      {agent}
    </span>
  );
}

function CategoryBadge({ category }: { category: string }) {
  return (
    <span
      className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono"
      style={{ background: "var(--bg-secondary)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
    >
      {category}
    </span>
  );
}

function DecisionRow({ d }: { d: Decision }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="rounded-[var(--radius-md)] overflow-hidden"
      style={{ border: "1px solid var(--border)", background: "var(--bg-card)" }}
    >
      <button
        className="w-full flex items-center gap-2 px-[var(--pad-4)] py-[var(--pad-3)] text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="text-[11px] font-mono shrink-0" style={{ color: "var(--text-dim)" }}>
          {formatTs(d.ts)}
        </span>
        <AgentBadge agent={d.agent} />
        <CategoryBadge category={d.category} />
        <span className="flex-1 min-w-0 text-[13px] font-medium truncate" style={{ color: "var(--text-primary)" }}>
          {d.chosen}
        </span>
        <span style={{ color: "var(--text-dim)" }}>
          {expanded ? <Icon.ChevronDown size={13} /> : <Icon.ChevronRight size={13} />}
        </span>
      </button>

      {expanded && (
        <div
          className="px-[var(--pad-4)] pb-[var(--pad-4)] pt-0 space-y-[var(--pad-3)]"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <div>
            <div className="text-[10px] uppercase tracking-widest font-semibold mb-1" style={{ color: "var(--text-muted)" }}>
              Reason
            </div>
            <pre
              className="text-[12px] whitespace-pre-wrap font-sans leading-relaxed"
              style={{ color: "var(--text-secondary)" }}
            >
              {d.reason}
            </pre>
          </div>
          {d.alternatives && d.alternatives.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest font-semibold mb-1" style={{ color: "var(--text-muted)" }}>
                Alternatives considered
              </div>
              <ul className="space-y-0.5">
                {d.alternatives.map((alt, i) => (
                  <li key={i} className="text-[12px] flex items-start gap-1.5" style={{ color: "var(--text-secondary)" }}>
                    <span style={{ color: "var(--text-dim)" }}>·</span> {alt}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {d.task_id && (
            <div className="text-[11px] font-mono" style={{ color: "var(--text-dim)" }}>
              task: {d.task_id}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function DecisionsView() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState<string>("all");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`${REST_URL}/decisions?limit=200`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Decision[]>;
      })
      .then((data) => {
        if (!cancelled) {
          setDecisions(data);
          setLoading(false);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, []);

  const agents = ["all", ...Array.from(new Set(decisions.map((d) => d.agent))).sort()];

  const filtered = agentFilter === "all"
    ? decisions
    : decisions.filter((d) => d.agent === agentFilter);

  return (
    <div className="h-full overflow-hidden flex flex-col p-[var(--pad-6)]">
      <div className="mb-[var(--pad-5)] flex items-end justify-between shrink-0">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] font-semibold mb-1" style={{ color: "var(--text-muted)" }}>
            Architecture
          </div>
          <h1 className="text-[28px] font-display font-semibold tracking-tight">Decisions</h1>
        </div>
        <select
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="text-[12px] px-2 py-1.5 rounded-md"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            color: "var(--text-secondary)",
          }}
        >
          {agents.map((a) => (
            <option key={a} value={a}>{a === "all" ? "All agents" : a}</option>
          ))}
        </select>
      </div>

      {error && (
        <div
          className="mb-[var(--pad-4)] px-[var(--pad-4)] py-[var(--pad-3)] rounded-[var(--radius-md)] text-[13px] shrink-0"
          style={{ background: "var(--status-error-bg, #3b0000)", color: "var(--status-error, #f87171)", border: "1px solid var(--status-error, #f87171)" }}
        >
          Failed to load decisions: {error}
        </div>
      )}

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-[13px] animate-pulse" style={{ color: "var(--text-muted)" }}>Loading…</div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex-1">
          <EmptyState
            icon={Icon.Layers}
            title="No decisions logged yet"
            desc="Architecture decisions will appear here as the orchestrator makes them."
          />
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto space-y-[var(--pad-2)] pr-1">
          <div className="mb-[var(--pad-3)] shrink-0">
            <EyebrowLabel count={filtered.length}>Log</EyebrowLabel>
          </div>
          {filtered.map((d) => <DecisionRow key={d.id} d={d} />)}
        </div>
      )}
    </div>
  );
}

export default DecisionsView;
