use std::collections::HashMap;
use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;

use serde::Serialize;
use tauri::{AppHandle, Emitter, State};

/// Live map of step-id → child handle, so `cancel_setup_step` can kill an
/// in-flight step (e.g. the interactive `claude` REPL during OAuth) without
/// waiting for it to exit on its own.
///
/// Each handle is an `Arc<Mutex<Option<Child>>>`. The waiter thread and the
/// cancel path both try to `.take()` the Child; whichever runs first wins
/// and the other sees `None` and exits silently.
pub struct SetupProcesses(pub Mutex<HashMap<String, Arc<Mutex<Option<Child>>>>>);

impl Default for SetupProcesses {
    fn default() -> Self {
        SetupProcesses(Mutex::new(HashMap::new()))
    }
}

#[derive(Serialize, Clone)]
struct StreamLine {
    stream: String,
    line: String,
}

#[derive(Serialize, Clone)]
struct StepDone {
    step_id: String,
    ok: bool,
    exit_code: Option<i32>,
}

/// Translate a step id into a concrete shell command. Everything funnels
/// through `cmd /c` on Windows so that `npm.cmd` / `claude.cmd` wrappers are
/// resolved via `PATHEXT` — `Command::new("npm")` alone fails on Windows.
fn make_command(step_id: &str) -> Result<Command, String> {
    let (program, args): (&str, Vec<&str>) = match step_id {
        "check-node" => ("node", vec!["--version"]),
        "install-cli" => ("npm", vec!["install", "-g", "@anthropic-ai/claude-code"]),
        "verify-cli" => ("claude", vec!["--version"]),
        "trigger-oauth" => ("claude", vec![]),
        "run-doctor" => ("claude", vec!["/doctor"]),
        _ => return Err(format!("unknown step: {step_id}")),
    };
    #[cfg(windows)]
    {
        let mut c = Command::new("cmd");
        c.arg("/c").arg(program).args(&args);
        Ok(c)
    }
    #[cfg(not(windows))]
    {
        let mut c = Command::new(program);
        c.args(&args);
        Ok(c)
    }
}

/// Spawn a setup step asynchronously. Returns as soon as the child is alive;
/// the frontend listens on:
///   - `setup-stream-{step_id}`      — per-line stdout/stderr payloads
///   - `setup-step-done-{step_id}`   — final exit code
///
/// A second call for the same `step_id` kills the previous child first so a
/// user tapping "Run again" can't leak subprocesses.
#[tauri::command]
pub fn run_setup_step(
    app: AppHandle,
    state: State<'_, SetupProcesses>,
    step_id: String,
) -> Result<(), String> {
    let mut cmd = make_command(&step_id)?;
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = cmd.spawn().map_err(|e| format!("spawn failed: {e}"))?;
    let stdout = child.stdout.take().ok_or("no stdout pipe")?;
    let stderr = child.stderr.take().ok_or("no stderr pipe")?;

    let child_arc: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(Some(child)));

    // Register the handle; evict + kill any previous run of the same step.
    {
        let mut map = state.0.lock().map_err(|_| "state mutex poisoned")?;
        if let Some(prev) = map.insert(step_id.clone(), Arc::clone(&child_arc)) {
            if let Ok(mut prev_guard) = prev.lock() {
                if let Some(mut old) = prev_guard.take() {
                    let _ = old.kill();
                    let _ = old.wait();
                }
            }
        }
    }

    let event = format!("setup-stream-{step_id}");

    // stdout reader
    {
        let app = app.clone();
        let event = event.clone();
        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                let Ok(line) = line else { break };
                let _ = app.emit(
                    &event,
                    StreamLine {
                        stream: "stdout".to_string(),
                        line,
                    },
                );
            }
        });
    }
    // stderr reader
    {
        let app = app.clone();
        let event = event.clone();
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                let Ok(line) = line else { break };
                let _ = app.emit(
                    &event,
                    StreamLine {
                        stream: "stderr".to_string(),
                        line,
                    },
                );
            }
        });
    }

    // waiter — emits step-done when the child exits on its own OR after cancel.
    // If cancel_setup_step got there first the Option is already None; no
    // event is emitted (cancel is the authority for that case).
    let app_done = app.clone();
    let step_for_done = step_id.clone();
    thread::spawn(move || {
        let taken = {
            let Ok(mut guard) = child_arc.lock() else {
                return;
            };
            guard.take()
        };
        let Some(mut child) = taken else {
            return;
        };
        let exit = child.wait().ok().and_then(|s| s.code());
        let _ = app_done.emit(
            &format!("setup-step-done-{step_for_done}"),
            StepDone {
                step_id: step_for_done.clone(),
                ok: exit == Some(0),
                exit_code: exit,
            },
        );
    });

    Ok(())
}

/// Stop a running step by killing its child process. No-op if the step isn't
/// running or has already exited. Used by the UI's "Done" / "Skip" buttons
/// during OAuth, where the `claude` REPL would otherwise hang forever.
#[tauri::command]
pub fn cancel_setup_step(
    state: State<'_, SetupProcesses>,
    step_id: String,
) -> Result<(), String> {
    let map = state.0.lock().map_err(|_| "state mutex poisoned")?;
    if let Some(handle) = map.get(&step_id) {
        if let Ok(mut guard) = handle.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_step_id_errors() {
        let r = make_command("something-not-real");
        assert!(r.is_err());
        assert!(
            r.as_ref().err().unwrap().contains("unknown step"),
            "unexpected error: {:?}",
            r
        );
    }

    #[test]
    fn every_documented_step_id_resolves_to_command() {
        for id in [
            "check-node",
            "install-cli",
            "verify-cli",
            "trigger-oauth",
            "run-doctor",
        ] {
            let r = make_command(id);
            assert!(r.is_ok(), "{id} did not resolve");
        }
    }

    #[test]
    fn setup_processes_default_is_empty() {
        let sp = SetupProcesses::default();
        let guard = sp.0.lock().expect("mutex");
        assert!(guard.is_empty());
    }
}
