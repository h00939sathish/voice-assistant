param(
    [switch]$Deep
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $ProjectRoot

$results = New-Object System.Collections.Generic.List[object]
$pythonCommand = $null

function Add-Result {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Detail
    )

    $results.Add([PSCustomObject]@{
            Check  = $Name
            Status = $Status
            Detail = $Detail
        })

    switch ($Status) {
        "PASS" { Write-Host "[PASS] $Name - $Detail" -ForegroundColor Green }
        "WARN" { Write-Host "[WARN] $Name - $Detail" -ForegroundColor Yellow }
        default { Write-Host "[FAIL] $Name - $Detail" -ForegroundColor Red }
    }
}

function Invoke-Check {
    param(
        [string]$Name,
        [scriptblock]$Check,
        [switch]$WarnOnly
    )

    try {
        $detail = & $Check
        if ([string]::IsNullOrWhiteSpace([string]$detail)) {
            $detail = "OK"
        }
        Add-Result -Name $Name -Status "PASS" -Detail $detail
    } catch {
        $detail = $_.Exception.Message
        if ($WarnOnly) {
            Add-Result -Name $Name -Status "WARN" -Detail $detail
        } else {
            Add-Result -Name $Name -Status "FAIL" -Detail $detail
        }
    }
}

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

function Invoke-PythonInline {
    param(
        [string]$Code,
        [string[]]$Arguments = @()
    )

    if (-not $script:pythonCommand) {
        throw "Python interpreter is not initialized."
    }

    $hadNativeErrorPreference = Test-Path variable:PSNativeCommandUseErrorActionPreference
    if ($hadNativeErrorPreference) {
        $previousNativeErrorPreference = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }

    try {
        $output = & $script:pythonCommand.Cmd @($script:pythonCommand.Args + @("-c", $Code) + $Arguments) 2>&1
        return [PSCustomObject]@{
            ExitCode = $LASTEXITCODE
            Output   = $output
        }
    } finally {
        if ($hadNativeErrorPreference) {
            $PSNativeCommandUseErrorActionPreference = $previousNativeErrorPreference
        }
    }
}

function Invoke-PythonFile {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    if (-not $script:pythonCommand) {
        throw "Python interpreter is not initialized."
    }

    $hadNativeErrorPreference = Test-Path variable:PSNativeCommandUseErrorActionPreference
    if ($hadNativeErrorPreference) {
        $previousNativeErrorPreference = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }

    try {
        $output = & $script:pythonCommand.Cmd @($script:pythonCommand.Args + @($FilePath) + $Arguments) 2>&1
        return [PSCustomObject]@{
            ExitCode = $LASTEXITCODE
            Output   = $output
        }
    } finally {
        if ($hadNativeErrorPreference) {
            $PSNativeCommandUseErrorActionPreference = $previousNativeErrorPreference
        }
    }
}

Write-Host "Buddy health check (project: $ProjectRoot)"
Write-Host ""

Invoke-Check -Name "Virtualenv path" -WarnOnly -Check {
    $venvPath = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    if (-not (Test-Path $venvPath)) {
        throw "Missing $venvPath"
    }
    "Found"
}

Invoke-Check -Name "Python interpreter" -Check {
    $script:pythonCommand = Resolve-PythonCommand -Root $ProjectRoot
    "Using $($pythonCommand.Name): $($pythonCommand.Executable)"
}

$requiredFiles = @("main.py", "config.py", "requirements.txt")
foreach ($file in $requiredFiles) {
    Invoke-Check -Name "File $file" -Check {
        $fullPath = Join-Path $ProjectRoot $file
        if (-not (Test-Path $fullPath)) {
            throw "Not found: $file"
        }
        "Present"
    }
}

Invoke-Check -Name "File .env" -WarnOnly -Check {
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envPath)) {
        throw "Missing .env (copy .env.example and fill keys)"
    }
    "Present"
}

Invoke-Check -Name "Project root writable" -Check {
    $probePath = Join-Path $ProjectRoot ".write_probe_$PID.tmp"
    "ok" | Set-Content -Path $probePath -Encoding ASCII
    Remove-Item -Path $probePath -Force
    "Writable"
}

