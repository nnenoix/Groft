import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export type CliDetectResult = {
  installed: boolean;
  path: string | null;
  version: string | null;
};

type StepId = "check-node" | "install-cli" | "verify-cli" | "trigger-oauth" | "run-doctor";

type StepStatus = "pending" | "running" | "waiting_user" | "done" | "failed";

type StepDef = {
  id: StepId;
  title: string;
  hint: string;
  // `waitingPattern` — if a line matches while running, flip to waiting_user.
  // Used for trigger-oauth (claude prints a URL and hangs on user OAuth).
  waitingPattern?: RegExp;
  // human-facing instructions shown as the banner when status=waiting_user.
  waitingBanner?: string;
};

const STEPS: StepDef[] = [
  {
    id: "check-node",
    title: "Node.js",
    hint: "node --version",
    waitingBanner:
      "Node.js не найден. Установи LTS с https://nodejs.org и нажми «Далее».",
  },
  {
    id: "install-cli",
    title: "Install claude",
    hint: "npm install -g @anthropic-ai/claude-code",
  },
  {
    id: "verify-cli",
    title: "Verify",
    hint: "claude --version",
  },
  {
    id: "trigger-oauth",
    title: "Sign in",
    hint: "claude (откроет браузер для OAuth)",
    waitingPattern: /https?:\/\/\S+/i,
    waitingBanner:
      "Завершите авторизацию в браузере. Когда claude скажет «Welcome» — нажми «Далее».",
  },
  {
    id: "run-doctor",
    title: "Health check",
    hint: "claude /doctor",
  },
];

type StreamFrame = { stream: "stdout" | "stderr"; line: string };
type StepDoneFrame = { step_id: string; ok: boolean; exit_code: number | null };

type Props = {
  detect: CliDetectResult;
  onRecheck: () => Promise<void> | void;
};

