import React, { useState, useEffect } from "react";
import type { AgentState } from "../store/agentStore";
import { Avatar, Sparkline, StatusLabel } from "./primitives";
import { Icon } from "./icons";
import { MODEL_OPTIONS } from "../data/models";

/* ---------- Internal sub-components for settings tab ---------- */

interface SelectProps {
  options: string[];
  value: string;
  onChange: (v: string) => void;
}
function Select({ options, value, onChange }: SelectProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-2 py-1 rounded-md text-[11.5px] font-mono focus:outline-none"
      style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
    >
      {options.map((o) => <option key={o}>{o}</option>)}
    </select>
  );
}

interface SliderProps {
  min: number;
  max: number;
  value: number;
  suffix?: string;
  onChange: (v: number) => void;
}
function Slider({ min, max, value, suffix, onChange }: SliderProps) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-28 accent-[var(--accent-primary)]"
      />
      <span className="font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>{value}{suffix}</span>
    </div>
  );
}

interface ToggleProps {
  checked: boolean;
  onChange: (v: boolean) => void;
}
function Toggle({ checked, onChange }: ToggleProps) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className="w-9 h-5 rounded-full transition-colors"
      style={{ background: checked ? "var(--accent-primary)" : "var(--border)" }}
      aria-checked={checked}
    >
      <span
        className="block w-3.5 h-3.5 rounded-full bg-white transition-transform mx-[3px]"
        style={{ transform: checked ? "translateX(16px)" : "translateX(0)" }}
      />
    </button>
  );
}

function TagInput({ tags }: { tags: string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((t) => (
        <span key={t} className="chip text-[10.5px]">{t}</span>
      ))}
    </div>
  );
}

/* ---------- MetricBox ---------- */
function MetricBox({ label, value, mono }: { label: string; value: string | number | undefined; mono?: boolean }) {
  return (
    <div className="card-flat p-3">
      <div className="text-[10px] uppercase tracking-[0.16em] font-semibold" style={{ color: "var(--text-muted)" }}>{label}</div>
      <div className={`text-[16px] mt-1 font-semibold${mono ? " font-mono" : ""}`}>{value ?? "—"}</div>
    </div>
  );
}

