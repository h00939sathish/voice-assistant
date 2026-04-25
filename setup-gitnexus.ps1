#!/usr/bin/env pwsh
<#
.SYNOPSIS
    GitNexus Setup Script for JARVIS Project

.DESCRIPTION
    Installs GitNexus git hooks and creates convenient aliases.

.EXAMPLE
    .\setup-gitnexus.ps1
#>

$ErrorActionPreference = "Stop"
$REPO_ROOT = git rev-parse --show-toplevel

Write-Host "======================================" -ForegroundColor Magenta
Write-Host "  GitNexus Setup for JARVIS" -ForegroundColor Magenta
Write-Host "======================================" -ForegroundColor Magenta

# 1. Install post-commit hook
Write-Host "`n[1/3] Installing post-commit hook..." -ForegroundColor Cyan
$HOOK_CONTENT = @"
#!/usr/bin/env pwsh
`$REPO_ROOT = git rev-parse --show-toplevel 2>`$null
if (-not `$REPO_ROOT) { exit 0 }

`$CURRENT_DIR = (Get-Location).Path
if (`$CURRENT_DIR -notmatch "voice-assistant" -and `$CURRENT_DIR -notmatch "new`$") {
    exit 0
}

try {
    Push-Location `$REPO_ROOT
    gitnexus analyze --quiet 2>`$null
    Pop-Location
} catch {
    exit 0
}
exit 0
"@

$HOOK_PATH = Join-Path $REPO_ROOT ".git\hooks\post-commit"
$HOOK_PATH_PS1 = Join-Path $REPO_ROOT ".git\hooks\post-commit.ps1"

# Create .ps1 hook (the actual script)
Set-Content -Path $HOOK_PATH_PS1 -Value $HOOK_CONTENT -Encoding UTF8

# Create .ps1 stub that invokes the .ps1 hook
Set-Content -Path $HOOK_PATH -Value "@echo off`npowershell -ExecutionPolicy Bypass -File `"%~dp0post-commit.ps1`"" -Encoding ASCII

Write-Host "  Hook installed: $HOOK_PATH" -ForegroundColor Green
Write-Host "  Script file: $HOOK_PATH_PS1" -ForegroundColor Green

# 2. Verify GitNexus
Write-Host "`n[2/3] Verifying GitNexus..." -ForegroundColor Cyan
try {
    $version = gitnexus --version 2>&1
    Write-Host "  GitNexus $version" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: GitNexus not found. Run: npm install -g gitnexus" -ForegroundColor Red
    exit 1
}

# 3. Verify index
Write-Host "`n[3/3] Checking index..." -ForegroundColor Cyan
Push-Location $REPO_ROOT
try {
    gitnexus status 2>&1 | ForEach-Object { Write-Host "  $_" }
} catch {
    Write-Host "  WARNING: Status check failed" -ForegroundColor Yellow
}
Pop-Location

Write-Host "`n======================================" -ForegroundColor Magenta
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Magenta

Write-Host @"

Quick Commands:
  .\briefing.ps1              - Get project briefing (recommended for new AI sessions)
  gitnexus query `"concept`"   - Find code by concept
  gitnexus context `"name`"    - Get symbol details
  gitnexus impact `"name`"     - See what breaks if changed

"@