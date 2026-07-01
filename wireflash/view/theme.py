"""Temas de la interfaz.

Cada tema se define con una **paleta** pequeña; el QSS global de Qt se genera a
partir de ella (``_qss``). Cada tema aporta además los colores del lienzo (fondo
y rejilla). La elección se guarda con ``QSettings`` para que persista entre
sesiones.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings


def _qss(p: dict) -> str:
    """Construye la hoja de estilo a partir de una paleta."""
    return f"""
QMainWindow, QWidget {{ background:{p['bg']}; color:{p['fg']}; }}
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background:{p['panel']}; padding:5px; }}
QTreeWidget, QTableWidget {{ background:{p['field']};
    alternate-background-color:{p['field_alt']}; border:1px solid {p['border']}; }}
QHeaderView::section {{ background:{p['panel']}; color:{p['muted']}; padding:4px;
    border:none; border-right:1px solid {p['bg']}; }}
QTabWidget::pane {{ border:1px solid {p['border']}; }}
QTabBar::tab {{ background:{p['panel']}; padding:6px 12px; color:{p['muted']}; }}
QTabBar::tab:selected {{ background:{p['tab_sel']}; color:{p['tab_sel_fg']}; }}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{ background:{p['field']};
    border:1px solid {p['border2']}; padding:3px; border-radius:3px; color:{p['fg']}; }}
QComboBox::drop-down {{ border:none; width:18px; }}
QComboBox QAbstractItemView {{ background:{p['field']}; color:{p['fg']};
    border:1px solid {p['border2']}; selection-background-color:{p['sel']};
    selection-color:{p['sel_fg']}; outline:0; }}
QListView, QTreeView {{ background:{p['field']}; color:{p['fg']}; }}
QPushButton {{ background:{p['button']}; color:{p['fg']};
    border:1px solid {p['border2']}; padding:4px 10px; border-radius:3px; }}
