@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "OCR_ROOT=%ROOT%"
set "YES=0"
if /i "%~1"=="/y" set "YES=1"

echo ==== OCR tool uninstall (Windows) ====
echo Project folder: %ROOT%
if "%YES%"=="0" (
  choice /c YN /m "Continue uninstalling"
  if errorlevel 2 goto :cancel
)

echo [1/6] Stopping the tray app and any capture in progress ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($env:OCR_ROOT + '\.venv', [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
timeout /t 1 /nobreak >nul

echo [2/6] Removing "start with Windows" entry ...
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\OCR Tool.lnk" >nul 2>nul
del "%USERPROFILE%\Desktop\OCR Tool.lnk" >nul 2>nul
if defined OneDrive del "%OneDrive%\Desktop\OCR Tool.lnk" >nul 2>nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v ocrtool /f >nul 2>nul
if errorlevel 1 (echo   not set) else (echo   removed)

echo [3/6] Removing Python environment and language data from the project folder ...
if exist "%ROOT%\.venv" rd /s /q "%ROOT%\.venv" & echo   removed .venv
if exist "%ROOT%\tessdata" rd /s /q "%ROOT%\tessdata" & echo   removed tessdata
if exist "%ROOT%\src\ocrtool.egg-info" rd /s /q "%ROOT%\src\ocrtool.egg-info" & echo   removed egg-info
for /d /r "%ROOT%" %%D in (__pycache__) do if exist "%%D" rd /s /q "%%D"
if exist "%ROOT%\.venv" echo   [!] .venv could not be fully removed (a file is in use?). Close other programs and run again.

echo [4/6] User data (settings, history of images + text, log) ...
set "DATA=%LOCALAPPDATA%\ocrtool"
if not exist "%DATA%" (echo   none & goto :tess)
if "%YES%"=="0" (
  choice /c YN /m "Delete %DATA%"
  if errorlevel 2 (echo   kept & goto :tess)
)
rd /s /q "%DATA%" & echo   removed %DATA%

:tess
echo [5/6] Tesseract (installed by setup.bat through winget) ...
if "%YES%"=="1" (echo   skipped, other programs may use it & goto :folder)
where winget >nul 2>nul
if errorlevel 1 (echo   winget not found; remove "Tesseract-OCR" from Settings ^> Apps if you want it gone & goto :folder)
choice /c YN /d N /t 15 /m "Also uninstall Tesseract (default N after 15s)"
if errorlevel 2 (echo   kept & goto :folder)
winget uninstall -e --id UB-Mannheim.TesseractOCR

:folder
echo [6/6] Project folder ...
if "%YES%"=="1" (echo   kept & goto :done)
choice /c YN /d N /t 15 /m "Delete the whole folder %ROOT% (including source code) (default N after 15s)"
if errorlevel 2 (echo   kept & goto :done)
cd /d "%TEMP%"
echo   The folder will be deleted in a moment.
start "" /min cmd /c "timeout /t 2 /nobreak >nul & rd /s /q "%ROOT%""

:done
echo.
echo Done. OCR tool has been uninstalled.
if "%YES%"=="0" pause
exit /b 0

:cancel
echo Cancelled.
exit /b 0
