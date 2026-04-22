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
use std::io::ErrorKind;
use std::path::PathBuf;

const MAX_FILE_BYTES: u64 = 2 * 1024 * 1024;

fn project_root() -> Result<PathBuf, String> {
    env::current_dir().map_err(|e| e.to_string())
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
    let mut dir = project_root()?;
    dir.push("memory");
    let entries = match fs::read_dir(&dir) {
        Ok(e) => e,
        Err(err) if err.kind() == ErrorKind::NotFound => return Ok(Vec::new()),
        Err(err) => return Err(err.to_string()),
    };
    let mut out: Vec<String> = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if path.extension().and_then(|s| s.to_str()) != Some("md") {
            continue;
        }
        if let Some(name) = path.file_name().and_then(|s| s.to_str()) {
            if is_safe_md_name(name) && path.is_file() {
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
    let mut path = project_root()?;
    path.push("memory");
    path.push(&name);
    read_md_capped(&path)
}

#[tauri::command]
pub fn read_current_plan() -> Result<Option<String>, String> {
    let mut path = project_root()?;
    path.push("memory");
    path.push("current-plan.md");
    match read_md_capped(&path) {
        Ok(s) => Ok(Some(s)),
        Err(_) if !path.exists() => Ok(None),
        Err(e) => Err(e),
    }
}

#[tauri::command]
pub fn read_audit_log_tail(max_lines: usize) -> Result<String, String> {
    let mut path = project_root()?;
    path.push(".claudeorch");
    path.push("audit.log");
    let content = match fs::read_to_string(&path) {
        Ok(s) => s,
        Err(err) if err.kind() == ErrorKind::NotFound => return Ok(String::new()),
        Err(err) => return Err(err.to_string()),
    };
    let cap = max_lines.max(1).min(2000);
    // Counting '\n' from the end and slicing avoids the intermediate
    // Vec<&str> that .lines().collect() would build on every poll.
    let bytes = content.as_bytes();
    let mut newlines = 0usize;
    let mut start = 0usize;
    for (i, b) in bytes.iter().enumerate().rev() {
        if *b == b'\n' {
            newlines += 1;
            if newlines > cap {
                start = i + 1;
                break;
            }
        }
    }
    Ok(content[start..].trim_end_matches('\n').to_string())
}

#[tauri::command]
pub fn read_architecture_file(name: String) -> Result<String, String> {
    if !is_safe_md_name(&name) {
        return Err("invalid filename".into());
    }
    let mut path = project_root()?;
    path.push("architecture");
    path.push(&name);
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
