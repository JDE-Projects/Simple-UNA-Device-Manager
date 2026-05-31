@echo off
echo =====================================================
echo  Simple UNA Device Manager - Build Script
echo =====================================================
echo.
echo Installing build + runtime dependencies...
pip install pyinstaller pywebview PyQt6 PyQt6-WebEngine
echo.
echo Building executable...
pyinstaller --onefile --windowed --name "Simple UNA Device Manager" ^
  --icon "simple_una_device_manager.ico" ^
  --splash "simple_una_device_manager-splash.png" ^
  --add-data "simple_una_device_manager-UI.html;." ^
  --add-data "simple_una_device_manager.png;." ^
  --add-data "fonts;fonts" ^
  --collect-all PyQt6 ^
  --collect-all qtpy ^
  simple_una_device_manager.py
echo.
echo =====================================================
echo  Done. Your .exe is in:  dist\Simple UNA Device Manager.exe
echo =====================================================
echo.
pause
