import { useState } from "react";
import useChannels, { type ChannelStatus } from "../hooks/useChannels";

type TabKey = "telegram" | "discord" | "webhook";

interface StatusDotProps {
  status: ChannelStatus;
  username: string | null;
  errorMessage: string | null;
}

function StatusDot({ status, username, errorMessage }: StatusDotProps) {
  let dotClass = "bg-text-dim";
  let label = "Не подключён";
  if (status === "connecting") {
    dotClass = "bg-status-warning";
    label = "Подключение...";
  } else if (status === "connected") {
    dotClass = "bg-status-active";
    label = username ? `Подключён — ${username}` : "Подключён";
  } else if (status === "error") {
    dotClass = "bg-status-stuck";
    label = errorMessage ? `Ошибка — ${errorMessage}` : "Ошибка";
  }
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={`inline-block w-2.5 h-2.5 rounded-full ${dotClass}`} />
      <span className="text-text-secondary">{label}</span>
    </div>
  );
}

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  label: string;
}

function TabButton({ active, onClick, label }: TabButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "px-4 py-2 text-sm border-b-2 border-accent-primary text-text-primary"
          : "px-4 py-2 text-sm border-b-2 border-transparent text-text-muted hover:text-text-primary"
      }
    >
      {label}
    </button>
  );
}

interface FieldProps {
  label: string;
  children: React.ReactNode;
}

function Field({ label, children }: FieldProps) {
  return (
    <label className="block space-y-1">
      <span className="text-xs uppercase tracking-widest text-text-muted">
        {label}
      </span>
      {children}
    </label>
  );
}

const INPUT_CLASS =
  "w-full px-3 py-2 rounded bg-bg-secondary border border-border text-sm focus:outline-none focus:border-accent-primary disabled:opacity-60";

const PRIMARY_BTN =
  "px-4 py-2 rounded text-sm bg-accent-primary text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed";

const SECONDARY_BTN =
  "px-4 py-2 rounded text-sm border border-border text-text-secondary hover:bg-bg-secondary disabled:opacity-50 disabled:cursor-not-allowed";

interface TelegramTabProps {
  channels: ReturnType<typeof useChannels>;
}

function TelegramTab({ channels }: TelegramTabProps) {
  const [token, setToken] = useState("");
  const [code, setCode] = useState("");
  const isTelegram = channels.current === "telegram";
  const connecting = isTelegram && channels.status === "connecting";
  const paired = isTelegram && channels.status === "connected";
  const showPairing = isTelegram && channels.status === "connecting";

  async function handleConnect() {
    if (!token.trim()) return;
    await channels.connect("telegram", { token: token.trim() });
  }

  async function handlePair() {
    if (!code.trim()) return;
    await channels.pair(code.trim());
  }

  return (
    <div className="space-y-4">
      <Field label="Bot Token">
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          disabled={connecting || paired}
          placeholder="123456:ABC-DEF..."
          className={INPUT_CLASS}
        />
      </Field>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleConnect}
          disabled={connecting || paired || !token.trim()}
          className={PRIMARY_BTN}
        >
          {connecting ? "Подключение..." : "Подключить"}
        </button>
        {(paired || connecting) && (
          <button
            type="button"
            onClick={() => {
              void channels.disconnect();
              setToken("");
              setCode("");
            }}
            className={SECONDARY_BTN}
          >
            Отключить
          </button>
        )}
      </div>

      {showPairing && (
        <div className="rounded border border-border bg-bg-secondary p-3 space-y-3 text-sm">
          <div className="text-text-secondary leading-relaxed">
            Напиши любое сообщение боту в Telegram. В ответ получишь
            6-значный код сопряжения.
          </div>
          <Field label="Код сопряжения">
            <input
              type="text"
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
              className={INPUT_CLASS}
            />
          </Field>
          <button
            type="button"
            onClick={handlePair}
            disabled={!code.trim()}
            className={PRIMARY_BTN}
          >
            Подтвердить
          </button>
        </div>
      )}

      <StatusDot
        status={isTelegram ? channels.status : "not-connected"}
        username={channels.username}
        errorMessage={channels.errorMessage}
      />
    </div>
  );
}

