@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    exit /b 1
  )
)

echo Installing dependencies...
call .venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 (
  echo ERROR: Failed to upgrade pip.
  exit /b 1
)
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: Failed to install dependencies.
  exit /b 1
)

if not exist "data" (
  mkdir data
)

set "EXE_PATH=dist\KaraokeTicker.exe"
if exist "%EXE_PATH%" (
  del /f /q "%EXE_PATH%" >nul 2>&1
  if exist "%EXE_PATH%" (
    echo ERROR: Could not remove existing %EXE_PATH%.
    echo Close KaraokeTicker.exe and any process locking the file, then retry.
    exit /b 1
  )
)

echo Building KaraokeTicker.exe...
call .venv\Scripts\pyinstaller.exe --noconfirm --clean --onefile --windowed --name KaraokeTicker ^
  --hidden-import engineio.async_drivers.threading ^
  --hidden-import simple_websocket ^
  --add-data "web;web" ^
  --add-data "karaoke;karaoke" ^
  --add-data "data;data" ^
  main.py
if errorlevel 1 (
  echo ERROR: PyInstaller failed.
  exit /b 1
)

if not exist "%EXE_PATH%" (
  echo ERROR: Build completed but %EXE_PATH% was not produced.
  exit /b 1
)

echo Build complete: %EXE_PATH%
endlocal

