#!/usr/bin/env pwsh
<#
.SYNOPSIS
    GitNexus quick briefing script for JARVIS project.
    Shows recent changes and project status without long context.

.DESCRIPTION
    Run this at the start of a new AI session to get:
    - Recent changes since last session
    - Modified files with impact summary
    - Project status and index freshness

.EXAMPLE
    .\briefing.ps1
    .\briefing.ps1 -Days 7
    .\briefing.ps1 -Full
#>

param(
    [int]$Days = 3,
    [switch]$Full
)

$ErrorActionPreference = "Continue"
$REPO_NAME = "voice-assistant"

function Get-GitNexusStatus {
    Write-Host "`n=== GitNexus Status ===" -ForegroundColor Cyan
    gitnexus status 2>&1 | ForEach-Object {
        if ($_ -match "✅") {
            Write-Host $_ -ForegroundColor Green
        } elseif ($_ -match "❌|stale") {
            Write-Host $_ -ForegroundColor Red
        } else {
            Write-Host $_
        }
    }
}

function Get-RecentChanges {
    param([int]$LastDays)

    Write-Host "`n=== Recent Changes (Last $LastDays days) ===" -ForegroundColor Cyan

    $since = (Get-Date).AddDays(-$LastDays)
    $commits = git log --since=$since --oneline --format="%h %s" 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Host "No recent commits found" -ForegroundColor Yellow
        return
    }

    $commitList = @($commits)
    Write-Host "Found $($commitList.Count) commits:`n" -ForegroundColor Gray

    foreach ($commit in $commitList) {
        $hash = $commit.Substring(0, 7)
        $msg = $commit.Substring(8)

        Write-Host "  $($hash) - $msg" -ForegroundColor White
    }
}

function Get-ModifiedFiles {
    param([int]$LastDays)

    Write-Host "`n=== Modified Files (Uncommitted + Recent) ===" -ForegroundColor Cyan

    # Uncommitted changes
    $staged = git diff --name-only --cached 2>&1
    $unstaged = git diff --name-only 2>&1
    $untracked = git ls-files --others --exclude-standard 2>&1

    if ($staged -or $unstaged -or $untracked) {
        Write-Host "`n--- Uncommitted Changes ---" -ForegroundColor Yellow

        if ($staged) {
            Write-Host "Staged:" -ForegroundColor Gray
            $staged | ForEach-Object { Write-Host "  + $_" -ForegroundColor Green }
        }

        if ($unstaged) {
            Write-Host "Modified:" -ForegroundColor Gray
            $unstaged | ForEach-Object { Write-Host "  ~ $_" -ForegroundColor Yellow }
        }

        if ($untracked) {
            Write-Host "New files:" -ForegroundColor Gray
            $untracked | ForEach-Object { Write-Host "  ? $_" -ForegroundColor White }
        }
    } else {
        Write-Host "No uncommitted changes" -ForegroundColor Gray
    }
}

function Get-ChangeBriefing {
    param([int]$LastDays)

    Write-Host "`n=== Change Briefing ===" -ForegroundColor Cyan

    try {
        $result = gitnexus detect_changes --scope staged --repo $REPO_NAME 2>&1

        if ($LASTEXITCODE -eq 0 -and $result) {
            Write-Host $result -ForegroundColor White
        } else {
            Write-Host "Use: gitnexus detect_changes --scope staged --repo voice-assistant" -ForegroundColor Gray
            Write-Host "     gitnexus detect_changes --scope all --repo voice-assistant" -ForegroundColor Gray
        }
    } catch {
        Write-Host "Run manually: gitnexus detect_changes --scope staged --repo voice-assistant" -ForegroundColor Gray
    }
}

function Get-SymbolContext {
    Write-Host "`n=== Quick Reference ===" -ForegroundColor Cyan

    Write-Host @"

Commands for new sessions:
  gitnexus query `"concept`" --repo voice-assistant    Find code by concept
  gitnexus context `"SymbolName`" --repo voice-assistant    Full symbol details
  gitnexus impact `"FunctionName`" --repo voice-assistant    What breaks if changed
  gitnexus detect_changes --scope staged --repo voice-assistant    Uncommitted changes

"@
}

# Main execution
Clear-Host
Write-Host "======================================" -ForegroundColor Magenta
Write-Host "  JARVIS Project Briefing" -ForegroundColor Magenta
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm')" -ForegroundColor Magenta
Write-Host "======================================" -ForegroundColor Magenta

Get-GitNexusStatus
Get-RecentChanges -LastDays $Days
Get-ModifiedFiles -LastDays $Days
Get-ChangeBriefing -LastDays $Days

if ($Full) {
    Get-SymbolContext
}

Write-Host "`n======================================" -ForegroundColor Magenta
Write-Host "End of Briefing" -ForegroundColor Magenta
Write-Host "======================================" -ForegroundColor Magenta