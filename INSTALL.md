# Install

## Requirements
- Windows 10/11 recommended
- Python 3.11+
- Network access for guest devices on same LAN

## Quick Install
1. Open terminal in project root.
2. Run `run.bat`.

`run.bat` creates `.venv`, installs dependencies from `requirements.txt`, and launches `main.py`.

## Manual Install
```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Start
- Desktop host flow: `.venv\Scripts\python.exe main.py`
- Web server only: `.venv\Scripts\python.exe app.py`
