mod agent_fs;
mod messenger;

use std::path::Path;
use std::process::Child;
use std::sync::Mutex;

use tauri::{AppHandle, Manager, WindowEvent};

/// Sync-held handle to the spawned orchestrator process.
///
/// `std::process::Child` is not `Clone` and is cheaply moved through `.kill()`,
/// so we keep it behind a `Mutex<Option<...>>` that is parked in Tauri's state
/// store via `app.manage(...)`. On CloseRequested we take the child out of the
/// mutex and dispose of it from a std thread — Tauri's main thread is not a
/// place to do blocking I/O.
struct OrchestratorChild(Mutex<Option<Child>>);

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

/// Recursively copy `src` directory into `dst`. Creates `dst` if missing.
/// Only regular files and directories are handled — symlinks mirror via copy.
fn copy_dir_all(src: &Path, dst: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let from = entry.path();
        let to = dst.join(entry.file_name());
        if file_type.is_dir() {
            copy_dir_all(&from, &to)?;
        } else {
            std::fs::copy(&from, &to)?;
        }
    }
    Ok(())
}

/// Best-effort graceful shutdown of the orchestrator sidecar.
///
/// Sequence:
///   1. POST http://localhost:8766/shutdown with a 2s connect+read timeout;
///      the Python endpoint returns 200 immediately and does the actual
///      shutdown via `asyncio.create_task`, so we don't wait on it.
///   2. Sleep 1s to give the orchestrator a window to unwind uvicorn/WS/DB.
///   3. If the child is still alive, `kill()` it. Errors are swallowed — the
///      app is closing regardless.
///   4. `app.exit(0)` dismisses the Tauri event loop on the main thread.
///
/// Runs in a detached std thread because `reqwest::blocking` must not be
/// called from Tauri's async runtime (risk of nested-runtime panic).
fn graceful_shutdown(app: AppHandle) {
    std::thread::spawn(move || {
        // Fire the graceful request; ignore the outcome — the orchestrator may
        // already be gone, or uvicorn may close the socket mid-response.
        let _ = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(2))
            .build()
            .and_then(|client| client.post("http://localhost:8766/shutdown").send());

        std::thread::sleep(std::time::Duration::from_secs(1));

        if let Some(state) = app.try_state::<OrchestratorChild>() {
            let mut guard = state.0.lock().expect("OrchestratorChild mutex poisoned");
            if let Some(mut child) = guard.take() {
                // Don't care if the process already exited on its own.
                let _ = child.kill();
                let _ = child.wait();
            }
        }

        app.exit(0);
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // On a second launch, pull focus to the existing window instead
            // of spawning another orchestrator alongside the live one.
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.set_focus();
            }
        }))
        .setup(|app| {
            // app_data_dir() resolves per-OS from the bundle identifier:
            //   Windows: %APPDATA%\com.groft.app
            //   Linux:   ~/.local/share/com.groft.app
            //   macOS:   ~/Library/Application Support/com.groft.app
            let user_data_dir = app.path().app_data_dir()?;
            std::fs::create_dir_all(&user_data_dir)?;

            // resource_dir is empty under `cargo tauri dev` because there's
            // no bundle. In that case we skip first-run seed + orchestrator
            // spawn entirely and rely on the developer running
            // `python core/main.py` in another terminal.
            let resource_dir = match app.path().resource_dir() {
                Ok(dir) => dir,
                Err(err) => {
                    eprintln!(
                        "[groft] resource_dir unavailable ({}); skipping sidecar init",
                        err
                    );
                    return Ok(());
                }
            };

            // --- First-run seed: config.yml -------------------------------
            let config_dst = user_data_dir.join("config.yml");
            if !config_dst.exists() {
                // PyInstaller onedir places bundled `datas` under `_internal/`
                // relative to the exe. In some older layouts they land right
                // next to the exe. Probe both.
                let config_candidates = [
                    resource_dir.join("orchestrator/_internal/config.yml"),
                    resource_dir.join("orchestrator/config.yml"),
                ];
                let mut seeded = false;
                for src in &config_candidates {
                    if src.is_file() {
                        if let Err(err) = std::fs::copy(src, &config_dst) {
                            eprintln!(
                                "[groft] failed to seed config.yml from {}: {}",
                                src.display(),
                                err
                            );
                        } else {
                            seeded = true;
                        }
                        break;
                    }
                }
                if !seeded {
                    eprintln!(
                        "[groft] config.yml template not found in resource bundle; \
                         orchestrator will boot with defaults"
                    );
                }
            }

            // --- First-run seed: .claude/agents ---------------------------
            let agents_dst = user_data_dir.join(".claude").join("agents");
            if !agents_dst.exists() {
                let agents_candidates = [
                    resource_dir.join("orchestrator/_internal/.claude/agents"),
                    resource_dir.join("orchestrator/.claude/agents"),
                ];
                for src in &agents_candidates {
                    if src.is_dir() {
                        if let Err(err) = copy_dir_all(src, &agents_dst) {
                            eprintln!(
                                "[groft] failed to seed .claude/agents from {}: {}",
                                src.display(),
                                err
                            );
                        }
                        break;
                    }
                }
            }

            // --- Claude CLI availability probe ----------------------------
            // TODO: surface a blocker modal when `claude` is missing from PATH.
            // PR C only logs — UX work ships in a follow-up.
            if which::which("claude").is_err() {
                eprintln!(
                    "[groft] `claude` CLI not found on PATH; agent spawning will fail \
                     until it is installed"
                );
            }

            // --- Spawn the orchestrator sidecar ---------------------------
            let exe_name = if cfg!(windows) {
                "orchestrator.exe"
            } else {
                "orchestrator"
            };
            let exe_path = resource_dir.join("orchestrator").join(exe_name);
            if exe_path.is_file() {
                match std::process::Command::new(&exe_path)
                    .env("CLAUDEORCH_USER_DATA", &user_data_dir)
                    .stdin(std::process::Stdio::null())
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .spawn()
                {
                    Ok(child) => {
                        app.manage(OrchestratorChild(Mutex::new(Some(child))));
                    }
                    Err(err) => {
                        eprintln!(
                            "[groft] failed to spawn orchestrator at {}: {}",
                            exe_path.display(),
                            err
                        );
                    }
                }
            } else {
                eprintln!(
                    "[groft] orchestrator binary not found at {} (dev mode?)",
                    exe_path.display()
                );
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // Hold the window open until graceful_shutdown has killed the
                // sidecar and called app.exit(0). Without prevent_close() the
                // Tauri runtime tears down before our detached thread fires.
                api.prevent_close();
                graceful_shutdown(window.app_handle().clone());
            }
        })
        .invoke_handler(tauri::generate_handler![
            greet,
            agent_fs::write_agent_file,
            agent_fs::read_agent_files,
            agent_fs::delete_agent_file,
            messenger::save_messenger_config,
            messenger::get_messenger_status,
            messenger::run_tmux_command,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
