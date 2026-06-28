"""Ventana principal de WireFlash."""

from __future__ import annotations

import os
import uuid

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction, QActionGroup, QBrush, QColor, QCursor, QDrag, QIcon, QKeySequence)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..view import icons
from ..view import items
from . import pdf_export as pdfexport
from ..model import reports
from ..view.dialogs import (
    AssemblyBlockDialog,
    ComponentEditorDialog,
    LibraryManagerDialog,
    PdfExportDialog,
    ProjectInfoDialog,
    SettingsDialog,
)
from ..model.templates import FrameTemplate
from ..model.library import (
    ComponentLibrary,
    TerminalPart,
    app_icon_path,
    assembly_path_for,
    discover_assemblies,
    discover_libraries,
    ensure_assemblies_root,
    ensure_libraries_root,
    import_library_folder,
)
from ..view.items import CableItem, ConnectorItem, NoteItem, TerminalItem
from ..model import (
    AWG_SIZES, ASSEMBLY_EXT, Cable, Connector, Endpoint, Harness, Note, Project,
    PROJECT_EXT, Terminal, WIRE_COLORS, Wire)
from ..view.scene import HarnessScene
from ..view.canvas import HarnessView
from ..view import theme

SIDE_LABELS = [("Derecha", "right"), ("Izquierda", "left"),
               ("Arriba", "top"), ("Abajo", "bottom")]
_SIDE_VALUES = [v for _, v in SIDE_LABELS]


_LIB_ROLE = Qt.UserRole + 1
_COMP_ROLE = Qt.UserRole + 2
_SEARCH_ROLE = Qt.UserRole + 3
_CAT_ROLE = Qt.UserRole + 4      # ruta de subgrupo (categoría) en un nodo de grupo
_KIND_ROLE = Qt.UserRole + 5     # "connector" | "cable" | "terminal"
_LIBNODE_ROLE = Qt.UserRole + 6  # True si el nodo es la raíz de una librería


