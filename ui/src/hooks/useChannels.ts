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

export interface TelegramStatusSnapshot {
  status: ChannelStatus;
  username: string | null;
  pairedUserId: number | null;
}

export interface DiscordStatusSnapshot {
  status: ChannelStatus;
  botUser: string | null;
  pairedUserId: number | null;
}

export interface WebhookConfig {
  url: string;
  secret: string;
  template: string;
}

export interface WebhookStatusSnapshot {
  status: ChannelStatus;
  url: string | null;
}

export interface WebhookTestResult {
  ok: boolean;
  status: number | null;
  error: string | null;
}

export interface UseChannelsResult {
  current: Messenger | null;
  status: ChannelStatus;
  errorMessage: string | null;
  username: string | null;
  pairedUserId: number | null;
  pairingCode: string | null;
  connect: (m: Messenger, config: Record<string, string>) => Promise<void>;
  pair: (code: string) => Promise<void>;
  disconnect: () => Promise<void>;
  // testWebhook is kept for backwards compat with old callers — now routes
  // through the backend /messenger/webhook/test endpoint (which is the same
  // thing testWebhookLive does). Both take a config-shaped object for
  // compatibility; both ignore client-side templates and use the saved one.
  testWebhook: (cfg: { url: string; secret: string }) => Promise<boolean>;
  testWebhookLive: () => Promise<WebhookTestResult>;
  configureWebhook: (cfg: WebhookConfig) => Promise<void>;
  getWebhookStatus: () => Promise<WebhookStatusSnapshot>;
  configureTelegram: (token: string) => Promise<void>;
  pairTelegram: (code: string) => Promise<void>;
  getTelegramStatus: () => Promise<TelegramStatusSnapshot>;
  startTelegramPairing: () => Promise<string>;
  configureDiscord: (token: string) => Promise<void>;
  startDiscordPairing: () => Promise<string>;
  getDiscordStatus: () => Promise<DiscordStatusSnapshot>;
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

// Discord bot tokens are `<id>.<ts>.<hmac>` (dot-separated base64url).
export const DISCORD_TOKEN_RE = /^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}$/;

