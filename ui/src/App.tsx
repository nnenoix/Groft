import { useState, useEffect } from "react";
import {
  CommandCenterLayout,
  INITIAL_CMD_STATE,
  type CommandCenterState,
} from "./components/CommandCenterLayout";
import { CmdK } from "./components/CmdK";
import { loadUISettings, saveUISettings } from "./hooks/useUISettings";

function App() {
  const [state, setStateRaw] = useState<CommandCenterState>({
    ...INITIAL_CMD_STATE,
    view: "terminals",
    gridMode: 1,
    uiSettings: loadUISettings(),
  });
  const [cmdk, setCmdk] = useState(false);

  const setState = (patch: Partial<CommandCenterState>) =>
    setStateRaw((prev) => ({ ...prev, ...patch }));

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
