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
        const resp = await fetch(
          "http://localhost:8766/messenger/telegram/status",
        );
        if (!resp.ok) return;
        const body = (await resp.json()) as {
          status?: string;
          username?: string | null;
        };
        if (cancelled) return;
        const mapped = toChannelStatus(body.status ?? "");
        setStatus(mapped);
        if (typeof body.username === "string") setUsername(body.username);
        if (mapped === "connected" || mapped === "connecting") {
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
          const token = (config.token ?? "").trim();
          // Length sanity — empty/whitespace tokens never make the trip,
          // real format validation happens on the backend via getMe.
          if (token.length < 20 || /\s/.test(token)) {
            throw new Error("Invalid Telegram bot token format");
          }
          const resp = await fetch(
            "http://localhost:8766/messenger/telegram/configure",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ token }),
            },
          );
          let body: { ok?: boolean; username?: string | null; error?: string };
          try {
            body = await resp.json();
          } catch {
            throw new Error(`HTTP ${resp.status}`);
          }
          if (!resp.ok || !body.ok) {
            throw new Error(body.error || `HTTP ${resp.status}`);
          }
          setUsername(
            typeof body.username === "string" ? body.username : null,
          );
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

  // Poll /status every 2s until status flips to "connected" or "error",
  // or until the 2-minute ceiling. The user pastes the code in Telegram;
  // backend sets paired_user_id when the /pair ... message lands.
  const pair = useCallback(async (_code: string) => {
    setErrorMessage(null);
    const deadline = Date.now() + 120_000;
    while (Date.now() < deadline) {
      try {
        const resp = await fetch(
          "http://localhost:8766/messenger/telegram/status",
        );
        if (resp.ok) {
          const body = (await resp.json()) as {
            status?: string;
            username?: string | null;
          };
          const mapped = toChannelStatus(body.status ?? "");
          if (typeof body.username === "string") setUsername(body.username);
          if (mapped === "connected") {
            setStatus("connected");
            return;
          }
          if (mapped === "error") {
            setStatus("error");
            return;
          }
        }
      } catch (err) {
        log.info("telegram status poll failed", err);
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
    setStatus("error");
    setErrorMessage("Pairing timed out — user didn't pair within 2 minutes");
  }, []);

  const disconnect = useCallback(async () => {
    // TODO: backend has no disconnect endpoint yet — just clear local state
    // so the UI doesn't show a stale "connected" badge. Token/paired_user_id
    // stays on disk until the backend grows a DELETE/reset.
    setStatus("not-connected");
    setUsername(null);
    setErrorMessage(null);
    log.info("telegram disconnect: local-only, backend reset not implemented");
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
      const resp = await fetch(
        "http://localhost:8766/messenger/telegram/status",
      );
      if (!resp.ok) return "not-connected";
      const body = (await resp.json()) as {
        status?: string;
        username?: string | null;
      };
      const mapped = toChannelStatus(body.status ?? "");
      setStatus(mapped);
      if (typeof body.username === "string") setUsername(body.username);
      if (mapped === "connected" || mapped === "connecting") {
        setCurrent("telegram");
      }
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
