use std::env;
use std::fs;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;

fn agents_dir() -> Result<PathBuf, String> {
    let cwd = env::current_dir().map_err(|e| e.to_string())?;
    let mut p = cwd;
    p.push(".claude");
    p.push("agents");
    Ok(p)
}

fn is_valid_agent_name(name: &str) -> bool {
    let bytes = name.as_bytes();
    let len = bytes.len();
    if len < 2 || len > 31 {
        return false;
    }
    if !(bytes[0] >= b'a' && bytes[0] <= b'z') {
        return false;
    }
    for &b in &bytes[1..] {
        let ok = (b >= b'a' && b <= b'z') || (b >= b'0' && b <= b'9') || b == b'-';
        if !ok {
            return false;
        }
    }
    true
}

#[tauri::command]
pub async fn write_agent_file(
    name: String,
    content: String,
    _app_handle: tauri::AppHandle,
) -> Result<(), String> {
    if !is_valid_agent_name(&name) {
        return Err("invalid name: must match ^[a-z][a-z0-9-]{1,30}$".into());
    }
    let mut target = agents_dir()?;
    fs::create_dir_all(&target).map_err(|e| e.to_string())?;
    target.push(format!("{}.md", name));
    if target.exists() {
        return Err("agent file already exists".into());
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&target)
        .map_err(|e| e.to_string())?;
    file.write_all(content.as_bytes()).map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn list_agent_files() -> Result<Vec<String>, String> {
    let dir = agents_dir()?;
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let entries = fs::read_dir(&dir).map_err(|e| e.to_string())?;
    let mut out: Vec<String> = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        if path.extension().and_then(|s| s.to_str()) != Some("md") {
            continue;
        }
        let filename = match path.file_name().and_then(|s| s.to_str()) {
            Some(f) => f.to_string(),
            None => continue,
        };
        let content = fs::read_to_string(&path).map_err(|e| e.to_string())?;
        out.push(format!("{}|{}", filename, content));
    }
    out.sort();
    Ok(out)
}

#[tauri::command]
pub fn delete_agent_file(name: String) -> Result<(), String> {
    if !is_valid_agent_name(&name) {
        return Err("invalid name: must match ^[a-z][a-z0-9-]{1,30}$".into());
    }
    let mut target = agents_dir()?;
    target.push(format!("{}.md", name));
    if !target.exists() {
        return Err("agent file not found".into());
    }
    fs::remove_file(&target).map_err(|e| e.to_string())
}
