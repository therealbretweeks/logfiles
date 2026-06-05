@echo off
cd /d C:\Users\bretw\Desktop\app
echo Starting server...
start "" "http://127.0.0.1:5000"
python app.py
pause
