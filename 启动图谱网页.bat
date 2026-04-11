@echo off
cd /d "%~dp0"
python -m knowledge_graph.run_web
if errorlevel 1 (
  echo.
  echo Startup failed. Check the error above.
  pause
)
