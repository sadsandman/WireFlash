@echo off
REM Empaqueta WireFlash para Windows con PyInstaller.
REM Resultado: dist\WireFlash.exe  (un solo archivo, se puede copiar a cualquier PC)
setlocal
cd /d "%~dp0"

set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo --^> Creando entorno e instalando dependencias (si falta)...
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
)
"%PY%" -m pip install --quiet --upgrade pip
"%PY%" -m pip install --quiet -r requirements.txt pyinstaller

echo --^> Limpiando build anterior...
if exist dist\WireFlash.exe del /f /q dist\WireFlash.exe
if exist build rmdir /s /q build

echo --^> Construyendo ejecutable unico...
"%PY%" -m PyInstaller --noconfirm WireFlash.spec

echo.
if exist dist\WireFlash.exe (
    echo [OK] dist\WireFlash.exe listo para distribuir.
    echo      Copia solo ese .exe a cualquier PC con Windows; no se necesita nada mas.
    echo      Las carpetas de datos se crean junto al .exe al primer uso.
) else (
    echo [ERROR] No se encontro el ejecutable. Revisa los mensajes de PyInstaller arriba.
)
endlocal
