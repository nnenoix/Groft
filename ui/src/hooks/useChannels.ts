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
          await invoke<string>("run_tmux_command", {
            command: `/telegram:configure ${token}`,
          });
          // Stay in "connecting" — the user still has to pair via code.
        } else if (m === "discord") {
          const token = config.token ?? "";
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
      log.warn("tmux disconnect failed", err);
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

  return {
    current,
    status,
    errorMessage,
    username,
    connect,
    pair,
    disconnect,
    testWebhook,
  };
}

export default useChannels;