interface DiscordTabProps {
  channels: ReturnType<typeof useChannels>;
}

function DiscordTab({ channels }: DiscordTabProps) {
  const [token, setToken] = useState("");
  const [serverId, setServerId] = useState("");
  const isDiscord = channels.current === "discord";
  const connecting = isDiscord && channels.status === "connecting";
  const connected = isDiscord && channels.status === "connected";

  async function handleConnect() {
    if (!token.trim() || !serverId.trim()) return;
    await channels.connect("discord", {
      token: token.trim(),
      serverId: serverId.trim(),
    });
  }

  return (
    <div className="space-y-4">
      <Field label="Bot Token">
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          disabled={connecting || connected}
          placeholder="Bot token"
          className={INPUT_CLASS}
        />
      </Field>
      <Field label="Server ID">
        <input
          type="text"
          value={serverId}
          onChange={(e) => setServerId(e.target.value)}
          disabled={connecting || connected}
          placeholder="123456789012345678"
          className={INPUT_CLASS}
        />
      </Field>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleConnect}
          disabled={
            connecting || connected || !token.trim() || !serverId.trim()
          }
          className={PRIMARY_BTN}
        >
          {connecting ? "Подключение..." : "Подключить"}
        </button>
        {connected && (
          <button
            type="button"
            onClick={() => {
              void channels.disconnect();
              setToken("");
              setServerId("");
            }}
            className={SECONDARY_BTN}
          >
            Отключить
          </button>
        )}
      </div>
      <StatusDot
        status={isDiscord ? channels.status : "not-connected"}
        username={channels.username}
        errorMessage={channels.errorMessage}
      />
    </div>
  );
}

interface WebhookTabProps {
  channels: ReturnType<typeof useChannels>;
}

function WebhookTab({ channels }: WebhookTabProps) {
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const isWebhook = channels.current === "webhook";
  const testing = isWebhook && channels.status === "connecting";

  async function handleTest() {
    if (!url.trim()) return;
    await channels.testWebhook({ url: url.trim(), secret: secret.trim() });
  }

  return (
    <div className="space-y-4">
      <Field label="URL">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/webhook"
          className={INPUT_CLASS}
        />
      </Field>
      <Field label="Secret token">
        <input
          type="password"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          placeholder="shared secret"
          className={INPUT_CLASS}
        />
      </Field>
      <div>
        <button
          type="button"
          onClick={handleTest}
          disabled={testing || !url.trim()}
          className={PRIMARY_BTN}
        >
          {testing ? "Проверка..." : "Проверить соединение"}
        </button>
      </div>
      <StatusDot
        status={isWebhook ? channels.status : "not-connected"}
        username={channels.username}
        errorMessage={channels.errorMessage}
      />
    </div>
  );
}

function MessengerSettings() {
  const [tab, setTab] = useState<TabKey>("telegram");
  const channels = useChannels();

  const tabs: Array<{ key: TabKey; label: string }> = [
    { key: "telegram", label: "Telegram" },
    { key: "discord", label: "Discord" },
    { key: "webhook", label: "Webhook" },
  ];

  return (
    <div className="w-full max-w-[640px] bg-bg-card border border-border rounded-md p-5 text-text-primary space-y-4">
      <h2 className="text-base font-semibold">Настройка мессенджера</h2>
      <div className="flex border-b border-border">
        {tabs.map((t) => (
          <TabButton
            key={t.key}
            active={tab === t.key}
            onClick={() => setTab(t.key)}
            label={t.label}
          />
        ))}
      </div>
      <div className="pt-2">
        {tab === "telegram" && <TelegramTab channels={channels} />}
        {tab === "discord" && <DiscordTab channels={channels} />}
        {tab === "webhook" && <WebhookTab channels={channels} />}
      </div>
    </div>
  );
}

export default MessengerSettings;
