# ClaudeOrch Windows stopper.
# PowerShell 5.1 compatible.
#
# Reads PIDs from .claudeorch\orch.pid and .claudeorch\ui.pid and stops them.
# Continues through errors so a dead-PID for the UI doesn't block orchestrator
# cleanup (and vice versa).

$ErrorActionPreference = "Continue"

Write-Host "Stopping ClaudeOrch..."

function Stop-PidFile {
    param(
        [string]$Path,
        [string]$Label
    )
    if (-not (Test-Path $Path)) {
        return
    }
    $raw = Get-Content -Path $Path -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $raw) {
        Remove-Item -Path $Path -ErrorAction SilentlyContinue
        return
    }
    $pidValue = 0
    if ([int]::TryParse($raw.Trim(), [ref]$pidValue) -and $pidValue -gt 0) {
        try {
            Stop-Process -Id $pidValue -Force -ErrorAction Stop
            Write-Host "   $Label stopped (PID: $pidValue)"
        }
        catch {
            # already-dead processes are expected here — don't treat as fatal.
            Write-Host "   $Label not running (PID $pidValue was stale)"
        }
    }
    Remove-Item -Path $Path -ErrorAction SilentlyContinue
}

Stop-PidFile -Path ".claudeorch\ui.pid" -Label "UI"
Stop-PidFile -Path ".claudeorch\orch.pid" -Label "Orchestrator"

Write-Host "ClaudeOrch stopped."
