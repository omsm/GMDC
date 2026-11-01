@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo === GMDC Digitizer Decoder - Windows EXE build ===
echo.

where pyinstaller >nul 2>&1
if errorlevel 1 (
  echo Installing PyInstaller...
  python -m pip install --upgrade pip
  python -m pip install pyinstaller
  if errorlevel 1 (
    echo Failed to install PyInstaller.
    exit /b 1
  )
)

echo Installing app requirements...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install requirements.
  exit /b 1
)

echo Cleaning previous build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Building DigitizerDecoder.exe ...
python -m PyInstaller --noconfirm --clean digitizer_decoder.spec
if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

if not exist "dist\DigitizerDecoder.exe" (
  echo EXE was not created.
  exit /b 1
)

REM Seed editable config beside the EXE for first run / field edits
copy /Y "config.json" "dist\config.json" >nul
copy /Y "VERSION" "dist\VERSION" >nul

echo.
echo Build OK.
echo   EXE : %cd%\dist\DigitizerDecoder.exe
echo   Put the serial PC's config.json next to the EXE ^(copied once above^).
echo   Logs:  dist\logs\  ^(created when the app runs^)
echo.
echo Run: dist\DigitizerDecoder.exe
echo Dashboard default API mode: http://127.0.0.1:8800/
echo.
endlocal
exit /b 0
