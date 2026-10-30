@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Window Pet Studio - One-click build
echo ============================================

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH. Please install Python 3.10+ first.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtualenv .venv ...
    python -m venv .venv || goto :err
)

echo [2/4] Installing dependencies (requirements + PyInstaller) ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller || goto :err

echo [3/4] Building exe ...
".venv\Scripts\python.exe" build_exe.py || goto :err

echo.
echo [4/4] Done!
echo       Output: dist\WindowPetStudio\WindowPetStudio.exe
pause
exit /b 0

:err
echo.
echo Build FAILED. Check the error messages above.
pause
exit /b 1