/* ---------- DrawerRow ---------- */
function DrawerRow({ label, hint, children, danger }: { label: string; hint?: string; children?: React.ReactNode; danger?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px] font-medium" style={{ color: danger ? "var(--status-stuck)" : "var(--text-primary)" }}>{label}</div>
        {hint && <div className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

/* ---------- AgentDrawer ---------- */
type DrawerTab = "state" | "settings" | "prompt" | "danger";
const TABS: Array<[DrawerTab, string]> = [
  ["state",    "Состояние"],
  ["settings", "Настройки"],
  ["prompt",   "System prompt"],
  ["danger",   "Опасно"],
];

interface AgentDrawerProps {
  agent: AgentState | null;
  onClose: () => void;
  onOpenTerminal: (name: string) => void;
}

export function AgentDrawer({ agent, onClose, onOpenTerminal }: AgentDrawerProps) {
  const [tab, setTab] = useState<DrawerTab>("state");
  const [mounted, setMounted] = useState(false);
  // settings state is driven by the currently open agent's props — reset on
  // each agent switch so Select/Toggle reflect the fresh agent, not whatever
  // the previous one last touched.
  const [modelChoice, setModelChoice] = useState<string>(agent?.model ?? "");
  const [maxTokens, setMaxTokens] = useState(120);
  const [temperature, setTemperature] = useState(30);
  const [stuckThreshold, setStuckThreshold] = useState(3);
  const [autoRestart, setAutoRestart] = useState(true);
  const [pauseOnDone, setPauseOnDone] = useState(false);

  // Vision "See pane" inline prompt state. Collapsed by default so the
  // button doesn't eat vertical space on every drawer open; expands on
  // click, reveals input + submit, then folds the answer underneath.
  const [visionOpen, setVisionOpen] = useState(false);
  const [visionQuestion, setVisionQuestion] = useState("");
  const [visionAnswer, setVisionAnswer] = useState<string | null>(null);
  const [visionError, setVisionError] = useState<string | null>(null);
  const [visionLoading, setVisionLoading] = useState(false);

  useEffect(() => {
    if (agent) {
      setMounted(false);
      const id = requestAnimationFrame(() => setMounted(true));
      return () => cancelAnimationFrame(id);
    }
  }, [agent?.name]);

  useEffect(() => {
    if (agent) {
      setModelChoice(agent.model);
      setMaxTokens(120);
      setTemperature(30);
      setStuckThreshold(3);
      setAutoRestart(true);
      setPauseOnDone(false);
      // Reset vision panel across agent switches — a question asked about
      // backend-dev's pane is meaningless once the drawer flips to frontend-dev.
      setVisionOpen(false);
      setVisionQuestion("");
      setVisionAnswer(null);
      setVisionError(null);
      setVisionLoading(false);
    }
  }, [agent?.name]);

  async function submitVision() {
    if (!agent) return;
    const q = visionQuestion.trim();
    if (!q) return;
    setVisionLoading(true);
    setVisionError(null);
    setVisionAnswer(null);
    try {
      const resp = await fetch("http://localhost:8766/vision/see-pane", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ agent: agent.name, question: q }),
      });
      const data = (await resp.json()) as { answer?: string; error?: string };
      if (!resp.ok) {
        setVisionError(data.error ?? `HTTP ${resp.status}`);
      } else if (typeof data.answer === "string") {
        setVisionAnswer(data.answer);
      } else {
        setVisionError("Empty response");
      }
    } catch (err) {
      setVisionError(err instanceof Error ? err.message : String(err));
    } finally {
      setVisionLoading(false);
    }
  }

  if (!agent) return null;

  const tokensK = (((agent.tokensIn ?? 0) + (agent.tokensOut ?? 0)) / 1000).toFixed(1) + "k";

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-[var(--pad-5)]" onClick={onClose}>
      <div className="absolute inset-0" style={{ background: "rgba(15, 22, 20, 0.45)" }} />
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative flex flex-col rounded-[var(--radius-lg)] overflow-hidden"
        style={{
          width: 560, maxWidth: "100%", maxHeight: "90vh",
          background: "var(--bg-card)", border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)",
          opacity: mounted ? 1 : 0,
          transform: mounted ? "translateY(0) scale(1)" : "translateY(8px) scale(0.98)",
          transition: "opacity 220ms ease-out, transform 280ms cubic-bezier(0.2, 0.9, 0.3, 1)",
        }}
      >
        {/* header */}
        <div className="shrink-0 p-[var(--pad-5)]" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="flex items-start gap-3">
            <Avatar name={agent.name} letter={agent.avatar} size={44} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="font-display font-semibold text-[18px] tracking-tight">{agent.name}</h2>
                <StatusLabel status={agent.status} />
              </div>
              <div className="text-[12px] mt-0.5" style={{ color: "var(--text-muted)" }}>{agent.role}</div>
              <div className="text-[11px] mt-1 font-mono" style={{ color: "var(--text-code)" }}>{agent.model}</div>
            </div>
            <button onClick={onClose} className="btn btn-ghost !p-1"><Icon.X size={14} /></button>
          </div>
          <div className="mt-[var(--pad-4)] flex gap-1 overflow-x-auto" style={{ scrollbarWidth: "thin" }}>
            {TABS.map(([k, l]) => (
              <button
                key={k}
                onClick={() => setTab(k)}
                className="shrink-0 px-3 py-1.5 rounded-md text-[12px] transition-colors whitespace-nowrap"
                style={{
                  background: tab === k ? "var(--accent-light)" : "transparent",
                  color: tab === k ? "var(--accent-hover)" : "var(--text-muted)",
                  fontWeight: tab === k ? 600 : 400,
                }}
              >
                {l}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-[var(--pad-5)]">
          {tab === "state" && (
            <div className="space-y-[var(--pad-4)]">
              <div>
                <div className="text-[10.5px] uppercase tracking-[0.16em] font-semibold mb-2" style={{ color: "var(--text-muted)" }}>Текущее действие</div>
                <div className="card-flat p-3 text-[13px]">{agent.currentAction}</div>
                <div className="text-[11px] font-mono mt-1.5" style={{ color: "var(--text-code)" }}>{agent.currentTask}</div>
              </div>
              <div className="grid grid-cols-2 gap-[var(--pad-3)]">
                <MetricBox label="Uptime" value={agent.uptime} />
                <MetricBox label="Cycles" value={agent.cycles} />
                <MetricBox label="Mode" value={agent.mode} mono />
                <MetricBox label="Tokens" value={tokensK} mono />
              </div>
              <div>
                <div className="text-[10.5px] uppercase tracking-[0.16em] font-semibold mb-2" style={{ color: "var(--text-muted)" }}>Активность (1ч)</div>
                <div className="card-flat p-3" style={{ color: "var(--accent-primary)" }}>
                  <Sparkline values={agent.spark ?? []} width={380} height={42} />
                </div>
              </div>
              <button onClick={() => onOpenTerminal(agent.name)} className="btn btn-primary w-full !justify-center">
                <Icon.Terminal size={13} /> Открыть терминал
              </button>

              {/*
                Vision "See pane" — cheap text-only Claude lookup over the
                agent's captured tmux pane. Collapsed by default to keep the
                drawer tidy; expands on click. Uses POST /vision/see-pane
                (see communication/server.py) which in turn wraps
                core.vision.ask_about_text. The answer is folded inline so
                the operator doesn't have to leave the drawer.
              */}
              <button
                onClick={() => setVisionOpen((v) => !v)}
                className="btn btn-outline w-full !justify-center"
              >
                See pane {visionOpen ? "▲" : "▼"}
              </button>
              {visionOpen && (
                <div
                  className="card-flat p-3 space-y-2"
                  style={{ border: "1px solid var(--border)" }}
                >
                  <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    Ask a question about this agent's pane
                  </div>
                  <textarea
                    rows={3}
                    value={visionQuestion}
                    onChange={(e) => setVisionQuestion(e.target.value)}
                    placeholder="e.g. What tool did this agent just call?"
                    className="w-full px-2 py-1.5 rounded-md text-[12px] font-mono focus:outline-none"
                    style={{
                      background: "var(--bg-secondary)",
                      border: "1px solid var(--border)",
                      color: "var(--text-primary)",
                      resize: "vertical",
                    }}
                  />
                  <div className="flex justify-end">
                    <button
                      onClick={submitVision}
                      disabled={visionLoading || !visionQuestion.trim()}
                      className="btn btn-primary text-[12px]"
                    >
                      {visionLoading ? "Asking..." : "Ask"}
                    </button>
                  </div>
                  {visionError && (
                    <div
                      className="text-[12px] font-mono p-2 rounded-md"
                      style={{
                        background: "var(--bg-secondary)",
                        color: "var(--status-stuck)",
                        border: "1px solid var(--status-stuck)",
                      }}
                    >
                      {visionError}
                    </div>
                  )}
                  {visionAnswer && (
                    <div
                      className="text-[12px] p-2 rounded-md whitespace-pre-wrap"
                      style={{
                        background: "var(--bg-secondary)",
                        color: "var(--text-primary)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      {visionAnswer}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {tab === "settings" && (
            <div className="space-y-[var(--pad-4)]">
              <DrawerRow label="Модель" hint="Можно переопределить дефолт">
                <Select options={[...MODEL_OPTIONS]} value={modelChoice} onChange={setModelChoice} />
              </DrawerRow>
              <DrawerRow label="Max tokens / cycle">
                <Slider min={10} max={200} value={maxTokens} suffix="k" onChange={setMaxTokens} />
              </DrawerRow>
              <DrawerRow label="Temperature">
                <Slider min={0} max={100} value={temperature} suffix="%" onChange={setTemperature} />
              </DrawerRow>
              <DrawerRow label="Tools" hint="Что разрешено агенту">
                <TagInput tags={["Read", "Write", "Edit", "Bash"]} />
              </DrawerRow>
              <DrawerRow label="Auto-restart при stuck">
                <Toggle checked={autoRestart} onChange={setAutoRestart} />
              </DrawerRow>
              <DrawerRow label="Stuck threshold">
                <Slider min={1} max={15} value={stuckThreshold} suffix="м" onChange={setStuckThreshold} />
              </DrawerRow>
              <DrawerRow label="Пауза при done">
                <Toggle checked={pauseOnDone} onChange={setPauseOnDone} />
              </DrawerRow>
            </div>
          )}

          {tab === "prompt" && (
            <div className="space-y-3">
              <div className="text-[11.5px]" style={{ color: "var(--text-muted)" }}>
                Сохраняется в{" "}
                <span className="font-mono" style={{ color: "var(--text-code)" }}>.claude/agents/{agent.name}.md</span>
              </div>
              <textarea
                rows={14}
                defaultValue={`# ${agent.name}\n\nТы ${agent.role}. Работаешь в команде под opus'ом.\n\n## Стиль\n- Сначала план, потом код\n- TDD где уместно\n- Пиши кратко в shared memory\n\n## Инструменты\nRead / Write / Edit / Bash\n\n## Контекст\n${agent.currentAction}`}
                className="w-full px-3 py-2 rounded-md text-[12px] font-mono focus:outline-none"
                style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-primary)", resize: "vertical" }}
              />
              <div className="flex justify-end gap-2">
                <button className="btn btn-outline text-[12px]">Сбросить</button>
                <button className="btn btn-primary text-[12px]">Сохранить</button>
              </div>
            </div>
          )}

          {tab === "danger" && (
            <div className="space-y-[var(--pad-4)]">
              <DrawerRow label="Очистить историю агента" danger>
                <button className="btn btn-outline text-[11.5px]" style={{ color: "var(--status-stuck)", borderColor: "var(--status-stuck)" }}>Очистить</button>
              </DrawerRow>
              <DrawerRow label="Hard kill" hint="SIGKILL процесса и чекпоинта" danger>
                <button className="btn btn-outline text-[11.5px]" style={{ color: "var(--status-stuck)", borderColor: "var(--status-stuck)" }}>
                  <Icon.X size={11} /> Kill
                </button>
              </DrawerRow>
              <DrawerRow label="Удалить агента" hint="Безвозвратно · файл и память" danger>
                <button className="btn btn-outline text-[11.5px]" style={{ color: "var(--status-stuck)", borderColor: "var(--status-stuck)" }}>
                  <Icon.Trash size={11} /> Удалить
                </button>
              </DrawerRow>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AgentDrawer;
