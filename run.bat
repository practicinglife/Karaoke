@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
)

echo Installing dependencies...
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install -r requirements.txt

echo Starting Karaoke Ticker...
call .venv\Scripts\python.exe main.py

endlocal

