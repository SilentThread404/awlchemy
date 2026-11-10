@echo off
REM Start Awlchemy and open it in your browser. Close this window to stop it.
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo uv is not installed. Install it with:  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  pause
  exit /b 1
)
uv run awlchemy serve %*
pause
