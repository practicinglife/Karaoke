#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-1.0.0}"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

pyinstaller --noconfirm --clean --windowed --name "Karaoke Ticker" \
  --hidden-import engineio.async_drivers.threading \
  --hidden-import simple_websocket \
  --add-data "web:web" \
  --add-data "karaoke:karaoke" \
  --add-data "data:data" \
  main.py

mkdir -p dist/release
if command -v hdiutil >/dev/null 2>&1; then
  hdiutil create -volname "Karaoke Ticker" -srcfolder "dist/Karaoke Ticker.app" -ov -format UDZO "dist/release/KaraokeTicker-${VERSION}.dmg"
fi

echo "macOS build artifacts are in dist/."
