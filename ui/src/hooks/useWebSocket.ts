import { useEffect, useRef, useState, useCallback } from "react";
import { createLogger } from "../utils/logger";

const log = createLogger("useWebSocket");

export type WSStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting";

export interface UseWebSocketOptions {
  url: string;
  agentName: string;
  reconnectDelayMs?: number;
}

export interface UseWebSocketResult {
  status: WSStatus;
  connected: boolean;
  sendMessage: (obj: unknown) => boolean;
  lastMessage: Record<string, unknown> | null;
}

/**
 * Connects to the ClaudeOrch WebSocket server at `url`.
 *
 * Protocol notes (see communication/server.py):
 *  - First frame MUST be `{"type":"register","agent":<name>}` — server closes
 *    with code 1008 otherwise. No role/id fields are expected or used.
 *  - Reconnect logic: on any close/error we schedule a retry after
 *    `reconnectDelayMs` (default 3000ms). Status flips through the full
 *    `disconnected → connecting → connected → reconnecting → connecting …` loop.
 *  - Send buffer: messages sent while the socket is not OPEN are silently
 *    dropped (returns `false`). We keep state simple; the user retries via UI.
 */
function useWebSocket({
  url,
  agentName,
  reconnectDelayMs = 3000,
}: UseWebSocketOptions): UseWebSocketResult {
  const [status, setStatus] = useState<WSStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<Record<string, unknown> | null>(
    null,
  );

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldRunRef = useRef(true);
  const RECONNECT_MAX_MS = 30_000;
  // use a ref for the latest connect() to break the circular dep between
  // scheduleReconnect and connect without re-creating timers on every render
  const connectRef = useRef<() => void>(() => {});

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!shouldRunRef.current) return;
    if (reconnectTimerRef.current !== null) return;
    setStatus("reconnecting");
    // exponential backoff capped at RECONNECT_MAX_MS so a dead server
    // doesn't pin the event loop with a 3s retry loop.
    const attempt = reconnectAttemptsRef.current;
    const delay = Math.min(reconnectDelayMs * 2 ** attempt, RECONNECT_MAX_MS);
    reconnectAttemptsRef.current = attempt + 1;
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      connectRef.current();
    }, delay);
  }, [reconnectDelayMs]);

  const connect = useCallback(() => {
    if (!shouldRunRef.current) return;
    // close any stale socket before opening a new one
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (err) {
        log.debug("ws close before reopen", err);
      }
      wsRef.current = null;
    }
    setStatus("connecting");
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      log.warn("ws construct failed", err);
      scheduleReconnect();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      // register is mandatory first frame
      try {
        ws.send(JSON.stringify({ type: "register", agent: agentName }));
        setStatus("connected");
        // successful handshake — reset backoff so the next drop retries fast
        reconnectAttemptsRef.current = 0;
      } catch (err) {
        log.warn("ws register send failed", err);
        setStatus("reconnecting");
        scheduleReconnect();
      }
    };

    ws.onmessage = (event) => {
      const raw = event.data;
      if (typeof raw !== "string") return;
      try {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          setLastMessage(parsed as Record<string, unknown>);
        }
      } catch (err) {
        log.warn("ws frame parse failed", raw, err);
      }
    };

    ws.onerror = () => {
      // onerror is followed by onclose; we just mark reconnecting here so the
      // UI reflects the failure immediately.
      if (shouldRunRef.current) {
        setStatus("reconnecting");
      }
    };

    ws.onclose = () => {
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      if (shouldRunRef.current) {
        scheduleReconnect();
      } else {
        setStatus("disconnected");
      }
    };
  }, [url, agentName, scheduleReconnect]);

  // keep latest connect() in a ref so timers call the current closure
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    // depend only on the identity keys for the socket — `connect` is rebuilt
    // whenever reconnectDelayMs flips, and we don't want that tearing the
    // socket down mid-session. connectRef holds the latest closure.
    shouldRunRef.current = true;
    connectRef.current();
    return () => {
      shouldRunRef.current = false;
      clearReconnectTimer();
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch (err) {
          log.debug("ws teardown noop", err);
        }
        wsRef.current = null;
      }
      setStatus("disconnected");
    };
  }, [url, agentName, clearReconnectTimer]);

  const sendMessage = useCallback((obj: unknown): boolean => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // buffering would add complexity (order, size limit, flush races); we
      // instead surface `connected` so callers can gate UI actions.
      return false;
    }
    try {
      ws.send(JSON.stringify(obj));
      return true;
    } catch (err) {
      log.warn("ws send failed", err);
      return false;
    }
  }, []);

  return {
    status,
    connected: status === "connected",
    sendMessage,
    lastMessage,
  };
}

export default useWebSocket;
