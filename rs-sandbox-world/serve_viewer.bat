@echo off
cd /d "%~dp0"
echo Stopping any old process on port 8848...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8848" ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
timeout /t 2 /nobreak >nul
echo Starting RS viewer + cache APIs on http://127.0.0.1:8848/
echo NPCs, Objects, GFX, Sounds — from cache/ on demand.
echo (Do NOT use "python -m http.server" — Objects API will be missing.)
.venv\Scripts\python.exe -m src.cli.serve_viewer --port 8848 --cache "..\cache-runescape-live-en-b377-2006-05-02-00-00-00-openrs2#657"
pause