class PartTree(QTreeWidget):
    """Arbol de librerias con conectores y cables; arrastrables al lienzo.

    Soporta subcategorias: el campo ``category`` se divide por "/" para
    construir nodos anidados (estilo KiCad). Clic derecho sobre un componente
    para editarlo, duplicarlo o eliminarlo de su libreria.
    """

    def __init__(self, libraries: list[ComponentLibrary]) -> None:
        super().__init__()
        self.libraries = libraries
        self._filter = ""
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.populate()

    def populate(self) -> None:
        self.clear()
        for lib in self.libraries:
            ln = QTreeWidgetItem([f"📚 {lib.name}  ({len(lib)})"])
            ln.setData(0, _LIB_ROLE, lib)
            ln.setData(0, _LIBNODE_ROLE, True)
            self.addTopLevelItem(ln)
            if lib.connectors:
                cg = QTreeWidgetItem(["Conectores"])
                ln.addChild(cg)
                self._fill_group(cg, lib, lib.connectors, "connector")
                cg.setExpanded(True)
            if lib.cables:
                kg = QTreeWidgetItem(["Cables"])
                ln.addChild(kg)
                self._fill_group(kg, lib, lib.cables, "cable")
                kg.setExpanded(True)
            # Los terminales NO se listan como nodos sueltos: no se arrastran al
            # lienzo, solo se asocian a un conector desde su editor de librería.
            ln.setExpanded(True)
        self.apply_filter(self._filter)

    # ----- busqueda ---------------------------------------------------
    def apply_filter(self, text: str) -> None:
        """Filtra el árbol por tipo / número de parte / SKU / fabricante."""
        self._filter = text or ""
        needle = self._filter.strip().lower()
        for i in range(self.topLevelItemCount()):
            self._filter_node(self.topLevelItem(i), needle)

    def _filter_node(self, item, needle: str) -> bool:
        """Devuelve True si el nodo (o algún descendiente) es visible."""
        search = item.data(0, _SEARCH_ROLE)
        if search is not None:                       # es una hoja (componente)
            visible = (not needle) or (needle in search)
            item.setHidden(not visible)
            return visible
        any_visible = False
        for i in range(item.childCount()):
            if self._filter_node(item.child(i), needle):
                any_visible = True
        item.setHidden(not any_visible)
        if needle and any_visible:
            item.setExpanded(True)
        return any_visible

    def _fill_group(self, group, lib, comps, kind):
        cache: dict[tuple, QTreeWidgetItem] = {}
        for comp in sorted(comps, key=lambda x: (x.category, x.part_number)):
            parent = self._category_node(group, comp.category, cache, lib, kind)
            self._leaf(parent, lib, comp, kind)

    def _category_node(self, group, category, cache, lib, kind):
        """Crea/recupera el nodo anidado para una ruta de categoria."""
        parent = group
        path = ()
        for seg in [s.strip() for s in (category or "").split("/") if s.strip()]:
            path = path + (seg,)
            node = cache.get(path)
            if node is None:
                node = QTreeWidgetItem([f"▸ {seg}"])
                parent.addChild(node)
                node.setExpanded(True)
                node.setData(0, _LIB_ROLE, lib)
                node.setData(0, _KIND_ROLE, kind)
                node.setData(0, _CAT_ROLE, "/".join(path))
                cache[path] = node
            parent = node
        return parent

    def _leaf(self, parent, lib, comp, kind):
        if kind == "cable":
            # los cables se listan por TIPO (4H 22AWG…) y su número de parte
            label = f"{comp.type_label()} · {comp.part_number}  ({comp.conductor_count}h)"
            tip = ((f"PN: {comp.part_number}")
                   + (f"\nSKU: {comp.sku}" if comp.sku else "")
                   + f"\n{comp.manufacturer}\n{comp.description}")
            search = f"{comp.type_label()} {comp.part_number} {comp.sku}"
        elif kind == "terminal":
            sku = f"[{comp.sku}] " if comp.sku else ""
            orient = "⟷" if comp.orientation == "h" else "↕"
            label = f"{orient} {sku}{comp.part_number}"
            tip = f"{comp.manufacturer}\n{comp.description}"
            search = f"{comp.part_number} {comp.sku} terminal"
        else:
            sku = f"[{comp.sku}] " if comp.sku else ""
            label = f"{sku}{comp.part_number}  ({comp.pin_count}p)"
            tip = f"{comp.manufacturer}\n{comp.description}"
            search = f"{comp.part_number} {comp.sku}"
        leaf = QTreeWidgetItem([label])
        leaf.setToolTip(0, tip)
        leaf.setData(0, Qt.UserRole, f"{kind}|{comp.part_number}")
        leaf.setData(0, _LIB_ROLE, lib)
        leaf.setData(0, _COMP_ROLE, comp)
        leaf.setData(0, _SEARCH_ROLE, f"{search} {comp.manufacturer}".lower())
        parent.addChild(leaf)

    def _selected_component(self):
        item = self.currentItem()
        if item is None:
            return None, None
        return item.data(0, _LIB_ROLE), item.data(0, _COMP_ROLE)

    def _context_menu(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return
        self.setCurrentItem(item)
        lib, comp = item.data(0, _LIB_ROLE), item.data(0, _COMP_ROLE)
        win = self.window()
        cat = item.data(0, _CAT_ROLE)
        if comp is None:
            if cat:                       # nodo de subgrupo (categoría)
                self._category_menu(pos, win, lib, item.data(0, _KIND_ROLE), cat)
            elif item.data(0, _LIBNODE_ROLE):     # raíz de una librería
                self._library_menu(pos, win, lib)
            return
        menu = QMenu(self)
        a_edit = menu.addAction("Editar componente…")
        a_dup = menu.addAction("Duplicar…")
        menu.addSeparator()
        a_del = menu.addAction("Eliminar de la librería…")
        act = menu.exec(self.viewport().mapToGlobal(pos))
        if act == a_edit:
            win.edit_library_component(lib, comp)
        elif act == a_dup:
            win.duplicate_library_component(lib, comp)
        elif act == a_del:
            win.delete_library_component(lib, comp)

    def _category_menu(self, pos, win, lib, kind, cat):
        menu = QMenu(self)
        a_ren = menu.addAction("Renombrar subgrupo…")
        a_del = menu.addAction("Eliminar subgrupo…")
        act = menu.exec(self.viewport().mapToGlobal(pos))
        if act == a_ren:
            win.rename_library_category(lib, kind, cat)
        elif act == a_del:
            win.delete_library_category(lib, kind, cat)

    def _library_menu(self, pos, win, lib):
        menu = QMenu(self)
        a_new = menu.addAction("Nuevo componente aquí…")
        menu.addSeparator()
        a_del = menu.addAction("Eliminar librería…")
        act = menu.exec(self.viewport().mapToGlobal(pos))
        if act == a_new:
            win.open_component_editor()
        elif act == a_del:
            win.delete_library(lib)

    def startDrag(self, actions):
        item = self.currentItem()
        spec = item.data(0, Qt.UserRole) if item else None
        if not spec:
            return
        mime = QMimeData()
        mime.setData("application/x-rh-part", QByteArray(spec.encode()))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WireFlash — editor local de arneses")
        self.resize(1500, 920)
        _icon = app_icon_path()
        if _icon:
            icon = QIcon(_icon)
            self.setWindowIcon(icon)
            app = QApplication.instance()
            if app is not None:
                app.setWindowIcon(icon)

        ensure_libraries_root()
        ensure_assemblies_root()
        self.library_paths: list[str] = theme.saved_library_paths()
        self.libraries: list[ComponentLibrary] = []
        self._load_all_libraries()
        self.project = Project("Proyecto sin titulo")
        self.project.add_assembly(Harness("Ensamblaje 1"))
        self._active = 0
        self.harness = self.project.assemblies[0]
        self.current_path: str | None = None
        self._clipboard: dict | None = None   # copiar/pegar de nodos

        # historial deshacer/rehacer (snapshots del ensamblaje activo)
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._last_snapshot: dict = self.harness.to_dict()
        self._restoring = False
        self._snap_timer = QTimer(self)
        self._snap_timer.setSingleShot(True)
        self._snap_timer.timeout.connect(self._commit_snapshot)

        # estado del marco de hoja (plantilla en el lienzo)
        self.page_name = "A4"
        self.landscape = False
        self.show_frame = True

        # escala de gráficos (configurable, persistida)
        self._graphics_scale = theme.saved_scale()
        items.set_graphics_scale(self._graphics_scale)

        self._make_scene()
        self._apply_page_to_scene()
        self.view = HarnessView(self.scene)
        self.setCentralWidget(self.view)

        self._build_project_dock()
        self._build_library_dock()
        self._build_props_dock()
        self._build_reports_dock()
        self._build_toolbar()
        self._build_menu()
        self.statusBar().showMessage(
            "Arrastra conectores y cables al lienzo · clic en un puerto y luego "
            "en otro para conectar · Supr borra · rueda=zoom")
        self.refresh_reports()
        self.set_theme(theme.saved_theme())

    def _make_scene(self):
        self.scene = HarnessScene(self.harness)
        self.scene.changed_model.connect(self.refresh_reports)
        self.scene.selection_info.connect(self.show_properties)
        self.scene.changed_model.connect(self._schedule_snapshot)
        self.scene.dirtied.connect(self._schedule_snapshot)

    # ----- deshacer / rehacer ----------------------------------------
    def _schedule_snapshot(self) -> None:
        if not self._restoring:
            self._snap_timer.start(350)

    def _commit_snapshot(self) -> None:
        if self._restoring:
            return
        state = self.harness.to_dict()
        if state != self._last_snapshot:
            self._undo.append(self._last_snapshot)
            if len(self._undo) > 100:
                self._undo.pop(0)
            self._last_snapshot = state
            self._redo.clear()

    def _reset_history(self) -> None:
        self._snap_timer.stop()
        self._undo.clear()
        self._redo.clear()
        self._last_snapshot = self.harness.to_dict()

    def _restore_state(self, state: dict) -> None:
        self._restoring = True
        try:
            restored = Harness.from_dict(state)
            restored.filename = self.harness.filename
            self.project.assemblies[self._active] = restored
            self.harness = restored
            self._reload_scene()
        finally:
            self._restoring = False
        self.refresh_reports()

    def undo(self) -> None:
        self._snap_timer.stop()
        self._commit_snapshot()
        if not self._undo:
            self.statusBar().showMessage("Nada que deshacer", 2000)
            return
        self._redo.append(self._last_snapshot)
        self._last_snapshot = self._undo.pop()
        self._restore_state(self._last_snapshot)
        self.statusBar().showMessage("Deshecho", 1500)

    def redo(self) -> None:
        if not self._redo:
            self.statusBar().showMessage("Nada que rehacer", 2000)
            return
        self._undo.append(self._last_snapshot)
        self._last_snapshot = self._redo.pop()
        self._restore_state(self._last_snapshot)
        self.statusBar().showMessage("Rehecho", 1500)

    # ----- docks ------------------------------------------------------
    def _build_project_dock(self) -> None:
        self.assembly_list = QListWidget()
        self.assembly_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.assembly_list.customContextMenuRequested.connect(
            self._assembly_context_menu)
        self.assembly_list.currentRowChanged.connect(self._on_assembly_row)
        self._switching = False

        btns = QHBoxLayout(); btns.setContentsMargins(0, 0, 0, 0); btns.setSpacing(4)
        b_new = QPushButton("＋ Nuevo")
        b_new.setToolTip("Añadir un ensamblaje vacío al proyecto")
        b_new.clicked.connect(self.add_assembly)
        b_lib = QPushButton("Desde librería…")
        b_lib.setToolTip("Insertar un ensamblaje ya armado de la librería")
        b_lib.clicked.connect(self.add_assembly_from_library)
        btns.addWidget(b_new); btns.addWidget(b_lib)

        name_row = QHBoxLayout(); name_row.setContentsMargins(0, 0, 0, 0)
        self.project_label = QLabel()
        self.project_label.setStyleSheet("font-weight:bold; font-size:13px;")
        self.project_label.setWordWrap(True)
        edit_btn = QPushButton("✎")
        edit_btn.setToolTip("Datos del proyecto (nombre, autor, versión, logo)")
        edit_btn.setFixedWidth(28)
        edit_btn.clicked.connect(self.edit_project_info)
        name_row.addWidget(self.project_label, 1)
        name_row.addWidget(edit_btn)

        wrap = QWidget(); v = QVBoxLayout(wrap)
        v.setContentsMargins(4, 4, 4, 4); v.setSpacing(4)
        v.addWidget(QLabel("Proyecto:"))
        v.addLayout(name_row)
        v.addWidget(QLabel("Ensamblajes del proyecto:"))
        v.addWidget(self.assembly_list)
        v.addLayout(btns)

        dock = QDockWidget("Proyecto", self)
        dock.setWidget(wrap)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self._refresh_assembly_list()
        self._update_project_label()

    def _update_project_label(self):
        if hasattr(self, "project_label"):
            extra = []
            if self.project.version:
                extra.append(f"v{self.project.version}")
            if self.project.author:
                extra.append(self.project.author)
            suffix = f"  ({' · '.join(extra)})" if extra else ""
            self.project_label.setText(f"{self.project.name}{suffix}")

    def _refresh_assembly_list(self):
        self._switching = True
        self.assembly_list.clear()
        for i, h in enumerate(self.project.assemblies):
            label = f"{h.name}  ({len(h.connectors)}c · {len(h.wires)}h)"
            self.assembly_list.addItem(QListWidgetItem(label))
        self.assembly_list.setCurrentRow(self._active)
        self._switching = False

    def _on_assembly_row(self, row: int):
        if self._switching or row < 0 or row == self._active:
            return
        self._switch_assembly(row)

    def _switch_assembly(self, index: int):
        if index < 0 or index >= len(self.project.assemblies):
            return
        self._active = index
        self.harness = self.project.assemblies[index]
        self._reload_scene()

    def _assembly_context_menu(self, pos):
        item = self.assembly_list.itemAt(pos)
        if item is None:
            return
        row = self.assembly_list.row(item)
        menu = QMenu(self)
        a_ren = menu.addAction("Renombrar ensamblaje…")
        a_dup = menu.addAction("Duplicar ensamblaje")
        a_libsave = menu.addAction("Guardar en librería de ensamblajes…")
        menu.addSeparator()
        a_del = menu.addAction("Quitar del proyecto")
        act = menu.exec(self.assembly_list.viewport().mapToGlobal(pos))
        if act == a_ren:
            self.rename_assembly(row)
        elif act == a_dup:
            self.duplicate_assembly(row)
        elif act == a_libsave:
            self.save_assembly_to_library(row)
        elif act == a_del:
            self.remove_assembly(row)

    # ----- gestión de ensamblajes ------------------------------------
    def add_assembly(self):
        name = self.project.unique_name("Ensamblaje")
        h = self.project.add_assembly(Harness(name))
        self._active = len(self.project.assemblies) - 1
        self.harness = h
        self._refresh_assembly_list()
        self._reload_scene()
        self.statusBar().showMessage(f"Ensamblaje «{name}» añadido.", 4000)

    def rename_assembly(self, row: int):
        h = self.project.assemblies[row]
        name, ok = QInputDialog.getText(
            self, "Renombrar ensamblaje", "Nombre:", text=h.name)
        if ok and name.strip():
            h.name = name.strip()
            self._refresh_assembly_list()
            self.refresh_reports()

    def duplicate_assembly(self, row: int):
        import copy
        clone = copy.deepcopy(self.project.assemblies[row])
        clone.name = self.project.unique_name(f"{clone.name} copia")
        self.project.assemblies.insert(row + 1, clone)
        self._active = row + 1
        self.harness = clone
        self._refresh_assembly_list()
        self._reload_scene()

    def remove_assembly(self, row: int):
        if len(self.project.assemblies) <= 1:
            QMessageBox.information(
                self, "No se puede", "El proyecto debe tener al menos un ensamblaje.")
            return
        h = self.project.assemblies[row]
        if QMessageBox.question(
                self, "Quitar ensamblaje",
                f"¿Quitar «{h.name}» del proyecto?\n"
                "(No borra el que esté guardado en la librería de ensamblajes.)"
                ) != QMessageBox.Yes:
            return
        self.project.assemblies.pop(row)
        self._active = max(0, min(self._active, len(self.project.assemblies) - 1))
        self.harness = self.project.assemblies[self._active]
        self._refresh_assembly_list()
        self._reload_scene()

    def save_assembly_to_library(self, row: int):
        h = self.project.assemblies[row]
        name, ok = QInputDialog.getText(
            self, "Guardar en librería de ensamblajes",
            "Nombre del ensamblaje en la librería:", text=h.name)
        if not ok or not name.strip():
            return
        import copy
        to_save = copy.deepcopy(h)
        to_save.name = name.strip()
        path = assembly_path_for(name.strip())
        if os.path.exists(path) and QMessageBox.question(
                self, "Ya existe",
                f"Ya hay un ensamblaje «{name.strip()}» en la librería. "
                "¿Reemplazarlo?") != QMessageBox.Yes:
            return
        to_save.save(path)
        self.statusBar().showMessage(
            f"Ensamblaje guardado en la librería: {os.path.basename(path)}", 5000)

    def add_assembly_from_library(self):
        items = discover_assemblies()
        if not items:
            QMessageBox.information(
                self, "Librería vacía",
                "No hay ensamblajes guardados todavía.\n"
                "Guarda uno con clic derecho ▸ «Guardar en librería de ensamblajes».")
            return
        names = [n for n, _ in items]
        name, ok = QInputDialog.getItem(
            self, "Añadir ensamblaje desde librería",
            "Ensamblaje:", names, 0, False)
        if not ok or not name:
            return
        path = dict(items)[name]
        try:
            h = Harness.load(path)            # copia independiente en el proyecto
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo cargar:\n{exc}")
            return
        h.name = self.project.unique_name(h.name or name)
        self.project.add_assembly(h)
        self._active = len(self.project.assemblies) - 1
        self.harness = h
        self._refresh_assembly_list()
        self._reload_scene()
        self.statusBar().showMessage(f"Ensamblaje «{h.name}» insertado.", 4000)

    def _build_library_dock(self) -> None:
        self.part_tree = PartTree(self.libraries)
        self.part_tree.itemDoubleClicked.connect(self._add_center)

        search = QLineEdit()
        search.setClearButtonEnabled(True)
        search.setPlaceholderText("🔎 Buscar por tipo o número de parte…")
        search.textChanged.connect(self.part_tree.apply_filter)

        wrap = QWidget(); v = QVBoxLayout(wrap)
        v.setContentsMargins(4, 4, 4, 4); v.setSpacing(4)
        v.addWidget(search); v.addWidget(self.part_tree)

        dock = QDockWidget("Componentes", self)
        dock.setWidget(wrap)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _build_props_dock(self) -> None:
        self.props = QWidget()
        self.props_layout = QVBoxLayout(self.props)
        self.props_layout.setAlignment(Qt.AlignTop)
        self.show_properties(None)
        dock = QDockWidget("Propiedades", self)
        dock.setWidget(self.props)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._props_dock = dock

    def _build_reports_dock(self) -> None:
        self.tabs = QTabWidget()
        self.bom_table = QTableWidget()
        self.cut_table = QTableWidget()
        self.net_table = QTableWidget()
        for t in (self.bom_table, self.cut_table, self.net_table):
            t.setEditTriggers(QTableWidget.NoEditTriggers)
            t.horizontalHeader().setStretchLastSection(True)
        self.tabs.addTab(self.bom_table, "BOM")
        self.tabs.addTab(self.cut_table, "Tabla de corte")
        self.tabs.addTab(self.net_table, "Netlist")
        dock = QDockWidget("Reportes", self)
        dock.setWidget(self.tabs)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.resizeDocks([self._props_dock, dock], [360, 500], Qt.Vertical)

    # ----- toolbar / menu --------------------------------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar("Acciones")
        tb.setIconSize(QSize(22, 22))
        # acciones principales con icono (estilo KiCad). Se irán agregando más
        # iconos conforme avance el proyecto.
        self._tb_action(tb, icons.new_icon(), "Nuevo", self.new_file,
                        "Nuevo proyecto")
        self._tb_action(tb, icons.open_icon(), "Abrir", self.open_file,
                        "Abrir proyecto / arnés")
        self._tb_action(tb, icons.save_icon(), "Guardar", self.save_file,
                        "Guardar proyecto (Ctrl+S)")
        self._tb_action(tb, icons.pdf_icon(), "PDF", self.export_assembly_pdf,
                        "Exportar ensamblaje a PDF")
        tb.addSeparator()
        self._tb_action(tb, icons.flip_h_icon(), "Voltear H",
                        self.flip_selected_h,
                        "Voltear selección izquierda↔derecha (tecla X)")
        self._tb_action(tb, icons.flip_v_icon(), "Voltear V",
                        self.flip_selected_v,
                        "Voltear selección arriba↔abajo (tecla Y)")
        self._tb_action(tb, icons.fit_icon(), "Encajar hoja", self.fit_page,
                        "Encajar la hoja en la vista (Espacio)")
        tb.addSeparator()
        tb.addWidget(QLabel(" Hilo suelto — AWG: "))
        self.gauge_combo = QComboBox(); self.gauge_combo.addItems(AWG_SIZES)
        self.gauge_combo.setCurrentText(self.scene.default_gauge)
        self.gauge_combo.currentTextChanged.connect(
            lambda v: setattr(self.scene, "default_gauge", v))
        tb.addWidget(self.gauge_combo)
        tb.addWidget(QLabel("  Color: "))
        self.color_combo = QComboBox(); self.color_combo.addItems(list(WIRE_COLORS))
        self.color_combo.setCurrentText(self.scene.default_color)
        self.color_combo.currentTextChanged.connect(
            lambda v: setattr(self.scene, "default_color", v))
        tb.addWidget(self.color_combo)
        self.addToolBar(tb)

    def _tb_action(self, tb, icon, text, slot, tip):
        a = QAction(icon, text, self)
        a.setToolTip(tip)
        a.triggered.connect(slot)
        tb.addAction(a)
        return a

    def _build_menu(self) -> None:
        m = self.menuBar().addMenu("&Archivo")
        self._act(m, "Nuevo proyecto", QKeySequence.New, self.new_file)
        self._act(m, "Abrir proyecto / arnés…", QKeySequence.Open, self.open_file)
        self._act(m, "Guardar proyecto", QKeySequence.Save, self.save_file)
        self._act(m, "Guardar proyecto como…", QKeySequence.SaveAs, self.save_file_as)
        m.addSeparator()
        self._act(m, "Datos del proyecto (autor, versión, logo)…", None,
                  self.edit_project_info)
        # configuración de hoja (documento/impresión)
        hoja = m.addMenu("Configurar hoja")
        self._frame_act = QAction("Mostrar marco y cajetín", self, checkable=True)
        self._frame_act.setChecked(self.show_frame)
        self._frame_act.triggered.connect(self._toggle_frame)
        hoja.addAction(self._frame_act); self.addAction(self._frame_act)
        hoja.addSeparator()
        smenu = hoja.addMenu("Tamaño")
        self._page_size_group = QActionGroup(self)
        self._page_size_group.setExclusive(True)
        for nm in ("A4", "A3", "A2", "A1"):
            a = QAction(nm, self, checkable=True)
            a.setChecked(nm == self.page_name)
            a.triggered.connect(lambda _=False, n=nm: self._set_page_size(n))
            self._page_size_group.addAction(a); smenu.addAction(a)
        omenu = hoja.addMenu("Orientación")
        self._page_orient_group = QActionGroup(self)
        self._page_orient_group.setExclusive(True)
        for label, land in (("Vertical", False), ("Horizontal", True)):
            a = QAction(label, self, checkable=True)
            a.setChecked(land == self.landscape)
            a.triggered.connect(lambda _=False, l=land: self._set_page_orient(l))
            self._page_orient_group.addAction(a); omenu.addAction(a)
        m.addSeparator()
        # exportar agrupado: PDF + CSV
        ex = m.addMenu("Exportar")
        pdf = ex.addMenu("PDF (BOM + diagrama)")
        self._act(pdf, "Proyecto completo…", None, self.export_project_pdf)
        self._act(pdf, "Ensamblaje actual… (imprimir)", QKeySequence.Print,
                  self.export_assembly_pdf)
        csv = ex.addMenu("CSV")
        self._act(csv, "BOM compras (totales)…", None,
                  lambda: self._export(reports.purchase_bom_to_csv, "bom_compras"))
        self._act(csv, "BOM armado (qué va con qué)…", None,
                  lambda: self._export(reports.bom_to_csv, "bom_armado"))
        self._act(csv, "Tabla de corte…", None, lambda: self._export(reports.cut_list_to_csv, "cutlist"))
        self._act(csv, "Netlist…", None, lambda: self._export(reports.netlist_to_csv, "netlist"))

        e = self.menuBar().addMenu("&Edición")
        self._act(e, "Deshacer", QKeySequence.Undo, self.undo)
        a_redo = self._act(e, "Rehacer", QKeySequence.Redo, self.redo)
        a_redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        e.addSeparator()
        # atajos acotados al lienzo para no pisar el copiar/pegar de los
        # campos de texto del panel de propiedades
        for text, seq, slot in (
                ("Copiar", QKeySequence.Copy, self.copy_selection),
                ("Cortar", QKeySequence.Cut, self.cut_selection),
                ("Pegar", QKeySequence.Paste, self.paste_clipboard)):
            a = QAction(text, self)
            a.setShortcut(seq)
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            a.triggered.connect(slot)
            e.addAction(a)
            self.view.addAction(a)
        e.addSeparator()
        self._act(e, "Borrar selección", QKeySequence.Delete,
                  lambda: self.scene.delete_selected())
        e.addSeparator()
        self._act(e, "Voltear horizontal (X)", None, self.flip_selected_h)
        self._act(e, "Voltear vertical (Y)", None, self.flip_selected_v)
        e.addSeparator()
        self._act(e, "Cancelar conexión (Esc)", None,
                  lambda: self.scene.cancel_pending())

        en = self.menuBar().addMenu("&Ensamblaje")
        self._act(en, "Nuevo ensamblaje", None, self.add_assembly)
        self._act(en, "Renombrar ensamblaje…", None,
                  lambda: self.rename_assembly(self._active))
        self._act(en, "Duplicar ensamblaje", None,
                  lambda: self.duplicate_assembly(self._active))
        en.addSeparator()
        self._act(en, "Guardar ensamblaje actual…", None,
                  self.save_current_assembly)
        self._act(en, "Añadir desde librería de ensamblajes…", None,
                  self.add_assembly_from_library)
        self._act(en, "Guardar ensamblaje en librería…", None,
                  lambda: self.save_assembly_to_library(self._active))
        en.addSeparator()
        self._act(en, "Agregar cajetín de ensamblaje…", None,
                  self.add_assembly_note)
        en.addSeparator()
        self._act(en, "Quitar ensamblaje del proyecto", None,
                  lambda: self.remove_assembly(self._active))

        lib = self.menuBar().addMenu("&Librería")
        self._act(lib, "Gestor de librerías…", None, self.manage_libraries)
        lib.addSeparator()
        self._act(lib, "Nueva librería…", None, self.new_library)
        self._act(lib, "Importar librería (carpeta)…", None, self.import_library)
        self._act(lib, "Nuevo componente…", None, self.open_component_editor)
        lib.addSeparator()
        self._act(lib, "Abrir carpeta de librerías…", None, self.reveal_libraries_root)

        v = self.menuBar().addMenu("&Ver")
        self._act(v, "Encajar hoja en la vista (Espacio)", None, self.fit_page)
        v.addSeparator()
        tema = v.addMenu("Tema")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._theme_actions: dict[str, QAction] = {}
        for name, spec in theme.THEMES.items():
            a = QAction(spec["label"], self, checkable=True)
            a.triggered.connect(lambda _=False, n=name: self.set_theme(n))
            self._theme_group.addAction(a)
            tema.addAction(a)
            self._theme_actions[name] = a
        v.addSeparator()
        self._act(v, "Configuración…", None, self.open_settings)

    def _act(self, menu, text, shortcut, slot):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(slot)
        menu.addAction(a); self.addAction(a)
        return a

    def set_theme(self, name: str) -> None:
        """Aplica el tema (claro/oscuro) a la app y al lienzo, y lo recuerda."""
        if name not in theme.THEMES:
            name = theme.DEFAULT
        spec = theme.THEMES[name]
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(spec["qss"])
        self.scene.set_theme(spec["canvas_bg"], spec["grid"])
        act = self._theme_actions.get(name)
        if act is not None and not act.isChecked():
            act.setChecked(True)
        theme.save_theme(name)

    # ----- marco de hoja (plantilla en el lienzo) --------------------
    def _frame_fields(self) -> dict:
        from datetime import date
        return {
            "project": self.project.name,
            "assembly": self.harness.name,
            "author": self.project.author,
            "version": self.project.version,
            "logo": self.project.logo,
            "date": date.today().isoformat(),
        }

    def _apply_page_to_scene(self) -> None:
        self.scene.frame_fields = self._frame_fields()
        self.scene.set_page(self.page_name, self.landscape, self.show_frame)

    def _toggle_frame(self, checked: bool) -> None:
        self.show_frame = bool(checked)
        self.scene.set_page(show=self.show_frame)

    def _set_page_size(self, name: str) -> None:
        self.page_name = name
        self.scene.set_page(page_name=name)
        self.view.request_fit()

    def _set_page_orient(self, landscape: bool) -> None:
        self.landscape = landscape
        self.scene.set_page(landscape=landscape)
        self.view.request_fit()

    # ----- voltear / encajar (toolbar) -------------------------------
    def flip_selected_h(self) -> None:
        self.scene.flip_selected("h")

    def flip_selected_v(self) -> None:
        self.scene.flip_selected("v")

    def fit_page(self) -> None:
        self.view.request_fit()

    # ----- configuración (escala de gráficos) ------------------------
    def open_settings(self) -> None:
        dlg = SettingsDialog(
            int(round(self._graphics_scale * 100)),
            int(theme.MIN_SCALE * 100), int(theme.MAX_SCALE * 100), self)
        if dlg.exec():
            self.set_graphics_scale(dlg.result_scale())

    def set_graphics_scale(self, scale: float) -> None:
        self._graphics_scale = scale
        items.set_graphics_scale(scale)
        theme.save_scale(scale)
        self.scene.rebuild()
        self.scene.update()

    # ----- alta de componentes ---------------------------------------
    def find_component(self, spec: str):
        kind, _, pn = spec.partition("|")
        for lib in self.libraries:
            if kind == "connector":
                comp = lib.find_connector(pn)
            elif kind == "cable":
                comp = lib.find_cable(pn)
            else:
                comp = lib.find_terminal(pn)
            if comp:
                return comp
        return None

    def _add_center(self, item, _col=0):
        spec = item.data(0, Qt.UserRole)
        if spec:
            center = self.view.mapToScene(self.view.viewport().rect().center())
            self.drop_component(spec, center)

    def drop_component(self, spec: str, pos) -> None:
        comp = self.find_component(spec)
        if comp:
            self.scene.add_component(comp, pos)

    # ----- cajetin de ensamblaje --------------------------------------
    def add_assembly_note(self) -> None:
        note = Note()
        opts = reports.assembly_field_options(self.harness)
        dlg = AssemblyBlockDialog(note, opts, self)
        if not dlg.exec():
            return
        self._apply_note_cfg(note, dlg.result_note())
        center = self.view.mapToScene(self.view.viewport().rect().center())
        self.scene.add_note(note, center)
        self.statusBar().showMessage(
            "Cajetín agregado · arrástralo a su sitio · doble clic para editar", 5000)

    def edit_note(self, note) -> None:
        opts = reports.assembly_field_options(self.harness)
        dlg = AssemblyBlockDialog(note, opts, self)
        if not dlg.exec():
            return
        self._apply_note_cfg(note, dlg.result_note())
        it = self.scene.note_item(note.id)
        if it:
            it.refresh()
        self.scene.changed_model.emit()

    def _apply_note_cfg(self, note, cfg: dict) -> None:
        note.title = cfg["title"]
        note.fields = cfg["fields"]
        note.labels = cfg.get("labels", {})
        note.comment = cfg["comment"]

    # ----- editar el componente seleccionado (tecla E) ----------------
    def edit_selected(self) -> None:
        sel = self.scene.selectedItems()
        if len(sel) != 1:
            return
        it = sel[0]
        if isinstance(it, NoteItem):
            self.edit_note(it.note)
        elif isinstance(it, ConnectorItem):
            self._edit_selected_part("connector", it.connector.part_number)
        elif isinstance(it, CableItem):
            self._edit_selected_part("cable", it.cable.part_number)

    def _edit_selected_part(self, kind: str, pn: str) -> None:
        lib, part = self._find_library_part(kind, pn)
        if part:
            self.edit_library_component(lib, part)
        else:
            QMessageBox.information(
                self, "Sin librería",
                f"«{pn}» no está en una librería cargada; no se puede editar.")

    # ----- librerias --------------------------------------------------
    def _load_all_libraries(self) -> None:
        """Reconstruye self.libraries: estándar embebida + carpeta ``librerias/``
        + cada ruta externa guardada en el gestor de librerías."""
        libs: list[ComponentLibrary] = (
            [ComponentLibrary.load_builtin()] + discover_libraries())
        seen = {os.path.abspath(l.directory) for l in libs if l.directory}
        for p in self.library_paths:
            if not os.path.isdir(p):
                continue
            ap = os.path.abspath(p)
            if ap in seen:
                continue
            try:
                libs.append(ComponentLibrary.load(p))
                seen.add(ap)
            except Exception:
                pass
        self.libraries = libs
        if hasattr(self, "part_tree"):
            self.part_tree.libraries = self.libraries
            self.part_tree.populate()

    def manage_libraries(self):
        dlg = LibraryManagerDialog(
            list(self.library_paths), root_hint=ensure_libraries_root(),
            parent=self)
        if not dlg.exec():
            return
        self.library_paths = dlg.result_paths()
        theme.save_library_paths(self.library_paths)
        self._load_all_libraries()
        self.statusBar().showMessage(
            f"Librerías recargadas ({len(self.libraries)} en total)", 5000)

    def load_library(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de librería externa")
        if d:
            self.libraries.append(ComponentLibrary.load(d))
            self.part_tree.populate()
            self.statusBar().showMessage(f"Librería cargada: {d}", 4000)

    def new_library(self):
        name, ok = QInputDialog.getText(self, "Nueva librería",
                                        "Nombre de la librería:")
        if not ok or not name.strip():
            return
        root = ensure_libraries_root()
        from ..model.library import _slug
        path = os.path.join(root, _slug(name.strip()))
        os.makedirs(path, exist_ok=True)
        self.libraries.append(ComponentLibrary(path, name=name.strip()))
        self.part_tree.populate()
        self.statusBar().showMessage(
            f"Librería creada en librerias/{os.path.basename(path)}", 5000)

    def import_library(self):
        d = QFileDialog.getExistingDirectory(
            self, "Carpeta de librería a importar (se copiará a librerias/)")
        if not d:
            return
        try:
            lib = import_library_folder(d)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo importar:\n{exc}")
            return
        self.libraries.append(lib)
        self.part_tree.populate()
        self.statusBar().showMessage(
            f"Librería importada: {lib.name} ({len(lib)} componentes)", 5000)

    def reveal_libraries_root(self):
        QMessageBox.information(
            self, "Carpeta de librerías",
            "Las librerías compartibles viven en:\n\n"
            f"{ensure_libraries_root()}\n\n"
            "Cada subcarpeta es una librería. Copia ahí la carpeta de otra "
            "persona (o usa «Importar librería») y reiníciala para verla.")

    def open_component_editor(self):
        dlg = ComponentEditorDialog(self.libraries, self)
        if dlg.exec() and dlg.saved_library is not None:
            self.part_tree.populate()
            self.statusBar().showMessage("Componente guardado en su archivo JSON.", 4000)

    # ----- edicion de componentes de libreria ------------------------
    def edit_library_component(self, lib, comp):
        if lib is None or comp is None:
            return
        old_pn = comp.part_number
        dlg = ComponentEditorDialog(self.libraries, self,
                                    component=comp, edit_library=lib)
        if dlg.exec() and dlg.saved_library is not None:
            # propaga los cambios a las instancias ya colocadas (sin re-arrastrar)
            n = self._propagate_part_to_instances(dlg.saved_component, old_pn)
            self.part_tree.populate()
            self.scene.rebuild()
            self.refresh_reports()
            self.statusBar().showMessage(
                f"Componente actualizado en «{lib.name}» · "
                f"{n} instancia(s) sincronizada(s).", 5000)

    def _propagate_part_to_instances(self, part, old_pn: str) -> int:
        """Vuelca los valores de catalogo del componente de libreria a las
        instancias colocadas con el part number anterior. Respeta los datos
        propios de la instancia (ref, posicion, longitud, nombres de pin)."""
        if part is None:
            return 0
        is_conn = part.kind == "connector"
        pool = self.harness.connectors if is_conn else self.harness.cables
        count = 0
        for inst in pool:
            if inst.part_number != old_pn:
                continue
            inst.sku = part.sku
            inst.part_number = part.part_number
            inst.manufacturer = part.manufacturer
            inst.description = part.description
            inst.image = part.image_abs()
            inst.params = dict(getattr(part, "params", {}))
            if is_conn:
                inst.color = part.color
                inst.terminal = part.terminal
                inst.terminal_desc = part.terminal_desc
                if len(inst.pins) == len(part.pins):
                    for pin, num in zip(inst.pins, part.pins):
                        pin.number = num
            else:
                inst.cable_type = part.cable_type
                inst.gauge = part.gauge
                if len(inst.conductor_colors) == len(part.conductor_colors):
                    inst.conductor_colors = list(part.conductor_colors)
            count += 1
        return count

    def duplicate_library_component(self, lib, comp):
        if lib is None or comp is None:
            return
        import copy
        clone = copy.deepcopy(comp)
        clone.image = comp.image_abs()   # absoluta: se re-importará al guardar
        clone.source_path = ""
        clone.part_number = f"{comp.part_number}-copia"
        dlg = ComponentEditorDialog(self.libraries, self, component=clone)
        if dlg.exec() and dlg.saved_library is not None:
            self.part_tree.populate()
            self.statusBar().showMessage("Componente duplicado.", 4000)

    def delete_library_component(self, lib, comp):
        if lib is None or comp is None:
            return
        if QMessageBox.question(
                self, "Eliminar componente",
                f"¿Eliminar «{comp.part_number}» de la librería «{lib.name}»?\n"
                "Se borrará su archivo JSON (las instancias ya colocadas se "
                "conservan).") != QMessageBox.Yes:
            return
        lib.remove_component(comp)
        self.part_tree.populate()
        self.statusBar().showMessage("Componente eliminado de la librería.", 4000)

    # ----- subgrupos (categorías) ------------------------------------
    def _lib_comps(self, lib, kind):
        return {"connector": lib.connectors, "cable": lib.cables,
                "terminal": lib.terminals}[kind]

    def _category_members(self, lib, kind, path):
        """Componentes en la categoría exacta o en cualquier subcategoría."""
        return [c for c in self._lib_comps(lib, kind)
                if c.category == path or c.category.startswith(path + "/")]

    def delete_library_category(self, lib, kind, path):
        if lib is None:
            return
        comps = self._category_members(lib, kind, path)
        if not comps:
            return
        if QMessageBox.question(
                self, "Eliminar subgrupo",
                f"¿Eliminar el subgrupo «{path}» y sus {len(comps)} "
                f"componente(s) de «{lib.name}»?\n"
                "Se borrarán sus archivos JSON (las instancias ya colocadas se "
                "conservan).") != QMessageBox.Yes:
            return
        for c in list(comps):
            lib.remove_component(c)
        self.part_tree.populate()
        self.statusBar().showMessage(
            f"Subgrupo «{path}» eliminado ({len(comps)} componentes).", 4000)

    def rename_library_category(self, lib, kind, path):
        if lib is None:
            return
        comps = self._category_members(lib, kind, path)
        if not comps:
            return
        segs = path.split("/")
        new_leaf, ok = QInputDialog.getText(
            self, "Renombrar subgrupo", "Nuevo nombre del subgrupo:",
            text=segs[-1])
        if not ok:
            return
        new_leaf = new_leaf.strip().replace("/", "-")
        if not new_leaf:
            return
        new_path = "/".join(segs[:-1] + [new_leaf])
        if new_path == path:
            return
        for c in comps:
            c.category = new_path + c.category[len(path):]
            lib.save_component(c)
        self.part_tree.populate()
        self.statusBar().showMessage(
            f"Subgrupo renombrado a «{new_path}».", 4000)

    def delete_library(self, lib):
        if lib is None:
            return
        from ..model.library import LIBRARIES_ROOT
        root = os.path.abspath(LIBRARIES_ROOT)
        d = os.path.abspath(lib.directory)
        # solo librerías de usuario (dentro de librerias/); la estándar se protege
        if not d.startswith(root + os.sep):
            QMessageBox.information(
                self, "No editable",
                "La librería estándar no se puede eliminar.\n"
                "Solo las librerías de usuario (en la carpeta «librerias/»).")
            return
        if QMessageBox.question(
                self, "Eliminar librería",
                f"¿Eliminar la librería «{lib.name}» y TODA su carpeta?\n\n"
                f"{d}\n\nEsta acción no se puede deshacer.") != QMessageBox.Yes:
            return
        import shutil
        try:
            shutil.rmtree(d)
        except OSError as exc:
            QMessageBox.warning(self, "Error", f"No se pudo borrar:\n{exc}")
            return
        if lib in self.libraries:
            self.libraries.remove(lib)
        self.part_tree.populate()
        self.statusBar().showMessage(f"Librería «{lib.name}» eliminada.", 4000)

    # ----- propiedades -----------------------------------------------
    def _clear_props(self):
        while self.props_layout.count():
            w = self.props_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

    def _form(self):
        wrap = QWidget(); form = QFormLayout(wrap)
        self.props_layout.addWidget(wrap)
        return form

    def show_properties(self, obj):
        self._clear_props()
        if obj is None:
            lbl = QLabel("Sin selección.\nSelecciona un conector, un cable o un hilo.")
            lbl.setStyleSheet("color:#90a4ae;")
            self.props_layout.addWidget(lbl)
        elif isinstance(obj, Connector):
            self._props_connector(obj)
        elif isinstance(obj, Cable):
            self._props_cable(obj)
        elif isinstance(obj, Terminal):
            self._props_terminal(obj)
        elif isinstance(obj, Wire):
            self._props_wire(obj)
        elif isinstance(obj, Note):
            self._props_note(obj)

    def _terminal_options(self) -> list[str]:
        """PNs de terminales disponibles en todas las librerías cargadas."""
        seen: set[str] = set()
        result: list[str] = []
        for lib in self.libraries:
            for t in getattr(lib, "terminals", []):
                if t.part_number and t.part_number not in seen:
                    seen.add(t.part_number)
                    result.append(t.part_number)
        for lib in self.libraries:
            for conn in getattr(lib, "connectors", []):
                if conn.terminal and conn.terminal not in seen:
                    seen.add(conn.terminal)
                    result.append(conn.terminal)
        return sorted(result)

    def _connector_terminal_options(self, part_number: str) -> list[str]:
        """Terminales compatibles para este conector (definidos en su entrada de librería).
        Si no tiene lista propia, devuelve todos los terminales de la librería."""
        for lib in self.libraries:
            part = lib.find_connector(part_number)
            if part and getattr(part, "compatible_terminals", []):
                return list(part.compatible_terminals)
        return self._terminal_options()

    def _terminal_descs(self) -> dict[str, str]:
        """Mapa PN de terminal -> descripción (de TerminalPart o del conector)."""
        desc: dict[str, str] = {}
        for lib in self.libraries:
            for t in getattr(lib, "terminals", []):
                if t.part_number and t.description and not desc.get(t.part_number):
                    desc[t.part_number] = t.description
            for conn in getattr(lib, "connectors", []):
                if conn.terminal and conn.terminal_desc and not desc.get(conn.terminal):
                    desc[conn.terminal] = conn.terminal_desc
        return desc

    def _terminal_choices(self, part_number: str) -> list[tuple[str, str]]:
        """Terminales válidos para este conector como (PN, etiqueta legible)."""
        desc = self._terminal_descs()
        out: list[tuple[str, str]] = []
        for pn in self._connector_terminal_options(part_number):
            d = desc.get(pn, "")
            out.append((pn, f"{pn} — {d}" if d else pn))
        return out

    def _stock_cables(self) -> list[tuple[str, str]]:
        """Cables de stock como (part_number, etiqueta tipo) para el combo."""
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for lib in self.libraries:
            for cp in sorted(lib.cables, key=lambda x: x.type_label()):
                if cp.part_number and cp.part_number not in seen:
                    seen.add(cp.part_number)
                    out.append((cp.part_number, f"{cp.type_label()} · {cp.part_number}"))
        for cab in self.harness.cables:
            if cab.part_number and cab.part_number not in seen:
                seen.add(cab.part_number)
                out.append((cab.part_number, f"{cab.type_label()} · {cab.part_number}"))
        return out

    def _source_cable_colors(self, pn: str) -> list[str]:
        """Códigos de color de conductor disponibles en el cable de origen."""
        for lib in self.libraries:
            cp = lib.find_cable(pn)
            if cp:
                return list(cp.conductor_colors)
        for cab in self.harness.cables:
            if cab.part_number == pn:
                return list(cab.conductor_colors)
        return []

    def _set_wire_source(self, w, combo):
        pn = combo.currentData()
        if pn:
            colors = self._source_cable_colors(pn)
            if colors and w.color not in colors:
                QMessageBox.warning(
                    self, "Color no disponible",
                    f"No puedes sacar este puenteo del cable «{pn}»:\n"
                    f"no tiene un conductor de color {w.color}.\n\n"
                    f"Colores disponibles: {', '.join(colors)}.")
                idx = combo.findData(w.source_cable)
                combo.blockSignals(True)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
                combo.blockSignals(False)
                return
        w.source_cable = pn
        self.refresh_reports()

    def _find_library_part(self, kind, pn):
        for lib in self.libraries:
            part = lib.find_part(kind, pn)
            if part:
                return lib, part
        return None, None

    def _edit_in_library_row(self, kind, pn):
        wrap = QWidget(); row = QHBoxLayout(wrap); row.setContentsMargins(0, 0, 0, 0)
        lib, part = self._find_library_part(kind, pn)
        if part is None:
            lbl = QLabel("(no está en una librería cargada)")
            lbl.setStyleSheet("color:#90a4ae;")
            row.addWidget(lbl)
        else:
            btn = QPushButton(f"Editar «{pn}» en {lib.name}…")
            btn.clicked.connect(lambda: self.edit_library_component(lib, part))
            row.addWidget(btn)
        return wrap

    def _props_connector(self, c: Connector):
        self.props_layout.addWidget(QLabel(f"<b>Conector {c.ref}</b>"))
        form = self._form()
        ref = QLineEdit(c.ref)
        ref.editingFinished.connect(lambda: (setattr(c, "ref", ref.text()), self._repaint()))
        form.addRow("Referencia", ref)
        form.addRow("SKU", QLabel(c.sku or "—"))
        form.addRow("Part number", QLabel(c.part_number or "—"))
        form.addRow("Fabricante", QLabel(c.manufacturer or "—"))
        form.addRow("Descripción", QLabel(c.description or "—"))
        side = QComboBox()
        for label, val in SIDE_LABELS:
            side.addItem(label, val)
        side.setCurrentIndex(_SIDE_VALUES.index(c.side) if c.side in _SIDE_VALUES else 0)
        side.currentIndexChanged.connect(lambda: self._set_side(c, side.currentData()))
        form.addRow("Salida de cables", side)
        if c.terminal or c.terminal_desc:
            t_info = c.terminal
            if c.terminal_desc:
                t_info = f"{t_info}  ({c.terminal_desc})" if t_info else c.terminal_desc
            lbl = QLabel(t_info)
            lbl.setStyleSheet("color:#90a4ae;")
            form.addRow("Terminal (librería)", lbl)
        form.addRow("Librería", self._edit_in_library_row("connector", c.part_number))

        self.props_layout.addWidget(QLabel("<b>Pines</b>  (señal · terminal):"))
        term_choices = self._terminal_choices(c.part_number)
        inherit_lbl = (f"(hereda: {c.terminal})" if c.terminal
                       else "(hereda — conector sin terminal)")
        for pin in c.pins:
            wrap = QWidget(); row = QHBoxLayout(wrap); row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(QLabel(f"  {pin.number}"))
            sig_edit = QLineEdit(pin.name); sig_edit.setPlaceholderText("señal…")
            sig_edit.editingFinished.connect(
                lambda e=sig_edit, p=pin: (setattr(p, "name", e.text()), self._repaint()))
            row.addWidget(sig_edit, 2)

            # selector restringido a la lista de la librería (sin texto libre)
            term_combo = QComboBox()
            term_combo.addItem(inherit_lbl, "")     # vacío = hereda del conector
            term_combo.addItem("Sin terminal", "-")  # explícitamente sin terminal
            for pn, label in term_choices:
                term_combo.addItem(label, pn)
            cur = pin.terminal.strip()
            idx = term_combo.findData(cur)
            if idx < 0 and cur not in ("", "-"):
                # PN heredado de un proyecto previo que ya no está en la librería
                term_combo.addItem(f"{cur}  (fuera de librería)", cur)
                idx = term_combo.count() - 1
            term_combo.setCurrentIndex(max(idx, 0))
            term_combo.setToolTip(
                "Terminal de este pin (solo opciones de la librería).\n"
                "  hereda  →  usa el terminal por defecto del conector\n"
                "  sin terminal  →  este pin no lleva contacto\n"
                "  PN  →  terminal específico para este pin"
            )

            def _update_terminal(idx, p=pin, combo=term_combo):
                p.terminal = (combo.currentData() or "").strip()
                self.refresh_reports()
                self._repaint()

            term_combo.activated.connect(_update_terminal)
            row.addWidget(term_combo, 2)
            self.props_layout.addWidget(wrap)

    def _props_cable(self, c: Cable):
        self.props_layout.addWidget(QLabel(f"<b>Cable {c.ref}</b>"))
        form = self._form()
        ref = QLineEdit(c.ref)
        ref.editingFinished.connect(lambda: (setattr(c, "ref", ref.text()), self._repaint()))
        form.addRow("Referencia", ref)
        form.addRow("Tipo", QLabel(f"<b>{c.type_label()}</b>"))
        form.addRow("SKU", QLabel(c.sku or "—"))
        form.addRow("Part number", QLabel(c.part_number or "—"))
        form.addRow("Fabricante", QLabel(c.manufacturer or "—"))
        form.addRow("Calibre", QLabel(f"AWG {c.gauge}"))
        form.addRow("Conductores", QLabel(
            ", ".join(f"{i+1}:{col}" for i, col in enumerate(c.conductor_colors))))
        length = QDoubleSpinBox(); length.setRange(0, 100000); length.setSuffix(" mm")
        length.setValue(c.length_mm)
        length.valueChanged.connect(lambda v: (setattr(c, "length_mm", v), self._repaint()))
        form.addRow("Longitud", length)
        form.addRow("Librería", self._edit_in_library_row("cable", c.part_number))

    def _props_terminal(self, t: Terminal):
        self.props_layout.addWidget(QLabel(f"<b>Terminal {t.ref}</b>"))
        form = self._form()
        ref = QLineEdit(t.ref)
        ref.editingFinished.connect(
            lambda: (setattr(t, "ref", ref.text()), self._repaint()))
        form.addRow("Referencia", ref)
        form.addRow("SKU", QLabel(t.sku or "—"))
        form.addRow("Part number", QLabel(t.part_number or "—"))
        form.addRow("Fabricante", QLabel(t.manufacturer or "—"))
        form.addRow("Descripción", QLabel(t.description or "—"))
        orient = QComboBox()
        orient.addItem("Horizontal (⟷)", "h")
        orient.addItem("Vertical (↕)", "v")
        orient.setCurrentIndex(0 if t.orientation == "h" else 1)
        orient.currentIndexChanged.connect(
            lambda: self._set_terminal_orientation(t, orient.currentData()))
        form.addRow("Orientación", orient)
        form.addRow("Librería", self._edit_in_library_row("terminal", t.part_number))

    def _set_terminal_orientation(self, t: Terminal, orientation: str):
        t.orientation = orientation
        self.scene.rebuild_node(t.id)
        self.refresh_reports()

    def _props_note(self, n: Note):
        self.props_layout.addWidget(QLabel(f"<b>Cajetín: {n.title}</b>"))
        lbl = QLabel("Tabla terminal↔conector colocable en la hoja "
                     "(se imprime con el diagrama).")
        lbl.setStyleSheet("color:#90a4ae;"); lbl.setWordWrap(True)
        self.props_layout.addWidget(lbl)
        btn = QPushButton("Editar cajetín…")
        btn.clicked.connect(lambda: self.edit_note(n))
        self.props_layout.addWidget(btn)
        self.props_layout.addStretch(1)

    def _props_wire(self, w: Wire):
        self.props_layout.addWidget(QLabel("<b>Hilo / conexión</b>"))
        form = self._form()
        form.addRow("Desde", QLabel(self.harness.endpoint_label(w.a)))
        form.addRow("Hasta", QLabel(self.harness.endpoint_label(w.b)))
        on_cable = w.a.kind == "cable" or w.b.kind == "cable"
        sig = QLineEdit(w.signal)
        sig.editingFinished.connect(lambda: (setattr(w, "signal", sig.text()), self.refresh_reports()))
        form.addRow("Señal", sig)
        g, col = self.harness.wire_style(w)
        if on_cable:
            form.addRow("AWG", QLabel(f"{g}  (heredado del cable)"))
            form.addRow("Color", QLabel(f"{col}  (heredado del cable)"))
        else:
            gauge = QComboBox(); gauge.addItems(AWG_SIZES); gauge.setCurrentText(w.gauge)
            gauge.currentTextChanged.connect(lambda v: (setattr(w, "gauge", v), self._refresh_styles()))
            form.addRow("AWG", gauge)
            color = QComboBox(); color.addItems(list(WIRE_COLORS)); color.setCurrentText(w.color)
            color.currentTextChanged.connect(lambda v: (setattr(w, "color", v), self._refresh_styles()))
            form.addRow("Color", color)
            length = QDoubleSpinBox(); length.setRange(0, 100000); length.setSuffix(" mm")
            length.setValue(w.length_mm)
            length.valueChanged.connect(lambda v: (setattr(w, "length_mm", v), self._repaint()))
            form.addRow("Longitud", length)

            # ----- puenteo / cable de origen -----
            jumper = QCheckBox("Es puenteo (se saca y vuelve)")
            jumper.setChecked(w.is_jumper)
            form.addRow("Puenteo", jumper)
            extra = QDoubleSpinBox(); extra.setRange(0, 100000); extra.setSuffix(" mm")
            extra.setValue(w.extra_length_mm)
            extra.setToolTip("Cable extra para enrutar el puenteo (se suma al BOM/corte)")
            extra.valueChanged.connect(lambda v: (setattr(w, "extra_length_mm", v), self._repaint()))
            form.addRow("Longitud extra", extra)
            jumper.toggled.connect(
                lambda on: (setattr(w, "is_jumper", on),
                            extra.setEnabled(on), self._repaint()))
            extra.setEnabled(w.is_jumper)

            source = QComboBox()
            source.addItem("— suelto (sin origen) —", "")
            for pn, label in self._stock_cables():
                source.addItem(label, pn)
            if w.source_cable and source.findData(w.source_cable) < 0:
                source.addItem(w.source_cable, w.source_cable)
            source.setCurrentIndex(max(0, source.findData(w.source_cable)))
            source.setToolTip("Cable de stock del que se corta este hilo (BOM lo acumula)")
            source.currentIndexChanged.connect(
                lambda: self._set_wire_source(w, source))
            form.addRow("Sacar de cable", source)

            cut = QLineEdit(w.cut_group)
            cut.setPlaceholderText("vacío = mismo corte que el resto de ese cable")
            cut.setToolTip(
                "Conductores del mismo cable de origen y mismo grupo de corte "
                "cuentan como UN corte (el máximo). Deja vacío si todo sale del "
                "mismo corte; usa etiquetas (1, 2…) para cortes separados.")
            cut.editingFinished.connect(
                lambda: (setattr(w, "cut_group", cut.text().strip()),
                         self.refresh_reports()))
            form.addRow("Grupo de corte", cut)

    # ----- handlers ---------------------------------------------------
    def _set_side(self, c, side):
        c.side = side
        self.scene.relayout_connector(c.id)

    def _refresh_styles(self):
        self.scene.refresh_styles()
        self.refresh_reports()

    def _repaint(self):
        self.scene.update()
        self.refresh_reports()

    # ----- reportes ---------------------------------------------------
    def refresh_reports(self):
        self._fill_bom(self.bom_table, reports.bill_of_materials(self.harness))
        self._fill(self.cut_table,
                   ["Cable", "Señal", "AWG", "Color", "mm", "Desde", "Hasta"],
                   [[r.cable, r.signal, r.gauge, r.color, str(r.length_mm),
                     r.from_end, r.to_end] for r in reports.cut_list(self.harness)])
        self._fill(self.net_table, ["Net", "Pines"],
                   [[name, " , ".join(labels)]
                    for name, labels in reports.netlist(self.harness)])
        n, w, cab, term = (len(self.harness.connectors), len(self.harness.wires),
                           len(self.harness.cables), len(self.harness.terminals))
        title_parts = [f"{n} conectores", f"{cab} cables"]
        if term:
            title_parts.append(f"{term} terminales")
        title_parts.append(f"{w} hilos")
        self.setWindowTitle(
            f"WireFlash — {self.project.name}"
            f"{'*' if self.current_path is None else ''}"
            f"  ▸  {self.harness.name}  [{' · '.join(title_parts)}]")
        # mantiene fresca la etiqueta del ensamblaje activo en el dock
        if hasattr(self, "assembly_list"):
            it = self.assembly_list.item(self._active)
            if it is not None:
                it.setText(f"{self.harness.name}  ({n}c · {w}h)")
        self._update_project_label()

    def _fill(self, table, headers, rows):
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                table.setItem(i, j, QTableWidgetItem(val))
        table.resizeColumnsToContents()

    def _fill_bom(self, table, rows):
        headers = ["Categoría", "SKU", "Item", "Descripción", "Cant.", "Ud"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        sub_fg = QBrush(QColor("#78909c"))
        sub_bg = QBrush(QColor(255, 255, 255, 8))
        for i, r in enumerate(rows):
            data = [r.category, r.sku, r.item, r.description, str(r.qty), r.unit]
            for j, val in enumerate(data):
                it = QTableWidgetItem(val)
                if r.level == 1:
                    it.setForeground(sub_fg)
                    it.setBackground(sub_bg)
                table.setItem(i, j, it)
        table.resizeColumnsToContents()

    # ----- archivo ----------------------------------------------------
    def new_file(self):
        self.project = Project("Proyecto sin titulo")
        self.project.add_assembly(Harness("Ensamblaje 1"))
        self._active = 0
        self.harness = self.project.assemblies[0]
        self.current_path = None
        self._refresh_assembly_list()
        self._reload_scene()

    def open_file(self):
        flt = (f"Proyecto ({'*' + PROJECT_EXT});;"
               f"Ensamblaje ({'*' + ASSEMBLY_EXT});;"
               "Proyecto / Arnés JSON (*.json);;Todos (*)")
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir proyecto o ensamblaje", "", flt)
        if not path:
            return
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == PROJECT_EXT:
                self.project = Project.load_project(path)
            elif ext == ASSEMBLY_EXT:
                # abrir un ensamblaje suelto como proyecto de un solo ensamblaje
                h = Harness.load(path)
                h.filename = os.path.basename(path)
                self.project = Project(h.name or "Proyecto")
                self.project.assemblies = [h]
            else:
                # compatibilidad: JSON antiguo (proyecto o arnés embebido)
                self.project = Project.load(path)
            self._active = 0
            self.harness = self.project.assemblies[0]
            self.current_path = path
            self._refresh_assembly_list()
            self._reload_scene()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo abrir:\n{exc}")

    def _save_to(self, path: str) -> None:
        """Guarda según la extensión: formato carpeta (PROJECT_EXT) o JSON."""
        if os.path.splitext(path)[1].lower() == PROJECT_EXT:
            self.project.save_project(path)
        else:
            self.project.save(path)

    def save_file(self):
        if self.current_path:
            self._save_to(self.current_path)
            self.statusBar().showMessage(f"Guardado en {self.current_path}", 4000)
            self.refresh_reports()
        else:
            self.save_file_as()

    def save_file_as(self):
        if not self.project.name or self.project.name == "Proyecto sin titulo":
            suggested = "Proyecto"
        else:
            suggested = self.project.name
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar proyecto (se creará una carpeta con su nombre)",
            f"{suggested}{PROJECT_EXT}",
            f"Proyecto ({'*' + PROJECT_EXT});;Proyecto JSON (*.json)")
        if not path:
            return
        # extensión por defecto si el usuario no la escribió
        if not os.path.splitext(path)[1]:
            path += PROJECT_EXT
        # si el proyecto sigue sin nombre propio, toma el del archivo
        if not self.project.name or self.project.name == "Proyecto sin titulo":
            self.project.name = os.path.splitext(os.path.basename(path))[0]
        # formato carpeta: inicializa una carpeta con el nombre del proyecto
        if os.path.splitext(path)[1].lower() == PROJECT_EXT:
            base = os.path.splitext(os.path.basename(path))[0]
            folder = os.path.dirname(path)
            if os.path.basename(folder) != base:
                folder = os.path.join(folder, base)
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, base + PROJECT_EXT)
        try:
            self._save_to(path)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{exc}")
            return
        self.current_path = path
        if os.path.splitext(path)[1].lower() == PROJECT_EXT:
            self.statusBar().showMessage(
                f"Proyecto guardado en la carpeta: {os.path.dirname(path)}", 6000)
        else:
            self.statusBar().showMessage(f"Guardado en {path}", 4000)
        self.refresh_reports()

    def save_current_assembly(self):
        """Guarda SOLO el ensamblaje activo en su propio archivo."""
        default = f"{self.harness.name}{ASSEMBLY_EXT}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar ensamblaje", default,
            f"Ensamblaje ({'*' + ASSEMBLY_EXT});;JSON (*.json)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ASSEMBLY_EXT
        try:
            self.harness.save(path)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{exc}")
            return
        self.harness.filename = os.path.basename(path)
        self.statusBar().showMessage(f"Ensamblaje guardado: {path}", 4000)

    # ----- copiar / cortar / pegar (nodos) ---------------------------
    def copy_selection(self) -> bool:
        nodes: list[tuple] = []
        node_ids: set[str] = set()
        for it in self.scene.selectedItems():
            if isinstance(it, ConnectorItem):
                nodes.append(("conn", it.connector.to_dict()))
                node_ids.add(it.connector.id)
            elif isinstance(it, CableItem):
                nodes.append(("cable", it.cable.to_dict()))
                node_ids.add(it.cable.id)
            elif isinstance(it, TerminalItem):
                nodes.append(("terminal", it.terminal.to_dict()))
                node_ids.add(it.terminal.id)
        if not nodes:
            return False
        # incluye los hilos cuyos dos extremos estén dentro de la selección
        wires = [w.to_dict() for w in self.harness.wires
                 if w.a.node in node_ids and w.b.node in node_ids]
        self._clipboard = {"nodes": nodes, "wires": wires}
        self.statusBar().showMessage(
            f"Copiado: {len(nodes)} elemento(s)", 3000)
        return True

    def cut_selection(self) -> None:
        if self.copy_selection():
            self.scene.delete_selected()

    def _paste_target_scene(self):
        """Posición de escena donde pegar: bajo el ratón si está sobre el
        lienzo; si no, el centro de la vista."""
        vp = self.view.viewport()
        local = vp.mapFromGlobal(QCursor.pos())
        if vp.rect().contains(local):
            return self.view.mapToScene(local)
        return self.view.mapToScene(vp.rect().center())

    def paste_clipboard(self) -> None:
        cb = self._clipboard
        if not cb or not cb.get("nodes"):
            return
        # ancla = esquina sup-izq del grupo copiado; se traslada al ratón
        xs = [d.get("x", 0.0) for _, d in cb["nodes"]]
        ys = [d.get("y", 0.0) for _, d in cb["nodes"]]
        target = self._paste_target_scene()
        ox, oy = target.x() - min(xs), target.y() - min(ys)

        def place(obj):
            obj.x = round((obj.x + ox) / 10) * 10
            obj.y = round((obj.y + oy) / 10) * 10

        nid = lambda: uuid.uuid4().hex[:8]
        idmap: dict[str, str] = {}
        pinmap: dict[str, str] = {}
        new_ids: list[str] = []
        for kind, d in cb["nodes"]:
            if kind == "conn":
                c = Connector.from_dict(d)
                idmap[c.id] = c.id = nid()
                c.ref = self.harness.next_ref()
                place(c)
                for p in c.pins:
                    pinmap[p.id] = p.id = nid()
                self.harness.add_connector(c); new_ids.append(c.id)
            elif kind == "cable":
                c = Cable.from_dict(d)
                idmap[c.id] = c.id = nid()
                c.ref = self.harness.next_cable_ref()
                place(c)
                self.harness.add_cable(c); new_ids.append(c.id)
            elif kind == "terminal":
                t = Terminal.from_dict(d)
                idmap[t.id] = t.id = nid()
                t.ref = self.harness.next_terminal_ref()
                place(t)
                self.harness.add_terminal(t); new_ids.append(t.id)
        for wd in cb.get("wires", []):
            w = Wire.from_dict(wd)
            w.id = nid()
            w.a = Endpoint(w.a.kind, idmap.get(w.a.node, w.a.node),
                           pinmap.get(w.a.port, w.a.port))
            w.b = Endpoint(w.b.kind, idmap.get(w.b.node, w.b.node),
                           pinmap.get(w.b.port, w.b.port))
            self.harness.add_wire(w)
        self.scene.rebuild()
        for i in new_ids:
            item = self.scene._node_items.get(i)
            if item is not None:
                item.setSelected(True)
        self.refresh_reports()
        self.statusBar().showMessage(
            f"Pegado: {len(new_ids)} elemento(s)", 3000)

    def edit_project_info(self):
        dlg = ProjectInfoDialog(self.project, self)
        if dlg.exec():
            self._apply_page_to_scene()
            self.refresh_reports()

    def _export(self, func, default_name):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar CSV",
                                              f"{default_name}.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(func(self.harness))
            self.statusBar().showMessage(f"Exportado a {path}", 4000)

    def export_project_pdf(self):
        self._do_pdf(self.project.assemblies, f"{self.project.name}.pdf")

    def export_assembly_pdf(self):
        self._do_pdf([self.harness], f"{self.harness.name}.pdf")

    def _pdf_fields_base(self) -> dict:
        return {"project": self.project.name, "author": self.project.author,
                "version": self.project.version, "logo": self.project.logo}

    def _do_pdf(self, harnesses, suggested_name):
        # el PDF hereda el tamaño/orientación de hoja configurados
        opt = PdfExportDialog(self, page_name=self.page_name,
                              landscape=self.landscape)
        if not opt.exec():
            return
        o = opt.result_options()
        if o["svg_path"]:
            try:
                template = FrameTemplate.from_svg(o["svg_path"])
            except Exception as exc:
                QMessageBox.critical(self, "Error",
                                     f"No se pudo leer la plantilla SVG:\n{exc}")
                return
        else:
            template = FrameTemplate.generic(self.project.logo)
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar a PDF", suggested_name, "PDF (*.pdf)")
        if not path:
            return
        try:
            pdfexport.export_pdf(
                harnesses, path, self._pdf_fields_base(),
                page_name=o["page_name"], landscape=o["landscape"],
                template=template)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo exportar el PDF:\n{exc}")
            return
        self.statusBar().showMessage(
            f"PDF exportado ({len(harnesses)} ensamblaje/s): {path}", 6000)

    def _reload_scene(self):
        self._make_scene()
        self.scene.default_gauge = self.gauge_combo.currentText()
        self.scene.default_color = self.color_combo.currentText()
        self.view.setScene(self.scene)
        self._apply_page_to_scene()
        self.view.request_fit()
        self.show_properties(None)
        self.refresh_reports()
        # al cambiar de ensamblaje/proyecto se empieza un historial nuevo; durante
        # un deshacer/rehacer NO se resetea (se está restaurando un estado).
        if not self._restoring:
            self._reset_history()
