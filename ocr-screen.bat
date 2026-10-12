@echo off
rem One-shot capture without the tray: drag to select a region, text goes to the clipboard.
rem Tip: make a shortcut to this file and give it a shortcut key (e.g. Ctrl+Alt+O).
start "" "%~dp0.venv\Scripts\pythonw.exe" -m ocrtool.job --toast --delay 0
