import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  CommandCenterLayout,
  INITIAL_CMD_STATE,
  type CommandCenterState,
} from "./components/CommandCenterLayout";
import { CmdK } from "./components/CmdK";
import { loadUISettings, saveUISettings } from "./hooks/useUISettings";
import { SetupView, type CliDetectResult } from "./views/SetupView";

function App() {
  const [state, setStateRaw] = useState<CommandCenterState>({
    ...INITIAL_CMD_STATE,
    view: "terminals",
    gridMode: 1,
    uiSettings: loadUISettings(),
  });
  const [cmdk, setCmdk] = useState(false);
  // null = probe in flight. Undefined path is handled by the route below:
  // while probing we render a splash so the main UI doesn't flash before we
  // know whether setup is needed.
  const [cliDetect, setCliDetect] = useState<CliDetectResult | null>(null);

  const setState = (patch: Partial<CommandCenterState>) =>
    setStateRaw((prev) => ({ ...prev, ...patch }));

  const probeCli = useCallback(async () => {
    try {
      const r = await invoke<CliDetectResult>("detect_claude_cli");
      setCliDetect(r);
    } catch (err) {
      // tauri-api is available in packaged and dev modes alike, but a missing
      // backend command (e.g. very old bundle) shouldn't brick the UI —
      // fall through to "installed: true" so the main UI still renders.
      console.error("detect_claude_cli failed", err);
      setCliDetect({ installed: true, path: null, version: null });
    }
  }, []);

  useEffect(() => {
    void probeCli();
  }, [probeCli]);

  useEffect(() => {
    const h = document.documentElement;
    h.dataset.theme = state.uiSettings.theme;
    h.dataset.font = state.uiSettings.font;
    h.dataset.density = state.uiSettings.density;
    h.dataset.accent = state.uiSettings.accent;
    h.dataset.backdrop = state.uiSettings.backdrop;
  }, [state.uiSettings]);

  useEffect(() => {
    saveUISettings(state.uiSettings);
  }, [state.uiSettings]);

  useEffect(() => {
    let focusTimer: number | null = null;
    function onKey(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      const target = e.target as HTMLElement | null;
      const inField =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);

      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdk((v) => !v);
      } else if (e.key === "Escape") {
        setCmdk(false);
        setStateRaw((prev) => ({ ...prev, composerOpen: false }));
      } else if (
        mod &&
        !e.shiftKey &&
        !e.altKey &&
        ["1", "2", "3", "4", "5"].includes(e.key)
      ) {
        e.preventDefault();
        const map: Record<string, CommandCenterState["view"]> = {
          "1": "agents",
          "2": "tasks",
          "3": "terminals",
          "4": "messengers",
          "5": "settings",
        };
        setStateRaw((prev) => ({ ...prev, view: map[e.key] }));
        setCmdk(false);
      } else if (e.key === "/" && !inField && !mod) {
        e.preventDefault();
        setStateRaw((prev) => ({ ...prev, composerOpen: true }));
        if (focusTimer !== null) window.clearTimeout(focusTimer);
        focusTimer = window.setTimeout(() => {
          focusTimer = null;
          const composer = document.querySelector(
            "[data-composer-input]",
          ) as HTMLElement | null;
          if (composer) composer.focus();
        }, 80);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (focusTimer !== null) window.clearTimeout(focusTimer);
    };
  }, []);

  if (cliDetect === null) {
    return <div className="app-splash">Loading…</div>;
  }

  if (!cliDetect.installed) {
    return <SetupView detect={cliDetect} onRecheck={probeCli} />;
  }

  return (
    <>
      <CommandCenterLayout
        state={state}
        setState={setState}
        openCmdK={() => setCmdk(true)}
      />
      <CmdK
        open={cmdk}
        onClose={() => setCmdk(false)}
        setState={setState}
      />
    </>
  );
}

export default App;
