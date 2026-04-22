import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

interface Step {
  text: string;
  status: "done" | "active" | "pending";
}

interface ParsedPlan {
  goal: string | null;
  started: string | null;
  updated: string | null;
  steps: Step[];
}

const STEP_RE = /^\d+\.\s+\[(.)\]\s+(.*)$/;

function parsePlan(raw: string): ParsedPlan {
  const lines = raw.split(/\r?\n/);
  let goal: string | null = null;
  let started: string | null = null;
  let updated: string | null = null;
  const steps: Step[] = [];

  for (const line of lines) {
    const goalMatch = line.match(/^\*\*Goal:\*\*\s+(.*)$/);
    if (goalMatch) {
      goal = goalMatch[1].trim();
      continue;
    }
    const startedMatch = line.match(/^\*\*Started:\*\*\s+(.*)$/);
    if (startedMatch) {
      started = startedMatch[1].trim();
      continue;
    }
    const updatedMatch = line.match(/^Last updated:\s+(.*)$/);
    if (updatedMatch) {
      updated = updatedMatch[1].trim();
      continue;
    }
    const stepMatch = line.match(STEP_RE);
    if (stepMatch) {
      const mark = stepMatch[1];
      const text = stepMatch[2];
      const status: Step["status"] =
        mark === "x" ? "done" : mark === "~" ? "active" : "pending";
      steps.push({ text, status });
    }
  }
  return { goal, started, updated, steps };
}

function formatRelative(iso: string | null): string {
  if (!iso) return "";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const diffSec = Math.round((Date.now() - then) / 1000);
  if (diffSec < 60) return `${diffSec}s назад`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m назад`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h назад`;
  return `${Math.floor(diffSec / 86400)}d назад`;
}

export function HomeView() {
  const [plan, setPlan] = useState<ParsedPlan | null>(null);
  const [planRaw, setPlanRaw] = useState<string | null>(null);
  const [sessionLog, setSessionLog] = useState<string>("");
  const [auditLog, setAuditLog] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [p, s, a] = await Promise.all([
        invoke<string | null>("read_current_plan"),
        invoke<string>("read_memory_file", { name: "session-log.md" }).catch(() => ""),
        invoke<string>("read_audit_log_tail", { maxLines: 30 }),
      ]);
      setPlanRaw(p);
      setPlan(p ? parsePlan(p) : null);
      setSessionLog(s);
      setAuditLog(a);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const completed = plan?.steps.filter((s) => s.status === "done").length ?? 0;
  const total = plan?.steps.length ?? 0;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="flex-1 overflow-auto">
      <header
        className="px-[var(--pad-6)] py-[var(--pad-5)] flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div>
          <h1 className="font-display text-[20px] font-semibold tracking-tight">Главная</h1>
          <div className="text-[11.5px] mt-0.5" style={{ color: "var(--text-muted)" }}>
            Текущий план, session log, outbound audit — всё что видит конституция
          </div>
        </div>
        <button
          onClick={() => void refresh()}
          className="btn btn-outline text-[11.5px] gap-1.5"
          title="Обновить"
        >
          ↻ Обновить
        </button>
      </header>

      {error && (
        <div
          className="mx-[var(--pad-6)] mt-[var(--pad-4)] px-3 py-2 rounded-md text-[12px]"
          style={{
            background: "var(--status-stuck-bg, rgba(239, 68, 68, 0.1))",
            color: "var(--status-stuck)",
            border: "1px solid var(--status-stuck)",
          }}
        >
          {error}
        </div>
      )}

      <div className="px-[var(--pad-6)] py-[var(--pad-5)] space-y-[var(--pad-5)]">
        <PlanPanel plan={plan} planRaw={planRaw} pct={pct} completed={completed} total={total} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-[var(--pad-5)]">
          <SessionLogPanel log={sessionLog} />
          <AuditLogPanel log={auditLog} />
        </div>
      </div>
    </div>
  );
}

