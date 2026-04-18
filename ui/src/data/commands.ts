export interface Command {
  id: string;
  label: string;
  hint: string;
  kbd?: string;
}

export const COMMANDS: Command[] = [
  { id: "new-agent",        label: "Создать нового агента",      hint: "Agents · form",   kbd: "N" },
  { id: "new-task",         label: "Добавить задачу в backlog",  hint: "Tasks",           kbd: "T" },
  { id: "switch-solo",      label: "Переключить opus → Solo",    hint: "Mode",            kbd: "S" },
  { id: "switch-team",      label: "Переключить opus → Team",    hint: "Mode",            kbd: "⇧S" },
  { id: "open-telegram",    label: "Настроить Telegram",         hint: "Messengers" },
  { id: "expand-term-opus", label: "Раскрыть терминал opus",     hint: "Terminals" },
  { id: "restart-reviewer", label: "Перезапустить reviewer",     hint: "Actions" },
  { id: "toggle-dark",      label: "Переключить тему",           hint: "View",            kbd: "⇧D" },
  { id: "focus-composer",   label: "Написать сообщение opus",    hint: "Composer",        kbd: "/" },
  { id: "view-graph",       label: "Открыть граф зависимостей",  hint: "Tasks · graph",   kbd: "G" },
];
