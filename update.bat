@echo off
cd /d C:\Users\bretw\Desktop\app
echo Pulling latest code from GitHub...
set GIT_TERMINAL_PROMPT=0
git fetch origin claude/sweet-heisenberg-3X4ca -v
if errorlevel 1 (
    echo.
    echo Fetch failed - likely a credential issue. Run this manually once in a normal terminal:
    echo   git fetch origin claude/sweet-heisenberg-3X4ca
    echo to trigger the login popup and cache your credentials, then re-run update.bat.
    pause
    exit /b 1
)
git reset --hard origin/claude/sweet-heisenberg-3X4ca
echo Done.
pause
