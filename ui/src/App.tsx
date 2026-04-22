import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  CommandCenterLayout,
  INITIAL_CMD_STATE,
  type CommandCenterState,
} from "./components/CommandCenterLayout";
import { loadUISettings, saveUISettings } from "./hooks/useUISettings";
import { SetupView, type CliDetectResult } from "./views/SetupView";
import { ProjectPickerView } from "./views/ProjectPickerView";

function App() {
  const [state, setStateRaw] = useState<CommandCenterState>({
    ...INITIAL_CMD_STATE,
    uiSettings: loadUISettings(),
  });
  const [cliDetect, setCliDetect] = useState<CliDetectResult | null>(null);
  const [projectRoot, setProjectRoot] = useState<string | null | undefined>(undefined);

  const setState = (patch: Partial<CommandCenterState>) =>
    setStateRaw((prev) => ({ ...prev, ...patch }));

  const probeCli = useCallback(async () => {
    try {
      const r = await invoke<CliDetectResult>("detect_claude_cli");
      setCliDetect(r);
    } catch (err) {
      console.error("detect_claude_cli failed", err);
      setCliDetect({ installed: true, path: null, version: null });
    }
  }, []);

  const probeRoot = useCallback(async () => {
    try {
      const r = await invoke<string | null>("get_project_root");
      setProjectRoot(r);
    } catch (err) {
      console.error("get_project_root failed", err);
      setProjectRoot(null);
    }
  }, []);

  useEffect(() => {
    void probeCli();
    void probeRoot();
  }, [probeCli, probeRoot]);

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
    function onKey(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (
        mod &&
        !e.shiftKey &&
        !e.altKey &&
        ["1", "2", "3", "4", "5", "6"].includes(e.key)
      ) {
        e.preventDefault();
        const map: Record<string, CommandCenterState["view"]> = {
          "1": "home",
          "2": "memory",
          "3": "decisions",
          "4": "subagents",
          "5": "messengers",
          "6": "settings",
        };
        setStateRaw((prev) => ({ ...prev, view: map[e.key] }));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (cliDetect === null || projectRoot === undefined) {
    return <div className="app-splash">Loading…</div>;
  }

  if (!cliDetect.installed) {
    return <SetupView detect={cliDetect} onRecheck={probeCli} />;
  }

  if (projectRoot === null) {
    return <ProjectPickerView onPicked={(p) => setProjectRoot(p)} />;
  }

  return <CommandCenterLayout state={state} setState={setState} />;
}

export default App;
