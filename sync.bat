@echo off
REM Fetch new patterns from your sources (Settings > Pattern sources), then update the library.
cd /d "%~dp0"
uv run awlchemy sync %*
pause
