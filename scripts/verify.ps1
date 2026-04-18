param(
  [switch]$IncludeDist
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Invoke-Step {
  param(
    [string]$Title,
    [string]$FilePath,
    [string[]]$Arguments
  )

  Write-Host ""
  Write-Host "==> $Title" -ForegroundColor Cyan
  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Title failed with exit code $LASTEXITCODE"
  }
}

function Stop-RunningDesktopApp {
  param(
    [string]$ProcessName
  )

  $running = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue
  if (-not $running) {
    return
  }

  Write-Host ""
  Write-Host "==> Closing running $ProcessName processes" -ForegroundColor DarkYellow
  foreach ($proc in $running) {
    try {
      if ($proc.MainWindowHandle -ne 0) {
        $null = $proc.CloseMainWindow()
      }
    } catch {
    }
  }

  Start-Sleep -Seconds 2
  Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

Set-Location $root

Invoke-Step -Title "Ensure frontend dependencies" -FilePath "node" -Arguments @("scripts/ensure_frontend_deps.js")
Invoke-Step -Title "Python tests" -FilePath "python" -Arguments @("-m", "pytest", "-q")
Invoke-Step -Title "Frontend tests" -FilePath "npm.cmd" -Arguments @("test")
Invoke-Step -Title "Renderer build" -FilePath "npm.cmd" -Arguments @("run", "build")
Invoke-Step -Title "Electron/Node script syntax checks" -FilePath "node" -Arguments @(
  "--check", "electron/main.js"
)
Invoke-Step -Title "Electron preload syntax checks" -FilePath "node" -Arguments @(
  "--check", "electron/preload.js"
)
Invoke-Step -Title "Worker client syntax checks" -FilePath "node" -Arguments @(
  "--check", "electron/python-worker-client.js"
)
Invoke-Step -Title "Build launcher script syntax checks" -FilePath "node" -Arguments @(
  "--check", "scripts/run_build_backend.js"
)

if ($IncludeDist) {
  Stop-RunningDesktopApp -ProcessName "RelationGraph"
  Invoke-Step -Title "Desktop unpacked build" -FilePath "npm.cmd" -Arguments @("run", "dist:dir")
  Invoke-Step -Title "Desktop packaged smoke" -FilePath "powershell" -Arguments @(
    "-ExecutionPolicy", "Bypass",
    "-File", "scripts/desktop_smoke.ps1",
    "-ExecutablePath", "desktop-dist/electron/win-unpacked/RelationGraph.exe",
    "-ScreenshotPath", (Join-Path ([System.IO.Path]::GetTempPath()) "relationgraph-desktop-smoke.png")
  )
}
