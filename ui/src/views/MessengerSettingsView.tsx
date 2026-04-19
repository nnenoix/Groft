import { useEffect, useRef, useState } from "react";
import { Icon } from "../components/icons";
import useChannels, { type ChannelStatus } from "../hooks/useChannels";

type TabKey = "telegram" | "discord" | "imessage" | "webhook";

type TelegramStep = 1 | 2 | 3;

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "telegram", label: "Telegram" },
  { key: "discord", label: "Discord" },
  { key: "imessage", label: "iMessage" },
  { key: "webhook", label: "Webhook" },
];

function StatusDot({ status }: { status: ChannelStatus }) {
  const color =
    status === "connected"
      ? "var(--status-active)"
      : status === "error"
        ? "var(--status-stuck)"
        : status === "connecting"
          ? "var(--accent-primary)"
          : "var(--text-dim)";
  return (
    <span
      className="inline-block w-2 h-2 rounded-full mr-2 align-middle"
      style={{ background: color }}
    />
  );
}

function Crumbs({ step }: { step: TelegramStep }) {
  const items: Array<{ n: TelegramStep; label: string }> = [
    { n: 1, label: "Токен" },
    { n: 2, label: "Пара" },
    { n: 3, label: "Готово" },
  ];
  return (
    <div className="flex items-center gap-2 mb-[var(--pad-5)]">
      {items.map((it, i) => {
        const done = step > it.n;
        const active = step === it.n;
        return (
          <div key={it.n} className="flex items-center gap-2">
            <div
              className="flex items-center gap-1.5 px-2 py-1 rounded-md text-[11.5px]"
              style={{
                background: active
                  ? "var(--accent-light)"
                  : done
                    ? "var(--tint-success, var(--bg-secondary))"
                    : "var(--bg-secondary)",
                color: active
                  ? "var(--accent-hover)"
                  : done
                    ? "var(--status-active)"
                    : "var(--text-muted)",
                border: "1px solid var(--border)",
                fontWeight: active ? 600 : 400,
              }}
            >
              <span className="font-mono">{it.n}</span>
              <span>{it.label}</span>
            </div>
            {i < items.length - 1 && (
              <span style={{ color: "var(--text-dim)" }}>›</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function StepCard({
  title,
  desc,
  children,
}: {
  title: string;
  desc?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="rounded-[var(--radius-lg)] p-[var(--pad-5)] mb-[var(--pad-4)]"
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
      }}
    >
      <h3 className="text-[15px] font-display font-semibold tracking-tight mb-1">
        {title}
      </h3>
      {desc && (
        <p
          className="text-[12.5px] mb-[var(--pad-3)]"
          style={{ color: "var(--text-muted)" }}
        >
          {desc}
        </p>
      )}
      {children}
    </section>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      className="mt-[var(--pad-3)] px-3 py-2 rounded-md text-[12px]"
      style={{
        background: "var(--tint-danger, var(--bg-secondary))",
        border: "1px solid var(--status-stuck)",
        color: "var(--status-stuck)",
      }}
    >
      {message}
    </div>
  );
}

function TelegramFlow() {
  const {
    status,
    errorMessage,
    username,
    pairedUserId,
    pairingCode,
    disconnect,
    configureTelegram,
    pairTelegram,
    startTelegramPairing,
    getTelegramStatus,
  } = useChannels();

  const [step, setStep] = useState<TelegramStep>(1);
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState<"token" | null>(null);
  const [probed, setProbed] = useState(false);
  // localCode lets us render the code immediately from startTelegramPairing's
  // resolved value even before the hook's pairingCode state re-settles on
  // the next render.
  const [localCode, setLocalCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pairingError, setPairingError] = useState<string | null>(null);
  const pollingRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const s = await getTelegramStatus();
      if (cancelled) return;
      if (s.status === "connected") setStep(3);
      else if (s.status === "connecting") setStep(2);
      setProbed(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [getTelegramStatus]);

  // While waiting on pairing, launch a single status-polling loop. The hook
  // handles the 2s cadence + 2m deadline; guard with pollingRef so we never
  // stack multiple loops on re-render.
  useEffect(() => {
    if (step !== 2) return;
    if (pollingRef.current) return;
    pollingRef.current = true;
    (async () => {
      try {
        await pairTelegram("");
      } finally {
        pollingRef.current = false;
      }
    })();
  }, [step, pairTelegram]);

  // status==="connected" arrives either from mount probe or from the poll
  // started on step 2 — either way, surface the success card.
  useEffect(() => {
    if (status === "connected" && step !== 3) setStep(3);
  }, [status, step]);

  const tokenValid = token.trim().length >= 20 && !/\s/.test(token.trim());

  async function onSubmitToken() {
    if (!tokenValid || submitting) return;
    setSubmitting("token");
    setPairingError(null);
    try {
      await configureTelegram(token.trim());
      // configureTelegram sets status to "connecting" on success. If it
      // failed, status is "error" and errorMessage holds the reason.
      // Kick the pairing-code issue before switching to step 2 so the
      // user sees the code immediately.
      try {
        const issued = await startTelegramPairing();
        setLocalCode(issued);
        setStep(2);
      } catch (e) {
        setPairingError(
          e instanceof Error ? e.message : "Failed to issue pairing code",
        );
      }
    } finally {
      setSubmitting(null);
    }
  }

  async function onCopyCode() {
    const value = pairingCode ?? localCode;
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard unavailable — show no feedback rather than a scary error */
    }
  }

  async function onDisconnect() {
    if (!window.confirm("Отключить Telegram-канал?")) return;
    await disconnect();
    setToken("");
    setLocalCode(null);
    setStep(1);
  }

  const bannerError =
    pairingError ?? (status === "error" ? errorMessage : null);
  const visibleCode = pairingCode ?? localCode;

  if (!probed) {
    return (
      <div
        className="text-[12px] p-[var(--pad-4)]"
        style={{ color: "var(--text-muted)" }}
      >
        Проверяем статус…
      </div>
    );
  }

  return (
    <>
      <Crumbs step={step} />

      {step === 1 && (
        <StepCard
          title="Шаг 1 — Bot Token"
          desc="Получи токен у @BotFather, затем вставь его сюда."
        >
          <label className="block">
            <span
              className="text-[11px] uppercase tracking-[0.16em] font-semibold"
              style={{ color: "var(--text-muted)" }}
            >
              Bot Token
            </span>
            <input
              type="text"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="123456:ABCdef_ghiJKLmnopQRS-TUVwxyz012345"
              className="mt-1.5 w-full px-3 py-2 rounded-md text-[13px] font-mono focus:outline-none"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
            <span
              className="block mt-1.5 text-[11.5px]"
              style={{ color: "var(--text-muted)" }}
            >
              Минимум 20 символов, без пробелов. Формат проверит сам Telegram
              через <code>getMe</code>.
            </span>
          </label>
          <div className="mt-[var(--pad-4)] flex items-center gap-2">
            <button
              onClick={onSubmitToken}
              disabled={!tokenValid || submitting !== null}
              className="btn btn-primary text-[12.5px]"
              style={{
                opacity: !tokenValid || submitting !== null ? 0.5 : 1,
                cursor:
                  !tokenValid || submitting !== null
                    ? "not-allowed"
                    : "pointer",
              }}
            >
              {submitting === "token" ? "Подключаем…" : "Подключить"}
            </button>
            {!tokenValid && token.length > 0 && (
              <span
                className="text-[11.5px]"
                style={{ color: "var(--status-stuck)" }}
              >
                Слишком короткий токен
              </span>
            )}
          </div>
          {bannerError && <ErrorBanner message={bannerError} />}
        </StepCard>
      )}

      {step === 2 && (
        <StepCard
          title="Шаг 2 — Парный код"
          desc={
            username
              ? `Открой Telegram, найди бота @${username} и отправь ему /pair <код>.`
              : "Открой Telegram, найди своего бота и отправь ему /pair <код>."
          }
        >
          <div
            className="rounded-[var(--radius-md)] px-[var(--pad-4)] py-[var(--pad-5)] flex items-center justify-between gap-[var(--pad-4)]"
            style={{
              background: "var(--accent-light)",
              border: "1px solid var(--accent-primary)",
            }}
          >
            <div
              className="font-mono tracking-[0.28em] text-[26px] font-semibold select-all"
              style={{ color: "var(--accent-hover)" }}
            >
              {visibleCode ?? "—"}
            </div>
            <button
              onClick={onCopyCode}
              disabled={!visibleCode}
              className="btn btn-ghost text-[12.5px]"
              style={{
                opacity: visibleCode ? 1 : 0.5,
                cursor: visibleCode ? "pointer" : "not-allowed",
              }}
            >
              {copied ? "Скопировано" : "Скопировать"}
            </button>
          </div>
          <div
            className="mt-[var(--pad-4)] text-[12.5px]"
            style={{ color: "var(--text-muted)" }}
          >
            В Telegram отправь боту команду:{" "}
            <code>/pair {visibleCode ?? "<код>"}</code>.
          </div>
          <div className="mt-[var(--pad-4)] flex items-center gap-2">
            <div
              className="text-[12.5px] flex items-center gap-2"
              style={{ color: "var(--text-muted)" }}
            >
              <span
                className="inline-block w-3 h-3 rounded-full animate-pulse"
                style={{ background: "var(--accent-primary)" }}
              />
              Ждём подтверждения от Telegram…
            </div>
          </div>
          <div className="mt-[var(--pad-4)] flex items-center gap-2">
            <button
              onClick={() => setStep(1)}
              className="btn btn-ghost text-[12.5px]"
            >
              Назад
            </button>
          </div>
          {bannerError && <ErrorBanner message={bannerError} />}
        </StepCard>
      )}

      {step === 3 && (
        <StepCard title="Шаг 3 — Готово">
          {status === "error" ? (
            <div
              className="text-[13px]"
              style={{ color: "var(--status-stuck)" }}
            >
              <StatusDot status="error" />
              Ошибка — {errorMessage ?? "канал недоступен"}
            </div>
          ) : (
            <>
              <div className="text-[13px]">
                <StatusDot status="connected" />
                {username ? `Подключён как бот @${username}` : "Подключён"}
              </div>
              {pairedUserId !== null && (
                <div
                  className="text-[12.5px] mt-1"
                  style={{ color: "var(--text-muted)" }}
                >
                  Спарен с пользователем id {pairedUserId}
                </div>
              )}
            </>
          )}
          <div className="mt-[var(--pad-4)]">
            <button
              onClick={onDisconnect}
              className="btn btn-outline text-[12.5px]"
              style={{
                color: "var(--status-stuck)",
                borderColor: "var(--status-stuck)",
              }}
            >
              Отключить
            </button>
          </div>
        </StepCard>
      )}
    </>
  );
}

// Discord flow mirrors Telegram's — token → pairing code → poll status —
// with two deliberate differences:
//   1. The server-side `/configure` is format-only (discord.py cannot cheaply
//      probe a token without opening a gateway), so a 200 just means the
//      token shape is valid.
//   2. Discord requires the operator to invite the bot to a server before
//      slash commands are usable. We render the OAuth2 URL pattern and ask
//      the operator to paste their Application (client) ID — the full OAuth2
//      invite flow needs a client secret that Groft never sees.
function DiscordFlow() {
  const {
    configureDiscord,
    startDiscordPairing,
    getDiscordStatus,
    status: hookStatus,
    errorMessage,
  } = useChannels();

  const [step, setStep] = useState<TelegramStep>(1);
  const [token, setToken] = useState("");
  const [clientId, setClientId] = useState("");
  const [submitting, setSubmitting] = useState<"token" | null>(null);
  const [probed, setProbed] = useState(false);
  const [localCode, setLocalCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pairingError, setPairingError] = useState<string | null>(null);
  const [botUser, setBotUser] = useState<string | null>(null);
  const [pairedUserId, setPairedUserId] = useState<number | null>(null);
  const [discordStatus, setDiscordStatus] = useState<ChannelStatus>(
    "not-connected",
  );
  const pollRef = useRef(false);

  // Hydrate from backend on mount. We maintain local state rather than
  // leaning on useChannels' global status because a user may be configuring
  // multiple messengers simultaneously in separate tabs.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const s = await getDiscordStatus();
      if (cancelled) return;
      setDiscordStatus(s.status);
      setBotUser(s.botUser);
      setPairedUserId(s.pairedUserId);
      if (s.status === "connected") setStep(3);
      else if (s.status === "connecting") setStep(2);
      setProbed(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [getDiscordStatus]);

  // Poll /status while in step 2 (waiting for /pair from the bot channel).
  // Same 2s cadence + 2-minute deadline as Telegram's loop.
  useEffect(() => {
    if (step !== 2) return;
    if (pollRef.current) return;
    pollRef.current = true;
    let cancelled = false;
    (async () => {
      const deadline = Date.now() + 120_000;
      try {
        while (!cancelled && Date.now() < deadline) {
          try {
            const s = await getDiscordStatus();
            setDiscordStatus(s.status);
            setBotUser(s.botUser);
            setPairedUserId(s.pairedUserId);
            if (s.status === "connected") {
              setStep(3);
              return;
            }
          } catch {
            // transient; keep polling
          }
          await new Promise((r) => setTimeout(r, 2000));
        }
        if (!cancelled) {
          setPairingError(
            "Pairing timed out — operator didn't /pair within 2 minutes",
          );
        }
      } finally {
        pollRef.current = false;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [step, getDiscordStatus]);

  const tokenTrimmed = token.trim();
  // Discord bot tokens: <id>.<ts>.<hmac>. We accept length as a cheap
  // client-side sanity — the server does the authoritative regex match.
  const tokenValid = tokenTrimmed.length >= 20 && !/\s/.test(tokenTrimmed);

  async function onSubmitToken() {
    if (!tokenValid || submitting) return;
    setSubmitting("token");
    setPairingError(null);
    try {
      await configureDiscord(tokenTrimmed);
      try {
        const issued = await startDiscordPairing();
        setLocalCode(issued);
        setStep(2);
      } catch (e) {
        setPairingError(
          e instanceof Error ? e.message : "Failed to issue pairing code",
        );
      }
    } finally {
      setSubmitting(null);
    }
  }

  async function onCopyCode() {
    if (!localCode) return;
    try {
      await navigator.clipboard.writeText(localCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard unavailable — silent */
    }
  }

  const bannerError =
    pairingError ?? (hookStatus === "error" ? errorMessage : null);

  // OAuth2 invite URL template. scope=bot+applications.commands gives the
  // bot the slash-command surface and the ability to appear in channel
  // member lists. We can't run the full OAuth2 code-grant flow (requires
  // a client secret), so the operator handles the invite step manually.
  const inviteUrl = clientId.trim()
    ? `https://discord.com/api/oauth2/authorize?client_id=${encodeURIComponent(
        clientId.trim(),
      )}&scope=bot+applications.commands`
    : null;

  if (!probed) {
    return (
      <div
        className="text-[12px] p-[var(--pad-4)]"
        style={{ color: "var(--text-muted)" }}
      >
        Проверяем статус…
      </div>
    );
  }

  return (
    <>
      <Crumbs step={step} />

      {step === 1 && (
        <StepCard
          title="Шаг 1 — Bot Token + приглашение в сервер"
          desc="Создай приложение на Discord Developer Portal, получи bot token и пригласи бота в свой сервер. Client ID используется только для ссылки приглашения — Groft его не сохраняет."
        >
          <label className="block mb-[var(--pad-3)]">
            <span
              className="text-[11px] uppercase tracking-[0.16em] font-semibold"
              style={{ color: "var(--text-muted)" }}
            >
              Application (Client) ID
            </span>
            <input
              type="text"
              autoComplete="off"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              placeholder="123456789012345678"
              className="mt-1.5 w-full px-3 py-2 rounded-md text-[13px] font-mono focus:outline-none"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
            <span
              className="block mt-1.5 text-[11.5px]"
              style={{ color: "var(--text-muted)" }}
            >
              Только для генерации ссылки приглашения. Groft не требует и не хранит client secret.
            </span>
          </label>

          {inviteUrl && (
            <div
              className="mb-[var(--pad-3)] px-3 py-2 rounded-md text-[12px]"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
              }}
            >
              <div
                className="text-[11px] uppercase tracking-[0.16em] font-semibold mb-1"
                style={{ color: "var(--text-muted)" }}
              >
                Invite link
              </div>
              <a
                href={inviteUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-[12px] break-all"
                style={{ color: "var(--accent-hover)" }}
              >
                {inviteUrl}
              </a>
              <div
                className="mt-1 text-[11.5px]"
                style={{ color: "var(--text-muted)" }}
              >
                Открой ссылку, выбери сервер и подтверди. Бот появится в списке участников — только после этого пригодится слэш-команда /pair.
              </div>
            </div>
          )}

          <label className="block">
            <span
              className="text-[11px] uppercase tracking-[0.16em] font-semibold"
              style={{ color: "var(--text-muted)" }}
            >
              Bot Token
            </span>
            <input
              type="password"
              autoComplete="new-password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.GabcDE.abcdefghijkl..."
              className="mt-1.5 w-full px-3 py-2 rounded-md text-[13px] font-mono focus:outline-none"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
            <span
              className="block mt-1.5 text-[11.5px]"
              style={{ color: "var(--text-muted)" }}
            >
              Формат: три base64url-сегмента через точку. Проверка формата на бэке; live-probe возможен только после коннекта к gateway.
            </span>
          </label>

          <div className="mt-[var(--pad-4)] flex items-center gap-2">
            <button
              onClick={onSubmitToken}
              disabled={!tokenValid || submitting !== null}
              className="btn btn-primary text-[12.5px]"
              style={{
                opacity: !tokenValid || submitting !== null ? 0.5 : 1,
                cursor:
                  !tokenValid || submitting !== null
                    ? "not-allowed"
                    : "pointer",
              }}
            >
              {submitting === "token" ? "Подключаем…" : "Подключить"}
            </button>
            {!tokenValid && token.length > 0 && (
              <span
                className="text-[11.5px]"
                style={{ color: "var(--status-stuck)" }}
              >
                Слишком короткий токен
              </span>
            )}
          </div>
          {bannerError && <ErrorBanner message={bannerError} />}
        </StepCard>
      )}

      {step === 2 && (
        <StepCard
          title="Шаг 2 — Парный код"
          desc="В сервере, куда ты пригласил бота, отправь слэш-команду /pair <код>. Появится не сразу: глобальная sync до нескольких минут."
        >
          <div
            className="rounded-[var(--radius-md)] px-[var(--pad-4)] py-[var(--pad-5)] flex items-center justify-between gap-[var(--pad-4)]"
            style={{
              background: "var(--accent-light)",
              border: "1px solid var(--accent-primary)",
            }}
          >
            <div
              className="font-mono tracking-[0.28em] text-[26px] font-semibold select-all"
              style={{ color: "var(--accent-hover)" }}
            >
              {localCode ?? "—"}
            </div>
            <button
              onClick={onCopyCode}
              disabled={!localCode}
              className="btn btn-ghost text-[12.5px]"
              style={{
                opacity: localCode ? 1 : 0.5,
                cursor: localCode ? "pointer" : "not-allowed",
              }}
            >
              {copied ? "Скопировано" : "Скопировать"}
            </button>
          </div>
          <div
            className="mt-[var(--pad-4)] text-[12.5px]"
            style={{ color: "var(--text-muted)" }}
          >
            В Discord отправь:{" "}
            <code>/pair code:{localCode ?? "<код>"}</code>
          </div>
          <div className="mt-[var(--pad-4)] flex items-center gap-2">
            <div
              className="text-[12.5px] flex items-center gap-2"
              style={{ color: "var(--text-muted)" }}
            >
              <span
                className="inline-block w-3 h-3 rounded-full animate-pulse"
                style={{ background: "var(--accent-primary)" }}
              />
              Ждём подтверждения из Discord…
            </div>
          </div>
          <div className="mt-[var(--pad-4)] flex items-center gap-2">
            <button
              onClick={() => setStep(1)}
              className="btn btn-ghost text-[12.5px]"
            >
              Назад
            </button>
          </div>
          {bannerError && <ErrorBanner message={bannerError} />}
        </StepCard>
      )}

      {step === 3 && (
        <StepCard title="Шаг 3 — Готово">
          {discordStatus === "error" ? (
            <div
              className="text-[13px]"
              style={{ color: "var(--status-stuck)" }}
            >
              <StatusDot status="error" />
              Ошибка — {errorMessage ?? "канал недоступен"}
            </div>
          ) : (
            <>
              <div className="text-[13px]">
                <StatusDot status="connected" />
                {botUser ? `Подключён как бот ${botUser}` : "Подключён"}
              </div>
              {pairedUserId !== null && (
                <div
                  className="text-[12.5px] mt-1"
                  style={{ color: "var(--text-muted)" }}
                >
                  Спарен с Discord user id {pairedUserId}
                </div>
              )}
            </>
          )}
        </StepCard>
      )}
    </>
  );
}

function StubPanel({ title, note }: { title: string; note: string }) {
  return (
    <StepCard title={title} desc={note}>
      <p className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
        Раздел доступен в общих «Настройки → Мессенджеры» — эта вкладка
        зарезервирована под будущий мастер.
      </p>
    </StepCard>
  );
}

// Default template is the minimal JSON shape with all three tokens.
// Gives the operator a working example; they can trim/rearrange for
// their own endpoint before hitting Save.
const DEFAULT_WEBHOOK_TEMPLATE =
  '{"event":"{event}","from":"{agent}","content":"{text}"}';

function WebhookPanel() {
  const { configureWebhook, testWebhookLive, getWebhookStatus } = useChannels();

  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [template, setTemplate] = useState(DEFAULT_WEBHOOK_TEMPLATE);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  // Last result from /test — displayed as a banner until the next action.
  const [testResult, setTestResult] = useState<{
    kind: "success" | "error";
    message: string;
  } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [status, setStatus] = useState<"not-connected" | "connected">(
    "not-connected",
  );

  useEffect(() => {
    // Hydrate from saved config on mount so the user sees their existing
    // URL (secret intentionally NOT prefilled — we never round-trip it to
    // the frontend; operator retypes if they want to change it).
    let cancelled = false;
    (async () => {
      const s = await getWebhookStatus();
      if (cancelled) return;
      if (s.url) setUrl(s.url);
      setStatus(s.status === "connected" ? "connected" : "not-connected");
    })();
    return () => {
      cancelled = true;
    };
  }, [getWebhookStatus]);

  async function onSave() {
    if (saving) return;
    setSaving(true);
    setSaveError(null);
    setTestResult(null);
    try {
      await configureWebhook({ url: url.trim(), secret, template });
      setStatus("connected");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    if (testing) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testWebhookLive();
      if (result.ok) {
        setTestResult({
          kind: "success",
          message: `Delivered (HTTP ${result.status ?? "2xx"})`,
        });
      } else {
        setTestResult({
          kind: "error",
          message:
            result.error ??
            (result.status ? `HTTP ${result.status}` : "Test failed"),
        });
      }
    } finally {
      setTesting(false);
    }
  }

  const canSave =
    url.trim().length > 0 && template.trim().length > 0 && !saving;

  return (
    <StepCard
      title="Webhook"
      desc="Groft будет отправлять POST на указанный URL. Шаблон подставляет {event}, {agent}, {text}."
    >
      <label className="block mb-[var(--pad-3)]">
        <span
          className="text-[11px] uppercase tracking-[0.16em] font-semibold"
          style={{ color: "var(--text-muted)" }}
        >
          URL
        </span>
        <input
          type="text"
          autoComplete="off"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://hooks.example.com/abc123"
          className="mt-1.5 w-full px-3 py-2 rounded-md text-[13px] font-mono focus:outline-none"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            color: "var(--text-primary)",
          }}
        />
      </label>

      <label className="block mb-[var(--pad-3)]">
        <span
          className="text-[11px] uppercase tracking-[0.16em] font-semibold"
          style={{ color: "var(--text-muted)" }}
        >
          Shared secret
        </span>
        <input
          type="password"
          autoComplete="new-password"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          placeholder="•••"
          className="mt-1.5 w-full px-3 py-2 rounded-md text-[13px] font-mono focus:outline-none"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            color: "var(--text-primary)",
          }}
        />
        <span
          className="block mt-1.5 text-[11.5px]"
          style={{ color: "var(--text-muted)" }}
        >
          Отправляется в заголовке <code>X-Webhook-Secret</code>. Не
          возвращается назад в UI.
        </span>
      </label>

      <label className="block mb-[var(--pad-3)]">
        <span
          className="text-[11px] uppercase tracking-[0.16em] font-semibold"
          style={{ color: "var(--text-muted)" }}
        >
          JSON template
        </span>
        <textarea
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          rows={5}
          spellCheck={false}
          className="mt-1.5 w-full px-3 py-2 rounded-md text-[13px] font-mono focus:outline-none"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            color: "var(--text-primary)",
            resize: "vertical",
          }}
        />
        <span
          className="block mt-1.5 text-[11.5px]"
          style={{ color: "var(--text-muted)" }}
        >
          Доступные токены: <code>{"{event}"}</code>, <code>{"{agent}"}</code>,{" "}
          <code>{"{text}"}</code>. Результат должен быть валидным JSON.
        </span>
      </label>

      <div className="mt-[var(--pad-4)] flex items-center gap-2">
        <button
          onClick={onSave}
          disabled={!canSave}
          className="btn btn-primary text-[12.5px]"
          style={{
            opacity: canSave ? 1 : 0.5,
            cursor: canSave ? "pointer" : "not-allowed",
          }}
        >
          {saving ? "Сохраняем…" : "Сохранить"}
        </button>
        <button
          onClick={onTest}
          disabled={testing || status !== "connected"}
          className="btn btn-ghost text-[12.5px]"
          style={{
            opacity: testing || status !== "connected" ? 0.5 : 1,
            cursor:
              testing || status !== "connected" ? "not-allowed" : "pointer",
          }}
          title={
            status === "connected"
              ? "Отправить пробный POST"
              : "Сначала сохрани конфигурацию"
          }
        >
          {testing ? "Отправляем…" : "Test"}
        </button>
        {status === "connected" && (
          <span
            className="text-[11.5px] ml-2"
            style={{ color: "var(--text-muted)" }}
          >
            <StatusDot status="connected" />
            Настроено
          </span>
        )}
      </div>

      {saveError && <ErrorBanner message={saveError} />}

      {testResult && testResult.kind === "success" && (
        <div
          className="mt-[var(--pad-3)] px-3 py-2 rounded-md text-[12px]"
          style={{
            background: "var(--tint-success, var(--bg-secondary))",
            border: "1px solid var(--status-active)",
            color: "var(--status-active)",
          }}
        >
          ✓ {testResult.message}
        </div>
      )}
      {testResult && testResult.kind === "error" && (
        <ErrorBanner message={testResult.message} />
      )}
    </StepCard>
  );
}

export function MessengerSettingsView() {
  const [tab, setTab] = useState<TabKey>("telegram");

  return (
    <div className="h-full overflow-y-auto p-[var(--pad-6)]">
      <div className="max-w-[900px] mx-auto">
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
            Подключение каналов для алертов и задач.
          </p>
        </div>

        <div
          className="flex items-center gap-1 mb-[var(--pad-5)] p-1 rounded-md"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            width: "fit-content",
          }}
        >
          {TABS.map((t) => {
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                aria-pressed={active}
                className="px-3 py-1.5 rounded-md text-[12.5px] transition-colors"
                style={{
                  background: active ? "var(--bg-card)" : "transparent",
                  color: active
                    ? "var(--accent-hover)"
                    : "var(--text-secondary)",
                  fontWeight: active ? 600 : 400,
                  boxShadow: active ? "var(--shadow-sm)" : "none",
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        {tab === "telegram" && <TelegramFlow />}
        {tab === "discord" && <DiscordFlow />}
        {tab === "imessage" && (
          <StubPanel
            title="iMessage"
            note="Скоро — требуется локальный macOS-bridge."
          />
        )}
        {tab === "webhook" && <WebhookPanel />}
      </div>
    </div>
  );
}

export default MessengerSettingsView;
