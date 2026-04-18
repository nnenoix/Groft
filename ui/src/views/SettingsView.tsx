import { useState, type ReactNode } from "react";
import { Icon } from "../components/icons";
import { Avatar, StatusLabel, type Status } from "../components/primitives";
import { MODEL_OPTIONS as MODELS } from "../data/models";
import { useAgents } from "../store/agentStore";

/* ---- Types ---- */

export type UISettings = {
  theme: "light" | "dark";
  font: "inter" | "geist" | "plex";
  density: "compact" | "normal" | "spacious";
  accent: "default" | "violet" | "moss" | "ocean";
  backdrop: "none" | "froggly";
};

interface Role {
  key: string;
  label: string;
  model: string;
  desc: string;
  locked: boolean;
}

interface MessengerTab {
  key: string;
  label: string;
  status: Status;
  account: string | null;
}

/* ---- Shared helper ---- */

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[10.5px] uppercase tracking-[0.16em] font-semibold" style={{ color: "var(--text-muted)" }}>
        {label}
      </span>
      {children}
    </label>
  );
}

/* ---- Settings layout primitives ---- */

function SettingsSection({ title, desc, children }: { title: ReactNode; desc?: string; children: ReactNode }) {
  return (
    <section className="mb-[var(--pad-6)]">
      <div className="mb-[var(--pad-4)]">
        <h2 className="text-[17px] font-display font-semibold tracking-tight">{title}</h2>
        {desc && <p className="text-[12.5px] mt-1" style={{ color: "var(--text-muted)" }}>{desc}</p>}
      </div>
      <div className="card divide-y" style={{ borderColor: "var(--border)" }}>{children}</div>
    </section>
  );
}

function SettingRow({ label, hint, children, danger }: {
  label: ReactNode;
  hint?: ReactNode;
  children?: ReactNode;
  danger?: boolean;
}) {
  return (
    <div className="px-[var(--pad-5)] py-[var(--pad-4)] flex items-start gap-[var(--pad-4)]"
      style={{ borderBottom: "1px solid var(--border)" }}>
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-medium"
          style={{ color: danger ? "var(--status-stuck)" : "var(--text-primary)" }}>
          {label}
        </div>
        {hint && <div className="text-[11.5px] mt-1 leading-relaxed" style={{ color: "var(--text-muted)" }}>{hint}</div>}
      </div>
      <div className="shrink-0 flex items-center gap-2">{children}</div>
    </div>
  );
}

/* ---- Form primitives ---- */

function Toggle({ checked, onChange }: { checked?: boolean; onChange?: (v: boolean) => void }) {
  const [local, setLocal] = useState(checked ?? false);
  const v = onChange !== undefined ? (checked ?? false) : local;
  return (
    <button
      onClick={() => { const n = !v; setLocal(n); onChange?.(n); }}
      role="switch" aria-checked={v}
      className="relative rounded-full transition-colors"
      style={{ width: 34, height: 20, background: v ? "var(--accent-primary)" : "var(--border)" }}
    >
      <span className="absolute top-0.5 rounded-full transition-all"
        style={{ width: 16, height: 16, background: "var(--bg-card)", left: v ? 16 : 2, boxShadow: "var(--shadow-sm)" }} />
    </button>
  );
}

