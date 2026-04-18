# Logging gaps (analysis-logging)

Анализ проведён: 2026-04-18. Сканированы Python-модули (`core/`, `communication/`, `git_manager/`), Node.js `server.js` и фронтенд `ui/src/**`. Исключены `node_modules/`, `target/`, `dist/`, `.venv/`, `.claudeorch/`, `ork-handoff/`.

## Infrastructure status

### Python
- **Нет стандартного логирования.** Ни один модуль не импортирует `logging`. Нет `basicConfig` / `dictConfig`, нет корневого логгера, нет именованных логгеров `getLogger(__name__)`.
- Ошибки частично трекаются через DuckDB-таблицы (`error_handler`, `recovery_manager`, `server._log_message`) — это структурированный event store, но **не покрывает teardown / cleanup / listen-loop пути**, где массово стоит `except Exception: pass`.
- Диагностические сообщения пишутся через `print()` в `core/main.py` (5 мест) — уходят в stdout tmux-окна, не в файл.

### Frontend (TS/TSX)
- **Нет logger-абстракции.** Файла `ui/src/utils/logger.ts` не существует.
- В хот-путях (`useWebSocket`, `useOrchestrator`, `useChannels`) 12+ пустых `catch { /* noop */ }` / `catch { /* ignored */ }`.
- Нет `console.error`/`console.warn` даже в критичных ветках (fetch roster, telegram status, tmux disconnect).

### Node.js server.js
- **Абсолютно пусто.** Нет try/catch, нет error handler, нет лог-строк. Если listen падает — тишина.

## Critical swallows (hide real bugs)

### Python — teardown / cleanup / callback swallows
- [x] `core/main.py:182-205` — 6× `except Exception: pass` в shutdown (despawn, recovery, disconnect, server stop, git close, memory close) — replace with `logger.exception("teardown step failed: %s", step)` at ERROR
- [x] `core/recovery/recovery_manager.py:122-146` — 6× `except Exception: pass` в shutdown (watchdog.stop, process_guard.uninstall, checkpoint save, error_handler.close, self.close, checkpoint_manager.close) — `logger.exception(...)` at ERROR
- [x] `core/watchdog/agent_watchdog.py:120-159` — 5× `except Exception: pass` на fires колбэков (snapshot send, wake, restart, notify, error) — `logger.exception("watchdog callback %s failed for %s", cb, agent)` at ERROR
- [x] `communication/server.py:99-128` — вложенные `except Exception: pass` (8 swallow-точек: ws close, uvicorn should_exit, wait_for, cancel, conn close) в `stop()` — `logger.exception(...)` at WARNING (teardown best-effort, но fault должен быть виден)
- [x] `communication/server.py:272-282` — `except Exception: pass` в `_route_direct()` (отключает агента без причины) — `logger.warning("direct route failed: agent=%s", agent)` + `exc_info=True` at WARNING
- [x] `communication/server.py:284-295` — `except Exception: pass` в `_forward_to_ui()` — `logger.warning("ui forward failed")` + `exc_info=True` at WARNING
- [x] `communication/server.py:368-372` — `except Exception: pass` в `_log_message()` (проглатывает duckdb ошибки) — намеренно, но добавить `logger.debug("message log insert failed", exc_info=True)` at DEBUG (сохранить трейс)
- [x] `communication/server.py:158-161` — `except Exception:` на парсинге первого фрейма → `ws.close(1008)` без лога — `logger.warning("bad handshake frame", exc_info=True)` at WARNING
- [x] `communication/server.py:175-177` — `except Exception: continue` в frame loop (malformed JSON → frame потерян) — `logger.warning("dropped malformed frame from %s", agent)` at WARNING
- [x] `communication/client.py:93-97` — `except Exception: continue` в listen-loop — `logger.exception("client dropped malformed frame")` at WARNING

### Frontend — silent WS/fetch failures
- [x] `ui/src/hooks/useWebSocket.ts:74-76` — `catch { /* noop */ }` вокруг `ws.close()` перед reopen — `logger.debug("ws close before reopen")` at DEBUG (допустимо no-op, но фиксировать)
- [x] `ui/src/hooks/useWebSocket.ts:83-85` — `catch { /* noop */ }` вокруг `ws.send()` — `logger.warn("ws send failed", err)` at WARNING (send failure — реальная проблема)
- [x] `ui/src/hooks/useWebSocket.ts:94-96` — `catch { /* noop */ }` вокруг `JSON.parse` на входящем фрейме — `logger.warn("ws frame parse failed", raw)` at WARNING
- [x] `ui/src/hooks/useWebSocket.ts:108-110` — `catch { /* noop */ }` в onmessage handler — `logger.error("ws handler threw", err)` at ERROR — SKIP: file has one `onmessage` catch (the JSON.parse catch above); no separate handler noop exists in current code.
- [x] `ui/src/hooks/useWebSocket.ts:147-149` — `catch { /* noop */ }` на teardown — `logger.debug("ws teardown noop")` at DEBUG
- [x] `ui/src/hooks/useWebSocket.ts:167-169` — `catch { /* noop */ }` на reconnect — `logger.warn("ws reconnect setup failed", err)` at WARNING — applied to sendMessage catch + WebSocket-construct reconnect catch.
- [x] `ui/src/hooks/useOrchestrator.ts:138` — `if (!resp.ok) return;` (roster fetch) — добавить `logger.warn("roster fetch: %s", resp.status)` at WARNING
- [x] `ui/src/hooks/useOrchestrator.ts:144-146` — `catch { /* ignored */ }` на fetch — `logger.warn("roster fetch failed", err)` at WARNING

