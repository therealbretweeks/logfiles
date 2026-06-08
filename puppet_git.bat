@echo off
cd /d C:\Users\bretw\Desktop\app
git fetch origin claude/sweet-heisenberg-3X4ca
git reset --hard origin/claude/sweet-heisenberg-3X4ca
echo Updated. Starting server...
start "" "http://127.0.0.1:5000"
python puppet_app.py
pause
