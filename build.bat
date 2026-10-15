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

rem PyInstaller's prebuilt launcher is shared by many programs, malware included, so some
rem antivirus scanners flag any exe built with it. Compile our own copy once per venv
rem (needs the Visual Studio C++ build tools).
call .venv\Scripts\python.exe check_bootloader.py
if errorlevel 1 (
  echo Compiling PyInstaller's launcher from source...
  set "PYINSTALLER_COMPILE_BOOTLOADER=1"
  call .venv\Scripts\python.exe -m pip install --force-reinstall --no-deps --no-binary pyinstaller --no-cache-dir -r requirements-build.txt
  set "PYINSTALLER_COMPILE_BOOTLOADER="
  call .venv\Scripts\python.exe check_bootloader.py
  if errorlevel 1 (
    echo ERROR: Could not compile PyInstaller's launcher. Install Visual Studio Build Tools
    echo with "Desktop development with C++", then run build.bat again.
    exit /b 1
  )
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
  --version-file version_info.txt ^
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

rem Code signing (optional): set KT_SIGN_ARGS to the signtool arguments for your certificate,
rem e.g. /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a  (KT_SIGNTOOL = signtool path).
if defined KT_SIGN_ARGS (
  if not defined KT_SIGNTOOL set "KT_SIGNTOOL=signtool.exe"
  echo Signing %EXE_PATH%...
  call "%%KT_SIGNTOOL%%" sign %KT_SIGN_ARGS% "%EXE_PATH%"
  if errorlevel 1 (
    echo ERROR: Signing failed.
    exit /b 1
  )
) else (
  echo Not signing: KT_SIGN_ARGS is not set.
)

echo Checking the stage screen inside the build...
start "" /wait "%EXE_PATH%" --self-test "%CD%\dist\selftest.json"
if errorlevel 1 (
  echo ERROR: Self-test failed. See dist\selftest.json
  exit /b 1
)

echo Build complete: %EXE_PATH%
endlocal

