mod agent_fs;
mod messenger;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
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
