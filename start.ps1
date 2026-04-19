# ClaudeOrch Windows launcher.
# PowerShell 5.1 compatible (default on Windows 10/11) — no PS7-only idioms.
#
# Mirrors start.sh:
#   1. create .claudeorch/
#   2. boot Python orchestrator (logs -> .claudeorch\orch.log / orch.err)
#   3. spawn Opus claude CLI in a new console window
#   4. start the Tauri UI dev server
#
# Stop everything with stop.ps1.

$ErrorActionPreference = "Stop"

Write-Host "Starting ClaudeOrch..."

# 1. state dir
New-Item -ItemType Directory -Force -Path ".claudeorch" | Out-Null

# 2. orchestrator (Python) — hidden window, logs redirected
Write-Host "-> Starting orchestrator..."
$orch = Start-Process `
    -FilePath python `
    -ArgumentList "core\main.py" `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput ".claudeorch\orch.log" `
    -RedirectStandardError ".claudeorch\orch.err"
$orch.Id | Out-File -FilePath ".claudeorch\orch.pid" -Encoding ascii

Start-Sleep -Seconds 3

if ($orch.HasExited) {
    Write-Error "Orchestrator failed to start (exit code: $($orch.ExitCode)). See .claudeorch\orch.err"
    exit 1
}

Write-Host "   orchestrator running (PID: $($orch.Id))"

# 3. Opus claude CLI in a fresh console window so the user can watch it.
# PS 5.1 does not support Start-Process -Environment, so we set env in the
# current session before spawning and the child inherits it.
Write-Host "-> Starting Claude Code (opus)..."
$env:AGENT_NAME = "opus"
$env:CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS = "1"
$claudeArgs = "--model claude-opus-4-7 --dangerously-skip-permissions --channels plugin:telegram@claude-plugins-official"
Start-Process -FilePath "claude" -ArgumentList $claudeArgs | Out-Null
Write-Host "   Claude Code launched (new console window)"
Write-Host "   Additional agents will be spawned by Opus on demand via AgentSpawner."

# 4. UI (Tauri + Vite) in a separate console so the dev server output is visible.
Write-Host "-> Starting UI..."
Push-Location ui
try {
    $ui = Start-Process `
        -FilePath "npm" `
        -ArgumentList "run", "tauri", "dev" `
        -PassThru
    $ui.Id | Out-File -FilePath "..\.claudeorch\ui.pid" -Encoding ascii
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "ClaudeOrch is up."
Write-Host "   WebSocket: ws://localhost:8765"
Write-Host "   REST API:  http://localhost:8766/agents"
Write-Host "   Stop:      .\stop.ps1"
