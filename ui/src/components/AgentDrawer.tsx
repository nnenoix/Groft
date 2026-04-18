import React, { useState, useEffect } from "react";
import type { AgentState } from "../store/agentStore";
import { Avatar, Sparkline, StatusLabel } from "./primitives";
import { Icon } from "./icons";
import { MODEL_OPTIONS } from "../data/models";

/* ---------- Internal sub-components for settings tab ---------- */

function Select({ options, value }: { options: string[]; value: string }) {
  return (
    <select
      defaultValue={value}
      className="px-2 py-1 rounded-md text-[11.5px] font-mono focus:outline-none"
      style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
    >
      {options.map((o) => <option key={o}>{o}</option>)}
    </select>
  );
}

function Slider({ min, max, value, suffix }: { min: number; max: number; value: number; suffix?: string }) {
  return (
    <div className="flex items-center gap-2">
      <input type="range" min={min} max={max} defaultValue={value} className="w-28 accent-[var(--accent-primary)]" />
      <span className="font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>{value}{suffix}</span>
    </div>
  );
}

function Toggle({ checked }: { checked?: boolean }) {
  const [on, setOn] = useState(!!checked);
  return (
    <button
      onClick={() => setOn((v) => !v)}
      className="w-9 h-5 rounded-full transition-colors"
      style={{ background: on ? "var(--accent-primary)" : "var(--border)" }}
      aria-checked={on}
    >
      <span
        className="block w-3.5 h-3.5 rounded-full bg-white transition-transform mx-[3px]"
        style={{ transform: on ? "translateX(16px)" : "translateX(0)" }}
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

  useEffect(() => {
    if (agent) {
      setMounted(false);
      const id = requestAnimationFrame(() => setMounted(true));
      return () => cancelAnimationFrame(id);
    }
  }, [agent?.name]);

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
            </div>
          )}

          {tab === "settings" && (
            <div className="space-y-[var(--pad-4)]">
              <DrawerRow label="Модель" hint="Можно переопределить дефолт">
                <Select options={[...MODEL_OPTIONS]} value={agent.model} />
              </DrawerRow>
              <DrawerRow label="Max tokens / cycle"><Slider min={10} max={200} value={120} suffix="k" /></DrawerRow>
              <DrawerRow label="Temperature"><Slider min={0} max={100} value={30} suffix="%" /></DrawerRow>
              <DrawerRow label="Tools" hint="Что разрешено агенту">
                <TagInput tags={["Read", "Write", "Edit", "Bash"]} />
              </DrawerRow>
              <DrawerRow label="Auto-restart при stuck"><Toggle checked /></DrawerRow>
              <DrawerRow label="Stuck threshold"><Slider min={1} max={15} value={3} suffix="м" /></DrawerRow>
              <DrawerRow label="Пауза при done"><Toggle /></DrawerRow>
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
