use std::fs;
use std::path::Path;

#[tauri::command]
pub fn write_agent_file(path: String, content: String) -> Result<(), String> {
    let p = Path::new(&path);
    if let Some(parent) = p.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(p, content).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn read_agent_files(dir: String) -> Result<Vec<String>, String> {
    let p = Path::new(&dir);
    if !p.exists() {
        return Ok(Vec::new());
    }
    let entries = fs::read_dir(p).map_err(|e| e.to_string())?;
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
pub fn delete_agent_file(path: String) -> Result<(), String> {
    fs::remove_file(Path::new(&path)).map_err(|e| e.to_string())
}
