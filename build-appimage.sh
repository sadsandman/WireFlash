#!/usr/bin/env bash
# Empaqueta WireFlash como AppImage para Linux.
# Resultado: WireFlash-x86_64.AppImage  (un solo archivo portable)
#
# Pasos: 1) PyInstaller -> dist/WireFlash   2) arma el AppDir
#        3) appimagetool -> WireFlash-x86_64.AppImage
set -e
cd "$(dirname "$0")"

ARCH="${ARCH:-x86_64}"
APPDIR="build/WireFlash.AppDir"
PY=".venv/bin/python"

# --- 1) entorno + binario con PyInstaller ---------------------------------
if [ ! -x "$PY" ]; then
    echo "→ Creando .venv…"
    python3 -m venv .venv
fi
echo "→ Instalando dependencias…"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt pyinstaller

echo "→ Construyendo binario con PyInstaller…"
rm -rf build/WireFlash.AppDir dist/WireFlash
"$PY" -m PyInstaller --noconfirm WireFlash.spec

[ -f dist/WireFlash ] || { echo "ERROR: no se generó dist/WireFlash"; exit 1; }

# --- 2) AppDir ------------------------------------------------------------
echo "→ Armando AppDir…"
mkdir -p "$APPDIR/usr/bin"
cp dist/WireFlash "$APPDIR/usr/bin/WireFlash"
chmod +x "$APPDIR/usr/bin/WireFlash"
cp packaging/WireFlash.desktop "$APPDIR/WireFlash.desktop"
cp packaging/wireflash.svg "$APPDIR/wireflash.svg"

# icono raíz (.DirIcon): PNG si hay convertidor, si no el SVG
if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w 256 -h 256 packaging/wireflash.svg -o "$APPDIR/.DirIcon"
elif command -v convert >/dev/null 2>&1; then
    convert -background none -resize 256x256 packaging/wireflash.svg "$APPDIR/.DirIcon"
else
    cp packaging/wireflash.svg "$APPDIR/.DirIcon"
fi

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/WireFlash" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# --- 3) appimagetool ------------------------------------------------------
TOOL="$(command -v appimagetool || true)"
if [ -z "$TOOL" ]; then
    TOOL="build/appimagetool-${ARCH}.AppImage"
    if [ ! -x "$TOOL" ]; then
        echo "→ Descargando appimagetool…"
        URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
        if command -v curl >/dev/null 2>&1; then
            curl -L -o "$TOOL" "$URL"
        else
            wget -O "$TOOL" "$URL"
        fi
        chmod +x "$TOOL"
    fi
fi

echo "→ Generando AppImage…"
# --appimage-extract-and-run evita necesitar FUSE en el host
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "WireFlash-${ARCH}.AppImage" \
    || ARCH="$ARCH" "$TOOL" "$APPDIR" "WireFlash-${ARCH}.AppImage"

echo
echo "✓ Listo: WireFlash-${ARCH}.AppImage"
echo "  Dale permiso de ejecución y córrelo:  chmod +x WireFlash-${ARCH}.AppImage && ./WireFlash-${ARCH}.AppImage"
