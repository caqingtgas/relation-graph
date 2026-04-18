param(
  [Parameter(Mandatory = $true)]
  [string]$ExecutablePath,
  [string]$ScreenshotPath = (Join-Path ([System.IO.Path]::GetTempPath()) "relationgraph-desktop-smoke.png"),
  [int]$LaunchTimeoutSeconds = 20,
  [int]$VisibleDelayMilliseconds = 1200
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $ExecutablePath)) {
  throw "Desktop executable not found: $ExecutablePath"
}

Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class DesktopSmokeWindow {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
'@

$resolvedExecutable = (Resolve-Path $ExecutablePath).Path
$processName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedExecutable)
$launchMark = Get-Date

Start-Process -FilePath $resolvedExecutable | Out-Null

try {
  $deadline = (Get-Date).AddSeconds($LaunchTimeoutSeconds)
  $windowProc = $null
  while ((Get-Date) -lt $deadline) {
    $windowProc = Get-Process -Name $processName -ErrorAction SilentlyContinue |
      Where-Object { $_.MainWindowHandle -ne 0 } |
      Sort-Object StartTime -Descending |
      Select-Object -First 1
    if ($windowProc) {
      break
    }
    Start-Sleep -Milliseconds 500
  }

  if (-not $windowProc) {
    throw "Desktop smoke failed: no visible window for $processName within $LaunchTimeoutSeconds seconds."
  }

  [DesktopSmokeWindow]::ShowWindow($windowProc.MainWindowHandle, 3) | Out-Null
  [DesktopSmokeWindow]::SetForegroundWindow($windowProc.MainWindowHandle) | Out-Null
  Start-Sleep -Milliseconds $VisibleDelayMilliseconds

  $rect = New-Object DesktopSmokeWindow+RECT
  [DesktopSmokeWindow]::GetWindowRect($windowProc.MainWindowHandle, [ref]$rect) | Out-Null
  $width = [Math]::Max(1, $rect.Right - $rect.Left)
  $height = [Math]::Max(1, $rect.Bottom - $rect.Top)

  $bitmap = New-Object System.Drawing.Bitmap($width, $height)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, (New-Object System.Drawing.Size($width, $height)))
  $graphics.Dispose()

  $targetDir = Split-Path -Parent $ScreenshotPath
  if ($targetDir) {
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
  }

  $bitmap.Save($ScreenshotPath, [System.Drawing.Imaging.ImageFormat]::Png)
  $bitmap.Dispose()

  Write-Host "Desktop smoke window title: $($windowProc.MainWindowTitle)"
  Write-Host "Desktop smoke screenshot: $ScreenshotPath"
}
finally {
  $launched = Get-Process -Name $processName -ErrorAction SilentlyContinue |
    Where-Object { $_.StartTime -ge $launchMark.AddSeconds(-2) }

  foreach ($proc in $launched) {
    try {
      if ($proc.MainWindowHandle -ne 0) {
        $null = $proc.CloseMainWindow()
      }
    } catch {
    }
  }

  Start-Sleep -Seconds 2

  $launched = Get-Process -Name $processName -ErrorAction SilentlyContinue |
    Where-Object { $_.StartTime -ge $launchMark.AddSeconds(-2) }
  foreach ($proc in $launched) {
    try {
      Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    } catch {
    }
  }
}
