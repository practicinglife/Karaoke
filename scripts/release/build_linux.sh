#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-1.0.0}"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

pyinstaller --noconfirm --clean --windowed --name "KaraokeTicker" \
  --hidden-import engineio.async_drivers.threading \
  --hidden-import simple_websocket \
  --add-data "web:web" \
  --add-data "karaoke:karaoke" \
  --add-data "data:data" \
  main.py

mkdir -p dist/release

if command -v appimagetool >/dev/null 2>&1; then
  APPDIR="dist/KaraokeTicker.AppDir"
  rm -rf "$APPDIR"
  mkdir -p "$APPDIR/usr/bin"
  cp "dist/KaraokeTicker" "$APPDIR/usr/bin/"
  cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
exec "$APPDIR/usr/bin/KaraokeTicker" "$@"
EOF
  chmod +x "$APPDIR/AppRun"
  appimagetool "$APPDIR" "dist/release/KaraokeTicker-${VERSION}.AppImage"
fi

if command -v fpm >/dev/null 2>&1; then
  mkdir -p dist/deb/usr/local/bin
  cp "dist/KaraokeTicker" dist/deb/usr/local/bin/
  fpm -s dir -t deb -n karaoke-ticker -v "$VERSION" -C dist/deb .
fi

echo "Linux build artifacts are in dist/."
