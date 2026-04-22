//! Project root resolution for packaged builds.
//!
//! A Tauri app bundle has no notion of "the repo". We need the user to
//! point us at one: the directory that contains `.mcp.json` + `.claude/`
//! (the two files that anchor the constitution).
//!
//! Resolution order — first hit wins:
//!   1. `CLAUDEORCH_PROJECT_ROOT` env var (dev override; not persisted)
//!   2. `<app_data_dir>/project_root.txt` (written by the picker UI)
//!   3. None — UI shows the picker
//!
//! State lives behind `Mutex<Option<PathBuf>>` in Tauri's state store; all
//! fs-reading commands pull it from there instead of calling
//! `env::current_dir()`.

use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use tauri::{AppHandle, Manager, State};

const ENV_VAR: &str = "CLAUDEORCH_PROJECT_ROOT";
const STORAGE_FILENAME: &str = "project_root.txt";

pub struct ProjectRoot(pub Mutex<Option<PathBuf>>);

impl Default for ProjectRoot {
    fn default() -> Self {
        ProjectRoot(Mutex::new(None))
    }
}

/// Does the path look like a Groft repo root? We accept anything that has
/// either `.mcp.json` or `.claude/settings.json` — both are canonical
/// anchors of the constitution. Not requiring both means users with a
/// stripped-down setup can still point us at the right place.
pub fn looks_like_project_root(path: &Path) -> bool {
    if !path.is_dir() {
        return false;
    }
    if path.join(".mcp.json").is_file() {
        return true;
    }
    if path.join(".claude").join("settings.json").is_file() {
        return true;
    }
    false
}

fn storage_path(app: &AppHandle) -> Result<PathBuf, String> {
    let base = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("app_data_dir unavailable: {}", e))?;
    fs::create_dir_all(&base).map_err(|e| e.to_string())?;
    Ok(base.join(STORAGE_FILENAME))
}

fn read_persisted(app: &AppHandle) -> Option<PathBuf> {
    let path = storage_path(app).ok()?;
    let raw = fs::read_to_string(&path).ok()?;
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return None;
    }
    Some(PathBuf::from(trimmed))
}

fn read_env() -> Option<PathBuf> {
    env::var(ENV_VAR).ok().and_then(|v| {
        let t = v.trim();
        if t.is_empty() {
            None
        } else {
            Some(PathBuf::from(t))
        }
    })
}

/// Load at app setup — env var first, then persisted file. UI still shows
/// the picker when nothing resolves.
pub fn load_initial(app: &AppHandle) -> Option<PathBuf> {
    if let Some(p) = read_env() {
        return Some(p);
    }
    read_persisted(app)
}

pub fn require(state: &State<'_, ProjectRoot>) -> Result<PathBuf, String> {
    state
        .0
        .lock()
        .map_err(|_| "project_root mutex poisoned".to_string())?
        .clone()
        .ok_or_else(|| "project_root not set".to_string())
}

#[tauri::command]
pub fn get_project_root(state: State<'_, ProjectRoot>) -> Result<Option<String>, String> {
    Ok(state
        .0
        .lock()
        .map_err(|_| "project_root mutex poisoned".to_string())?
        .as_ref()
        .map(|p| p.to_string_lossy().into_owned()))
}

#[tauri::command]
pub fn set_project_root(
    path: String,
    app: AppHandle,
    state: State<'_, ProjectRoot>,
) -> Result<(), String> {
    let candidate = PathBuf::from(path.trim());
    if !looks_like_project_root(&candidate) {
        return Err(
            "выбранная папка не похожа на Groft-репо: нужен `.mcp.json` или `.claude/settings.json`"
                .into(),
        );
    }
    let canonical = candidate.canonicalize().map_err(|e| e.to_string())?;
    let target = storage_path(&app)?;
    fs::write(&target, canonical.to_string_lossy().as_bytes()).map_err(|e| e.to_string())?;
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "project_root mutex poisoned".to_string())?;
    *guard = Some(canonical);
    Ok(())
}

#[tauri::command]
pub fn clear_project_root(
    app: AppHandle,
    state: State<'_, ProjectRoot>,
) -> Result<(), String> {
    if let Ok(target) = storage_path(&app) {
        // Ignore NotFound — clearing a never-set root is a no-op.
        let _ = fs::remove_file(&target);
    }
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "project_root mutex poisoned".to_string())?;
    *guard = None;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn looks_like_accepts_claude_settings() {
        let tmp = tempdir();
        std::fs::create_dir_all(tmp.path().join(".claude")).unwrap();
        std::fs::write(
            tmp.path().join(".claude").join("settings.json"),
            "{}",
        )
        .unwrap();
        assert!(looks_like_project_root(tmp.path()));
    }

    #[test]
    fn looks_like_accepts_mcp() {
        let tmp = tempdir();
        std::fs::write(tmp.path().join(".mcp.json"), "{}").unwrap();
        assert!(looks_like_project_root(tmp.path()));
    }

    #[test]
    fn looks_like_rejects_plain_dir() {
        let tmp = tempdir();
        assert!(!looks_like_project_root(tmp.path()));
    }

    #[test]
    fn looks_like_rejects_missing() {
        assert!(!looks_like_project_root(Path::new(
            "/absolutely/nonexistent/path/for/the/test"
        )));
    }

    fn tempdir() -> tempfile::TempDir {
        tempfile::tempdir().expect("tempdir")
    }
}
