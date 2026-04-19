## Agents view — gaps

### AgentDrawer.tsx — вкладка «System prompt»
- `AgentDrawer.tsx:265` **Кнопка «Сбросить»** — claim: сброс промпта / actual: нет `onClick` / verdict: **stub**
- `AgentDrawer.tsx:266` **Кнопка «Сохранить»** — claim: сохранить в `.claude/agents/{name}.md` / actual: нет `onClick`, файл не читается и не пишется / verdict: **stub**
- `AgentDrawer.tsx:260` **textarea `defaultValue`** — claim: показывает реальный system-prompt агента / actual: hardcoded шаблон, не читает `.claude/agents/{name}.md` / verdict: **fake**

### AgentDrawer.tsx — вкладка «Настройки»
- `AgentDrawer.tsx:125-129` **Слайдеры maxTokens/temperature/stuckThreshold, тогглы autoRestart/pauseOnDone** — claim: настройки агента / actual: локальный state, сбрасывается в hardcoded-дефолты при смене агента (`142-146`), никуда не отправляется / verdict: **stub**
- `AgentDrawer.tsx:238` **TagInput tools** — claim: список инструментов агента / actual: hardcoded `["Read","Write","Edit","Bash"]`, не редактируется / verdict: **fake**
- `AgentDrawer.tsx:228-248` **Select модели** — claim: "Можно переопределить дефолт" / actual: меняет локальный state, без Save-кнопки изменение теряется / verdict: **missing-wiring**

### AgentDrawer.tsx — вкладка «Опасно»
- `AgentDrawer.tsx:274` **Кнопка «Очистить»** — claim: очистить историю агента / actual: нет `onClick` / verdict: **stub**
- `AgentDrawer.tsx:277-279` **Кнопка «Kill»** — claim: SIGKILL процесса / actual: нет `onClick` / verdict: **stub**
- `AgentDrawer.tsx:282-283` **Кнопка «Удалить»** — claim: удалить файл и память / actual: нет `onClick` / verdict: **stub**

### Backend — отсутствие REST-эндпоинтов
- `communication/server.py` — нет `/agents/spawn`, `/agents/despawn`, `/agents/kill`, `/agents/clear-history`. `spawner.py` и `orchestrator.py` реализуют `spawn`/`despawn` полностью, но UI к ним подключиться не может: эндпоинты не задекларированы.  
  verdict: **missing-wiring** (Python-слой готов, HTTP-мост отсутствует)

### AgentsView.tsx — OK
- Кнопки «Новый агент», карточки, терминал-оверлей — все обработчики подключены. ✅

---

**Общий вердикт:** вкладки «Настройки», «System prompt» и «Опасно» в AgentDrawer — полностью нефункциональные заглушки; для действий Kill/Delete/Spawn нет REST-эндпоинтов на сервере, поэтому даже добавление `onClick` без новых маршрутов не решит проблему.
