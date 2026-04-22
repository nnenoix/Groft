mod agent_fs;
mod cli_detect;
mod fs_readers;
mod messenger;
mod project_root;
mod setup_runner;

use std::path::Path;

use tauri::Manager;

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
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

            // resource_dir is empty under `cargo tauri dev` — the seed below
            // is a no-op in dev and only fires on packaged launches.
            let resource_dir = match app.path().resource_dir() {
                Ok(dir) => dir,
                Err(err) => {
                    eprintln!(
                        "[groft] resource_dir unavailable ({}); skipping first-run seed",
                        err
                    );
                    return Ok(());
                }
            };

            let agents_dst = user_data_dir.join(".claude").join("agents");
            if !agents_dst.exists() {
                let src = resource_dir.join(".claude").join("agents");
                if src.is_dir() {
                    if let Err(err) = copy_dir_all(&src, &agents_dst) {
                        eprintln!(
                            "[groft] failed to seed .claude/agents from {}: {}",
                            src.display(),
                            err
                        );
                    }
                } else {
                    eprintln!(
                        "[groft] seed .claude/agents not found at {} — agents list \
                         will start empty",
                        src.display()
                    );
                }
            }

            if which::which("claude").is_err() {
                eprintln!(
                    "[groft] `claude` CLI not found on PATH; agent spawning will fail \
                     until it is installed"
                );
            }

            // Resolve project root from env or the persisted picker file and
            // seed the shared state. UI shows the picker when this is None.
            let initial_root = project_root::load_initial(&app.handle());
            app.manage(project_root::ProjectRoot(std::sync::Mutex::new(initial_root)));

            Ok(())
        })
        .manage(setup_runner::SetupProcesses::default())
        .invoke_handler(tauri::generate_handler![
            greet,
            agent_fs::write_agent_file,
            agent_fs::list_agent_files,
            agent_fs::delete_agent_file,
            cli_detect::detect_claude_cli,
            fs_readers::list_memory_files,
            fs_readers::read_memory_file,
            fs_readers::read_current_plan,
            fs_readers::read_audit_log_tail,
            fs_readers::read_architecture_file,
            fs_readers::read_health_report,
            fs_readers::read_hook_state,
            fs_readers::append_decision_entry,
            fs_readers::list_auto_memory_files,
            fs_readers::read_auto_memory_file,
            messenger::save_messenger_config,
            messenger::get_messenger_status,
            project_root::get_project_root,
            project_root::set_project_root,
            project_root::clear_project_root,
            setup_runner::run_setup_step,
            setup_runner::cancel_setup_step,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
