# WireFlash

Editor local y **100% offline** de **arneses de cableado** (wiring harness):
lienzo gráfico, librerías de conectores/cables/terminales, netlist, reportes
(BOM y tabla de corte) y exportación a **PDF** con plantilla de hoja y cajetín.
Construido con Python + PySide6 (Qt).

## Funcionalidades

- **Editor gráfico** drag-and-drop: conectores y cables (estilo WireViz, el cable
  es un componente de paso), zoom/paneo, snap a rejilla.
- **Librerías estilo KiCad**: cada subcarpeta de `librerias/` es una librería
  compartible (conectores, cables, **terminales**). Edición con sincronización en
  vivo hacia las instancias colocadas.
- **Terminales** por conector y por pin (elegidos de la librería); marca visual en
  el lienzo del pin con terminal asignado.
- **Proyectos con varios ensamblajes**: un proyecto agrupa varios cables armados;
  **librería de ensamblajes** reutilizables entre proyectos.
- **Reportes en vivo**: BOM, tabla de corte y netlist; exportables a CSV.
- **Exportar PDF** (BOM + diagrama) por proyecto o por ensamblaje, en A4/A3/A2/A1
  vertical u horizontal, con **plantilla de hoja** (marco + cajetín) genérica o
  importada desde **SVG**.
- **Temas** claro/oscuro y más.

## Ejecutar (desarrollo)

```bash
./run.sh            # crea .venv e instala PySide6 la primera vez
# o manualmente:
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

## Empaquetar

### Windows (.exe)

```bat
build.bat
```
Genera `dist\WireFlash.exe`: **un solo archivo** portable. Cópialo a cualquier PC
con Windows; las carpetas de datos se crean junto al `.exe` al primer uso.

### Linux (AppImage)

```bash
./build-appimage.sh
```
Genera `WireFlash-x86_64.AppImage`: un solo archivo portable. Requiere conexión la
primera vez (descarga `appimagetool`). Como el AppImage se monta en solo lectura,
las librerías/proyectos del usuario se guardan en `~/.local/share/WireFlash/`.

> PyInstaller compila para el SO en el que se ejecuta: el `.exe` se construye en
> Windows y el AppImage en Linux.

## Plantilla de hoja SVG (PDF)

La plantilla SVG admite estos *placeholders* de texto, que el programa
**sobrescribe** con los datos del proyecto al exportar:

| Placeholder | Valor |
|---|---|
| `{{project}}`  | nombre del proyecto |
| `{{assembly}}` | nombre del ensamblaje |
| `{{author}}`   | autor del proyecto |
| `{{version}}`  | versión del proyecto |
| `{{date}}`     | fecha de exportación |
| `{{page}}` / `{{pages}}` | nº de hoja / total |

Un `<rect id="content" .../>` (invisible) define la zona donde se dibuja el BOM o
el diagrama. Ejemplo completo en `plantillas/generica.svg`.

## Estructura

| Ruta | Rol |
|---|---|
| `wireflash/` | paquete de la aplicación |
| `wireflash/model.py` | modelo (Project, Harness, Connector, Cable, Wire, Terminal) + netlist |
| `wireflash/library.py` | librerías de componentes y de ensamblajes |
| `wireflash/reports.py` | BOM, tabla de corte y netlist (puro, CSV) |
| `wireflash/pdfexport.py`, `wireflash/templates.py` | exportación PDF + plantillas |
| `wireflash/scene.py`, `items.py`, `view.py`, `mainwindow.py`, `dialogs.py`, `app.py`, `theme.py` | GUI |
| `wireflash/data/components/` | librería estándar (un JSON por componente) |
| `librerias/`, `plantillas/`, `ejemplo_arnes.json` | datos de ejemplo |
| `WireFlash.spec`, `build.bat`, `build-appimage.sh`, `packaging/` | empaquetado |