function Input({ type = "text", placeholder, value, width = 220, mono = false, onChange }: {
  type?: string;
  placeholder?: string;
  value?: string;
  width?: number;
  mono?: boolean;
  onChange?: (v: string) => void;
}) {
  const [local, setLocal] = useState(value ?? "");
  const v = onChange !== undefined ? (value ?? "") : local;
  return (
    <input
      type={type}
      placeholder={placeholder}
      value={v}
      onChange={(e) => { setLocal(e.target.value); onChange?.(e.target.value); }}
      className={`px-3 py-1.5 rounded-md text-[12.5px] focus:outline-none${mono ? " font-mono" : ""}`}
      style={{ width, background: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
    />
  );
}

function Select({ options, value, onChange }: {
  options: string[];
  value?: string;
  onChange?: (v: string) => void;
}) {
  const [local, setLocal] = useState(value ?? options[0] ?? "");
  const v = onChange !== undefined ? (value ?? "") : local;
  return (
    <select
      value={v}
      onChange={(e) => { setLocal(e.target.value); onChange?.(e.target.value); }}
      className="px-2 py-1.5 rounded-md text-[12.5px] focus:outline-none"
      style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
    >
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

function Slider({ min = 0, max = 100, value = 50, suffix = "", onChange }: {
  min?: number;
  max?: number;
  value?: number;
  suffix?: string;
  onChange?: (v: number) => void;
}) {
  const [local, setLocal] = useState(value);
  const v = onChange !== undefined ? value : local;
  return (
    <div className="flex items-center gap-2" style={{ width: 220 }}>
      <input
        type="range" min={min} max={max} value={v}
        onChange={(e) => { setLocal(+e.target.value); onChange?.(+e.target.value); }}
        className="flex-1"
        style={{ accentColor: "var(--accent-primary)" }}
      />
      <span className="text-[11.5px] font-mono w-12 text-right" style={{ color: "var(--text-muted)" }}>{v}{suffix}</span>
    </div>
  );
}

function SecretField({ placeholder, value }: { placeholder?: string; value?: string }) {
  const [reveal, setReveal] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <Input type={reveal ? "text" : "password"} placeholder={placeholder} value={value} mono width={240} />
      <button onClick={() => setReveal(!reveal)} className="btn btn-ghost text-[11px]">
        {reveal ? "скрыть" : "показать"}
      </button>
    </div>
  );
}

function Segmented({ options, value, onChange }: {
  options: [string, string][];
  value?: string;
  onChange?: (v: string) => void;
}) {
  const [local, setLocal] = useState(value ?? options[0]?.[0] ?? "");
  const v = onChange !== undefined ? (value ?? "") : local;
  return (
    <div className="seg">
      {options.map(([k, l]) => (
        <button key={k} aria-pressed={v === k} onClick={() => { setLocal(k); onChange?.(k); }}>{l}</button>
      ))}
    </div>
  );
}

export function ColorDots({ colors, value, onChange }: {
  colors: string[];
  value?: string;
  onChange?: (v: string) => void;
}) {
  const [local, setLocal] = useState(value ?? colors[0] ?? "");
  const v = onChange !== undefined ? (value ?? "") : local;
  return (
    <div className="flex items-center gap-1.5">
      {colors.map((c) => (
        <button key={c} onClick={() => { setLocal(c); onChange?.(c); }} aria-label={c}
          className="w-6 h-6 rounded-full transition-all"
          style={{ background: c, boxShadow: v === c ? `0 0 0 2px var(--bg-card), 0 0 0 4px ${c}` : "none" }} />
      ))}
    </div>
  );
}

function TagInput({ tags }: { tags: string[] }) {
  const [list, setList] = useState(tags);
  const [text, setText] = useState("");
  function add() {
    if (text.trim()) { setList([...list, text.trim()]); setText(""); }
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5" style={{ maxWidth: 320 }}>
      {list.map((t, i) => (
        <span key={i} className="chip !py-0.5">
          {t}
          <button onClick={() => setList(list.filter((_, j) => j !== i))} style={{ color: "var(--text-muted)" }}>
            <Icon.X size={10} />
          </button>
        </span>
      ))}
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && add()}
        placeholder="+ tag"
        className="px-2 py-0.5 text-[11.5px] rounded-md focus:outline-none"
        style={{ background: "transparent", border: "1px dashed var(--border)", color: "var(--text-primary)", width: 80 }}
      />
    </div>
  );
}

function KbdCapture({ shortcut }: { shortcut: string }) {
  const parts = shortcut.split("+");
  return (
    <button className="px-2.5 py-1 rounded-md text-[11.5px] flex items-center gap-1"
      style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
      {parts.flatMap((k, i) =>
        i === 0
          ? [<kbd key={k}>{k}</kbd>]
          : [
              <span key={`sep-${i}`} className="text-[10px]" style={{ color: "var(--text-dim)" }}>+</span>,
              <kbd key={k}>{k}</kbd>,
            ]
      )}
    </button>
  );
}

/* ---- General settings ---- */

function GeneralSettings({ state, setState }: {
  state: UISettings;
  setState?: (patch: Partial<UISettings>) => void;
}) {
  function update<K extends keyof UISettings>(k: K, v: UISettings[K]) {
    setState?.({ [k]: v } as Partial<UISettings>);
  }
  return (
    <>
      <SettingsSection title="Тема и плотность" desc="Меняется мгновенно, сохраняется между сессиями.">
        <SettingRow label="Тема" hint="Светлая / тёмная">
          <div className="seg">
            <button aria-pressed={state.theme === "light"} onClick={() => update("theme", "light")}>
              <Icon.Sun size={11} /> Light
            </button>
            <button aria-pressed={state.theme === "dark"} onClick={() => update("theme", "dark")}>
              <Icon.Moon size={11} /> Dark
            </button>
          </div>
        </SettingRow>
        <SettingRow label="Плотность" hint="Сколько воздуха между элементами">
          <div className="seg">
            {([ ["compact","Compact"], ["normal","Normal"], ["spacious","Spacious"] ] as [UISettings["density"], string][]).map(([k, l]) => (
              <button key={k} aria-pressed={state.density === k} onClick={() => update("density", k)}>{l}</button>
            ))}
          </div>
        </SettingRow>
        <SettingRow label="Шрифт" hint="Основной UI-шрифт">
          <div className="seg">
            {([ ["inter","Inter"], ["geist","Geist"], ["plex","IBM Plex"] ] as [UISettings["font"], string][]).map(([k, l]) => (
              <button key={k} aria-pressed={state.font === k} onClick={() => update("font", k)}>{l}</button>
            ))}
          </div>
        </SettingRow>
        <SettingRow label="Анимации" hint="Движение карточек, пульсация статусов">
          <Toggle checked />
        </SettingRow>
      </SettingsSection>

      <SettingsSection
        title={
          <span>
            Акцент{" "}
            <span className="chip !py-0.5 ml-2"
              style={{ background: "var(--tint-warning)", color: "var(--status-warning)", borderColor: "transparent" }}>
              эксперимент
            </span>
          </span>
        }
        desc="Тёплый оранжевый — фирменный. Остальное — показательная фича."
      >
        <SettingRow label="Цвет подсветки">
          <div className="seg">
            {([
              ["default", "Claude", "#d97757"],
              ["violet",  "Violet", "#8572d9"],
              ["moss",    "Moss",   "#6b8e4e"],
              ["ocean",   "Ocean",  "#4a8bc9"],
            ] as [UISettings["accent"], string, string][]).map(([k, l, c]) => (
              <button key={k} aria-pressed={state.accent === k} onClick={() => update("accent", k)}>
                <span className="inline-block w-2 h-2 rounded-full mr-1" style={{ background: c }} /> {l}
              </button>
            ))}
          </div>
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Атмосфера" desc="Декоративный фон под интерфейсом. Чисто эстетическая фича.">
        <SettingRow label="Фон приложения" hint="Мягкий градиент, проступающий через панели">
          <div className="seg">
            <button aria-pressed={!state.backdrop || state.backdrop === "none"} onClick={() => update("backdrop", "none")}>
              Выкл
            </button>
            <button aria-pressed={state.backdrop === "froggly"} onClick={() => update("backdrop", "froggly")}>
              <span className="inline-block w-2 h-2 rounded-full mr-1"
                style={{ background: "linear-gradient(180deg, #7cc0bd, #5ea14b)" }} />
              Pond
            </button>
          </div>
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Поведение">
        <SettingRow label="Автозапуск" hint="Поднимать WebSocket и агентов при старте системы">
          <Toggle checked />
        </SettingRow>
        <SettingRow label="Открывать на старте" hint="Какой экран будет первым">
          <Select options={["Terminals", "Agents", "Tasks", "Последний открытый"]} value="Последний открытый" />
        </SettingRow>
        <SettingRow label="⌘K — палитра команд">
          <KbdCapture shortcut="⌘+K" />
        </SettingRow>
        <SettingRow label="Фокус на композер Opus'а">
          <KbdCapture shortcut="⌘+/" />
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Уведомления">
        <SettingRow label="Агент застрял (stuck)" hint="Pop-up + звук при переходе агента в stuck">
          <Toggle checked />
        </SettingRow>
        <SettingRow label="Задача закрыта" hint="Тихое уведомление при done">
          <Toggle />
        </SettingRow>
        <SettingRow label="Звук уведомлений" hint="Громкость колокольчика">
          <Slider value={45} suffix="%" />
        </SettingRow>
      </SettingsSection>
    </>
  );
}

/* ---- Agents settings ---- */

const DEFAULT_ROLES: Role[] = [
  { key: "opus",     label: "Тимлид (opus)", model: "claude-opus-4-7",   desc: "Планирует, раздаёт, ревью",  locked: true },
  { key: "backend",  label: "Backend",        model: "claude-sonnet-4-6", desc: "Python / Rust / infra",      locked: false },
  { key: "frontend", label: "Frontend",       model: "claude-sonnet-4-6", desc: "React / TS / UI",            locked: false },
  { key: "tester",   label: "QA / tester",    model: "claude-haiku-4-5-20251001",  desc: "Быстрый test cycle",         locked: false },
  { key: "reviewer", label: "Reviewer",       model: "claude-sonnet-4-6", desc: "Diff review перед merge",    locked: false },
  { key: "docs",     label: "Docs",           model: "claude-haiku-4-5-20251001",  desc: "README, architecture notes", locked: false },
];

const MODEL_OPTIONS = MODELS;

function RoleRow({ role, editing, onEdit, onChange, onRemove }: {
  role: Role;
  editing: boolean;
  onEdit: () => void;
  onChange: (patch: Partial<Role>) => void;
  onRemove: () => void;
}) {
  return (
    <div className="px-[var(--pad-5)] py-[var(--pad-3)]" style={{ borderBottom: "1px solid var(--border)" }}>
      <div className="flex items-start gap-3">
        <Avatar name={role.key} letter={role.label[0]?.toUpperCase()} size={28} />
        <div className="flex-1 min-w-0">
          {editing ? (
            <input
              autoFocus
              value={role.label}
              onChange={(e) => onChange({ label: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && onEdit()}
              className="w-full px-2 py-1 text-[13px] font-medium rounded-md focus:outline-none"
              style={{ background: "var(--bg-secondary)", border: "1px solid var(--accent-primary)", color: "var(--text-primary)" }}
            />
          ) : (
            <div className="text-[13px] font-medium">{role.label}</div>
          )}
          <div className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>{role.desc}</div>
          <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
            <select
              value={role.model}
              onChange={(e) => onChange({ model: e.target.value })}
              className="px-2 py-1 rounded-md text-[11px] font-mono focus:outline-none"
              style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
            >
              {MODEL_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <button onClick={onEdit} className="btn btn-ghost !p-1.5" title={editing ? "Готово" : "Переименовать"}>
              {editing ? <Icon.Check size={12} /> : <Icon.Edit size={12} />}
            </button>
            {!role.locked ? (
              <button onClick={onRemove} className="btn btn-ghost !p-1.5" title="Удалить роль"
                style={{ color: "var(--text-muted)" }}>
                <Icon.Trash size={12} />
              </button>
            ) : (
              <span className="chip !py-0.5 !text-[9.5px]" title="Системная роль">lock</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function AgentsSettings() {
  const [roles, setRoles] = useState<Role[]>(DEFAULT_ROLES);
  const [editingKey, setEditingKey] = useState<string | null>(null);

  function updateRole(key: string, patch: Partial<Role>) {
    setRoles((rs) => rs.map((r) => r.key === key ? { ...r, ...patch } : r));
  }
  function addRole() {
    const i = roles.length + 1;
    const key = `custom-${i}`;
    setRoles((rs) => [...rs, { key, label: `custom-agent-${i}`, model: "claude-sonnet-4-6", desc: "Своя роль", locked: false }]);
    setEditingKey(key);
  }
  function removeRole(key: string) {
    setRoles((rs) => rs.filter((r) => r.key !== key));
  }

  return (
    <>
      <SettingsSection title="Роли и модели" desc="Какие агенты спаунятся по команде opus'а. Редактируй имена, роли и модели — эти же шаблоны использует Cmd+K → «Создать агента».">
        {roles.map((r) => (
          <RoleRow
            key={r.key}
            role={r}
            editing={editingKey === r.key}
            onEdit={() => setEditingKey(editingKey === r.key ? null : r.key)}
            onChange={(patch) => updateRole(r.key, patch)}
            onRemove={() => removeRole(r.key)}
          />
        ))}
        <div className="px-[var(--pad-5)] py-[var(--pad-3)] flex items-center justify-between"
          style={{ borderTop: "1px dashed var(--border)" }}>
          <span className="text-[11.5px]" style={{ color: "var(--text-muted)" }}>
            Добавь свою роль для узких задач — аудитор, миграции, devops…
          </span>
          <button onClick={addRole} className="btn btn-outline text-[11.5px]">
            <Icon.Plus size={12} /> Новая роль
          </button>
        </div>
      </SettingsSection>

      <SettingsSection title="Watchdog" desc="Автоматика вокруг зависших агентов.">
        <SettingRow label="Stuck threshold" hint="Через сколько минут idle помечать как stuck">
          <Slider min={1} max={15} value={3} suffix="м" />
        </SettingRow>
        <SettingRow label="Авто-рестарт" hint="Перезапускать stuck-агента автоматически">
          <Toggle checked />
        </SettingRow>
        <SettingRow label="Макс. попыток рестарта" hint="После чего watchdog сдаётся и зовёт тебя">
          <Slider min={1} max={10} value={3} />
        </SettingRow>
        <SettingRow label="Уведомлять opus" hint="Opus узнает о stuck-агенте сразу">
          <Toggle checked />
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Инструменты по умолчанию" desc="Что разрешено новому агенту из коробки.">
        <SettingRow label="Набор tools" hint="Read / Write / Edit / Bash / WebFetch и кастомные">
          <TagInput tags={["Read", "Write", "Edit", "Bash"]} />
        </SettingRow>
        <SettingRow label="Лимит токенов на цикл" hint="Чтобы сонный агент не съел бюджет">
          <Slider min={1} max={200} value={120} suffix="k" />
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Режим оркестрации">
        <SettingRow label="Порог Solo → Team" hint="Когда задача считается сложной">
          <Segmented options={[["auto", "Авто"], ["files", "> 2 файлов"], ["manual", "Вручную"]]} value="auto" />
        </SettingRow>
        <SettingRow label="TDD цикл обязателен" hint="Opus сначала пишет тест, потом код">
          <Toggle checked />
        </SettingRow>
        <SettingRow label="Аудит после каждого цикла" hint="Архитектура + безопасность + паттерны">
          <Toggle checked />
        </SettingRow>
      </SettingsSection>
    </>
  );
}

/* ---- Messengers settings (stub — useChannels wiring in FE-8) ---- */

function MessengersSettings() {
  const [tab, setTab] = useState("telegram");
  const tabs: MessengerTab[] = [
    { key: "telegram", label: "Telegram", status: "connected",     account: "@orch_team_bot" },
    { key: "imessage", label: "iMessage", status: "not-connected", account: null },
  ];
  const current = tabs.find((t) => t.key === tab);
  if (!current) return null;

  return (
    <>
      <SettingsSection title="Мессенджеры" desc="Куда приходят алерты и откуда opus принимает задачи.">
        {tabs.map((m) => (
          <SettingRow key={m.key} label={m.label} hint={m.account ?? "Не подключён"}>
            <StatusLabel status={m.status} />
            <button onClick={() => setTab(m.key)} className="btn btn-outline text-[11.5px]">Настроить</button>
          </SettingRow>
        ))}
      </SettingsSection>

      <SettingsSection title={`${current.label} · детали`} desc="Поля заполняются перед подключением канала.">
        {tab === "telegram" && (
          <>
            <SettingRow label="Bot token" hint="Получи у @BotFather">
              <SecretField placeholder="123456:ABC-DEF…" />
            </SettingRow>
            <SettingRow label="Long polling" hint="Дешевле чем webhook, но требует живого процесса">
              <Toggle checked />
            </SettingRow>
            <SettingRow label="Разрешённые чаты" hint="Whitelist — оркестр не ответит незнакомцу">
              <TagInput tags={[]} />
            </SettingRow>
            <SettingRow label="Переадресация алертов" hint="Кому пересылать stuck-уведомления">
              <Input placeholder="@username" width={200} />
            </SettingRow>
          </>
        )}
        {tab === "imessage" && (
          <>
            <SettingRow label="Локальный bridge" hint="Только macOS · использует osascript">
              <Toggle />
            </SettingRow>
            <SettingRow label="Handle" hint="Номер или email, с которого отвечает бот">
              <Input placeholder="+7…" width={200} />
            </SettingRow>
            <SettingRow label="Путь к bridge" hint="Unix socket локального relay">
              <Input value="/tmp/imessage-bridge.sock" mono width={280} />
            </SettingRow>
          </>
        )}
        <SettingRow label="Тест соединения" hint="Отправить пробный пинг прямо сейчас">
          <button className="btn btn-outline text-[11.5px]"><Icon.Zap size={12} /> Проверить</button>
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Фильтры уведомлений" desc="Какие события отправлять в мессенджеры.">
        <SettingRow label="Агент stuck"><Toggle checked /></SettingRow>
        <SettingRow label="Задача закрыта (done)"><Toggle /></SettingRow>
        <SettingRow label="Ошибка в watchdog"><Toggle checked /></SettingRow>
        <SettingRow label="Opus ждёт решения от пользователя"><Toggle checked /></SettingRow>
        <SettingRow label="Quiet hours" hint="Не беспокоить с… по…">
          <div className="flex items-center gap-2 text-[12px]">
            <Input type="time" value="23:00" width={80} />
            <span style={{ color: "var(--text-muted)" }}>→</span>
            <Input type="time" value="08:00" width={80} />
          </div>
        </SettingRow>
      </SettingsSection>
    </>
  );
}

/* ---- System settings ---- */

function SystemSettings() {
  const wsUrl =
    (import.meta.env.VITE_WS_URL as string | undefined) ?? "ws://localhost:8765";
  const restUrl =
    (import.meta.env.VITE_REST_URL as string | undefined) ??
    "http://localhost:8766";
  return (
    <>
      <SettingsSection title="Коммуникация" desc="WebSocket + REST сервер оркестратора.">
        <SettingRow label="WebSocket" hint="Живое соединение с оркестром">
          <Input value={wsUrl} mono width={240} />
        </SettingRow>
        <SettingRow label="REST API" hint="Снэпшот ростера / задач">
          <Input value={restUrl} mono width={240} />
        </SettingRow>
        <SettingRow label="MCP server" hint="Model Context Protocol endpoint">
          <Input value="stdio://" mono width={160} />
        </SettingRow>
        <SettingRow label="Авто-реконнект" hint="При разрыве соединения пробовать снова">
          <Toggle checked />
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Файлы и память">
        <SettingRow label="Рабочая директория">
          <Input value="/mnt/d/orchkerstr" mono width={280} />
        </SettingRow>
        <SettingRow label="Checkpoints">
          <Input value=".groft/recovery.duckdb" mono width={280} />
        </SettingRow>
        <SettingRow label="Shared memory TTL" hint="Сколько хранить общую память">
          <Slider min={7} max={90} value={30} suffix="д" />
        </SettingRow>
        <SettingRow label="Очистить кэш" hint="Логи + duckdb чекпоинты · не трогает код">
          <button className="btn btn-outline text-[11.5px]">Очистить · 142 MB</button>
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Git & VCS">
        <SettingRow label="Репозиторий">
          <Input placeholder="owner/repo" mono width={200} />
        </SettingRow>
        <SettingRow label="Ветка по умолчанию">
          <Input value="main" mono width={120} />
        </SettingRow>
        <SettingRow label="Авто-коммит после done" hint="Оркестр коммитит когда задача пройдёт ревью">
          <Toggle checked />
        </SettingRow>
        <SettingRow label="Требовать подпись" hint="GPG sign commits">
          <Toggle />
        </SettingRow>
      </SettingsSection>

      <SettingsSection title="Опасная зона">
        <SettingRow label="Перезапустить оркестр" hint="Остановит всех агентов и поднимет заново" danger>
          <button className="btn btn-outline text-[11.5px]"
            style={{ color: "var(--status-stuck)", borderColor: "var(--status-stuck)" }}>
            Перезапустить
          </button>
        </SettingRow>
        <SettingRow label="Сбросить настройки" hint="Удалит config.yml и вернёт дефолты" danger>
          <button className="btn btn-outline text-[11.5px]"
            style={{ color: "var(--status-stuck)", borderColor: "var(--status-stuck)" }}>
            Сбросить
          </button>
        </SettingRow>
        <SettingRow label="Удалить все checkpoints" hint="История сессий будет потеряна безвозвратно" danger>
          <button className="btn btn-outline text-[11.5px]"
            style={{ color: "var(--status-stuck)", borderColor: "var(--status-stuck)" }}>
            <Icon.Trash size={12} /> Удалить
          </button>
        </SettingRow>
      </SettingsSection>
    </>
  );
}

/* ---- About settings ---- */

function AboutSettings() {
  const agents = useAgents();
  const activeCount = agents.filter((a) => a.status === "active").length;
  const version = (import.meta.env.VITE_APP_VERSION as string | undefined) ?? "0.1.0";
  const rows = [
    { k: "Версия",  v: `Groft v${version}`, note: "desktop shell" },
    { k: "Tauri",   v: "2.0",               note: "runtime" },
    { k: "React",   v: "19",                note: "UI" },
    { k: "Агентов", v: `${activeCount} / ${agents.length}`, note: "активных / зарегистрированных" },
  ];
  return (
    <>
      <SettingsSection title="О приложении">
        {rows.map((r, i) => (
          <div key={i} className="px-[var(--pad-5)] py-[var(--pad-4)] flex items-center gap-4"
            style={{ borderBottom: i < rows.length - 1 ? "1px solid var(--border)" : "none" }}>
            <div className="w-28 text-[11.5px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{r.k}</div>
            <div className="flex-1 font-mono text-[13px]" style={{ color: "var(--text-code)" }}>{r.v}</div>
            <div className="text-[11.5px]" style={{ color: "var(--text-muted)" }}>{r.note}</div>
          </div>
        ))}
      </SettingsSection>
      <SettingsSection title="Ссылки">
        <SettingRow label="GitHub" hint="Исходники и issue tracker">
          <a href="#" className="text-[12px]" style={{ color: "var(--accent-primary)" }}>github.com/nnenoix/orck</a>
        </SettingRow>
        <SettingRow label="Документация">
          <a href="#" className="text-[12px]" style={{ color: "var(--accent-primary)" }}>docs.orch.dev</a>
        </SettingRow>
        <SettingRow label="Сообщить о баге">
          <button className="btn btn-outline text-[11.5px]">Открыть форму</button>
        </SettingRow>
      </SettingsSection>
    </>
  );
}

/* ---- Main SettingsView ---- */

export function SettingsView({ state, setState }: {
  state: UISettings;
  setState: (patch: Partial<UISettings>) => void;
}) {
  const [section, setSection] = useState("general");
  const navItems = [
    { key: "general",    label: "Внешний вид", NavIcon: Icon.Sliders },
    { key: "agents",     label: "Агенты",      NavIcon: Icon.Users },
    { key: "messengers", label: "Мессенджеры", NavIcon: Icon.Chat },
    { key: "system",     label: "Система",     NavIcon: Icon.Layers },
    { key: "about",      label: "О программе", NavIcon: Icon.Heart },
  ];
  return (
    <div className="h-full overflow-hidden flex flex-col">
      <div className="px-[var(--pad-6)] pt-[var(--pad-6)] pb-[var(--pad-3)] shrink-0">
        <div className="text-[11px] uppercase tracking-[0.2em] font-semibold mb-1" style={{ color: "var(--text-muted)" }}>
          Preferences
        </div>
        <h1 className="text-[28px] font-display font-semibold tracking-tight">Настройки</h1>
      </div>
      <div className="flex-1 min-h-0 grid grid-cols-[220px_1fr] gap-[var(--pad-5)] px-[var(--pad-6)] pb-[var(--pad-6)]">
        <nav className="space-y-1 overflow-y-auto">
          {navItems.map((s) => (
            <button key={s.key} onClick={() => setSection(s.key)} data-active={section === s.key}
              className="nav-pill w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] text-left transition-colors">
              <s.NavIcon size={14} />
              <span>{s.label}</span>
            </button>
          ))}
        </nav>
        <div className="overflow-y-auto pr-2">
          {section === "general"    && <GeneralSettings state={state} setState={setState} />}
          {section === "agents"     && <AgentsSettings />}
          {section === "messengers" && <MessengersSettings />}
          {section === "system"     && <SystemSettings />}
          {section === "about"      && <AboutSettings />}
        </div>
      </div>
    </div>
  );
}