QPushButton:hover {{ background:{p['button_hover']}; }}
QDialog {{ background:{p['bg']}; color:{p['fg']}; }}
QToolBar {{ background:{p['panel']}; border:none; spacing:3px; }}
QMenuBar {{ background:{p['panel']}; }} QMenuBar::item:selected {{ background:{p['sel']}; }}
QMenu {{ background:{p['menu_bg']}; color:{p['fg']}; }}
QMenu::item:selected {{ background:{p['sel']}; color:{p['sel_fg']}; }}
QStatusBar {{ background:{p['panel']}; color:{p['muted']}; }}
"""


# --- paletas -------------------------------------------------------------
_PALETTES = {
    "dark": dict(
        bg="#11181f", fg="#e0e6eb", panel="#1b2630", muted="#90a4ae",
        field="#0f1419", field_alt="#141b22", border="#1f2a33", border2="#2a3947",
        sel="#26343f", sel_fg="#ffffff", button="#26343f", button_hover="#314350",
        tab_sel="#26343f", tab_sel_fg="#ffffff", menu_bg="#1b2630"),
    "light": dict(
        bg="#eef1f4", fg="#1b2730", panel="#dde3e9", muted="#5b6b78",
        field="#ffffff", field_alt="#f4f6f8", border="#cdd5dd", border2="#b9c2cb",
        sel="#cfe3f5", sel_fg="#11181f", button="#e3e8ed", button_hover="#d3dae1",
        tab_sel="#ffffff", tab_sel_fg="#11181f", menu_bg="#ffffff"),
    "nord": dict(
        bg="#2e3440", fg="#d8dee9", panel="#3b4252", muted="#81a1c1",
        field="#292e39", field_alt="#323847", border="#434c5e", border2="#4c566a",
        sel="#434c5e", sel_fg="#eceff4", button="#434c5e", button_hover="#4c566a",
        tab_sel="#5e81ac", tab_sel_fg="#eceff4", menu_bg="#3b4252"),
    "solarized": dict(
        bg="#002b36", fg="#93a1a1", panel="#073642", muted="#586e75",
        field="#00212b", field_alt="#042f3a", border="#0a3b46", border2="#134f5c",
        sel="#094d5a", sel_fg="#fdf6e3", button="#073642", button_hover="#0d4150",
        tab_sel="#268bd2", tab_sel_fg="#fdf6e3", menu_bg="#073642"),
    "sepia": dict(
        bg="#efe6d4", fg="#4b3f2e", panel="#e2d5bd", muted="#8a7a5c",
        field="#fbf5e9", field_alt="#f3ead7", border="#d8c8a8", border2="#c8b58f",
        sel="#dcc89a", sel_fg="#3a3020", button="#e7dabf", button_hover="#dccaa6",
        tab_sel="#fbf5e9", tab_sel_fg="#3a3020", menu_bg="#fbf5e9"),
    "contrast": dict(
        bg="#000000", fg="#ffffff", panel="#111111", muted="#d0d000",
        field="#000000", field_alt="#0d0d0d", border="#555555", border2="#888888",
        sel="#ffcc00", sel_fg="#000000", button="#1a1a1a", button_hover="#333333",
        tab_sel="#ffcc00", tab_sel_fg="#000000", menu_bg="#0a0a0a"),
}

_CANVAS = {
    "dark": ("#0f1419", "#1b2630"),
    "light": ("#f4f6f8", "#d4dae0"),
    "nord": ("#2b303b", "#3b4252"),
    "solarized": ("#002129", "#073642"),
    "sepia": ("#f3ead7", "#ddcfb2"),
    "contrast": ("#000000", "#333333"),
}

_LABELS = {
    "dark": "Oscuro",
    "light": "Claro",
    "nord": "Nord",
    "solarized": "Solarized",
    "sepia": "Sepia",
    "contrast": "Alto contraste",
}

THEMES: dict[str, dict] = {
    name: {"label": _LABELS[name], "qss": _qss(pal),
           "canvas_bg": _CANVAS[name][0], "grid": _CANVAS[name][1]}
    for name, pal in _PALETTES.items()
}
DEFAULT = "dark"


def _settings() -> QSettings:
    return QSettings("WireFlash", "WireFlash")


def saved_theme() -> str:
    name = _settings().value("theme", DEFAULT)
    return name if name in THEMES else DEFAULT


def save_theme(name: str) -> None:
    if name in THEMES:
        _settings().setValue("theme", name)


# --- escala de gráficos (tamaño de conectores/cables/terminales) ---------
DEFAULT_SCALE = 0.85
MIN_SCALE, MAX_SCALE = 0.4, 1.5


def saved_scale() -> float:
    try:
        s = float(_settings().value("graphics_scale", DEFAULT_SCALE))
    except (TypeError, ValueError):
        s = DEFAULT_SCALE
    return min(MAX_SCALE, max(MIN_SCALE, s))


def save_scale(s: float) -> None:
    _settings().setValue("graphics_scale", float(s))


# --- tamaño de letra de los reportes (BOM / corte / netlist) -------------
DEFAULT_REPORT_PT = 9
MIN_REPORT_PT, MAX_REPORT_PT = 7, 20


def saved_report_pt() -> int:
    try:
        v = int(_settings().value("report_font_pt", DEFAULT_REPORT_PT))
    except (TypeError, ValueError):
        v = DEFAULT_REPORT_PT
    return min(MAX_REPORT_PT, max(MIN_REPORT_PT, v))


def save_report_pt(v: int) -> None:
    _settings().setValue("report_font_pt", int(v))


# --- autoguardado / recuperación -----------------------------------------
DEFAULT_AUTOSAVE = True
DEFAULT_AUTOSAVE_MIN = 5
MIN_AUTOSAVE_MIN, MAX_AUTOSAVE_MIN = 1, 60


def saved_autosave_enabled() -> bool:
    v = _settings().value("autosave_enabled", DEFAULT_AUTOSAVE)
    if isinstance(v, str):
        return v.lower() in ("1", "true", "yes", "on")
    return bool(v)


def save_autosave_enabled(on: bool) -> None:
    _settings().setValue("autosave_enabled", bool(on))


def saved_autosave_minutes() -> int:
    try:
        v = int(_settings().value("autosave_minutes", DEFAULT_AUTOSAVE_MIN))
    except (TypeError, ValueError):
        v = DEFAULT_AUTOSAVE_MIN
    return min(MAX_AUTOSAVE_MIN, max(MIN_AUTOSAVE_MIN, v))


def save_autosave_minutes(v: int) -> None:
    _settings().setValue("autosave_minutes", int(v))


# --- tamaños de texto del PDF exportado ----------------------------------
# tablas del BOM en puntos; cajetín y diagrama (conectores) en porcentaje.
DEFAULT_PDF_BOM_PT = 9
MIN_PDF_BOM_PT, MAX_PDF_BOM_PT = 6, 72
DEFAULT_PDF_PCT = 100
MIN_PDF_PCT, MAX_PDF_PCT = 50, 300


def saved_pdf_bom_pt() -> int:
    try:
        v = int(_settings().value("pdf_bom_pt", DEFAULT_PDF_BOM_PT))
    except (TypeError, ValueError):
        v = DEFAULT_PDF_BOM_PT
    return min(MAX_PDF_BOM_PT, max(MIN_PDF_BOM_PT, v))


def save_pdf_bom_pt(v: int) -> None:
    _settings().setValue("pdf_bom_pt", int(v))


def _saved_pct(key: str) -> int:
    try:
        v = int(_settings().value(key, DEFAULT_PDF_PCT))
    except (TypeError, ValueError):
        v = DEFAULT_PDF_PCT
    return min(MAX_PDF_PCT, max(MIN_PDF_PCT, v))


def saved_pdf_title_pct() -> int:
    return _saved_pct("pdf_title_pct")


def save_pdf_title_pct(v: int) -> None:
    _settings().setValue("pdf_title_pct", int(v))


def saved_pdf_diagram_pct() -> int:
    return _saved_pct("pdf_diagram_pct")


def save_pdf_diagram_pct(v: int) -> None:
    _settings().setValue("pdf_diagram_pct", int(v))


# --- rutas de librerías externas (gestor de librerías) -------------------
def saved_library_paths() -> list[str]:
    raw = _settings().value("library_paths", "")
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw if str(x).strip()]
    return [p for p in str(raw).split("\n") if p.strip()]


def save_library_paths(paths: list[str]) -> None:
    _settings().setValue("library_paths", "\n".join(paths))