export function SetupView({ detect, onRecheck }: Props) {
  const [statuses, setStatuses] = useState<Record<StepId, StepStatus>>(() => ({
    "check-node": "pending",
    "install-cli": "pending",
    "verify-cli": "pending",
    "trigger-oauth": "pending",
    "run-doctor": "pending",
  }));
  // One rolling buffer of lines per step. Rendered in TerminalBlock when
  // that step is the active one.
  const [streams, setStreams] = useState<Record<StepId, string[]>>(() => ({
    "check-node": [],
    "install-cli": [],
    "verify-cli": [],
    "trigger-oauth": [],
    "run-doctor": [],
  }));
  const [activeIdx, setActiveIdx] = useState(0);
  const [rechecking, setRechecking] = useState(false);

  // Refs let the async event callbacks see the latest status without
  // re-subscribing on every state change — keeps the listeners stable.
  const statusesRef = useRef(statuses);
  useEffect(() => {
    statusesRef.current = statuses;
  }, [statuses]);

  const activeStep = STEPS[activeIdx] ?? null;

  const patchStatus = useCallback((id: StepId, s: StepStatus) => {
    setStatuses((prev) => (prev[id] === s ? prev : { ...prev, [id]: s }));
  }, []);

  const appendLine = useCallback((id: StepId, line: string) => {
    setStreams((prev) => {
      const next = prev[id].slice();
      // Cap at 500 lines per step so a runaway npm install doesn't OOM.
      if (next.length >= 500) next.splice(0, next.length - 500 + 1);
      next.push(line);
      return { ...prev, [id]: next };
    });
  }, []);

  const startStep = useCallback(
    async (id: StepId) => {
      patchStatus(id, "running");
      try {
        await invoke("run_setup_step", { stepId: id });
      } catch (err) {
        appendLine(id, `[spawn error] ${String(err)}`);
        patchStatus(id, "failed");
      }
    },
    [appendLine, patchStatus],
  );

  const cancelStep = useCallback(async (id: StepId) => {
    try {
      await invoke("cancel_setup_step", { stepId: id });
    } catch {
      // kill is best-effort; if it's already gone we're fine.
    }
  }, []);

  // Subscribe once to the five stream events + five done events. Filters run
  // against the current status via the ref, so we never re-subscribe.
  useEffect(() => {
    const unlisteners: UnlistenFn[] = [];
    let cancelled = false;

    async function subscribe() {
      for (const step of STEPS) {
        const streamEv = `setup-stream-${step.id}`;
        const doneEv = `setup-step-done-${step.id}`;
        const uStream = await listen<StreamFrame>(streamEv, (e) => {
          const payload = e.payload;
          appendLine(step.id, payload.line);
          if (
            step.waitingPattern &&
            step.waitingPattern.test(payload.line) &&
            statusesRef.current[step.id] === "running"
          ) {
            patchStatus(step.id, "waiting_user");
          }
        });
        const uDone = await listen<StepDoneFrame>(doneEv, (e) => {
          const { ok } = e.payload;
          // Cancelled steps get no done event, so any emit here wins over
          // a prior waiting_user flip.
          patchStatus(step.id, ok ? "done" : "failed");
          if (ok) {
            // Auto-advance to the next pending step when this one finishes.
            setActiveIdx((idx) => {
              const curIdx = STEPS.findIndex((s) => s.id === step.id);
              if (idx === curIdx && curIdx < STEPS.length - 1) {
                const next = STEPS[curIdx + 1];
                void startStep(next.id);
                return curIdx + 1;
              }
              return idx;
            });
          }
        });
        if (cancelled) {
          uStream();
          uDone();
        } else {
          unlisteners.push(uStream, uDone);
        }
      }
    }

    void subscribe();
    return () => {
      cancelled = true;
      for (const u of unlisteners) u();
    };
  }, [appendLine, patchStatus, startStep]);

  // Kick off the first step on mount.
  useEffect(() => {
    if (statuses["check-node"] === "pending") {
      void startStep("check-node");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleNext() {
    if (!activeStep) return;
    const cur = statuses[activeStep.id];
    // waiting_user: the running process (if any) is blocking us. Kill it,
    // mark this step done (user confirmed they did the manual part), and
    // advance to the next step.
    if (cur === "waiting_user") {
      await cancelStep(activeStep.id);
      patchStatus(activeStep.id, "done");
      const nextIdx = activeIdx + 1;
      if (nextIdx < STEPS.length) {
        setActiveIdx(nextIdx);
        void startStep(STEPS[nextIdx].id);
      }
      return;
    }
    if (cur === "failed") {
      // Retry this step. Drop accumulated lines so the user sees a clean run.
      setStreams((prev) => ({ ...prev, [activeStep.id]: [] }));
      void startStep(activeStep.id);
      return;
    }
    if (cur === "done") {
      const nextIdx = activeIdx + 1;
      if (nextIdx < STEPS.length) {
        setActiveIdx(nextIdx);
        if (statuses[STEPS[nextIdx].id] === "pending") {
          void startStep(STEPS[nextIdx].id);
        }
      }
    }
  }

  async function handleFinish() {
    setRechecking(true);
    try {
      await onRecheck();
    } finally {
      setRechecking(false);
    }
  }

  const allDone = STEPS.every((s) => statuses[s.id] === "done");
  const activeStatus = activeStep ? statuses[activeStep.id] : "pending";

  const activeLines = activeStep ? streams[activeStep.id] : [];

  return (
    <div className="setup-view" style={styles.wrap}>
      <header style={styles.header}>
        <h1 style={styles.h1}>Groft — First-run setup</h1>
        <p style={styles.sub}>
          Устанавливаем <code>claude</code> CLI и связываем его с твоим
          Anthropic-аккаунтом. Прогресс слева, список шагов справа.
        </p>
        {detect.version && (
          <p style={styles.muted}>
            Found: <code>{detect.version}</code>
          </p>
        )}
      </header>

      <div style={styles.body}>
        <div style={styles.terminalWrap}>
          {activeStep && activeStatus === "waiting_user" && activeStep.waitingBanner && (
            <div style={styles.banner}>
              <b>Нужно вмешательство:</b> {activeStep.waitingBanner}
            </div>
          )}
          {activeStep && activeStatus === "failed" && (
            <div style={{ ...styles.banner, borderColor: "var(--status-stuck)" }}>
              <b>Шаг упал.</b> Нажми «Далее» чтобы перезапустить.
            </div>
          )}
          <div style={styles.terminalInner}>
            <TerminalPanel
              title={activeStep ? activeStep.id : "setup"}
              subtitle={activeStep?.title ?? ""}
              lines={activeLines}
              live={activeStatus === "running"}
            />
          </div>
          <div style={styles.actions}>
            <button
              type="button"
              className="btn btn-outline"
              onClick={handleNext}
              disabled={
                activeStatus === "running" ||
                activeStatus === "pending" ||
                (activeStatus === "done" && activeIdx === STEPS.length - 1)
              }
            >
              Далее
            </button>
            {allDone && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleFinish}
                disabled={rechecking}
              >
                {rechecking ? "Checking…" : "Готово — открыть Groft"}
              </button>
            )}
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleFinish}
              disabled={rechecking}
              title="Пропустить если claude уже работает"
            >
              {rechecking ? "Checking…" : "Recheck"}
            </button>
          </div>
        </div>

        <aside style={styles.sidebar}>
          <h2 style={styles.sidebarTitle}>Шаги</h2>
          <ol style={styles.stepList}>
            {STEPS.map((step, i) => {
              const status = statuses[step.id];
              const active = i === activeIdx;
              return (
                <li
                  key={step.id}
                  style={{
                    ...styles.stepItem,
                    background: active ? "var(--bg-secondary)" : "transparent",
                    cursor:
                      status === "pending" && i > activeIdx ? "not-allowed" : "pointer",
                  }}
                  onClick={() => {
                    if (status === "pending" && i > activeIdx) return;
                    setActiveIdx(i);
                  }}
                >
                  <span style={styles.stepIndex}>{i + 1}</span>
                  <span style={styles.stepBody}>
                    <span style={styles.stepTitle}>{step.title}</span>
                    <span style={styles.stepHint}>{step.hint}</span>
                  </span>
                  <span style={{ ...styles.stepStatus, ...statusStyle(status) }}>
                    {statusLabel(status)}
                  </span>
                </li>
              );
            })}
          </ol>
        </aside>
      </div>
    </div>
  );
}

