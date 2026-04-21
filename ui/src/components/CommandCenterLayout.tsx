import React from "react";
import { Icon } from "./icons";
import { SubagentsView } from "../views/SubagentsView";
import { SettingsView, type UISettings } from "../views/SettingsView";
import { MessengerSettingsView } from "../views/MessengerSettingsView";

export type NavView = "subagents" | "messengers" | "settings";

export interface CommandCenterState {
  view: NavView;
  uiSettings: UISettings;
}

export const INITIAL_CMD_STATE: CommandCenterState = {
  view: "subagents",
  uiSettings: {
    theme: "dark",
    font: "inter",
    density: "normal",
    accent: "default",
    backdrop: "none",
  },
};

export const NAV_ITEMS: Array<{
  key: NavView;
  label: string;
  Icon: (p: { size?: number }) => React.ReactElement;
}> = [
  { key: "subagents",  label: "Субагенты",  Icon: Icon.Users },
  { key: "messengers", label: "Каналы",     Icon: Icon.Chat },
  { key: "settings",   label: "Настройки",  Icon: Icon.Cog },
];

interface CommandCenterLayoutProps {
  state: CommandCenterState;
  setState: (patch: Partial<CommandCenterState>) => void;
}

export function CommandCenterLayout({ state, setState }: CommandCenterLayoutProps) {
  const { view, uiSettings } = state;

  function setUISettings(patch: Partial<UISettings>) {
    setState({ uiSettings: { ...uiSettings, ...patch } });
  }

  return (
    <div className="h-full flex" style={{ background: "var(--bg-primary)" }}>
      {/* LEFT RAIL */}
      <aside
        className="shrink-0 flex flex-col"
        style={{
          width: 240,
          borderRight: "1px solid var(--border)",
          background: "var(--bg-sidebar)",
        }}
      >
        <div className="px-[var(--pad-4)] pt-[var(--pad-5)] pb-[var(--pad-4)] flex items-center gap-2.5">
          <div style={{ color: "var(--accent-primary)" }}>
            <Icon.Logo size={26} />
          </div>
          <div className="min-w-0">
            <div className="font-display font-semibold text-[15px] leading-tight tracking-tight">
              Groft
            </div>
            <div className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
              solo opus · v0.1.0
            </div>
          </div>
        </div>

        <nav className="px-[var(--pad-3)] space-y-0.5">
          {NAV_ITEMS.map((n) => {
            const active = view === n.key;
            return (
              <button
                key={n.key}
                onClick={() => setState({ view: n.key })}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] text-left transition-colors"
                style={{
                  background: active ? "var(--accent-light)" : "transparent",
                  color: active ? "var(--accent-hover)" : "var(--text-secondary)",
                  fontWeight: active ? 600 : 400,
                }}
              >
                <n.Icon size={14} /> {n.label}
              </button>
            );
          })}
        </nav>

        <div className="flex-1" />

        <div
          className="shrink-0 px-[var(--pad-4)] py-[var(--pad-3)] text-[11px] leading-relaxed"
          style={{ borderTop: "1px solid var(--border)", color: "var(--text-muted)" }}
        >
          Opus-сессия работает в Claude Code, субагенты запускаются через Task tool.
          Эта панель — только для настроек.
        </div>
      </aside>

      {/* MAIN */}
      <main className="flex-1 min-w-0 overflow-hidden flex flex-col">
        {view === "subagents" && <SubagentsView />}
        {view === "messengers" && <MessengerSettingsView />}
        {view === "settings" && (
          <SettingsView state={uiSettings} setState={setUISettings} />
        )}
      </main>
    </div>
  );
}
