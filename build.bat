@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
)

echo Installing dependencies...
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install -r requirements.txt

echo Building KaraokeTicker.exe...
call .venv\Scripts\pyinstaller.exe --noconfirm --clean --onefile --windowed --name KaraokeTicker ^
  --hidden-import engineio.async_drivers.threading ^
  --hidden-import simple_websocket ^
  --add-data "web;web" ^
  --add-data "karaoke;karaoke" ^
  --add-data "data;data" ^
  main.py

echo Build complete: dist\KaraokeTicker.exe
endlocal