interface TerminalPanelProps {
  title: string;
  subtitle: string;
  lines: string[];
  live: boolean;
}

function TerminalPanel({ title, subtitle, lines, live }: TerminalPanelProps) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [autoscroll, setAutoscroll] = useState(true);

  useEffect(() => {
    if (autoscroll && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [lines, autoscroll]);

  function onScroll() {
    const el = bodyRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 6;
    if (!atBottom && autoscroll) setAutoscroll(false);
    else if (atBottom && !autoscroll) setAutoscroll(true);
  }

  return (
    <div
      className="rounded-[var(--radius-lg)] overflow-hidden flex flex-col h-full min-h-0"
      style={{
        background: "var(--bg-terminal)",
        border: "1px solid var(--border)",
      }}
    >
      <div
        className="px-[var(--pad-4)] py-[var(--pad-2)] flex items-center gap-2 shrink-0"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}
      >
        <span
          className="font-mono text-[12px] font-semibold"
          style={{ color: "var(--text-primary)" }}
        >
          {title}
        </span>
        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          · {subtitle}
        </span>
        <div className="flex-1" />
        {live && (
          <span
            className="text-[10px] uppercase tracking-wider font-semibold"
            style={{ color: "var(--accent-primary)" }}
          >
            live
          </span>
        )}
      </div>
      <div
        ref={bodyRef}
        onScroll={onScroll}
        className="flex-1 min-h-0 overflow-y-auto px-[var(--pad-4)] py-[var(--pad-3)] font-mono text-[12px] leading-[1.55]"
        style={{ color: "var(--text-primary)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}
      >
        {lines.length === 0 ? (
          <div style={{ color: "var(--text-muted)" }}>—</div>
        ) : (
          lines.map((line, i) => <div key={i}>{line}</div>)
        )}
      </div>
    </div>
  );
}

function statusLabel(s: StepStatus): string {
  switch (s) {
    case "pending":
      return "pending";
    case "running":
      return "running";
    case "waiting_user":
      return "wait you";
    case "done":
      return "done";
    case "failed":
      return "failed";
  }
}

function statusStyle(s: StepStatus): React.CSSProperties {
  switch (s) {
    case "running":
      return { color: "var(--accent-primary)" };
    case "waiting_user":
      return { color: "var(--status-stuck, #d89614)" };
    case "done":
      return { color: "var(--status-active, #3d8f3d)" };
    case "failed":
      return { color: "var(--status-stuck, #c44)" };
    default:
      return { color: "var(--text-muted)" };
  }
}

// Inline styles instead of a new CSS file — the setup screen is one page and
// not worth adding Tailwind classes or a separate sheet for.
const styles: Record<string, React.CSSProperties> = {
  wrap: {
    minHeight: "100vh",
    background: "var(--bg-primary)",
    color: "var(--text-primary)",
    padding: "24px 32px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  header: { display: "flex", flexDirection: "column", gap: 4 },
  h1: { fontSize: 22, fontWeight: 600, margin: 0 },
  sub: { color: "var(--text-secondary)", margin: 0 },
  muted: { color: "var(--text-muted)", margin: 0, fontSize: 13 },
  body: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) 320px",
    gap: 16,
    flex: 1,
    minHeight: 0,
  },
  terminalWrap: { display: "flex", flexDirection: "column", gap: 10, minWidth: 0 },
  terminalInner: { flex: 1, minHeight: 0 },
  actions: { display: "flex", gap: 8 },
  banner: {
    padding: "10px 14px",
    border: "1px solid var(--accent-primary)",
    borderRadius: "var(--radius-md, 8px)",
    background: "var(--bg-secondary)",
    fontSize: 13,
  },
  sidebar: {
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-lg, 10px)",
    padding: 12,
    background: "var(--bg-secondary)",
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  sidebarTitle: {
    fontSize: 13,
    textTransform: "uppercase",
    letterSpacing: 0.6,
    color: "var(--text-muted)",
    margin: 0,
  },
  stepList: { listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 4 },
  stepItem: {
    display: "flex",
    gap: 10,
    alignItems: "center",
    padding: "8px 10px",
    borderRadius: 6,
  },
  stepIndex: {
    width: 22,
    height: 22,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "50%",
    fontSize: 11,
    color: "var(--text-muted)",
  },
  stepBody: { display: "flex", flexDirection: "column", flex: 1, minWidth: 0 },
  stepTitle: { fontSize: 13, fontWeight: 500 },
  stepHint: { fontSize: 11, color: "var(--text-muted)", fontFamily: "ui-monospace, monospace" },
  stepStatus: { fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 },
};
