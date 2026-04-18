# Full audit — session of 2026-04-18

Scope: commits `7de65ec` (task #16 WS protocol), `e5d5177` (#19 spawner/handoff),
`7b7b089` (#17 logging), `865e871` (#18 bugs & races). Cross-referenced against
`architecture/analysis-{integration,gaps,logging,bugs}.md`.

## Critical

_None._ Every item marked `[x]` in `analysis-bugs.md` Critical and
`analysis-integration.md` Critical is backed by a concrete diff that addresses
the root cause, not the symptom. Shell-injection, subprocess-in-event-loop,
uvicorn-readiness, config.yml boot crash, snapshot-agent mis-labelling —
all verified in code.

## Important

- `865e871` `communication/server.py:_unregister` — analysis-bugs entry for
  `_unregister` (line 186-188) is checked `[x]` with note "addressed via
  background-task retention". That fixes task GC but does not fix the
  original concern: `asyncio.get_running_loop()` still raises
  `RuntimeError` if `_unregister` is ever reached from a non-loop thread,
  and the except-return swallows it — the roster still goes stale. In
  practice all current call-sites run on the loop, so it's latent, but
  the checklist line overclaims. Recommended fix: capture `self._loop`
  during `start()` and schedule via `self._loop.call_soon_threadsafe` (or
  mark the item as partially-addressed).

- `e5d5177` `core/main.py:222` — `comm_client.orchestrator = orchestrator`
  monkey-patches a typed class with `# type: ignore[attr-defined]`, and
  nothing consumes it. `consume_opus_inbox` (main.py:226-236) only logs
  frames, never dispatches to `Orchestrator.spawn_role`. So the
  AgentSpawner wiring is a facade reachable only from a Python REPL —
  the analysis-gaps claim "spawn теперь живёт через Orchestrator.spawn_role"
  is true at the class level, but the runtime trigger is still missing.
  Recommended fix: either route `message`-frames with `content=="spawn
  <role>"` through `orchestrator.spawn_role`, or delete the stash line and
  mark the gap as deferred.

- `e5d5177` commit message advertises `restart_role` — not implemented.
  `Orchestrator` exposes only `spawn_role`, `despawn_role`, `active`,
  `known_roles`. Recommended fix: either add `restart_role(name)` (despawn
  + spawn + `status_for(name, "restarting")`) or correct the commit
  narrative in a follow-up.

- `7de65ec` `core/main.py:239-245` — `poll_tasks_loop` calls
  `push_tasks_to_ui` every 5 s unconditionally; each call goes through
  `_log_message("__server__", ...)` which writes a row to
  `messages.duckdb` even when nothing changed. 17k rows/day of no-op
  task-snapshots. Recommended fix: diff against last push (hash the
  parsed buckets) and skip both the WS forward and DB insert when
  identical.

- `865e871` `core/watchdog/agent_watchdog.py:register_agent` — preserving
  state on re-register fixes the restart-starvation race but introduces
  the mirror risk: after a genuine despawn/spawn the new process inherits
  the *old* `last_change_time`; if the replacement is slow to first
  output, elapsed already exceeds `_possibly_stuck_after` and the
  watchdog will fire another restart on the first tick. Recommended fix:
  expose `reset_state(name)` and call it from
  `restart_claude_code` after `spawner.spawn` returns.

- `865e871` `ui/src/store/agentStore.tsx:SET_TERMINAL` creates a phantom
  agent (`role=name`, `status="idle"`) when the snapshot arrives before
  a roster frame for that name. On the next `SET_AGENT_ROSTER` the
  phantom is dropped only if its name is absent from the roster — so if
  the roster also includes it, the phantom's minimal fields are
  preserved via `existingByName`, masking real model/role data that a
  later `UPSERT_AGENT` would otherwise seed. Recommended fix: ignore
  `SET_TERMINAL` when agent is unknown, or mark the phantom
  distinctly so later upserts overwrite.

## Desirable / polish

- `e5d5177` `core/handoff.py:75` and `core/orchestrator.py:33,36` still
  use `print(...)` — inconsistent with the `logging`-based policy
  introduced in the very next commit (`7b7b089`). Switch to
  `logging.getLogger(__name__)`.

- `7de65ec` `communication/server.py:_dispatch` snapshot branch logs with
  `msg_to=None` always. Analytics grouping by `to` for snapshots now
  returns "no recipient"; previously showed the sink agent. Harmless,
  but worth documenting in `communication/` comments.

- `865e871` `communication/mcp_server.py` — `_inbox_lock` guards
  append/copy/clear, but `_ensure_connected` races on the
  `_connected` boolean between check and set without
  `_connect_lock` covering the whole path (lock is acquired, but the
  early-return `if _connected: return` reads the flag before
  acquiring). Effectively fine because the second check inside the
  lock rehandles it — worth leaving as-is but noting.

- `865e871` `ui/src/hooks/useWebSocket.ts:171` effect deps list now
  `[url, agentName, clearReconnectTimer]`. `clearReconnectTimer` is a
  stable `useCallback([])` so this is correct, but the ESLint
  `react-hooks/exhaustive-deps` rule will complain about
  `connectRef.current()` call using stale-closure-looking state.
  Consider a brief comment inline (partly already there) and an
  `// eslint-disable-next-line` if CI enforces the rule.

- [x] `7b7b089` `ui/src/utils/logger.ts` exposes `logger.exception(err, msg, ...)`
  but no existing caller uses it. Either wire one (e.g. replace the raw
  `log.warn("ws send failed", err)` calls with `log.exception(err, "ws
  send failed")`) or drop the helper to keep the surface honest.
  — Закрыто в `2c5c61c` (P1.2): `log.exception` подключён в `useWebSocket.ts`
  (`ws send failed`, `ws teardown noop`), `useChannels.ts` (`tmux disconnect failed`)
  и `useOrchestrator.ts:167` (`roster fetch failed`). Оставшийся
  `log.warn("roster fetch non-ok", resp.status)` в `useOrchestrator.ts:158`
  остаётся намеренно: это status-code предупреждение без `Error` объекта,
  `log.exception` тут не подходит.

- `e5d5177` `core/handoff.py` only runs once at startup. If `ork-handoff/`
  arrives while the orchestrator is already up, it stays invisible until
  the next boot. Low priority — document the limitation or add a
  manually-triggered WS command later.

- `7de65ec` `ui/src/hooks/useOrchestrator.ts:119` hard-codes
  `ROSTER_HIDDEN = Set(["ui"])`. `opus` is kept per the comment, but
  no mechanism lets a user reveal `ui` for debugging. Not a bug;
  consider a `VITE_SHOW_INTERNAL_AGENTS=1` gate.

## Verified clean

- Shell-injection guard in `useChannels.ts` — allowlist regexes
  (`TELEGRAM_TOKEN_RE`, `PAIR_CODE_RE`, `DISCORD_TOKEN_RE`) restrict
  to `[A-Za-z0-9_:.-]`; no shell metacharacters can slip through.
  Validation happens before `run_tmux_command`, the one real attack
  surface.
- `core/spawner.py` — asyncio subprocess with returncode check,
  orphan window killed on `send-keys` failure, `config.yml` errors
  demoted to warnings with empty-model fallback. Matches the fix.
- `communication/server.py` uvicorn readiness — checks
  `_uvicorn_task.done()` and re-raises the task's exception before
  reporting ready. Port-conflict regression closed.
- `core/session/checkpoint.py:save` — `conn` captured inside the
  lock, raises `RuntimeError` on closed manager; the
  assert-then-use-after-yield race is gone.
- `core/guard/process_guard.py` second SIGINT forces shutdown when
  already confirming — no SIGKILL-only escape hatch.
- `core/logging_setup.py` — idempotent via `_configured` flag,
  rotating handler (1MB×3), level via `CLAUDEORCH_LOG_LEVEL`,
  called once in `main()`. Handlers are replaced, not appended,
  so re-entry in tests is safe.
- 32 silent swallows replaced with `log.exception` / `log.warning`
  across `core/main.py`, `core/recovery`, `core/watchdog`,
  `communication/server.py`, `communication/client.py`,
  `git_manager/manager.py`, and the four UI hooks.
- `AgentDrawer` / `Select` / `Toggle` / `Slider` — all now
  controlled components driven by state that resets on
  `agent?.name` change.
- `useWebSocket` exponential backoff capped at 30 s, attempt
  counter reset on successful handshake, connect stabilised via
  `connectRef`.
- `communication/mcp_server.py` — `_inbox_lock` guards the
  copy/clear window, background consume task retained in
  `_background_tasks` set.
- Snapshot relay — `CommunicationClient.snapshot(terminal, agent=)`
  + `server._dispatch` trust payload agent, watchdog passes
  captured agent name. UI per-agent terminal view is now correct.
- `push_tasks_to_ui` uses reserved `__server__` sender marker so
  analytics doesn't conjure a phantom agent.
- `SET_TERMINAL` action replaces instead of appending — duplicate
  history prefix bug fixed.
- CLAUDE.md updates in `e5d5177` are honest: decisions.md/graph.md/
  interfaces.md/current-test.md all flagged as Opus-maintained
  (no Python writer), and `scan_and_record_handoff` is described
  as inventory-only with follow-up parsing as a TODO.

## Open questions for opus

- Should `comm_client.orchestrator` stash stay? Either wire
  `consume_opus_inbox` to dispatch `spawn`/`despawn`/`restart`
  commands through it, or delete the line and the type:ignore.
- Watchdog `register_agent` now preserves state — do we want an
  explicit `reset_state` call site after spawner restart, or is
  the current "state inheritance on re-register" intentional?
- `poll_tasks_loop` running every 5 s with unconditional DB
  insert — acceptable for now, or hash-and-skip?
- `Orchestrator.restart_role` — add it, or fix the commit
  message narrative?
- `SET_TERMINAL` creating phantom agents — should it silently
  drop unknown-agent snapshots instead?
