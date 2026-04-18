import React, { useState, useEffect, useRef } from "react";
import { Avatar } from "./Avatar";
import { Icon } from "../icons";
import { MODEL_OPTIONS, DEFAULT_MODEL } from "../../data/models";

const COMPOSER_SLASH = [
  { cmd: "/plan",   hint: "разбить на подзадачи без кода" },
  { cmd: "/ship",   hint: "команда делает + коммит" },
  { cmd: "/review", hint: "только ревью кода" },
  { cmd: "/test",   hint: "TDD цикл от тестов" },
  { cmd: "/fix",    hint: "починить stuck-агента" },
];

const COMPOSER_MODES = [
  { key: "solo",   label: "Solo",   hint: "opus работает один" },
  { key: "team",   label: "Team",   hint: "раздаёт команде" },
  { key: "review", label: "Review", hint: "ревью + комментарии" },
];

interface SlashItem { cmd: string; hint: string; }

interface ComposerPayload { text: string; mode: string; model: string; }

interface ComposerProps {
  placeholder?: string;
  compact?: boolean;
  onSubmit?: (payload: ComposerPayload) => void;
}

export function Composer({ placeholder = "Что поручить Opus?", compact = false, onSubmit }: ComposerProps) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState("team");
  const [model, setModel] = useState<string>(DEFAULT_MODEL);
  const [files, setFiles] = useState<string[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [slashOpen, setSlashOpen] = useState(false);
  const [thinking, setThinking] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const thinkingTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!settingsOpen && !slashOpen) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setSettingsOpen(false);
        setSlashOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [settingsOpen, slashOpen]);

  useEffect(() => {
    return () => {
      if (thinkingTimerRef.current !== null) {
        window.clearTimeout(thinkingTimerRef.current);
        thinkingTimerRef.current = null;
      }
    };
  }, []);

  function submit() {
    if (!text.trim()) return;
    setThinking(true);
    if (thinkingTimerRef.current !== null) {
      window.clearTimeout(thinkingTimerRef.current);
    }
    thinkingTimerRef.current = window.setTimeout(() => {
      thinkingTimerRef.current = null;
      setThinking(false);
    }, 1800);
    onSubmit?.({ text, mode, model });
    setText("");
  }

  function applySlash(c: SlashItem) {
    setText((t) => t.replace(/\/\w*$/, c.cmd) + " ");
    setSlashOpen(false);
    ref.current?.focus();
  }

  function onTextChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const v = e.target.value;
    setText(v);
    const tail = v.split(/\s/).pop();
    setSlashOpen(tail !== undefined && tail.startsWith("/") && tail.length <= 6);
  }

  const activeMode = COMPOSER_MODES.find((m) => m.key === mode) ?? COMPOSER_MODES[0];

  /* ---- COMPACT VARIANT ---- */
  if (compact) {
    return (
      <div ref={rootRef} className="relative card overflow-visible" style={{ boxShadow: "var(--shadow-md)" }}>
        {thinking && (
          <div className="absolute top-0 left-0 right-0 h-0.5 overflow-hidden">
            <div className="h-full w-1/3" style={{ background: "var(--accent-primary)", animation: "slide 1.2s ease-in-out infinite" }} />
          </div>
        )}

        {settingsOpen && (
          <div className="absolute left-2 right-2 bottom-[calc(100%+4px)] card fade-up z-20 p-2 space-y-2" style={{ boxShadow: "var(--shadow-lg)" }}>
            <div>
              <div className="text-[9.5px] uppercase tracking-[0.18em] font-semibold mb-1" style={{ color: "var(--text-dim)" }}>Модель</div>
              <div className="seg !p-0.5">
                {MODEL_OPTIONS.map((m) => (
                  <button key={m} aria-pressed={model === m} onClick={() => setModel(m)} className="!px-1.5 !text-[10px] font-mono">{m.replace(/^claude-/, "")}</button>
                ))}
              </div>
            </div>
            <div>
              <div className="text-[9.5px] uppercase tracking-[0.18em] font-semibold mb-1" style={{ color: "var(--text-dim)" }}>Режим</div>
              <div className="seg !p-0.5">
                {COMPOSER_MODES.map((m) => (
                  <button key={m.key} aria-pressed={mode === m.key} onClick={() => setMode(m.key)} className="!px-1.5 !text-[10px]">{m.label}</button>
                ))}
              </div>
            </div>
          </div>
        )}

        {slashOpen && (
          <div className="absolute left-2 right-2 bottom-[calc(100%+4px)] card fade-up z-20" style={{ boxShadow: "var(--shadow-lg)" }}>
            {COMPOSER_SLASH.map((c) => (
              <button key={c.cmd} onClick={() => applySlash(c)}
                className="w-full px-2.5 py-1.5 flex items-center gap-2 text-left hover:bg-[var(--bg-secondary)] transition-colors">
                <span className="font-mono text-[11px]" style={{ color: "var(--accent-primary)" }}>{c.cmd}</span>
                <span className="text-[10.5px] truncate" style={{ color: "var(--text-muted)" }}>{c.hint}</span>
              </button>
            ))}
          </div>
        )}

        <textarea
          ref={ref}
          data-composer-input
          rows={2}
          value={text}
          onChange={onTextChange}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
            if (e.key === "Escape") { setSlashOpen(false); setSettingsOpen(false); }
          }}
          placeholder={thinking ? "opus думает…" : placeholder}
          className="w-full px-[var(--pad-3)] pt-[var(--pad-3)] pb-1.5 text-[12.5px] resize-none focus:outline-none bg-transparent"
          style={{ color: "var(--text-primary)" }}
        />

        <div className="px-[var(--pad-2)] pb-[var(--pad-2)] flex items-center gap-0.5">
          <button
            onClick={() => { setSettingsOpen((v) => !v); setSlashOpen(false); }}
            className="flex items-center gap-1 px-1.5 py-1 rounded hover:bg-[var(--bg-secondary)] text-[10px] font-mono transition-colors"
            style={{ color: "var(--text-muted)", border: "1px solid var(--border)", background: settingsOpen ? "var(--bg-secondary)" : "transparent" }}
            title="Модель и режим · клик чтобы поменять"
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--accent-primary)" }} />
            {model.replace(/^claude-/, "")}
            <Icon.ChevronDown size={9} style={{ opacity: 0.6 }} />
          </button>
          <span className="text-[9.5px] font-mono ml-1" style={{ color: "var(--text-dim)" }}>· {activeMode.label}</span>
          <div className="flex-1" />
          <button className="btn btn-ghost !px-1.5 !py-1" title="Прикрепить"><Icon.Plus size={11} /></button>
          <button onClick={() => { setSlashOpen((v) => !v); setSettingsOpen(false); }} className="btn btn-ghost !px-1.5 !py-1" title="Команды">
            <span className="font-mono text-[10px]">/</span>
          </button>
          <button onClick={submit} disabled={!text.trim()}
            className="btn btn-primary !px-2 !py-1 !text-[10.5px] ml-0.5"
            style={{ opacity: text.trim() ? 1 : 0.45 }}>
            <Icon.ArrowRight size={11} />
          </button>
        </div>
      </div>
    );
  }

  /* ---- FULL VARIANT ---- */
  return (
    <div ref={rootRef} className="relative card overflow-hidden" style={{ boxShadow: "var(--shadow-md)" }}>
      <div className="px-[var(--pad-3)] pt-[var(--pad-3)] pb-[var(--pad-2)] flex items-center gap-2">
        <div className="relative">
          <Avatar name="opus" letter="O" size={24} />
          {thinking && (
            <span
              className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full pulse-dot"
              style={{ background: "var(--accent-primary)", "--accent-glow": "var(--accent-glow)" } as React.CSSProperties}
            />
          )}
        </div>
        <div className="text-[11.5px] min-w-0 flex-1">
          <span className="font-semibold" style={{ color: "var(--text-primary)" }}>opus</span>
          <span className="mx-1" style={{ color: "var(--text-dim)" }}>·</span>
          <span style={{ color: "var(--text-muted)" }}>
            {thinking ? "думает…" : activeMode.hint}
          </span>
        </div>
        <div className="seg !p-0.5" title="Модель для текущего сообщения">
          {MODEL_OPTIONS.map((m) => (
            <button key={m} aria-pressed={model === m} onClick={() => setModel(m)} className="!px-1.5 !py-0.5 !text-[10px] font-mono">
              {m.replace(/^claude-/, "")}
            </button>
          ))}
        </div>
      </div>

      <div className="px-[var(--pad-3)] pb-[var(--pad-2)] flex items-center gap-2">
        <div className="seg !p-0.5">
          {COMPOSER_MODES.map((m) => (
            <button key={m.key} aria-pressed={mode === m.key} onClick={() => setMode(m.key)} className="!text-[10.5px]">
              {m.label}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        {files.map((f, i) => (
          <span key={i} className="chip !py-0.5 !text-[10px]">
            <Icon.Code size={9} /> {f}
            <button onClick={() => setFiles(files.filter((_, j) => j !== i))} style={{ color: "var(--text-muted)" }}>
              <Icon.X size={9} />
            </button>
          </span>
        ))}
      </div>

      <textarea
        ref={ref}
        data-composer-input
        rows={3}
        value={text}
        onChange={onTextChange}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
          if (e.key === "Escape") setSlashOpen(false);
        }}
        placeholder={placeholder}
        className="w-full px-[var(--pad-3)] py-[var(--pad-2)] text-[13px] resize-none focus:outline-none bg-transparent"
        style={{ color: "var(--text-primary)" }}
      />

      {slashOpen && (
        <div className="absolute left-[var(--pad-3)] right-[var(--pad-3)] bottom-[58px] card fade-up z-10" style={{ boxShadow: "var(--shadow-lg)" }}>
          <div className="px-3 py-2 text-[10px] uppercase tracking-[0.2em] font-semibold" style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>Команды</div>
          {COMPOSER_SLASH.map((c) => (
            <button key={c.cmd} onClick={() => applySlash(c)}
              className="w-full px-3 py-2 flex items-center gap-3 text-left hover:bg-[var(--bg-secondary)] transition-colors">
              <span className="font-mono text-[12px]" style={{ color: "var(--accent-primary)" }}>{c.cmd}</span>
              <span className="text-[11.5px]" style={{ color: "var(--text-muted)" }}>{c.hint}</span>
            </button>
          ))}
        </div>
      )}

      <div className="px-[var(--pad-3)] pb-[var(--pad-3)] flex items-center gap-2">
        <button className="btn btn-ghost !px-2 !py-1 text-[11px]" title="Прикрепить файл"
          onClick={() => setFiles([...files, `file_${files.length + 1}.py`])}>
          <Icon.Plus size={12} />
        </button>
        <button className="btn btn-ghost !px-2 !py-1 text-[11px]" title="Голосом">
          <Icon.Waveform size={12} />
        </button>
        <button onClick={() => setSlashOpen(!slashOpen)} className="btn btn-ghost !px-2 !py-1 text-[11px]" title="Команды">
          <span className="font-mono">/</span>
        </button>
        <div className="flex-1 flex items-center gap-1.5 text-[10px]" style={{ color: "var(--text-dim)" }}>
          <kbd>⌘</kbd><kbd>↵</kbd><span>отправить</span>
        </div>
        <button onClick={submit} disabled={!text.trim()}
          className="btn btn-primary !px-3 !py-1.5 text-[12px]"
          style={{ opacity: text.trim() ? 1 : 0.5 }}>
          {thinking
            ? <><span className="w-2 h-2 rounded-full breathe" style={{ background: "var(--bg-card)" }} /> думает…</>
            : <>Отправить <Icon.ArrowRight size={12} /></>}
        </button>
      </div>

      {thinking && (
        <div className="absolute top-0 left-0 right-0 h-0.5 overflow-hidden">
          <div className="h-full w-1/3" style={{ background: "var(--accent-primary)", animation: "slide 1.2s ease-in-out infinite" }} />
        </div>
      )}
    </div>
  );
}
