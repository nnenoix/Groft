import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { createLogger } from "../utils/logger";

const log = createLogger("useChannels");

export type Messenger = "telegram" | "discord" | "webhook";

export type ChannelStatus =
  | "not-connected"
  | "connecting"
  | "connected"
  | "error";

export interface UseChannelsResult {
  current: Messenger | null;
  status: ChannelStatus;
  errorMessage: string | null;
  username: string | null;
  connect: (m: Messenger, config: Record<string, string>) => Promise<void>;
  pair: (code: string) => Promise<void>;
  disconnect: () => Promise<void>;
  testWebhook: (cfg: { url: string; secret: string }) => Promise<boolean>;
  configureTelegram: (token: string) => Promise<void>;
  pairTelegram: (code: string) => Promise<void>;
  getTelegramStatus: () => Promise<ChannelStatus>;
}

function toChannelStatus(raw: string): ChannelStatus {
  switch (raw) {
    case "connected":
    case "connecting":
    case "error":
    case "not-connected":
      return raw;
    default:
      return "not-connected";
  }
}

function errorToString(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  return String(e);
}

// Telegram bot token format is `<bot_id>:<base64url-ish secret>`; accept only
// that shape so a paste can't smuggle whitespace/quotes into run_tmux_command.
export const TELEGRAM_TOKEN_RE = /^[0-9]{5,15}:[A-Za-z0-9_-]{20,60}$/;
// Pairing codes are short alphanumerics issued by /telegram:access.
export const PAIR_CODE_RE = /^[A-Za-z0-9_-]{4,32}$/;
// Discord bot tokens are `<id>.<ts>.<hmac>` (dot-separated base64url).
export const DISCORD_TOKEN_RE = /^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}$/;

function useChannels(): UseChannelsResult {
  const [current, setCurrent] = useState<Messenger | null>(null);
  const [status, setStatus] = useState<ChannelStatus>("not-connected");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);

  // Track which messenger's status was last probed so disconnect knows the target.
  const currentRef = useRef<Messenger | null>(null);
  currentRef.current = current;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await invoke<string>("get_messenger_status", {
          messenger: "telegram",
        });
        if (cancelled) return;
        const mapped = toChannelStatus(raw);
        setStatus(mapped);
        if (mapped === "connected") {
          setCurrent("telegram");
        }
      } catch (err) {
        log.info("telegram status unavailable", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const connect = useCallback(
    async (m: Messenger, config: Record<string, string>) => {
      setStatus("connecting");
      setErrorMessage(null);
      setCurrent(m);
      try {
        await invoke<void>("save_messenger_config", {
          messenger: m,
          config: JSON.stringify(config),
        });
        if (m === "telegram") {
          const token = config.token ?? "";
          // allowlist — any other shape would flow straight into a tmux
          // send-keys command string below and let the user inject keystrokes.
          if (!TELEGRAM_TOKEN_RE.test(token)) {
            throw new Error("Invalid Telegram bot token format");
          }
          await invoke<string>("run_tmux_command", {
            command: `/telegram:configure ${token}`,
          });
          // Stay in "connecting" — the user still has to pair via code.
        } else if (m === "discord") {
          const token = config.token ?? "";
          if (!DISCORD_TOKEN_RE.test(token)) {
            throw new Error("Invalid Discord bot token format");
          }
          await invoke<string>("run_tmux_command", {
            command: `/discord:configure ${token}`,
          });
          setStatus("connected");
        } else {
          setStatus("connected");
        }
      } catch (e) {
        setStatus("error");
        setErrorMessage(errorToString(e));
      }
    },
    [],
  );

  const pair = useCallback(async (code: string) => {
    setErrorMessage(null);
    try {
      if (!PAIR_CODE_RE.test(code)) {
        throw new Error("Invalid pairing code format");
      }
      await invoke<string>("run_tmux_command", {
        command: `/telegram:access pair ${code}`,
      });
      setStatus("connected");
      // Real @handle would arrive via a future WS event; leave null for now
      // rather than show a misleading value.
      setUsername(null);
    } catch (e) {
      setStatus("error");
      setErrorMessage(errorToString(e));
    }
  }, []);

  const disconnect = useCallback(async () => {
    setStatus("not-connected");
    setUsername(null);
    setErrorMessage(null);
    try {
      await invoke<string>("run_tmux_command", {
        command: "/telegram:access policy disabled",
      });
    } catch (err) {
      log.exception(err, "tmux disconnect failed");
    }
  }, []);

  const testWebhook = useCallback(
    async (cfg: { url: string; secret: string }): Promise<boolean> => {
      setStatus("connecting");
      setErrorMessage(null);
      try {
        const resp = await fetch(cfg.url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Webhook-Secret": cfg.secret,
          },
          body: JSON.stringify({ type: "ping", source: "claudeorch" }),
        });
        const ok = resp.ok;
        setStatus(ok ? "connected" : "error");
        if (!ok) setErrorMessage(`HTTP ${resp.status}`);
        if (ok) setCurrent("webhook");
        return ok;
      } catch (e) {
        setStatus("error");
        setErrorMessage(errorToString(e));
        return false;
      }
    },
    [],
  );

  const configureTelegram = useCallback(
    (token: string) => connect("telegram", { token }),
    [connect],
  );

  const pairTelegram = useCallback((code: string) => pair(code), [pair]);

  const getTelegramStatus = useCallback(async (): Promise<ChannelStatus> => {
    try {
      const raw = await invoke<string>("get_messenger_status", {
        messenger: "telegram",
      });
      const mapped = toChannelStatus(raw);
      setStatus(mapped);
      if (mapped === "connected") setCurrent("telegram");
      return mapped;
    } catch (err) {
      log.info("telegram status unavailable", err);
      return "not-connected";
    }
  }, []);

  return {
    current,
    status,
    errorMessage,
    username,
    connect,
    pair,
    disconnect,
    testWebhook,
    configureTelegram,
    pairTelegram,
    getTelegramStatus,
  };
}

export default useChannels;
