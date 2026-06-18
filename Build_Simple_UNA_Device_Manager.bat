@echo off
echo =====================================================
echo  Simple UNA Device Manager - Build Script
echo =====================================================
echo.

cd /d "%~dp0"

REM --- skip interactive pauses when running in CI (GitHub Actions sets CI) ---
set "PAUSE=pause"
if defined CI set "PAUSE="

REM Use the LGPL Qt binding (PySide6), never PyQt6 (GPL).
set QT_API=pyside6

REM --- check Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Install Python 3 from https://python.org and tick "Add Python to PATH".
    %PAUSE%
    exit /b 1
)

echo Removing PyQt6 if present (keeps PySide6 as the bundled binding)...
pip uninstall -y PyQt6 PyQt6-Qt6 PyQt6-WebEngine PyQt6-WebEngine-Qt6 >nul 2>&1
echo.
echo Installing pinned dependencies from requirements.txt ...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies from requirements.txt.
    %PAUSE%
    exit /b 1
)
echo.
echo Building executable (onedir, closed / noncommercial build)...
pyinstaller --windowed --onedir --name "Simple UNA Device Manager" ^
  --icon "simple_una_device_manager.ico" ^
  --splash "simple_una_device_manager-splash.png" ^
  --add-data "simple_una_device_manager-UI.html;." ^
  --add-data "simple_una_device_manager.png;." ^
  --add-data "fonts;fonts" ^
  --collect-all PySide6 ^
  --collect-all qtpy ^
  simple_una_device_manager.py
echo.
echo =====================================================
echo  Done. Your app folder is in:
echo    dist\Simple UNA Device Manager\
echo  Run: dist\Simple UNA Device Manager\Simple UNA Device Manager.exe
echo =====================================================
echo.
%PAUSE%