function useChannels(): UseChannelsResult {
  const [current, setCurrent] = useState<Messenger | null>(null);
  const [status, setStatus] = useState<ChannelStatus>("not-connected");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [pairedUserId, setPairedUserId] = useState<number | null>(null);
  const [pairingCode, setPairingCode] = useState<string | null>(null);

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
          paired_user_id?: number | null;
        };
        if (cancelled) return;
        const mapped = toChannelStatus(body.status ?? "");
        setStatus(mapped);
        if (typeof body.username === "string") setUsername(body.username);
        if (typeof body.paired_user_id === "number") {
          setPairedUserId(body.paired_user_id);
        }
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
          const token = (config.token ?? "").trim();
          if (!DISCORD_TOKEN_RE.test(token)) {
            throw new Error("Invalid Discord bot token format");
          }
          // POST to the real REST endpoint — same shape as Telegram's
          // configure. The backend only does a format check (discord.py
          // can't cheaply probe a token without a gateway connect), so
          // a 200 here just means "token shape is valid and persisted".
          const resp = await fetch(
            "http://localhost:8766/messenger/discord/configure",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ token }),
            },
          );
          let body: { ok?: boolean; error?: string };
          try {
            body = await resp.json();
          } catch {
            throw new Error(`HTTP ${resp.status}`);
          }
          if (!resp.ok || !body.ok) {
            throw new Error(body.error || `HTTP ${resp.status}`);
          }
          // Stay in "connecting" — pairing still has to happen via
          // /pair in the Discord server.
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
            paired_user_id?: number | null;
          };
          const mapped = toChannelStatus(body.status ?? "");
          if (typeof body.username === "string") setUsername(body.username);
          if (typeof body.paired_user_id === "number") {
            setPairedUserId(body.paired_user_id);
          }
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
    setPairedUserId(null);
    setPairingCode(null);
    setErrorMessage(null);
    log.info("telegram disconnect: local-only, backend reset not implemented");
  }, []);

  // Live wrapper around POST /messenger/webhook/test. Shape matches the
  // backend response ({ok,status,error}) so the UI can render a single
  // message with the HTTP code when successful. Separate from testWebhook
  // so callers that want the full result (status code + error) don't have
  // to piece it together from boolean + errorMessage state.
  const testWebhookLive = useCallback(async (): Promise<WebhookTestResult> => {
    setStatus("connecting");
    setErrorMessage(null);
    const empty: WebhookTestResult = {
      ok: false,
      status: null,
      error: "request failed",
    };
    try {
      const resp = await fetch("http://localhost:8766/messenger/webhook/test", {
        method: "POST",
      });
      let body: WebhookTestResult;
      try {
        body = (await resp.json()) as WebhookTestResult;
      } catch {
        setStatus("error");
        setErrorMessage(`HTTP ${resp.status}`);
        return { ok: false, status: resp.status, error: `HTTP ${resp.status}` };
      }
      setStatus(body.ok ? "connected" : "error");
      if (body.ok) setCurrent("webhook");
      if (!body.ok && body.error) setErrorMessage(body.error);
      return body;
    } catch (e) {
      setStatus("error");
      setErrorMessage(errorToString(e));
      return { ...empty, error: errorToString(e) };
    }
  }, []);

  // Back-compat shim. Old callers pass {url,secret} and want a boolean.
  // We route through the backend so the secret never hits the browser's
  // fetch-and-log trail, and we use whatever template is already saved.
  // If nothing is saved yet, the backend returns 400 and we surface false.
  const testWebhook = useCallback(
    async (_cfg: { url: string; secret: string }): Promise<boolean> => {
      const result = await testWebhookLive();
      return result.ok;
    },
    [testWebhookLive],
  );

  const configureWebhook = useCallback(
    async (cfg: WebhookConfig): Promise<void> => {
      setStatus("connecting");
      setErrorMessage(null);
      setCurrent("webhook");
      try {
        const resp = await fetch(
          "http://localhost:8766/messenger/webhook/configure",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              url: cfg.url,
              secret: cfg.secret,
              template: cfg.template,
            }),
          },
        );
        let body: { ok?: boolean; error?: string };
        try {
          body = await resp.json();
        } catch {
          throw new Error(`HTTP ${resp.status}`);
        }
        if (!resp.ok || !body.ok) {
          throw new Error(body.error || `HTTP ${resp.status}`);
        }
        // Configure alone doesn't prove delivery — status becomes "connected"
        // only once a /test succeeds. Leave it at "connecting" so the UI
        // nudges the user toward the Test button.
      } catch (e) {
        setStatus("error");
        setErrorMessage(errorToString(e));
        throw e;
      }
    },
    [],
  );

  const getWebhookStatus = useCallback(async (): Promise<WebhookStatusSnapshot> => {
    const empty: WebhookStatusSnapshot = { status: "not-connected", url: null };
    try {
      const resp = await fetch(
        "http://localhost:8766/messenger/webhook/status",
      );
      if (!resp.ok) return empty;
      const body = (await resp.json()) as {
        status?: string;
        url?: string | null;
      };
      const mapped = toChannelStatus(body.status ?? "");
      const url = typeof body.url === "string" ? body.url : null;
      return { status: mapped, url };
    } catch (err) {
      log.info("webhook status unavailable", err);
      return empty;
    }
  }, []);

  const configureTelegram = useCallback(
    (token: string) => connect("telegram", { token }),
    [connect],
  );

  const pairTelegram = useCallback((code: string) => pair(code), [pair]);

  const getTelegramStatus =
    useCallback(async (): Promise<TelegramStatusSnapshot> => {
      const empty: TelegramStatusSnapshot = {
        status: "not-connected",
        username: null,
        pairedUserId: null,
      };
      try {
        const resp = await fetch(
          "http://localhost:8766/messenger/telegram/status",
        );
        if (!resp.ok) return empty;
        const body = (await resp.json()) as {
          status?: string;
          username?: string | null;
          paired_user_id?: number | null;
        };
        const mapped = toChannelStatus(body.status ?? "");
        const nextUsername =
          typeof body.username === "string" ? body.username : null;
        const nextPaired =
          typeof body.paired_user_id === "number"
            ? body.paired_user_id
            : null;
        setStatus(mapped);
        setUsername(nextUsername);
        setPairedUserId(nextPaired);
        if (mapped === "connected" || mapped === "connecting") {
          setCurrent("telegram");
        }
        return {
          status: mapped,
          username: nextUsername,
          pairedUserId: nextPaired,
        };
      } catch (err) {
        log.info("telegram status unavailable", err);
        return empty;
      }
    }, []);

  // One-shot pairing-code issuer. Backend keeps the nonce in-process for
  // TELEGRAM_PAIR_TTL (5 min). UI surfaces the returned code so the user
  // can paste it into the Telegram chat with the bot.
  const startTelegramPairing = useCallback(async (): Promise<string> => {
    const resp = await fetch(
      "http://localhost:8766/messenger/telegram/start-pairing",
      { method: "POST" },
    );
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const body = (await resp.json()) as { code?: string };
    if (typeof body.code !== "string" || body.code.length === 0) {
      throw new Error("Invalid pairing response");
    }
    setPairingCode(body.code);
    return body.code;
  }, []);

  // Discord configure — token-only, no live probe on the backend side.
  // Mirrors configureTelegram's shape so panel code can treat the two
  // channels symmetrically.
  const configureDiscord = useCallback(
    (token: string) => connect("discord", { token }),
    [connect],
  );

  // One-shot Discord pairing-code issuer. Separate store from Telegram's
  // on both the client (this hook) and server (see _discord_pairs),
  // so codes never cross-leak.
  const startDiscordPairing = useCallback(async (): Promise<string> => {
    const resp = await fetch(
      "http://localhost:8766/messenger/discord/start-pairing",
      { method: "POST" },
    );
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const body = (await resp.json()) as { code?: string };
    if (typeof body.code !== "string" || body.code.length === 0) {
      throw new Error("Invalid pairing response");
    }
    setPairingCode(body.code);
    return body.code;
  }, []);

  const getDiscordStatus =
    useCallback(async (): Promise<DiscordStatusSnapshot> => {
      const empty: DiscordStatusSnapshot = {
        status: "not-connected",
        botUser: null,
        pairedUserId: null,
      };
      try {
        const resp = await fetch(
          "http://localhost:8766/messenger/discord/status",
        );
        if (!resp.ok) return empty;
        const body = (await resp.json()) as {
          status?: string;
          bot_user?: string | null;
          paired_user_id?: number | null;
        };
        const mapped = toChannelStatus(body.status ?? "");
        const nextBotUser =
          typeof body.bot_user === "string" ? body.bot_user : null;
        const nextPaired =
          typeof body.paired_user_id === "number"
            ? body.paired_user_id
            : null;
        // We don't overwrite the shared status/username state here — a
        // Discord panel can be mounted alongside Telegram, and clobbering
        // the top-level hook state would cause cross-tab flicker. Panels
        // that want to track Discord status locally should use the
        // returned snapshot directly.
        setPairedUserId(nextPaired);
        return {
          status: mapped,
          botUser: nextBotUser,
          pairedUserId: nextPaired,
        };
      } catch (err) {
        log.info("discord status unavailable", err);
        return empty;
      }
    }, []);

  return {
    current,
    status,
    errorMessage,
    username,
    pairedUserId,
    pairingCode,
    connect,
    pair,
    disconnect,
    testWebhook,
    testWebhookLive,
    configureWebhook,
    getWebhookStatus,
    configureTelegram,
    pairTelegram,
    getTelegramStatus,
    startTelegramPairing,
    configureDiscord,
    startDiscordPairing,
    getDiscordStatus,
  };
}

export default useChannels;
