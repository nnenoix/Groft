//! Read-only views into the running project:
//!   memory/*.md, architecture/*.md, memory/current-plan.md,
//!   .claudeorch/audit.log.
//!
//! Project root resolution uses `env::current_dir()` — same as agent_fs —
//! which means these commands only work when the UI is launched from the
//! repo root (dev mode). A packaged MSI would need a configurable project
//! path; not in scope for PR-10.
//!
//! All filenames are validated to prevent path traversal: no "..", no
//! separators, must match `^[A-Za-z0-9][A-Za-z0-9._-]*\.md$`.

use std::env;
use std::fs;
use std::path::PathBuf;

const MAX_FILE_BYTES: u64 = 2 * 1024 * 1024;

fn project_root() -> Result<PathBuf, String> {
    env::current_dir().map_err(|e| e.to_string())
}

fn memory_dir() -> Result<PathBuf, String> {
    let mut p = project_root()?;
    p.push("memory");
    Ok(p)
}

fn architecture_dir() -> Result<PathBuf, String> {
    let mut p = project_root()?;
    p.push("architecture");
    Ok(p)
}

fn audit_log_path() -> Result<PathBuf, String> {
    let mut p = project_root()?;
    p.push(".claudeorch");
    p.push("audit.log");
    Ok(p)
}

/// Filename must be a plain .md file — no traversal, no separators,
/// no leading dot.
fn is_safe_md_name(name: &str) -> bool {
    if name.is_empty() || name.len() > 128 {
        return false;
    }
    if name.contains("..") || name.contains('/') || name.contains('\\') {
        return false;
    }
    if name.starts_with('.') {
        return false;
    }
    if !name.ends_with(".md") {
        return false;
    }
    name.chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '_' || c == '-')
}

fn read_md_capped(path: &PathBuf) -> Result<String, String> {
    let meta = fs::metadata(path).map_err(|e| e.to_string())?;
    if meta.len() > MAX_FILE_BYTES {
        return Err(format!(
            "file too large ({} bytes > {} cap)",
            meta.len(),
            MAX_FILE_BYTES
        ));
    }
    fs::read_to_string(path).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn list_memory_files() -> Result<Vec<String>, String> {
    let dir = memory_dir()?;
    if !dir.is_dir() {
        return Ok(Vec::new());
    }
    let mut out: Vec<String> = Vec::new();
    for entry in fs::read_dir(&dir).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        if path.extension().and_then(|s| s.to_str()) != Some("md") {
            continue;
        }
        if let Some(name) = path.file_name().and_then(|s| s.to_str()) {
            if is_safe_md_name(name) {
                out.push(name.to_string());
            }
        }
    }
    out.sort();
    Ok(out)
}

#[tauri::command]
pub fn read_memory_file(name: String) -> Result<String, String> {
    if !is_safe_md_name(&name) {
        return Err("invalid filename".into());
    }
    let mut path = memory_dir()?;
    path.push(&name);
    if !path.is_file() {
        return Err("file not found".into());
    }
    read_md_capped(&path)
}

#[tauri::command]
pub fn read_current_plan() -> Result<Option<String>, String> {
    let mut path = memory_dir()?;
    path.push("current-plan.md");
    if !path.is_file() {
        return Ok(None);
    }
    read_md_capped(&path).map(Some)
}

#[tauri::command]
pub fn read_audit_log_tail(max_lines: usize) -> Result<String, String> {
    let path = audit_log_path()?;
    if !path.is_file() {
        return Ok(String::new());
    }
    let content = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let lines: Vec<&str> = content.lines().collect();
    let cap = max_lines.max(1).min(2000);
    let start = if lines.len() > cap { lines.len() - cap } else { 0 };
    Ok(lines[start..].join("\n"))
}

#[tauri::command]
pub fn read_architecture_file(name: String) -> Result<String, String> {
    if !is_safe_md_name(&name) {
        return Err("invalid filename".into());
    }
    let mut path = architecture_dir()?;
    path.push(&name);
    if !path.is_file() {
        return Err("file not found".into());
    }
    read_md_capped(&path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_name_accepts_plain_md() {
        assert!(is_safe_md_name("shared.md"));
        assert!(is_safe_md_name("current-plan.md"));
        assert!(is_safe_md_name("MEMORY.md"));
    }

    #[test]
    fn safe_name_rejects_traversal() {
        assert!(!is_safe_md_name("../../etc/passwd"));
        assert!(!is_safe_md_name("..md"));
        assert!(!is_safe_md_name("foo/bar.md"));
        assert!(!is_safe_md_name("foo\\bar.md"));
    }

    #[test]
    fn safe_name_rejects_non_md() {
        assert!(!is_safe_md_name("passwd"));
        assert!(!is_safe_md_name("file.txt"));
        assert!(!is_safe_md_name(""));
    }

    #[test]
    fn safe_name_rejects_dotfile() {
        assert!(!is_safe_md_name(".hidden.md"));
    }
}
