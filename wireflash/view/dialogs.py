"""Editor de componentes (conector o cable) para las librerias de archivos."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QHeaderView,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from ..model import ASSEMBLY_FIELDS

# Campos fijos descriptivos que viven en la tabla de campos del editor:
# (atributo del modelo, etiqueta por defecto). El nombre es renombrable.
_FIELD_DEFS = [("sku", "SKU"), ("manufacturer", "Fabricante"),
               ("description", "Descripción")]

from ..model.library import CablePart, ComponentLibrary, Part, TerminalPart


class ProjectInfoDialog(QDialog):
    """Edita nombre, autor, versión y logo del proyecto (para el cajetín)."""

    def __init__(self, project, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Datos del proyecto")
        self.resize(440, 220)
        self.project = project
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(project.name)
        form.addRow("Nombre del proyecto", self.name)
        self.author = QLineEdit(project.author)
        form.addRow("Autor", self.author)
        self.version = QLineEdit(project.version)
        self.version.setPlaceholderText("p.ej. 1.0, Rev A")
        form.addRow("Versión", self.version)
        logo_row = QHBoxLayout()
        self.logo = QLineEdit(project.logo)
        self.logo.setPlaceholderText("ruta a logo (PNG/JPG) para el cajetín genérico")
        lbtn = QPushButton("Examinar…"); lbtn.clicked.connect(self._pick_logo)
        logo_row.addWidget(self.logo); logo_row.addWidget(lbtn)
        w = QWidget(); w.setLayout(logo_row)
        form.addRow("Logo", w)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Logo", "", "Imágenes (*.png *.jpg *.jpeg *.bmp *.svg)")
        if path:
            self.logo.setText(path)

    def _save(self):
        if self.name.text().strip():
            self.project.name = self.name.text().strip()
        self.project.author = self.author.text().strip()
        self.project.version = self.version.text().strip()
        self.project.logo = self.logo.text().strip()
        self.accept()


class PdfExportDialog(QDialog):
    """Opciones de exportación a PDF: tamaño, orientación y plantilla."""

    def __init__(self, parent=None, page_name: str = "A4",
                 landscape: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exportar PDF")
        self.resize(440, 220)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.size = QComboBox(); self.size.addItems(["A4", "A3", "A2", "A1"])
        # preseleccionar el tamaño/orientación de hoja ya configurados
        if page_name in ("A4", "A3", "A2", "A1"):
            self.size.setCurrentText(page_name)
        form.addRow("Tamaño de hoja", self.size)
        self.orient = QComboBox()
        self.orient.addItem("Vertical", False)
        self.orient.addItem("Horizontal", True)
        self.orient.setCurrentIndex(1 if landscape else 0)
        form.addRow("Orientación", self.orient)
        self.template = QComboBox()
        self.template.addItem("Genérica (marco + cajetín)", "generic")
        self.template.addItem("Plantilla SVG…", "svg")
        self.template.currentIndexChanged.connect(self._update)
        form.addRow("Plantilla", self.template)
        svg_row = QHBoxLayout()
        self.svg = QLineEdit(); self.svg.setPlaceholderText("ruta a plantilla .svg")
        sbtn = QPushButton("Examinar…"); sbtn.clicked.connect(self._pick_svg)
        svg_row.addWidget(self.svg); svg_row.addWidget(sbtn)
        self.svg_w = QWidget(); self.svg_w.setLayout(svg_row)
        form.addRow("Archivo SVG", self.svg_w)
        lay.addLayout(form)
        hint = QLabel("La plantilla SVG admite {{project}} {{assembly}} {{author}} "
                      "{{version}} {{date}} {{page}} {{pages}}.")
        hint.setWordWrap(True); hint.setStyleSheet("color:#90a4ae;")
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._update()

    def _update(self):
        self.svg_w.setEnabled(self.template.currentData() == "svg")

    def _pick_svg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Plantilla SVG", "", "SVG (*.svg)")
        if path:
            self.svg.setText(path)

    def result_options(self) -> dict:
        return {
            "page_name": self.size.currentText(),
            "landscape": bool(self.orient.currentData()),
            "svg_path": (self.svg.text().strip()
                         if self.template.currentData() == "svg" else ""),
        }


class SettingsDialog(QDialog):
    """Configuración general: escala de los gráficos y autoguardado."""

    def __init__(self, scale_pct: int, min_pct: int, max_pct: int,
                 autosave_enabled: bool = True, autosave_min: int = 5,
                 min_autosave: int = 1, max_autosave: int = 60,
                 pdf_bom_pt: int = 9, pdf_title_pct: int = 100,
                 pdf_diagram_pct: int = 100, pdf_bom_range=(6, 18),
                 pdf_pct_range=(50, 300), parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.resize(460, 440)
        lay = QVBoxLayout(self)
        form = QFormLayout()

        row = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(min_pct, max_pct)
        self.slider.setValue(scale_pct)
        self.spin = QSpinBox()
        self.spin.setRange(min_pct, max_pct)
        self.spin.setSuffix(" %")
        self.spin.setSingleStep(5)
        self.spin.setValue(scale_pct)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        row.addWidget(self.slider, 1)
        row.addWidget(self.spin)
        form.addRow("Escala de gráficos\n(conectores, cables, terminales)",
                    _wrap(row))
        lay.addLayout(form)

        hint = QLabel("Afecta a todo lo dibujado en el lienzo. La hoja (A4/A3…) "
                      "mantiene su tamaño físico, así que con una escala menor "
                      "caben más componentes en la hoja.")
        hint.setWordWrap(True); hint.setStyleSheet("color:#90a4ae;")
        lay.addWidget(hint)

        # --- autoguardado / recuperación ---
        self.autosave_cb = QCheckBox("Autoguardado (recuperación ante cuelgues)")
        self.autosave_cb.setChecked(autosave_enabled)
        lay.addWidget(self.autosave_cb)

        arow = QHBoxLayout()
        self.autosave_spin = QSpinBox()
        self.autosave_spin.setRange(min_autosave, max_autosave)
        self.autosave_spin.setSuffix(" min")
        self.autosave_spin.setValue(autosave_min)
        arow.addWidget(QLabel("Guardar copia cada"))
        arow.addWidget(self.autosave_spin)
        arow.addStretch(1)
        lay.addLayout(arow)
        self.autosave_cb.toggled.connect(self.autosave_spin.setEnabled)
        self.autosave_spin.setEnabled(autosave_enabled)

        ahint = QLabel("Guarda una copia de recuperación en segundo plano. Si el "
                       "programa se cierra por un cuelgue, al reabrir se ofrece "
                       "restaurar ese progreso.")
        ahint.setWordWrap(True); ahint.setStyleSheet("color:#90a4ae;")
        lay.addWidget(ahint)

        # --- tamaños de texto del PDF exportado ---
        grp = QGroupBox("Texto del PDF exportado")
        gf = QFormLayout(grp)
        self.pdf_bom_spin = QSpinBox()
        self.pdf_bom_spin.setRange(*pdf_bom_range)
        self.pdf_bom_spin.setSuffix(" pt")
        self.pdf_bom_spin.setValue(pdf_bom_pt)
        gf.addRow("Tablas (BOM)", self.pdf_bom_spin)

        self.pdf_title_spin = QSpinBox()
        self.pdf_title_spin.setRange(*pdf_pct_range)
        self.pdf_title_spin.setSuffix(" %")
        self.pdf_title_spin.setSingleStep(10)
        self.pdf_title_spin.setValue(pdf_title_pct)
        gf.addRow("Cajetín", self.pdf_title_spin)

        self.pdf_diagram_spin = QSpinBox()
        self.pdf_diagram_spin.setRange(*pdf_pct_range)
        self.pdf_diagram_spin.setSuffix(" %")
        self.pdf_diagram_spin.setSingleStep(10)
        self.pdf_diagram_spin.setValue(pdf_diagram_pct)
        gf.addRow("Diagrama (conectores)", self.pdf_diagram_spin)
        lay.addWidget(grp)

        phint = QLabel("Afecta al PDF y a su vista previa. El diagrama se imprime "
                       "tal cual la hoja del diseño (mismas posiciones y tamaños); "
                       "el % actúa como zoom.")
        phint.setWordWrap(True); phint.setStyleSheet("color:#90a4ae;")
        lay.addWidget(phint)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def result_scale(self) -> float:
        return self.spin.value() / 100.0

    def result_autosave_enabled(self) -> bool:
        return self.autosave_cb.isChecked()

    def result_autosave_minutes(self) -> int:
        return self.autosave_spin.value()

    def result_pdf_bom_pt(self) -> int:
        return self.pdf_bom_spin.value()

    def result_pdf_title_pct(self) -> int:
        return self.pdf_title_spin.value()

    def result_pdf_diagram_pct(self) -> int:
        return self.pdf_diagram_spin.value()


class LibraryManagerDialog(QDialog):
    """Gestor de librerías: rutas externas a cargar (además de ``librerias/``)."""

    def __init__(self, paths: list[str], root_hint: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gestor de librerías")
        self.resize(560, 360)
        lay = QVBoxLayout(self)

        if root_hint:
            info = QLabel(
                "Las librerías de la carpeta estándar se cargan solas:\n"
                f"{root_hint}\n\n"
                "Aquí puedes añadir carpetas EXTERNAS adicionales (cada carpeta "
                "es una librería). Se recuerdan entre sesiones.")
            info.setWordWrap(True); info.setStyleSheet("color:#90a4ae;")
            lay.addWidget(info)

        self.list = QListWidget()
        for p in paths:
            self.list.addItem(QListWidgetItem(p))
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        add = QPushButton("Añadir carpeta…"); add.clicked.connect(self._add)
        rem = QPushButton("Quitar seleccionada"); rem.clicked.connect(self._remove)
        row.addWidget(add); row.addWidget(rem); row.addStretch(1)
        lay.addLayout(row)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _add(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de librería")
        if not d:
            return
        existing = {self.list.item(i).text() for i in range(self.list.count())}
        if d not in existing:
            self.list.addItem(QListWidgetItem(d))

    def _remove(self):
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))

    def result_paths(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]


def _wrap(layout):
    w = QWidget()
    w.setLayout(layout)
    return w


class TerminalPickerDialog(QDialog):
    """Buscador para elegir terminales de la librería (multi-selección)."""

    def __init__(self, choices: list[tuple[str, str]],
                 preselected: set[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Seleccionar terminales compatibles")
        self.resize(440, 480)
        lay = QVBoxLayout(self)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por PN o descripción…")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        self.list = QListWidget()
        for pn, label in choices:
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, pn)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if pn in preselected else Qt.Unchecked)
            self.list.addItem(it)
        lay.addWidget(self.list)

        hint = QLabel("Marca los terminales válidos para este conector.")
        hint.setStyleSheet("color:#90a4ae;")
        lay.addWidget(hint)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.search.setFocus()

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(needle) and needle not in it.text().lower())

    def selected(self) -> list[str]:
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole))
        return out


class ComponentEditorDialog(QDialog):
    """Crea/edita un conector o un cable y lo guarda en su propio JSON."""

    def __init__(self, libraries: list[ComponentLibrary], parent=None,
                 component=None, edit_library: ComponentLibrary | None = None) -> None:
        super().__init__(parent)
        self.editing = component is not None and edit_library is not None
        self.setWindowTitle("Editar componente" if self.editing
                            else "Nuevo componente")
        self.libraries = libraries
        self.original = component
        self.edit_library = edit_library
        self.resize(460, 440)
        self.saved_library: ComponentLibrary | None = None
        self.saved_component = None

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.type_combo = QComboBox()
        self.type_combo.addItem("Conector", "connector")
        self.type_combo.addItem("Cable", "cable")
        self.type_combo.addItem("Terminal", "terminal")
        if component is not None:
            self.type_combo.setCurrentIndex(
                {"connector": 0, "cable": 1, "terminal": 2}[component.kind])
            self.type_combo.setEnabled(False)
        self.type_combo.currentIndexChanged.connect(self._update_visibility)
        form.addRow("Tipo", self.type_combo)

        self.lib_combo = QComboBox()
        for lib in libraries:
            self.lib_combo.addItem(lib.name, lib)
        if self.editing:
            idx = self.lib_combo.findData(edit_library)
            if idx >= 0:
                self.lib_combo.setCurrentIndex(idx)
            self.lib_combo.setEnabled(False)
        form.addRow("Guardar en", self.lib_combo)

        self.pn = QLineEdit(getattr(component, "part_number", "") if component else "")
        form.addRow("Part number*", self.pn)
        self.cat = QLineEdit(getattr(component, "category", "") if component else "General")
        self.cat.setPlaceholderText('Usa "/" para subcategorías: Molex/MicroFit')
        form.addRow("Categoría", self.cat)

        img_row = QHBoxLayout()
        self.image = QLineEdit(getattr(component, "image", "") if component else "")
        self.image.setPlaceholderText("ruta a PNG/JPG (opcional)")
        ibtn = QPushButton("Examinar…"); ibtn.clicked.connect(self._pick_image)
        img_row.addWidget(self.image); img_row.addWidget(ibtn)
        form.addRow("Imagen", _wrap(img_row))

        # --- campos de conector ---
        color_row = QHBoxLayout()
        self.color = QLineEdit(getattr(component, "color", "#37474f")
                               if isinstance(component, Part) else "#37474f")
        cbtn = QPushButton("Color…"); cbtn.clicked.connect(self._pick_color)
        color_row.addWidget(self.color); color_row.addWidget(cbtn)
        self.color_row_w = _wrap(color_row)
        form.addRow("Color", self.color_row_w)
        self.pins = QLineEdit(
            " ".join(component.pins) if isinstance(component, Part) else "")
        self.pins.setPlaceholderText('Ej: "1 2 3 4"  o un número como "8"')
        self.pins_label = QLabel("Pines")
        form.addRow(self.pins_label, self.pins)
        # Terminales: SOLO se asocian desde la librería de terminales (no se
        # escribe texto libre). Lista de compatibles + un terminal por defecto
        # elegido entre esos compatibles.
        compat = getattr(component, "compatible_terminals", []) if isinstance(component, Part) else []
        self._compat: list[str] = list(compat)
        cur_term = getattr(component, "terminal", "") if isinstance(component, Part) else ""
        # un terminal por defecto preexistente se considera compatible
        if cur_term and cur_term not in self._compat:
            self._compat.append(cur_term)
        self._initial_term = cur_term
        self._term_desc = self._collect_terminal_descs()
        compat_box = QVBoxLayout(); compat_box.setContentsMargins(0, 0, 0, 0)
        self.compat_view = QListWidget()
        self.compat_view.setMaximumHeight(96)
        compat_box.addWidget(self.compat_view)
        cbtn_row = QHBoxLayout()
        add_btn = QPushButton("Agregar de la librería…")
        add_btn.clicked.connect(self._pick_terminals)
        del_btn = QPushButton("Quitar")
        del_btn.clicked.connect(self._remove_terminal)
        cbtn_row.addWidget(add_btn); cbtn_row.addWidget(del_btn); cbtn_row.addStretch(1)
        compat_box.addLayout(cbtn_row)
        self.compat_terms_w = _wrap(compat_box)
        self.compat_terms_label = QLabel("Terminales compatibles")
        form.addRow(self.compat_terms_label, self.compat_terms_w)
        # terminal por defecto del conector: combo restringido a los compatibles
        self.def_term = QComboBox()
        self.def_term.setToolTip("Terminal por defecto de todos los pines. Solo se "
                                 "puede elegir entre los terminales compatibles\n"
                                 "(agrégalos arriba desde la librería de terminales).")
        self.def_term_label = QLabel("Terminal por defecto")
        form.addRow(self.def_term_label, self.def_term)
        self._refresh_compat_view()
        self._refresh_default_term()

        # --- campos de cable ---
        self.ctype = QLineEdit(getattr(component, "cable_type", "")
                               if isinstance(component, CablePart) else "")
        self.ctype.setPlaceholderText("Ej: 4H 22AWG · 2+2AWG 120OHMS  (vacío = auto)")
        self.ctype_label = QLabel("Tipo")
        form.addRow(self.ctype_label, self.ctype)
        self.gauge = QLineEdit(getattr(component, "gauge", "22")
                               if isinstance(component, CablePart) else "22")
        self.gauge_label = QLabel("Calibre AWG")
        form.addRow(self.gauge_label, self.gauge)
        self.conductors = QLineEdit(
            " ".join(component.conductor_colors)
            if isinstance(component, CablePart) else "")
        self.conductors.setPlaceholderText("Códigos de color: RD BK WH GN …")
        self.cond_label = QLabel("Conductores")
        form.addRow(self.cond_label, self.conductors)

        # --- campos de terminal ---
        self.orient = QComboBox()
        self.orient.addItem("Horizontal (⟷)", "h")
        self.orient.addItem("Vertical (↕)", "v")
        if isinstance(component, TerminalPart):
            self.orient.setCurrentIndex(0 if component.orientation == "h" else 1)
        self.orient_label = QLabel("Orientación")
        form.addRow(self.orient_label, self.orient)

        # --- tabla de campos (estilo KiCad): nombre + valor editables ---
        # Filas fijas (SKU/Fabricante/Descripción): se puede renombrar su nombre
        # (se recuerda en field_labels) y editar su valor. Botón «+ Fila» agrega
        # parámetros personalizados. PN* y Categoría siguen como campos aparte
        # (son estructurales: identidad y agrupación del árbol).
        fbox = QVBoxLayout(); fbox.setContentsMargins(0, 0, 0, 0)
        self.fields_table = QTableWidget(0, 2)
        self.fields_table.setHorizontalHeaderLabels(["Campo", "Valor"])
        self.fields_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.fields_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.fields_table.verticalHeader().setVisible(False)
        self.fields_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fields_table.setFixedHeight(160)
        fbox.addWidget(self.fields_table)
        frow = QHBoxLayout()
        addf = QPushButton("+ Fila"); addf.clicked.connect(lambda: self._add_field_row())
        delf = QPushButton("Quitar fila"); delf.clicked.connect(self._remove_field_row)
        frow.addWidget(addf); frow.addWidget(delf); frow.addStretch(1)
        fbox.addLayout(frow)
        self.fields_w = _wrap(fbox)
        form.addRow(QLabel("Campos\n(nombre / valor)"), self.fields_w)
        flabels = getattr(component, "field_labels", {}) if component else {}
        for key, deflabel in _FIELD_DEFS:
            name = flabels.get(key, deflabel)
            value = getattr(component, key, "") if component else ""
            self._add_field_row(name, value, key=key)
        for k, v in (getattr(component, "params", {}) or {}).items():
            self._add_field_row(k, str(v), key="")

        lay.addLayout(form)
        hint = QLabel("Colores válidos: BK RD BU GN YE WH OR VT GY BN PK")
        hint.setStyleSheet("color:#90a4ae;")
        lay.addWidget(hint)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._update_visibility()

    def _update_visibility(self):
        kind = self.type_combo.currentData()
        is_conn = kind == "connector"
        is_cable = kind == "cable"
        is_term = kind == "terminal"
        self.color_row_w.setVisible(is_conn)
        self.pins.setVisible(is_conn); self.pins_label.setVisible(is_conn)
        self.compat_terms_w.setVisible(is_conn); self.compat_terms_label.setVisible(is_conn)
        self.def_term.setVisible(is_conn); self.def_term_label.setVisible(is_conn)
        self.ctype.setVisible(is_cable); self.ctype_label.setVisible(is_cable)
        self.gauge.setVisible(is_cable); self.gauge_label.setVisible(is_cable)
        self.conductors.setVisible(is_cable)
        self.cond_label.setVisible(is_cable)
        self.orient.setVisible(is_term); self.orient_label.setVisible(is_term)
        # la tabla de campos (SKU/Fabricante/Descripción + personalizados) aplica
        # a todos los tipos, así que siempre visible.
        # al crear un terminal nuevo, sugiere su categoría propia
        if is_term and not self.editing and self.cat.text().strip() in ("", "General"):
            self.cat.setText("Terminales")
        elif is_cable and not self.editing and self.cat.text().strip() in ("", "Terminales"):
            self.cat.setText("Cables")
        elif is_conn and not self.editing and self.cat.text().strip() in ("", "Terminales", "Cables"):
            self.cat.setText("General")

    def _pick_color(self):
        col = QColorDialog.getColor()
        if col.isValid():
            self.color.setText(col.name())

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen", "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.svg)")
        if path:
            self.image.setText(path)

    # ----- terminales compatibles ------------------------------------
    def _collect_terminal_descs(self) -> dict[str, str]:
        """Mapa PN -> descripción de los terminales en las librerías."""
        desc: dict[str, str] = {}
        for lib in self.libraries:
            for t in getattr(lib, "terminals", []):
                if t.part_number and t.part_number not in desc:
                    desc[t.part_number] = t.description
        return desc

    def _terminal_label(self, pn: str) -> str:
        d = self._term_desc.get(pn)
        if d is None:
            return f"{pn}  (fuera de librería)"
        return f"{pn} — {d}" if d else pn

    def _terminal_choices(self) -> list[tuple[str, str]]:
        return [(pn, self._terminal_label(pn))
                for pn in sorted(self._term_desc)]

    def _refresh_compat_view(self):
        self.compat_view.clear()
        for pn in self._compat:
            it = QListWidgetItem(self._terminal_label(pn))
            it.setData(Qt.UserRole, pn)
            self.compat_view.addItem(it)

    def _refresh_default_term(self):
        """Rellena el combo del terminal por defecto con los compatibles,
        conservando la selección actual si sigue siendo válida."""
        prev = (self.def_term.currentData() if self.def_term.count()
                else self._initial_term)
        self.def_term.blockSignals(True)
        self.def_term.clear()
        self.def_term.addItem("(ninguno)", "")
        for pn in self._compat:
            self.def_term.addItem(self._terminal_label(pn), pn)
        idx = self.def_term.findData(prev or "")
        self.def_term.setCurrentIndex(idx if idx >= 0 else 0)
        self.def_term.blockSignals(False)

    def _pick_terminals(self):
        choices = self._terminal_choices()
        # incluye PNs ya elegidos aunque no estén en la librería (legacy)
        known = {pn for pn, _ in choices}
        for pn in self._compat:
            if pn not in known:
                choices.append((pn, self._terminal_label(pn)))
        if not choices:
            QMessageBox.information(
                self, "Sin terminales",
                "No hay terminales en las librerías cargadas.\n"
                "Crea componentes de tipo «Terminal» y vuelve a intentarlo.")
            return
        dlg = TerminalPickerDialog(choices, set(self._compat), self)
        if dlg.exec():
            self._compat = dlg.selected()
            self._refresh_compat_view()
            self._refresh_default_term()

    def _remove_terminal(self):
        for it in self.compat_view.selectedItems():
            pn = it.data(Qt.UserRole)
            if pn in self._compat:
                self._compat.remove(pn)
        self._refresh_compat_view()
        self._refresh_default_term()

    def _parse_list(self, text: str) -> list[str]:
        raw = text.replace(",", " ").split()
        if len(raw) == 1 and raw[0].isdigit():
            return [str(i) for i in range(1, int(raw[0]) + 1)]
        return raw

    def _add_field_row(self, name: str = "", value: str = "", key: str = "") -> None:
        """Agrega una fila a la tabla de campos. ``key`` no vacío = campo fijo
        (sku/manufacturer/description), cuyo nombre es renombrable; vacío =
        parámetro personalizado (su nombre ES la clave)."""
        r = self.fields_table.rowCount()
        self.fields_table.insertRow(r)
        n_item = QTableWidgetItem(name)
        n_item.setData(Qt.UserRole, key)
        if key:
            f = n_item.font(); f.setBold(True); n_item.setFont(f)
        self.fields_table.setItem(r, 0, n_item)
        self.fields_table.setItem(r, 1, QTableWidgetItem(value))

    def _remove_field_row(self) -> None:
        rows = sorted({i.row() for i in self.fields_table.selectedItems()},
                      reverse=True)
        for r in rows:
            self.fields_table.removeRow(r)

    def _collect_fields(self):
        """Devuelve (builtin, params, field_labels) leyendo la tabla de campos."""
        builtin = {"sku": "", "manufacturer": "", "description": ""}
        params: dict = {}
        field_labels: dict = {}
        defmap = dict(_FIELD_DEFS)
        for r in range(self.fields_table.rowCount()):
            n_item = self.fields_table.item(r, 0)
            v_item = self.fields_table.item(r, 1)
            key = (n_item.data(Qt.UserRole) if n_item else "") or ""
            name = (n_item.text().strip() if n_item else "")
            val = (v_item.text().strip() if v_item else "")
            if key:                       # campo fijo: nombre renombrable
                builtin[key] = val
                if name and name != defmap.get(key):
                    field_labels[key] = name
            elif name:                    # parámetro personalizado
                params[name] = val
        return builtin, params, field_labels

    def _on_save(self):
        pn = self.pn.text().strip()
        if not pn:
            QMessageBox.warning(self, "Falta dato", "El part number es obligatorio.")
            return
        lib: ComponentLibrary = self.lib_combo.currentData()
        if lib is None:
            QMessageBox.warning(self, "Falta librería", "Selecciona una librería.")
            return
        # copia la imagen DENTRO de la librería (relativa, sin referencias externas)
        image = lib.import_image(self.image.text().strip())
        builtin, params, field_labels = self._collect_fields()
        common = dict(part_number=pn, sku=builtin["sku"],
                      manufacturer=builtin["manufacturer"],
                      description=builtin["description"],
                      category=self.cat.text().strip() or "General",
                      image=image)
        kind = self.type_combo.currentData()
        if kind == "connector":
            pins = self._parse_list(self.pins.text())
            if not pins:
                QMessageBox.warning(self, "Falta dato", "Indica al menos un pin.")
                return
            compat = list(self._compat)
            def_term = (self.def_term.currentData() or "").strip()
            comp = Part(color=self.color.text().strip() or "#37474f",
                        terminal=def_term,
                        terminal_desc=self._term_desc.get(def_term, ""),
                        compatible_terminals=compat,
                        pins=pins, params=params, field_labels=field_labels,
                        **common)
        elif kind == "terminal":
            common["category"] = self.cat.text().strip() or "Terminales"
            comp = TerminalPart(orientation=self.orient.currentData(),
                                params=params, field_labels=field_labels, **common)
        else:
            cond = self._parse_list(self.conductors.text())
            if not cond:
                QMessageBox.warning(self, "Falta dato", "Indica los conductores.")
                return
            comp = CablePart(cable_type=self.ctype.text().strip(),
                             gauge=self.gauge.text().strip() or "22",
                             conductor_colors=cond, params=params,
                             field_labels=field_labels, **common)
        if self.editing:
            lib.update_component(self.original, comp)
        elif comp.kind == "connector":
            lib.add_connector(comp)
        elif comp.kind == "terminal":
            lib.add_terminal(comp)
        else:
            lib.add_cable(comp)
        self.saved_library = lib
        self.saved_component = comp
        self.accept()


class AssemblyBlockDialog(QDialog):
    """Configura el cajetín de ensamblaje: título, columnas a incluir (campos de
    fábrica + parámetros personalizados), el nombre de cada columna (editable,
    estilo KiCad) y un comentario libre."""

    def __init__(self, note, options=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cajetín de ensamblaje")
        self.resize(460, 460)
        # opciones = lista de (clave, etiqueta_por_defecto)
        self._options = list(options) if options else list(ASSEMBLY_FIELDS)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(note.title)
        form.addRow("Título", self.title)
        lay.addLayout(form)

        lay.addWidget(QLabel("Columnas (marca para incluir · edita el nombre "
                             "de la columna):"))
        self._checks: dict[str, QCheckBox] = {}
        self._labels: dict[str, tuple] = {}
        for key, deflabel in self._options:
            row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox(key); cb.setChecked(key in note.fields)
            le = QLineEdit(note.labels.get(key, deflabel))
            le.setPlaceholderText(deflabel)
            row.addWidget(cb, 1); row.addWidget(le, 1)
            self._checks[key] = cb
            self._labels[key] = (le, deflabel)
            holder = QWidget(); holder.setLayout(row)
            lay.addWidget(holder)

        lay.addWidget(QLabel("Comentarios:"))
        self.comment = QPlainTextEdit(note.comment)
        self.comment.setPlaceholderText("Notas de armado, observaciones, revisión…")
        lay.addWidget(self.comment)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_ok(self):
        if not any(cb.isChecked() for cb in self._checks.values()):
            QMessageBox.warning(self, "Sin columnas",
                                "Selecciona al menos un campo para el cajetín.")
            return
        self.accept()

    def result_note(self) -> dict:
        fields = [k for k, _ in self._options if self._checks[k].isChecked()]
        labels: dict = {}
        for k, (le, deflabel) in self._labels.items():
            txt = le.text().strip()
            if txt and txt != deflabel:
                labels[k] = txt
        return {
            "title": self.title.text().strip() or "Ensamblaje",
            "fields": fields,
            "labels": labels,
            "comment": self.comment.toPlainText(),
        }
