@echo off
chcp 65001 >nul
rem Same as ocr-tray.bat but keeps a console so start-up errors are visible.
"%~dp0.venv\Scripts\python.exe" -m ocrtool.tray
echo Exit code: %errorlevel%
pause
