import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { Icon } from "../components/icons";
import { ErrorBox } from "../components/ErrorBox";

interface ProjectPickerViewProps {
  onPicked: (path: string) => void;
}

function errorToString(e: unknown): string {
  if (typeof e === "string") return e;
  if (e instanceof Error) return e.message;
  return String(e);
}

export function ProjectPickerView({ onPicked }: ProjectPickerViewProps) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function pickFolder() {
    setError(null);
    try {
      const selected = await openDialog({
        directory: true,
        multiple: false,
        title: "Выберите корень Groft-репо",
      });
      if (selected === null) return; // user cancelled
      const path = Array.isArray(selected) ? selected[0] : selected;
      setBusy(true);
      await invoke<void>("set_project_root", { path });
      onPicked(path);
    } catch (e) {
      setError(errorToString(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="h-full flex items-center justify-center"
      style={{ background: "var(--bg-primary)" }}
    >
      <div
        className="max-w-lg w-full mx-8 rounded-xl p-8"
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center gap-3 mb-4">
          <div style={{ color: "var(--accent-primary)" }}>
            <Icon.Logo size={32} />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-semibold tracking-tight">
              Выбери Groft-репо
            </h1>
            <div className="text-[11.5px] mt-0.5" style={{ color: "var(--text-muted)" }}>
              папка с `.mcp.json` и `.claude/settings.json`
            </div>
          </div>
        </div>

        <p className="text-[13px] leading-relaxed mb-5" style={{ color: "var(--text-secondary)" }}>
          Groft читает план, память и конфигурацию хуков из корня репо.
          Мы запомним путь и будем использовать его при следующих запусках.
          Сменить можно в «Настройках».
        </p>

        <button
          onClick={pickFolder}
          disabled={busy}
          className="btn btn-primary w-full text-[13px] gap-2 py-2.5"
          style={{ opacity: busy ? 0.6 : 1 }}
        >
          <Icon.GitBranch size={14} />
          {busy ? "Сохраняю…" : "Выбрать папку"}
        </button>

        {error && (
          <div className="mt-4">
            <ErrorBox message={error} inset={false} />
          </div>
        )}

        <div
          className="mt-5 pt-4 text-[10.5px] font-mono leading-relaxed"
          style={{ borderTop: "1px solid var(--border)", color: "var(--text-muted)" }}
        >
          Dev override: установи переменную окружения{" "}
          <code>CLAUDEORCH_PROJECT_ROOT=/path/to/groft</code> и перезапусти приложение —
          выбор через диалог тогда не нужен.
        </div>
      </div>
    </div>
  );
}
