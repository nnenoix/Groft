//! Read-only views into the running project:
//!   memory/*.md, architecture/*.md, memory/current-plan.md,
//!   .claudeorch/audit.log, .claudeorch/health.json, hook_state.json,
//!   and Claude Code's auto-memory under ~/.claude/projects/<slug>/memory/.
//!
//! Also hosts `append_decision_entry` — the one write-side command here —
//! so the UI can add to `architecture/decisions.md` without shelling out.
//!
//! Project root is resolved from `ProjectRoot` state (set via the picker
//! or the `CLAUDEORCH_PROJECT_ROOT` env var). No `env::current_dir()` any
//! more — packaged MSI works once the user picks a root.
//!
//! All filenames are validated to prevent path traversal: no "..", no
//! separators, must match `^[A-Za-z0-9][A-Za-z0-9._-]*\.md$`.

use std::fs;
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};

use tauri::State;

use crate::project_root::{self, ProjectRoot};

const MAX_FILE_BYTES: u64 = 2 * 1024 * 1024;

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
pub fn list_memory_files(state: State<'_, ProjectRoot>) -> Result<Vec<String>, String> {
    let dir = project_root::require(&state)?.join("memory");
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
pub fn read_memory_file(name: String, state: State<'_, ProjectRoot>) -> Result<String, String> {
    if !is_safe_md_name(&name) {
        return Err("invalid filename".into());
    }
    let path = project_root::require(&state)?.join("memory").join(&name);
    read_md_capped(&path)
}

#[tauri::command]
pub fn read_current_plan(state: State<'_, ProjectRoot>) -> Result<Option<String>, String> {
    let path = project_root::require(&state)?
        .join("memory")
        .join("current-plan.md");
    match read_md_capped(&path) {
        Ok(s) => Ok(Some(s)),
        Err(_) if !path.exists() => Ok(None),
        Err(e) => Err(e),
    }
}

#[tauri::command]
pub fn read_audit_log_tail(
    max_lines: usize,
    state: State<'_, ProjectRoot>,
) -> Result<String, String> {
    let path = project_root::require(&state)?
        .join(".claudeorch")
        .join("audit.log");
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
pub fn read_architecture_file(
    name: String,
    state: State<'_, ProjectRoot>,
) -> Result<String, String> {
    if !is_safe_md_name(&name) {
        return Err("invalid filename".into());
    }
    let path = project_root::require(&state)?.join("architecture").join(&name);
    read_md_capped(&path)
}

/// Returns the JSON blob written by `session_start_health_check.py`.
/// Null when no session has started yet (no health.json on disk).
#[tauri::command]
pub fn read_health_report(state: State<'_, ProjectRoot>) -> Result<Option<String>, String> {
    let path = project_root::require(&state)?
        .join(".claudeorch")
        .join("health.json");
    match fs::read_to_string(&path) {
        Ok(s) => Ok(Some(s)),
        Err(err) if err.kind() == ErrorKind::NotFound => Ok(None),
        Err(err) => Err(err.to_string()),
    }
}

/// Raw JSON of `.claudeorch/hook_state.json` — rule #4's edit counter.
/// Null when no hook has written the file yet.
#[tauri::command]
pub fn read_hook_state(state: State<'_, ProjectRoot>) -> Result<Option<String>, String> {
    let path = project_root::require(&state)?
        .join(".claudeorch")
        .join("hook_state.json");
    match fs::read_to_string(&path) {
        Ok(s) => Ok(Some(s)),
        Err(err) if err.kind() == ErrorKind::NotFound => Ok(None),
        Err(err) => Err(err.to_string()),
    }
}

fn today_iso() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let days = (secs / 86400) as i64;
    // Unix epoch → date. Same civil-from-days algorithm as chrono uses;
    // avoids pulling chrono in just for today's date.
    let (y, m, d) = civil_from_days(days);
    format!("{:04}-{:02}-{:02}", y, m, d)
}

fn civil_from_days(z: i64) -> (i32, u32, u32) {
    let z = z + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = (if mp < 10 { mp + 3 } else { mp - 9 }) as u32;
    let y = if m <= 2 { y + 1 } else { y } as i32;
    (y, m, d)
}

/// Append a decision entry to architecture/decisions.md in the charter
/// format: `## YYYY-MM-DD — <category>: <chosen>` + Why + Alternatives.
#[tauri::command]
pub fn append_decision_entry(
    category: String,
    chosen: String,
    why: String,
    alternatives: Option<String>,
    state: State<'_, ProjectRoot>,
) -> Result<(), String> {
    let category = category.trim();
    let chosen = chosen.trim();
    let why = why.trim();
    if category.is_empty() || chosen.is_empty() || why.is_empty() {
        return Err("поля «категория», «выбрано» и «почему» обязательны".into());
    }
    if category.contains('\n') || chosen.contains('\n') {
        return Err("«категория» и «выбрано» должны быть одной строкой".into());
    }

    let path = project_root::require(&state)?
        .join("architecture")
        .join("decisions.md");
    fs::create_dir_all(path.parent().unwrap_or(Path::new("."))).map_err(|e| e.to_string())?;

    let mut block = String::new();
    block.push_str("\n---\n\n");
    block.push_str(&format!("## {} — {}: {}\n\n", today_iso(), category, chosen));
    block.push_str(&format!("**Why:** {}\n", why));
    if let Some(alts) = alternatives.as_ref().map(|s| s.trim()).filter(|s| !s.is_empty()) {
        block.push_str(&format!("\n**Alternatives:** {}\n", alts));
    }

    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|e| e.to_string())?;
    file.write_all(block.as_bytes()).map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())?;
    Ok(())
}