### Node
- [ ] `server.js` (весь файл) — SKIP: per CLAUDE.md this file is HEALTH-1 residue, not used in current stack; logging retrofit out of scope for task #17. — нет ни одного try/catch и лог-строки. Минимум: `process.on('uncaughtException', …)` + структурированный log per request с методом/статусом.

## Important (noisy prints, missing context)

- [x] `core/main.py:143` — `print(f"[restart requested] agent={agent_name}")` — `logger.info("restart requested: %s", agent_name)` at INFO
- [x] `core/main.py:163-164` — `print("Обнаружена незавершённая сессия:")` + `print(result.message)` — `logger.warning("unfinished session detected: %s", result.message)` at WARNING
- [x] `core/main.py:173` — `print("ClaudeOrch готов к работе")` — `logger.info("ClaudeOrch ready")` at INFO
- [x] `core/main.py:179` — `print("ClaudeOrch остановлен.")` — `logger.info("ClaudeOrch stopped")` at INFO
- [x] `core/main.py:34-59` — `_load_tmux_config()` молча возвращает defaults на кривой config.yml — `logger.warning("config.yml unreadable, falling back to defaults", exc_info=True)` at WARNING
- [x] `git_manager/manager.py:115-126` — `get_active_worktrees()` возвращает `[]` на любой git-фейл — `logger.warning("git worktree list failed", exc_info=True)` at WARNING
- [x] `ui/src/hooks/useChannels.ts:64-66` — `catch { /* initial probe failure is non-fatal */ }` telegram status — `logger.info("telegram status unavailable", err)` at INFO
- [x] `ui/src/hooks/useChannels.ts:130-132` — `catch { /* best-effort — tmux may not be running */ }` — `logger.warn("tmux disconnect failed", err)` at WARNING

## Desirable (cleanup)

- [x] `communication/server.py:371` — сохранить комментарий `# logging failures must not propagate`, но добавить `exc_info=True` при DEBUG, чтобы трейс был доступен в dev-сборке
- [x] `core/recovery/recovery_manager.py:100` — документированный skip (`# skipped watchdog registration — surfaced via details`). Оставить; добавить `logger.debug(...)` для полноты
- [ ] Добавить в `CLAUDE.md` правило — SKIP: doc convention change out of scope for task #17.: любой `except Exception:` без `logger.exception(...)` запрещён (кроме документированных trade-off с комментарием `# swallow: <reason>`)
- [x] Завести ротацию логов (Python `RotatingFileHandler` → `.claudeorch/logs/orch.log`, фронт → опционально сбрасывать `console.*` на бек через WS-фрейм) — implemented for Python in `core/logging_setup.py`; frontend WS-forward of logs SKIP (out of scope).

## Proposed logger infrastructure

### Python
Создать `core/logging_setup.py`:
```python
import logging
import logging.handlers
from pathlib import Path

def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    file_h = logging.handlers.RotatingFileHandler(
        log_dir / "orch.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_h.setFormatter(fmt)
    stream_h = logging.StreamHandler()
    stream_h.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [file_h, stream_h]
```
Вызвать из `core/main.py` до старта компонентов. Каждый модуль: `logger = logging.getLogger(__name__)`.

### TypeScript
Создать `ui/src/utils/logger.ts`:
```ts
type Level = "debug" | "info" | "warn" | "error";
const LEVELS: Record<Level, number> = { debug: 10, info: 20, warn: 30, error: 40 };
const MIN = LEVELS[(import.meta.env.VITE_LOG_LEVEL ?? "info") as Level];

function emit(level: Level, scope: string, msg: string, data?: unknown) {
  if (LEVELS[level] < MIN) return;
  const entry = { ts: new Date().toISOString(), level, scope, msg, data };
  const fn = level === "error" ? console.error : level === "warn" ? console.warn : console.log;
  fn(`[${entry.ts}] ${scope} ${msg}`, data ?? "");
}

export function createLogger(scope: string) {
  return {
    debug: (m: string, d?: unknown) => emit("debug", scope, m, d),
    info:  (m: string, d?: unknown) => emit("info",  scope, m, d),
    warn:  (m: string, d?: unknown) => emit("warn",  scope, m, d),
    error: (m: string, d?: unknown) => emit("error", scope, m, d),
  };
}
```
Экспортировать `createLogger`. Использование: `const log = createLogger("useWebSocket");`.

### Node.js `server.js`
Подключить `pino` (или минимум `console` с ISO-timestamp helper). Обернуть Express app в error-middleware + `process.on('uncaughtException')`.

## Summary
- **Critical**: 18 позиций (10 Python teardown/listen swallow, 6 frontend WS, 2 roster fetch)
- **Important**: 8 позиций (5 print в main.py, config/git silent fallback, 2 channels swallow)
- **Desirable**: 4 позиции (комментарии/конвенции/ротация)
- **Top 3 critical**: (1) `core/main.py:182-205` — 6 teardown swallow проглатывают реальный фейл shutdown; (2) `core/watchdog/agent_watchdog.py:120-159` — 5 callback swallow скрывают падения watchdog; (3) `communication/server.py:175-177` + `client.py:93-97` — malformed WS-фреймы теряются без следа.