function PlanPanel({
  plan,
  planRaw,
  pct,
  completed,
  total,
}: {
  plan: ParsedPlan | null;
  planRaw: string | null;
  pct: number;
  completed: number;
  total: number;
}) {
  if (!planRaw) {
    return (
      <Section title="Текущий план" subtitle="memory/current-plan.md">
        <div className="text-[12.5px] py-4" style={{ color: "var(--text-muted)" }}>
          Нет активного плана. Opus вызовет <code>set_plan</code> перед многошаговой задачей.
        </div>
      </Section>
    );
  }

  return (
    <Section
      title="Текущий план"
      subtitle={`memory/current-plan.md · обновлён ${formatRelative(plan?.updated ?? null)}`}
      right={
        total > 0 && (
          <div className="flex items-center gap-2 text-[11.5px]" style={{ color: "var(--text-muted)" }}>
            <span>
              {completed} / {total}
            </span>
            <div
              className="w-24 h-1.5 rounded-full overflow-hidden"
              style={{ background: "var(--bg-sidebar)" }}
            >
              <div
                style={{
                  width: `${pct}%`,
                  height: "100%",
                  background: "var(--accent-primary)",
                  transition: "width 0.3s",
                }}
              />
            </div>
            <span>{pct}%</span>
          </div>
        )
      }
    >
      {plan?.goal && (
        <div className="text-[13px] font-medium mb-3" style={{ color: "var(--text-primary)" }}>
          {plan.goal}
        </div>
      )}
      <ol className="space-y-1.5">
        {plan?.steps.map((s, i) => (
          <li key={i} className="flex items-start gap-2 text-[12.5px]">
            <StepMarker status={s.status} />
            <span
              style={{
                color:
                  s.status === "active"
                    ? "var(--text-primary)"
                    : s.status === "done"
                      ? "var(--text-muted)"
                      : "var(--text-secondary)",
                fontWeight: s.status === "active" ? 600 : 400,
                textDecoration: s.status === "done" ? "line-through" : "none",
              }}
            >
              {s.text}
            </span>
          </li>
        ))}
      </ol>
    </Section>
  );
}

function StepMarker({ status }: { status: Step["status"] }) {
  if (status === "done") {
    return (
      <span style={{ color: "var(--status-success, #10b981)" }} className="mt-0.5">
        ✓
      </span>
    );
  }
  if (status === "active") {
    return (
      <span
        className="mt-[3px] shrink-0 w-2 h-2 rounded-full"
        style={{
          background: "var(--accent-primary)",
          animation: "pulse 2s infinite",
        }}
      />
    );
  }
  return (
    <span
      className="mt-[5px] shrink-0 w-1.5 h-1.5 rounded-full"
      style={{ background: "var(--text-muted)", opacity: 0.4 }}
    />
  );
}

function SessionLogPanel({ log }: { log: string }) {
  const tail = log.split(/\r?\n/).slice(-60).join("\n");
  return (
    <Section title="Session log" subtitle="memory/session-log.md · последние строки">
      {tail.trim() === "" ? (
        <div className="text-[12.5px] py-2" style={{ color: "var(--text-muted)" }}>
          Лог пуст.
        </div>
      ) : (
        <pre
          className="text-[11.5px] font-mono whitespace-pre-wrap overflow-auto max-h-[320px] p-2 rounded"
          style={{
            background: "var(--bg-sidebar)",
            color: "var(--text-secondary)",
            border: "1px solid var(--border)",
          }}
        >
          {tail}
        </pre>
      )}
    </Section>
  );
}

function AuditLogPanel({ log }: { log: string }) {
  const lines = log.split(/\r?\n/).filter((l) => l.trim().length > 0);
  return (
    <Section title="Outbound audit" subtitle=".claudeorch/audit.log · последние 30">
      {lines.length === 0 ? (
        <div className="text-[12.5px] py-2" style={{ color: "var(--text-muted)" }}>
          Outbound-команд пока не было.
        </div>
      ) : (
        <div
          className="text-[11px] font-mono overflow-auto max-h-[320px] rounded"
          style={{
            background: "var(--bg-sidebar)",
            border: "1px solid var(--border)",
          }}
        >
          <table className="w-full">
            <tbody>
              {lines.slice(-30).reverse().map((line, i) => (
                <AuditLine key={`${i}-${line.slice(0, 32)}`} line={line} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function AuditLine({ line }: { line: string }) {
  const parts = line.split("\t");
  if (parts.length < 4) {
    return (
      <tr>
        <td colSpan={3} className="px-2 py-1" style={{ color: "var(--text-muted)" }}>
          {line}
        </td>
      </tr>
    );
  }
  const [ts, category, status, ...cmdParts] = parts;
  const cmd = cmdParts.join("\t");
  const statusColor =
    status === "allow"
      ? "var(--text-muted)"
      : status === "deny"
        ? "var(--status-stuck, #ef4444)"
        : "var(--text-secondary)";
  return (
    <tr style={{ borderBottom: "1px solid var(--border)" }}>
      <td className="px-2 py-1 whitespace-nowrap" style={{ color: "var(--text-muted)", fontSize: "10px" }}>
        {ts.slice(11, 19)}
      </td>
      <td className="px-2 py-1 whitespace-nowrap" style={{ color: statusColor }}>
        {category}:{status}
      </td>
      <td className="px-2 py-1 truncate max-w-[320px]" title={cmd} style={{ color: "var(--text-secondary)" }}>
        {cmd}
      </td>
    </tr>
  );
}

function Section({
  title,
  subtitle,
  right,
  children,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      className="rounded-lg p-[var(--pad-4)]"
      style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
    >
      <header className="flex items-start justify-between mb-3">
        <div>
          <h2 className="font-display text-[14px] font-semibold tracking-tight">{title}</h2>
          {subtitle && (
            <div className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>
              {subtitle}
            </div>
          )}
        </div>
        {right}
      </header>
      {children}
    </section>
  );
}
