use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

// Project root resolution uses current_dir(); this is fine when the dev server
// is launched from the repo root but not for packaged builds.
fn config_path(messenger: &str) -> Result<PathBuf, String> {
    let cwd = env::current_dir().map_err(|e| e.to_string())?;
    let mut path = cwd;
    path.push(".claudeorch");
    path.push(format!("messenger-{}.json", messenger));
    Ok(path)
}

#[tauri::command]
pub fn save_messenger_config(messenger: String, config: String) -> Result<(), String> {
    let path = config_path(&messenger)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(&path, config).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_messenger_status(messenger: String) -> Result<String, String> {
    let path = config_path(&messenger)?;
    match fs::metadata(&path) {
        Ok(meta) => {
            if meta.is_file() && meta.len() > 0 {
                Ok("connected".to_string())
            } else {
                Ok("not-connected".to_string())
            }
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            Ok("not-connected".to_string())
        }
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
pub fn run_tmux_command(command: String) -> Result<String, String> {
    let output = Command::new("tmux")
        .args([
            "send-keys",
            "-t",
            "claudeorch:0",
            command.as_str(),
            "Enter",
        ])
        .output()
        .map_err(|e| e.to_string())?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        return Err(stderr);
    }
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    Ok(stdout)
}
