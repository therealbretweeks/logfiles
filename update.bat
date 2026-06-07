@echo off
cd /d C:\Users\bretw\Desktop\app
echo Pulling latest code from GitHub...
set GIT_TERMINAL_PROMPT=0
set GCM_INTERACTIVE=Never
git fetch origin claude/sweet-heisenberg-3X4ca
if errorlevel 1 goto fetchfail
git reset --hard origin/claude/sweet-heisenberg-3X4ca
echo Done.
pause
goto :eof

:fetchfail
echo.
echo Fetch failed - your saved Git credentials are missing or expired.
echo Open a normal Command Prompt in this folder and run:
echo   git fetch origin claude/sweet-heisenberg-3X4ca
echo This will trigger the login popup so you can sign in and cache credentials.
echo Then re-run update.bat.
pause
