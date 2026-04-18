# Code Review: Python Core

Дата: 2026-04-18
Ревьюер: core-reviewer

## Критично (блокирует работу)

- **RecoveryManager не получает `agent_tmux_targets` в `main.py`.** `core/main.py:41-43` конструирует `RecoveryManager(checkpoint_manager, process_guard, agent_watchdog, error_handler)` без ключевого параметра `agent_tmux_targets`. В результате `restore_session` (recovery_manager.py:95) никогда не зарегистрирует агентов в watchdog — поле словарь пуст, все `agent_name` уйдут в `missing`. Рекомендация: прокинуть общий реестр целей (config.yml) как в `RecoveryManager`, так и в `CommunicationServer(lead_tmux_target=..., agent_tmux_targets=...)` — иначе и watchdog, и UI→tmux форвард мёртвые.

- **`CommunicationServer` создаётся без tmux-таргетов.** `core/main.py:23` — `CommunicationServer()` без аргументов, поэтому `_forward_to_tmux` (server.py:281) всегда возвращает `None`, и UI→агент через tmux не работает вообще. Рекомендация: читать config.yml при старте и передавать таргеты в оба модуля.

- **`restore_session` нигде не вызывается.** `core/recovery/recovery_manager.py:88` — после `recovery_manager.initialize()` (main.py:48) при `has_unfinished=True` оркестратор только печатает сообщение и идёт дальше, не восстанавливая агентов в watchdog/process_guard. Рекомендация: в `main.py` после `if result.has_unfinished` вызывать `await recovery_manager.restore_session(result.checkpoint)` либо явно `start_fresh()`.

- **Потерянные интеграции ErrorHandler.** `core/error/error_handler.py` содержит полный набор `set_checkpoint_callback`, `set_restart_callback`, `set_bad_code_callback`, `set_compaction_callback`, и сам метод `handle()` нигде вне модуля не вызывается (grep показал 0 использований `error_handler.handle`, 0 установок callback-ов). Без подписок `CLAUDE_CODE_CRASH` не триггерит рестарт, `CONTEXT_OVERFLOW` не триггерит compaction. Рекомендация: в `main.py` после создания компонентов связать: `error_handler.set_checkpoint_callback(...)`, `set_restart_callback(agent_watchdog callback или process_guard)`, `set_compaction_callback(session_manager.trigger_compaction)`; и создать путь доставки ошибок (из watchdog `stuck` → `handle(AGENT_STUCK)`).

- **`ProcessGuard` callback-и не установлены.** `core/main.py` не вызывает `process_guard.set_checkpoint_callback(...)` и `set_agent_stop_callback(...)`. На Ctrl-C `_shutdown` не сохранит чекпойнт (checkpoint_manager.save) и просто очистит in-memory set агентов вместо graceful-stop реальных процессов. Рекомендация: `process_guard.set_checkpoint_callback(lambda: checkpoint_manager.save(build_current_checkpoint()))` и `set_agent_stop_callback(...)` до `process_guard.install()`.

- **`SessionManager` создан, но нигде не используется.** `memory/session_manager.py` импортируется только в `memory/__init__.py`. Никто не инстанцирует его, `needs_compaction`/`trigger_compaction` мёртвы — следовательно `CONTEXT_OVERFLOW` в error-handler указывает в пустоту. Рекомендация: создать `SessionManager` на агента (или регистр по `tmux_target`) и подключить к `error_handler.set_compaction_callback`.

## Важно (нужно исправить)

- **`AgentWatchdog` не сообщает об stuck в `ErrorHandler`.** `core/watchdog/agent_watchdog.py:145-159` при `stuck`/`restart` дергает локальные callback-и, но они в `main.py` не установлены (`set_wake_up_callback`, `set_restart_callback`, `set_notification_callback` — нулевые usage вне модуля). Рекомендация: при старте связать watchdog-callback-и с `error_handler.handle(ErrorContext(..., AGENT_STUCK))`.

- **`GitManager.get_rollback_history` не используется.** `git_manager/manager.py:190` — функция возвращает историю, но никто её не читает. Если это спецификация для будущего — ок, но тогда должен быть хотя бы вызов из RecoveryManager при построении Opus-контекста. Иначе удалить.

- **Подавление `BaseException` в watchdog-мониторе.** `core/watchdog/agent_watchdog.py:102` — `if isinstance(result, BaseException): continue`. Ловля `BaseException` проглатывает `CancelledError`/`KeyboardInterrupt` внутри `gather` — цикл продолжит крутиться при попытке остановки. Рекомендация: ловить `Exception` (не `BaseException`); `CancelledError` должен прерывать цикл, а не игнорироваться.

- **`process_guard.register_agent` после рестарта.** `core/recovery/recovery_manager.py:93` регистрирует имена из `checkpoint.agent_states`, но `ProcessGuard` не знает про tmux-процессы — это только имена. Если реальные агенты после рестарта не стартуют, `has_active_agents()` вернёт True на пустом месте, и Ctrl-C будет спрашивать подтверждение зря. Рекомендация: регистрировать только после фактического спауна Agent Team.

- **Race при повторном `start()` в `CommunicationServer`.** `communication/server.py:65-93` — guard `if self._started: return` хороший, но busy-wait `for _ in range(100): await asyncio.sleep(0.05)` (5 сек всего) может истечь на медленном старте uvicorn, а `self._started=True` всё равно выставится. Рекомендация: если socket не забиндился за таймаут — raise и откатить состояние (остановить ws-сервер, закрыть conn).

