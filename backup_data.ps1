param(
    [string]$BackupRoot = "assistant_backups",
    [switch]$ExcludeEnv,
    [int]$Keep = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $ProjectRoot

if (-not [System.IO.Path]::IsPathRooted($BackupRoot)) {
    $BackupRoot = Join-Path $ProjectRoot $BackupRoot
}

if (-not (Test-Path $BackupRoot)) {
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
}

$rootProbe = Join-Path $BackupRoot ".write_probe_$PID.tmp"
"ok" | Set-Content -Path $rootProbe -Encoding ASCII
Remove-Item -Path $rootProbe -Force

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$targetDir = Join-Path $BackupRoot "buddy-backup-$timestamp"
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

$itemsToCopy = @(
    "data",
    "requirements.txt",
    "config.py",
    "README.md"
)

if (-not $ExcludeEnv) {
    $itemsToCopy += ".env"
    $itemsToCopy += ".env.example"
}

$copied = New-Object System.Collections.Generic.List[string]
$missing = New-Object System.Collections.Generic.List[string]

foreach ($item in $itemsToCopy) {
    $sourcePath = Join-Path $ProjectRoot $item
    if (Test-Path $sourcePath) {
        Copy-Item -Path $sourcePath -Destination $targetDir -Recurse -Force
        $copied.Add($item) | Out-Null
    } else {
        $missing.Add($item) | Out-Null
    }
}

$manifestPath = Join-Path $targetDir "manifest.txt"
@(
    "timestamp=$(Get-Date -Format o)",
    "project_root=$ProjectRoot",
    "backup_root=$BackupRoot",
    "copied_items=$($copied -join ',')",
    "missing_items=$($missing -join ',')"
) | Set-Content -Path $manifestPath -Encoding ASCII

if ($Keep -gt 0) {
    $allBackups = Get-ChildItem -Path $BackupRoot -Directory |
        Where-Object { $_.Name -like "buddy-backup-*" } |
        Sort-Object CreationTime -Descending

    if ($allBackups.Count -gt $Keep) {
        $toRemove = $allBackups | Select-Object -Skip $Keep
        foreach ($oldDir in $toRemove) {
            Remove-Item -Path $oldDir.FullName -Recurse -Force
        }
    }
}

Write-Host "Backup created: $targetDir" -ForegroundColor Green
if ($missing.Count -gt 0) {
    Write-Host "Missing items: $($missing -join ', ')" -ForegroundColor Yellow
}
if ($Keep -gt 0) {
    Write-Host "Retention: keeping latest $Keep backup folders." -ForegroundColor Cyan
}