$requiredDirs = @("logs", "data", "backups")
foreach ($dirName in $requiredDirs) {
    Invoke-Check -Name "Directory $dirName writable" -WarnOnly -Check {
        $dirPath = Join-Path $ProjectRoot $dirName
        $created = $false
        if (-not (Test-Path $dirPath)) {
            New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
            $created = $true
        }

        $probePath = Join-Path $dirPath ".write_probe_$PID.tmp"
        "ok" | Set-Content -Path $probePath -Encoding ASCII
        Remove-Item -Path $probePath -Force

        if ($created) {
            "Created and writable"
        } else {
            "Writable"
        }
    }
}

$coreImportCode = @"
import importlib
import sys

modules = sys.argv[1:]
failed = []
for name in modules:
    try:
        importlib.import_module(name)
    except Exception as exc:
        failed.append((name, str(exc)))

if failed:
    for name, err in failed:
        print(f'{name}: {err}')
    raise SystemExit(1)

print('ok')
"@

$coreModules = @(
    "dotenv",
    "assistant.audio_manager",
    "assistant.stt",
    "assistant.tts",
    "assistant.llm_router",
    "main"
)

Invoke-Check -Name "Core imports" -Check {
    $result = Invoke-PythonInline -Code $coreImportCode -Arguments $coreModules
    if ($result.ExitCode -ne 0) {
        throw (($result.Output -join "`n").Trim())
    }
    "Imports OK"
}

$dataDir = Join-Path $ProjectRoot "data"
$dbFiles = Get-ChildItem -Path $dataDir -Filter *.db -File -ErrorAction SilentlyContinue

if (-not $dbFiles -or $dbFiles.Count -eq 0) {
    Add-Result -Name "SQLite databases" -Status "WARN" -Detail "No .db files found in data/"
} else {
    foreach ($dbFile in $dbFiles) {
        $dbName = $dbFile.Name
        Invoke-Check -Name "DB integrity $dbName" -WarnOnly -Check {
            $checkCode = "import sqlite3,sys; db=sys.argv[1]; con=sqlite3.connect(db); r=con.execute('PRAGMA integrity_check;').fetchone()[0]; con.close(); print(r); raise SystemExit(0 if r=='ok' else 1)"
            $result = Invoke-PythonInline -Code $checkCode -Arguments @($dbFile.FullName)
            if ($result.ExitCode -ne 0) {
                throw (($result.Output -join "`n").Trim())
            }
            "ok"
        }
    }
}

if ($Deep) {
    $validatePath = Join-Path $ProjectRoot "validate_keys.py"
    if (Test-Path $validatePath) {
        Invoke-Check -Name "Deep API key validation" -WarnOnly -Check {
            $result = Invoke-PythonFile -FilePath $validatePath
            if ($result.ExitCode -ne 0) {
                throw "validate_keys.py exited with code $($result.ExitCode)`n$($result.Output -join "`n")"
            }
            "validate_keys.py completed"
        }
    } else {
        Add-Result -Name "Deep API key validation" -Status "WARN" -Detail "validate_keys.py not found"
    }

    $mcpCheckPath = Join-Path $ProjectRoot "check_mcp_status.py"
    if (Test-Path $mcpCheckPath) {
        Invoke-Check -Name "Deep MCP status check" -WarnOnly -Check {
            $result = Invoke-PythonFile -FilePath $mcpCheckPath
            if ($result.ExitCode -ne 0) {
                throw "check_mcp_status.py exited with code $($result.ExitCode)`n$($result.Output -join "`n")"
            }
            "check_mcp_status.py completed"
        }
    } else {
        Add-Result -Name "Deep MCP status check" -Status "WARN" -Detail "check_mcp_status.py not found"
    }
}

$passCount = @($results | Where-Object { $_.Status -eq "PASS" }).Count
$warnCount = @($results | Where-Object { $_.Status -eq "WARN" }).Count
$failCount = @($results | Where-Object { $_.Status -eq "FAIL" }).Count

Write-Host ""
Write-Host "Summary: PASS=$passCount WARN=$warnCount FAIL=$failCount"

if ($failCount -gt 0) {
    exit 1
}

exit 0


