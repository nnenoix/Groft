# UI Backlog — Запланированные фичи

## UI-7: Создание кастомных агентов

### Описание
Экран создания агентов прямо в UI без редактирования файлов.

### Форма создания:
- Имя агента (slug: только буквы и дефис)
- Роль (короткое описание)
- Модель (выпадающий список из config.yml)
- Системный промпт (textarea)
- Инструменты (чекбоксы: Read, Write, Edit, Bash)
- Scope (этот проект / все проекты)

### Технически:
- Tauri пишет .claude/agents/{name}.md
- Python file watcher замечает новый файл
- WebSocket broadcast — новый агент доступен
- Агент появляется в списке без перезапуска

### Компоненты:
- ui/src/pages/AgentCreate.tsx — форма
- ui/src/pages/AgentList.tsx — список с кнопкой "+"
- Tauri команда: write_agent_file(name, content)

---

## UI-8: Настройка мессенджера через UI

### Описание
Экран подключения Telegram/Discord/iMessage без терминала.

### Flow для Telegram:
1. Пользователь вводит Bot Token
2. UI вызывает /telegram:configure TOKEN
3. Claude Code перезапускается с --channels
4. UI показывает инструкцию для сопряжения
5. Пользователь пишет боту — получает код
6. UI показывает поле для кода
7. Подтверждение → /telegram:access pair CODE
8. Статус: ● Подключён — @username

### Поддерживаемые мессенджеры:
- Telegram (Bot Token)
- Discord (Bot Token + Server ID)
- iMessage (только macOS)
- Webhook (любой мессенджер через HTTP)

### Компоненты:
- ui/src/pages/MessengerSettings.tsx
- ui/src/hooks/useChannels.ts
- Tauri команды: configure_messenger, get_messenger_status

### Статусы:
- ● Не подключён
- ● Подключение...
- ● Подключён — @username
- ● Ошибка — причина

---

## Приоритет
1. UI-7 (создание агентов) — после интеграционного теста
2. UI-8 (мессенджер) — вместе с UI-7