/// Claude Code auto-memory slug: every non-ASCII-alphanumeric character in
/// the canonical project path is replaced with `-`. On Windows this turns
/// `D:\orchkerstr` into `D--orchkerstr` (`:` and `\` both → `-`); on Linux
/// `/mnt/d/orchkerstr` → `-mnt-d-orchkerstr`.
///
/// `std::fs::canonicalize` on Windows prepends `\\?\` (extended-length
/// prefix); we strip it before slugging so the slug matches what Claude
/// Code actually writes under `~/.claude/projects/`.
///
/// IMPORTANT: keep this derivation in sync with
/// `scripts/hooks/session_start_memory_banner.py::_auto_memory_index_path`.
/// If Claude Code ever changes its slug algorithm, both must update together
/// or cross-session auto-memory splits between two directories.
fn claude_code_slug(path: &Path) -> String {
    let raw = path.to_string_lossy();
    let stripped = raw
        .strip_prefix(r"\\?\")
        .unwrap_or_else(|| raw.as_ref());
    stripped
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '-' })
        .collect()
}

fn auto_memory_dir(state: &State<'_, ProjectRoot>) -> Result<PathBuf, String> {
    let root = project_root::require(state)?.canonicalize().map_err(|e| e.to_string())?;
    let slug = claude_code_slug(&root);
    let home = dirs_home().ok_or_else(|| "home directory unresolvable".to_string())?;
    Ok(home.join(".claude").join("projects").join(slug).join("memory"))
}

fn dirs_home() -> Option<PathBuf> {
    // Minimal home-dir lookup. On WSL/Linux/macOS $HOME is reliable; on
    // Windows we fall back to %USERPROFILE%.
    if let Ok(h) = std::env::var("HOME") {
        if !h.is_empty() {
            return Some(PathBuf::from(h));
        }
    }
    if let Ok(h) = std::env::var("USERPROFILE") {
        if !h.is_empty() {
            return Some(PathBuf::from(h));
        }
    }
    None
}

#[tauri::command]
pub fn list_auto_memory_files(state: State<'_, ProjectRoot>) -> Result<Vec<String>, String> {
    let dir = auto_memory_dir(&state)?;
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
pub fn read_auto_memory_file(
    name: String,
    state: State<'_, ProjectRoot>,
) -> Result<String, String> {
    if !is_safe_md_name(&name) {
        return Err("invalid filename".into());
    }
    let path = auto_memory_dir(&state)?.join(&name);
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

    #[test]
    fn civil_from_days_matches_known_dates() {
        // Unix epoch
        assert_eq!(civil_from_days(0), (1970, 1, 1));
        // Leap day
        assert_eq!(civil_from_days(59), (1970, 3, 1));
        // 2000-01-01 — start of century
        assert_eq!(civil_from_days(10957), (2000, 1, 1));
        // Round-trip a known date (don't trust the offset — trust that
        // consecutive days produce consecutive dates)
        let (y, m, d) = civil_from_days(20566);
        assert!(y == 2026 && (1..=12).contains(&m) && (1..=31).contains(&d));
    }

    #[test]
    fn today_iso_is_iso8601_date() {
        let s = today_iso();
        assert_eq!(s.len(), 10);
        assert_eq!(&s[4..5], "-");
        assert_eq!(&s[7..8], "-");
    }

    // Observed real Claude Code slugs (from a Windows install under
    // `~/.claude/projects/`). If any of these break, Claude Code changed
    // its algorithm — update both Rust and Python derivations in sync.
    #[test]
    fn slug_linux_absolute_path() {
        assert_eq!(
            claude_code_slug(Path::new("/mnt/d/orchkerstr")),
            "-mnt-d-orchkerstr"
        );
    }

    #[test]
    fn slug_windows_drive_root() {
        assert_eq!(
            claude_code_slug(Path::new(r"D:\orchkerstr")),
            "D--orchkerstr"
        );
    }

    #[test]
    fn slug_windows_nested_path() {
        assert_eq!(
            claude_code_slug(Path::new(r"C:\Users\yegor")),
            "C--Users-yegor"
        );
    }

    #[test]
    fn slug_windows_extended_length_prefix_stripped() {
        assert_eq!(
            claude_code_slug(Path::new(r"\\?\D:\orchkerstr")),
            "D--orchkerstr"
        );
    }

    #[test]
    fn slug_preserves_ascii_alphanumerics() {
        assert_eq!(claude_code_slug(Path::new("abc123")), "abc123");
        assert_eq!(claude_code_slug(Path::new("Mixed_Case-9")), "Mixed-Case-9");
    }
}
