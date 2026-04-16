@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where npm >nul 2>nul
if errorlevel 1 (
  echo [RelationGraph] Node.js / npm was not found.
  goto :fail
)

if not exist "node_modules\.bin\concurrently.cmd" (
  echo [RelationGraph] Installing frontend dependencies...
  call npm.cmd install
  if errorlevel 1 (
    echo [RelationGraph] npm install failed.
    goto :fail
  )
)

echo [RelationGraph] Starting desktop dev mode...
call npm.cmd run dev
if errorlevel 1 (
  echo [RelationGraph] Startup failed.
  goto :fail
)

exit /b 0

:fail
echo.
echo Press any key to close this window.
pause >nul
exit /b 1
