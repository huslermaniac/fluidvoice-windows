@echo off
REM build.bat — FluidVoice Windows
REM Packages the app into a single .exe using PyInstaller

echo === FluidVoice Windows — Build ===

REM Make sure PyInstaller is installed
pip install pyinstaller --quiet

REM Build
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "FluidVoice" ^
  --icon "assets\icon.ico" ^
  --add-data "assets;assets" ^
  --add-data "models;models" ^
  --hidden-import "customtkinter" ^
  --hidden-import "pystray" ^
  --hidden-import "PIL" ^
  --hidden-import "sounddevice" ^
  --hidden-import "faster_whisper" ^
  --hidden-import "keyboard" ^
  --hidden-import "pyperclip" ^
  --hidden-import "pyautogui" ^
  --hidden-import "httpx" ^
  --collect-all "customtkinter" ^
  --collect-all "faster_whisper" ^
  main.py

echo.
echo === Build complete! ===
echo Output: dist\FluidVoice.exe
pause
