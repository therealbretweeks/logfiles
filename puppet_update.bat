@echo off
setlocal
cd /d C:\Users\bretw\Desktop

echo Backing up your saved database files...
if exist app\puppet_db.json copy /y app\puppet_db.json db_backup.json >nul
if exist app\puppet_alt_db.json copy /y app\puppet_alt_db.json alt_db_backup.json >nul

echo Removing old app folder...
if exist app rmdir /s /q app

echo Cloning fresh copy from GitHub...
set GIT_TERMINAL_PROMPT=0
git clone -b claude/sweet-heisenberg-3X4ca https://github.com/therealbretweeks/logfiles.git app
if errorlevel 1 goto clonefail

echo Restoring your saved database files...
if exist db_backup.json move /y db_backup.json app\puppet_db.json >nul
if exist alt_db_backup.json move /y alt_db_backup.json app\puppet_alt_db.json >nul

echo.
echo Done. Fresh copy is ready in C:\Users\bretw\Desktop\app
pause
goto :eof

:clonefail
echo.
echo Clone failed - your saved Git credentials are missing or expired.
echo Open a normal Command Prompt anywhere and run:
echo   git clone -b claude/sweet-heisenberg-3X4ca https://github.com/therealbretweeks/logfiles.git C:\Users\bretw\Desktop\app_test
echo This will trigger the login popup so you can sign in and cache credentials.
echo Then delete app_test and re-run update.bat.
pause
