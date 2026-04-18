@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where npm >nul 2>nul
if errorlevel 1 (
  echo [RelationGraph] Node.js / npm was not found.
  goto :fail
)

where node >nul 2>nul
if errorlevel 1 (
  echo [RelationGraph] Node.js was not found.
  goto :fail
)

call node scripts\ensure_frontend_deps.js
if errorlevel 1 (
  echo [RelationGraph] Frontend dependency bootstrap failed.
  goto :fail
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
