@echo off
cd /d C:\Users\bretw\Desktop\app
echo Pulling latest code from GitHub...
set GIT_TERMINAL_PROMPT=0
git fetch origin claude/sweet-heisenberg-3X4ca
if errorlevel 1 goto fetchfail
git reset --hard origin/claude/sweet-heisenberg-3X4ca
echo Done.
pause
goto :eof

:fetchfail
echo.
echo Fetch failed - likely a credential issue.
echo Open a normal Command Prompt in this folder and run:
echo   git fetch origin claude/sweet-heisenberg-3X4ca
echo to trigger the login popup, then re-run update.bat.
pause
