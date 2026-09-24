@echo off
cd /d "%~dp0"
echo Digital AKK is starting on http://localhost:8080
start "" http://localhost:8080/?preview
py -m http.server 8080 2>nul || python -m http.server 8080
pause
