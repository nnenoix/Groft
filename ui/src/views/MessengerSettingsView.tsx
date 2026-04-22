import { Icon } from "../components/icons";

// The old MessengerSettingsView (Telegram/Discord/iMessage/Webhook flows
// with live pairing) relied on the Python orchestrator's REST API on
// localhost:8766 — which was retired in PR #35 (Tauri-only MSI). Every
// useChannels fetch would hang until a ~75s TCP timeout, leaving the
// view stuck on "Проверяем статус…" indefinitely.
//
// Messenger configuration now lives in Claude Code skills (/telegram:configure,
// etc.). A future iteration can read .claudeorch/messenger-*.json directly
// via a Tauri FS command and render status inline — until then, this
// placeholder explains the state of the world without blocking the UI.

export function MessengerSettingsView() {
  return (
    <div className="h-full overflow-y-auto p-[var(--pad-6)]">
      <div className="max-w-[720px] mx-auto">
        <div className="mb-[var(--pad-5)]">
          <div
            className="text-[11px] uppercase tracking-[0.2em] font-semibold mb-1"
            style={{ color: "var(--text-muted)" }}
          >
            Channels
          </div>
          <h1 className="text-[28px] font-display font-semibold tracking-tight flex items-center gap-2">
            <Icon.Chat size={22} /> Мессенджеры
          </h1>
          <p
            className="text-[13px] mt-1"
            style={{ color: "var(--text-muted)" }}
          >
            Настройка каналов для удалённой связи с opus.
          </p>
        </div>

        <section
          className="rounded-[var(--radius-lg)] p-[var(--pad-5)] mb-[var(--pad-4)]"
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
          }}
        >
          <h3 className="text-[15px] font-display font-semibold tracking-tight mb-2">
            Настройка через Claude Code
          </h3>
          <p
            className="text-[13px] leading-relaxed mb-[var(--pad-3)]"
            style={{ color: "var(--text-secondary)" }}
          >
            В текущей архитектуре каналы настраиваются плагинами и skill'ами
            самого Claude Code, а не через UI Groft. Чтобы настроить Telegram,
            запусти в терминале:
          </p>
          <pre
            className="text-[12.5px] font-mono px-3 py-2 rounded-md mb-[var(--pad-3)]"
            style={{
              background: "var(--bg-sidebar)",
              color: "var(--accent-hover)",
              border: "1px solid var(--border)",
            }}
          >
            claude → /telegram:configure
          </pre>
          <p
            className="text-[12px]"
            style={{ color: "var(--text-muted)" }}
          >
            Skill проведёт через получение бот-токена у @BotFather, сохранение,
            и pairing. Результат лежит в <code>.claudeorch/messenger-telegram.json</code>.
          </p>
        </section>

        <section
          className="rounded-[var(--radius-lg)] p-[var(--pad-5)]"
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
          }}
        >
          <h3 className="text-[15px] font-display font-semibold tracking-tight mb-2">
            Почему не в UI
          </h3>
          <p
            className="text-[13px] leading-relaxed"
            style={{ color: "var(--text-secondary)" }}
          >
            Старый UI настройки мессенджеров зависел от REST-сервера на
            localhost:8766, который был частью Python-оркестратора (удалён
            в PR #35 вместе с tmux/WebSocket-инфраструктурой). Новая
            реализация — следующий шаг; в ней UI будет читать
            <code> .claudeorch/messenger-*.json </code> напрямую через
            Tauri FS и показывать статус inline.
          </p>
        </section>
      </div>
    </div>
  );
}

export default MessengerSettingsView;
