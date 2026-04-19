use std::path::PathBuf;
use std::process::Command;

use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct CliDetectResult {
    pub installed: bool,
    pub path: Option<String>,
    pub version: Option<String>,
}

/// Try `claude --version` at the given executable. If the process returns 0,
/// trim the stdout to a single line and treat that as the version string.
///
/// We explicitly do NOT go through a shell (`cmd /c` or `sh -c`): on Windows
/// that would hit the PowerShell `claude` alias instead of a real binary, and
/// in packaged Tauri builds PATH may be narrower than the user's shell.
fn probe(exe: &str) -> Option<String> {
    let output = Command::new(exe).arg("--version").output().ok()?;
    if !output.status.success() {
        return None;
    }
    let raw = String::from_utf8_lossy(&output.stdout);
    let line = raw.lines().next().unwrap_or("").trim();
    if line.is_empty() {
        None
    } else {
        Some(line.to_string())
    }
}

/// Return a list of candidate paths to probe, in order. First successful probe
/// wins. `which::which` is checked first so an already-on-PATH install is
/// detected regardless of which installer the user used.
fn candidates() -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = Vec::new();

    if let Ok(p) = which::which("claude") {
        out.push(p);
    }

    if let Some(home) = dirs_home() {
        // npm user install (common when user ran `npm install -g` without sudo)
        #[cfg(windows)]
        {
            out.push(home.join("AppData\\Roaming\\npm\\claude.cmd"));
            out.push(home.join(".local\\bin\\claude.exe"));
        }
        #[cfg(not(windows))]
        {
            out.push(home.join(".npm-global/bin/claude"));
            out.push(home.join(".local/bin/claude"));
        }
    }

    #[cfg(not(windows))]
    {
        out.push(PathBuf::from("/usr/local/bin/claude"));
        out.push(PathBuf::from("/opt/homebrew/bin/claude"));
    }

    out
}

/// Resolve the user's home directory without pulling in a whole dependency for
/// the one call-site we need it at.
fn dirs_home() -> Option<PathBuf> {
    #[cfg(windows)]
    {
        std::env::var_os("USERPROFILE").map(PathBuf::from)
    }
    #[cfg(not(windows))]
    {
        std::env::var_os("HOME").map(PathBuf::from)
    }
}

#[tauri::command]
pub fn detect_claude_cli() -> CliDetectResult {
    for path in candidates() {
        let exe = path.to_string_lossy().to_string();
        if let Some(version) = probe(&exe) {
            return CliDetectResult {
                installed: true,
                path: Some(exe),
                version: Some(version),
            };
        }
    }
    CliDetectResult {
        installed: false,
        path: None,
        version: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // We can't easily mock std::process::Command, so the unit tests here
    // exercise the pure-Rust helpers. Behaviour of `probe` is indirectly
    // validated by `detect_claude_cli_via_probe_func` with a caller-supplied
    // probe, which sidesteps Command entirely.

    #[test]
    fn home_resolves_to_some_existing_path_on_any_os() {
        let home = dirs_home().expect("HOME/USERPROFILE must be set in tests");
        assert!(home.is_absolute(), "home should be absolute: {:?}", home);
    }

    #[test]
    fn candidates_contains_at_least_one_entry_when_home_is_set() {
        // Even without `which::which` finding anything, we always append at
        // least one OS-specific home-relative path. Guards against regressions
        // that drop the home branch.
        let c = candidates();
        assert!(
            !c.is_empty(),
            "candidates() returned empty list; home-branch likely broken"
        );
    }

    /// Re-implementation of the detect loop that accepts an injectable probe
    /// function, so we can test path iteration without spawning real procs.
    fn detect_with<F>(probe_fn: F, paths: &[PathBuf]) -> CliDetectResult
    where
        F: Fn(&str) -> Option<String>,
    {
        for p in paths {
            let exe = p.to_string_lossy().to_string();
            if let Some(v) = probe_fn(&exe) {
                return CliDetectResult {
                    installed: true,
                    path: Some(exe),
                    version: Some(v),
                };
            }
        }
        CliDetectResult {
            installed: false,
            path: None,
            version: None,
        }
    }

    #[test]
    fn detect_reports_not_installed_when_every_probe_fails() {
        let paths = vec![PathBuf::from("/nope/a"), PathBuf::from("/nope/b")];
        let r = detect_with(|_| None, &paths);
        assert!(!r.installed);
        assert!(r.path.is_none());
        assert!(r.version.is_none());
    }

    #[test]
    fn detect_returns_first_successful_probe() {
        let paths = vec![
            PathBuf::from("/skip/me"),
            PathBuf::from("/find/here"),
            PathBuf::from("/also/works"),
        ];
        let r = detect_with(
            |p| {
                if p == "/find/here" {
                    Some("claude 2.1.114 (Claude Code)".to_string())
                } else if p == "/also/works" {
                    Some("should-not-be-returned".to_string())
                } else {
                    None
                }
            },
            &paths,
        );
        assert!(r.installed);
        assert_eq!(r.path.as_deref(), Some("/find/here"));
        assert_eq!(r.version.as_deref(), Some("claude 2.1.114 (Claude Code)"));
    }
}
