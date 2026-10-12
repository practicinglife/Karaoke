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
rem Never bundle the repo's data folder: it holds the database, backups and the stage
rem browser profile (sign-in cookies). The packaged app keeps its data in
rem %%LOCALAPPDATA%%\KaraokeTicker instead.
rem Playwright (stage screen) ships its own PyInstaller hook; --collect-data makes sure its
rem driver (node.exe + package) is bundled. It drives the installed Microsoft Edge, so no
rem browser download is needed.
call .venv\Scripts\pyinstaller.exe --noconfirm --clean --onefile --windowed --name KaraokeTicker ^
  --hidden-import engineio.async_drivers.threading ^
  --hidden-import simple_websocket ^
  --hidden-import keyboard ^
  --collect-data playwright ^
  --add-data "web;web" ^
  --add-data "karaoke;karaoke" ^
  --add-data "stage;stage" ^
  main.py
if errorlevel 1 (
  echo ERROR: PyInstaller failed.
  exit /b 1
)

if not exist "%EXE_PATH%" (
  echo ERROR: Build completed but %EXE_PATH% was not produced.
  exit /b 1
)

echo Checking the stage screen inside the build...
start "" /wait "%EXE_PATH%" --self-test "%CD%\dist\selftest.json"
if errorlevel 1 (
  echo ERROR: Self-test failed. See dist\selftest.json
  exit /b 1
)

echo Build complete: %EXE_PATH%
endlocal