- **Глобальный `SNAPSHOT_SINK_AGENT = "opus"` жёстко зашит.** `communication/server.py:19`. Если оркестратор подключается под именем `orchestrator` (как в `core/main.py:26`), а не `opus`, snapshot-ы никуда не доходят. Это прямое расхождение. Рекомендация: либо переименовать оркестратора в `opus`, либо сделать sink-имя параметром конструктора и выставлять из config.

- **`CheckpointManager.has_unfinished_session` не используется.** `core/session/checkpoint.py:106` — логика дублируется в `RecoveryManager.initialize` через `load_latest`. Либо удалить, либо заменить вызов в RecoveryManager на него.

- **`memory_manager` используется только для `initialize/close`.** `core/main.py:34,39,80` — конструируется и инициализируется, но ни `get_context`, ни `update_*` нигде не вызываются из Python (это ожидаемо, Opus вызывает через CLI). Однако тогда `MemoryManager` должен быть тоньше или хотя бы иметь явный публичный API-entry для Opus (например, через WebSocket-команду сервера). Сейчас это «висящий» модуль — подтвердите сценарий вызова.

- **Поведение `shutdown_event` без подписчиков.** `core/guard/process_guard.py:81-84` — event устанавливается в `_shutdown`, но никто не `await`-ит его (в main используется `wait_for_stop()` через future). Рекомендация: или убрать `shutdown_event`, или применять его в watchdog/recovery для graceful-stop, чтобы избежать двойной координации (event + future).

## Замечания (можно улучшить)

- **Нет `logging` вообще — всё через `print`.** `core/main.py:51,54,60`. Для control-layer допустимо, но лучше единый logger: понадобится при работе под systemd/tmux без stdout.

- **`CheckpointManager.save` без защиты от race-at-shutdown.** checkpoint.py:84 — `assert self._conn is not None`. Если `close()` гонка c `save()` — AssertionError. Рекомендация: lock или graceful return.

- **`ErrorHandler.CLAUDE_CODE_CRASH` сбрасывает retry только через `_increment_retry`, но без лимита.** error_handler.py:155 — в отличие от `NETWORK_ERROR`, нет порога; бесконечный цикл рестартов возможен. Рекомендация: добавить `_MAX_CRASH_RETRIES`.

- **`AgentWatchdog._send_snapshot` создаётся через `asyncio.create_task` внутри `with self._lock`.** watchdog.py:119-123 — не критично (lock — threading), но лучше выносить наружу. Также двойной try (снаружи и внутри `_send_snapshot`) избыточен.

- **`GitManager._log("init", ...)` идёт после создания таблицы; если она падает — record-at-success неожиданный.** Рекомендация: log и успех, и неудачу `init`.

- **`CommunicationServer` помечен `websockets.WebSocketServer`, но у пакета `websockets` с 11.x публичный тип — `websockets.Server`.** Аннотация может ломать статическую проверку в новых версиях.

- **`aiosqlite.Row | tuple[Any, ...]` в `Checkpoint.from_row` принимает оба, но `_conn.execute` возвращает `Row` только если включить `row_factory` — сейчас это обычный tuple.** Аннотация вводит в заблуждение; оставьте `tuple[Any, ...]`.

- **`MemoryManager.compress` не логирует `bytes_before == 0`.** manager.py:143 — `bytes_before < THRESHOLD` молчаливо возвращает False; лучше залогировать «skipped» для телеметрии.

- **Конвенция: в scope модулях нет docstring-ов (в соответствии с памятью `project_claudeorch_stage0.md`), но встречаются избыточные inline-комментарии вроде `# re-entry guard: ...` — норм, они ценные. Однако `# script-mode: ensure project root is importable` в `main.py:6` можно упрощать.**

- **Дублирование логики журналирования DuckDB.** `error_handler`, `recovery_manager`, `git_manager`, `memory`, `communication/server` — все имеют одинаковый паттерн `_execute_insert`/`_log` с nearly identical sequence+insert. Можно выделить `core/storage/duckdb_event_log.py`.

## Хорошо сделано

- Чёткая изоляция control-layer (`main.py` — только wiring, без логики).
- Везде `from __future__ import annotations`, async-first API, lock-дисциплина (asyncio.Lock для DB, threading.Lock для cross-thread state).
- Идемпотентные `start()` / `install()` — повторный вызов не ломает систему.
- Graceful teardown: per-step try/except в `main.py` и `recovery_manager.shutdown` не допускает утечки при сбое в одном шаге.
- `ProcessGuard` корректно работает с `SIGHUP`-отсутствием на Windows и re-entry-guard на двойной Ctrl-C.
- `AgentWatchdog` — хорошая state-machine `active → possibly_stuck → restarting`, с per-state firing flags вместо булевой каши.
- Append-only история чекпойнтов (`CheckpointManager.save`) — нет риска затереть состояние.
- `GitManager` — разделение `create_worktree`/`merge_to_main`/`rollback` с чистым логированием `reason`, устойчиво к сбоям (конфликт merge оставляет worktree для ручного разбора).
- `CommunicationServer` — защита от падения на одной коннекции (`try/except` в `_handle_connection`), best-effort UI forward без блокировки основного потока.
