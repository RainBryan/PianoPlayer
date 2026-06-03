@echo off
REM ────────────────────────────────────────────────────────────────
REM   Build PianoPlayer.exe
REM   Run from the PianoPlayer/ folder.
REM ────────────────────────────────────────────────────────────────

setlocal
cd /d "%~dp0\.."

echo.
echo [1/3] Installing requirements...
python -m pip install --upgrade pip >NUL
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [2/3] Cleaning previous build...
if exist build\PianoPlayer rmdir /s /q build\PianoPlayer
if exist dist\PianoPlayer.exe del /q dist\PianoPlayer.exe

echo.
echo [3/3] Building executable (this takes 1-2 minutes)...
python -m PyInstaller build\PianoPlayer.spec --clean --noconfirm
if errorlevel 1 goto :error

echo.
echo ════════════════════════════════════════════════════════════════
echo   SUCCESS  —  dist\PianoPlayer.exe
echo ════════════════════════════════════════════════════════════════
echo.
goto :eof

:error
echo.
echo ════════════════════════════════════════════════════════════════
echo   BUILD FAILED
echo ════════════════════════════════════════════════════════════════
exit /b 1
