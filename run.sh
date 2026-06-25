#!/usr/bin/env bash
# Lanza WireFlash. Crea el entorno virtual local la primera vez si falta.
set -e
cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "→ No hay .venv; creándolo (solo la primera vez)…"
    python3 -m venv .venv
    echo "→ Instalando dependencias (PySide6)…"
    .venv/bin/pip install --quiet --upgrade pip
    .venv/bin/pip install --quiet -r requirements.txt
    echo "✓ Entorno listo."
fi

exec "$PY" main.py "$@"
