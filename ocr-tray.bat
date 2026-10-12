@echo off
rem Start the background OCR tray app (no console window).
rem Left-click the tray icon -> drag to select a region -> text is copied to the clipboard.
start "" "%~dp0.venv\Scripts\pythonw.exe" -m ocrtool.tray
