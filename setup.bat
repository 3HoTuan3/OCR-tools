@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ==== OCR tool setup (Windows) ====

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 goto :nopython

echo [1/4] Creating virtual environment .venv ...
%PY% -m venv .venv
if errorlevel 1 goto :fail

echo [2/4] Installing Python packages ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto :fail

echo [3/4] Checking Tesseract ...
set "TESS="
where tesseract >nul 2>nul && set "TESS=1"
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=1"
if exist "%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe" set "TESS=1"
if defined TESS goto :tessdata
where winget >nul 2>nul
if errorlevel 1 goto :notess
echo Installing Tesseract with winget (a UAC prompt may appear) ...
winget install -e --id UB-Mannheim.TesseractOCR --accept-source-agreements --accept-package-agreements
goto :tessdata

:notess
echo [!] Tesseract not found and winget is unavailable.
echo     Download the installer from https://github.com/UB-Mannheim/tesseract/wiki and run setup.bat again.

:tessdata
echo [4/4] Downloading Vietnamese + English data for Tesseract ...
".venv\Scripts\python.exe" scripts\get_tessdata.py
echo.
".venv\Scripts\python.exe" -m ocrtool
echo.
echo Done. Start the tray app with:  ocr-tray.bat
echo Then: click the tray icon (inside the ^ arrow), drag to select text, press Ctrl+V.
exit /b 0

:nopython
echo [!] Python 3 not found. Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH") and run again.
exit /b 1

:fail
echo [!] Setup failed. See the messages above.
exit /b 1
