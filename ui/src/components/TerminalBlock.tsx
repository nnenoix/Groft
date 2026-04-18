import React, { useEffect, useRef, useState } from "react";
import { Icon } from "./icons";
import { StatusDot, STATUS_COLOR } from "./primitives";
import type { AgentState } from "../store/agentStore";

interface TerminalBlockProps {
  agent: AgentState;
  lines: string[];
  live?: boolean;
  expandable?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
  heightClass?: string;
}

export function TerminalBlock({
  agent,
  lines,
  live = false,
  expandable = true,
  expanded,
  onToggle,
  heightClass = "h-48",
}: TerminalBlockProps) {
  const color = STATUS_COLOR[agent.status] ?? "var(--text-dim)";
  const bodyRef = useRef<HTMLDivElement>(null);
  const [autoscroll, setAutoscroll] = useState(true);

  useEffect(() => {
    if (autoscroll && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [lines, expanded, autoscroll]);

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
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* chrome */}
      <div
        className="px-[var(--pad-4)] py-[var(--pad-2)] flex items-center gap-2 shrink-0"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}
      >
        <StatusDot status={agent.status} pulse size={7} />
        <span className="font-mono text-[12px] font-semibold" style={{ color: "var(--text-primary)" }}>
          {agent.name}
        </span>
        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          · {agent.model}
        </span>
        <div className="flex-1" />
        {live && (
          <button
            onClick={(e) => { e.stopPropagation(); setAutoscroll((v) => !v); }}
            className="flex items-center gap-1 text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded transition-colors"
            style={{
              color: autoscroll ? color : "var(--text-muted)",
              background: autoscroll ? "transparent" : "var(--bg-card)",
              border: autoscroll ? "1px solid transparent" : "1px solid var(--border)",
            }}
            title={autoscroll ? "Автоскролл включён — клик чтобы запаузить" : "Автоскролл на паузе — клик чтобы возобновить"}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full${autoscroll ? " pulse-dot" : ""}`}
              style={{ background: autoscroll ? color : "var(--text-dim)", "--accent-glow": `${color}55` } as React.CSSProperties}
            />
            {autoscroll ? "live" : "paused"}
          </button>
        )}
        <button
          className="btn btn-ghost text-[11px] !px-1.5 !py-1"
          title="Скопировать вывод"
          onClick={(e) => e.stopPropagation()}
        >
          <Icon.Copy size={12} />
        </button>
        <button
          className="btn btn-ghost text-[11px] !px-1.5 !py-1"
          title="Очистить"
          onClick={(e) => e.stopPropagation()}
        >
          <Icon.Trash size={12} />
        </button>
        {expandable && (
          <button
            onClick={onToggle}
            className="btn btn-ghost text-[11px] !px-1.5 !py-1"
            aria-label={expanded ? "свернуть" : "раскрыть"}
          >
            {expanded ? <Icon.Minimize size={12} /> : <Icon.Maximize size={12} />}
          </button>
        )}
      </div>

      {/* body */}
      <div
        ref={bodyRef}
        onScroll={onScroll}
        className={`flex-1 min-h-0 overflow-y-auto px-[var(--pad-4)] py-[var(--pad-3)] font-mono text-[12px] leading-relaxed relative ${heightClass}`}
        style={{ color: "var(--text-terminal)" }}
      >
        {lines.map((line, i) => {
          const m = /^(\d{2}:\d{2})\s(.*)$/.exec(line);
          const ts = m ? m[1] : null;
          const body = m ? m[2] : line;
          const isCode = /^(npm |git |python |pytest|cd |VITE|======|\[|-m)/.test(body);
          const isErr = /error|stuck|fail|unexpectedly|401/i.test(body);
          return (
            <div key={i} className="flex gap-3 whitespace-pre-wrap">
              {ts && (
                <span style={{ color: "var(--text-muted)" }} className="shrink-0">
                  {ts}
                </span>
              )}
              <span
                style={{
                  color: isErr
                    ? "var(--status-stuck)"
                    : isCode
                    ? "var(--text-code)"
                    : "var(--text-terminal)",
                }}
              >
                {body}
              </span>
            </div>
          );
        })}
        {agent.status === "active" && (
          <div className="caret inline-block" style={{ color: "var(--accent-primary)" }} />
        )}

        {/* Jump to bottom when paused */}
        {live && !autoscroll && (
          <button
            onClick={() => setAutoscroll(true)}
            className="sticky bottom-2 ml-auto mr-0 float-right btn btn-outline !py-1 !px-2 text-[10.5px]"
            style={{ background: "var(--bg-card)" }}
          >
            <Icon.ArrowRight size={10} style={{ transform: "rotate(90deg)" }} /> к свежему
          </button>
        )}
      </div>
    </div>
  );
}
