param(
    [switch]$SkipHealthCheck,
    [switch]$DeepHealthCheck,
    [switch]$DryRun,
    [switch]$NoAudio,  # Skip audio hardware checks
    [switch]$NoLLM,  # Skip LLM checks
    [switch]$Quiet,  # Reduce output verbosity
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$MainArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $ProjectRoot

function Resolve-PythonCommand {
    param([string]$Root)

    $venvPython = Join-Path $Root "venv\Scripts\python.exe"
    $candidates = @()

    if (Test-Path $venvPython) {
        $candidates += [PSCustomObject]@{ Name = "venv"; Cmd = $venvPython; Args = @() }
    }

    $candidates += [PSCustomObject]@{ Name = "python"; Cmd = "python"; Args = @() }
    $candidates += [PSCustomObject]@{ Name = "py -3"; Cmd = "py"; Args = @("-3") }

    foreach ($candidate in $candidates) {
        try {
            $probe = & $candidate.Cmd @($candidate.Args + @("-c", "import sys; print(sys.executable)")) 2>&1
            if ($LASTEXITCODE -eq 0) {
                $exePath = ($probe | Select-Object -Last 1).ToString().Trim()
                return [PSCustomObject]@{
                    Name       = $candidate.Name
                    Cmd        = $candidate.Cmd
                    Args       = $candidate.Args
                    Executable = $exePath
                }
            }
        } catch {
            continue
        }
    }

    throw "No working Python interpreter found. Tried venv\\Scripts\\python.exe, python, and py -3."
}

function Ensure-Directory {
    param(
        [string]$Path,
        [string]$Label,
        [switch]$WarnOnly
    )

    try {
        if (-not (Test-Path $Path)) {
            New-Item -ItemType Directory -Path $Path -Force | Out-Null
        }
    } catch {
        if ($WarnOnly) {
            Write-Host "Warning: could not prepare $Label at $Path ($($_.Exception.Message))" -ForegroundColor Yellow
        } else {
            throw
        }
    }
}

$pythonCommand = Resolve-PythonCommand -Root $ProjectRoot
Write-Host "Using Python ($($pythonCommand.Name)): $($pythonCommand.Executable)" -ForegroundColor Cyan

Ensure-Directory -Path (Join-Path $ProjectRoot "logs") -Label "logs"
Ensure-Directory -Path (Join-Path $ProjectRoot "data") -Label "data"
Ensure-Directory -Path (Join-Path $ProjectRoot "backups") -Label "backups" -WarnOnly

if (-not $SkipHealthCheck) {
    $healthScript = Join-Path $ProjectRoot "health_check.ps1"
    if (Test-Path $healthScript) {
        if (-not $Quiet) { Write-Host "Running health check..." -ForegroundColor Cyan }
        $healthArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $healthScript)
        if ($DeepHealthCheck) {
            $healthArgs += "-Deep"
        }
        if ($NoAudio) {
            $healthArgs += "-NoAudio"
        }
        if ($NoLLM) {
            $healthArgs += "-NoLLM"
        }
        & powershell @healthArgs
        $healthExitCode = $LASTEXITCODE
        if ($healthExitCode -ne 0) {
            Write-Host "Health check failed (exit code $healthExitCode)." -ForegroundColor Red
            Write-Host "Use .\run.ps1 -SkipHealthCheck if you need to start anyway." -ForegroundColor Yellow
            exit $healthExitCode
        }
    } else {
        if (-not $Quiet) { Write-Host "health_check.ps1 not found, continuing without preflight checks." -ForegroundColor Yellow }
    }
}

if ($DryRun) {
    Write-Host "Dry run complete. Buddy was not started." -ForegroundColor Green
    exit 0
}

$startMsg = "Starting Buddy..."
if (-not $Quiet) { 
    Write-Host $startMsg -ForegroundColor Green
    Write-Host "======================================" -ForegroundColor Magenta
}
& $pythonCommand.Cmd @($pythonCommand.Args + @((Join-Path $ProjectRoot "main.py")) + $MainArgs)
$exitCode = $LASTEXITCODE
if (-not $Quiet) {
    Write-Host "======================================" -ForegroundColor Magenta
    Write-Host "Buddy exited with code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
}
exit $exitCode

