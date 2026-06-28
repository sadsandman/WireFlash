"""Escena del lienzo: puente entre el modelo Harness y los items graficos."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene

from .items import (
    CableItem, ConnectorItem, NoteItem, PortItem, TerminalItem, WireItem)
from ..model.library import CablePart, Part, TerminalPart
from ..model import Cable, Endpoint, Harness, Terminal, Wire
from ..model.templates import FrameTemplate, page_size_mm

# escala del lienzo: 96 ppp -> 1 mm = 3.7795 unidades de escena
PX_PER_MM = 96.0 / 25.4


class HarnessScene(QGraphicsScene):
    changed_model = Signal()
    selection_info = Signal(object)
    dirtied = Signal()              # cualquier cambio (incluye mover nodos) -> undo

    def __init__(self, harness: Harness) -> None:
        super().__init__()
        self.harness = harness
        self.bg_color = QColor("#0f1419")
        self.grid_color = QColor("#1b2630")
        self.setBackgroundBrush(self.bg_color)
        # rejilla y marco de hoja (la rejilla queda desactivada: se veía mal)
        self.draw_grid = False
        self.show_frame = False
        self.page_name = "A4"
        self.landscape = False
        self.frame_template: FrameTemplate | None = None  # None -> genérica
        self.frame_fields: dict = {}
        self._node_items: dict[str, object] = {}      # node_id -> Connector/CableItem
        self._wire_items: dict[str, WireItem] = {}
        self._pending: PortItem | None = None
        self.default_gauge = "20"
        self.default_color = "BK"
        self.selectionChanged.connect(self._on_selection)
        self._update_scene_rect()
        self.rebuild()

    # ----- area de trabajo --------------------------------------------
    def _update_scene_rect(self) -> None:
        """Ajusta el sceneRect para que siempre contenga la hoja con margen."""
        page = self.page_rect()
        margin = 300.0
        rect = page.adjusted(-margin, -margin, margin, margin)
        # asegurar un area minima de trabajo aunque la hoja sea pequena
        rect = rect.united(QRectF(-300, -300, 3000, 2200))
        self.setSceneRect(rect)

    # ----- voltear (mirror) ------------------------------------------
    def flip_selected(self, axis: str) -> None:
        """Orienta/voltea los nodos seleccionados cambiando su lado de salida.
        'h' (tecla X) = salida horizontal: alterna izquierda<->derecha, y si el
        conector mira arriba/abajo lo pasa a horizontal. 'v' (tecla Y) = salida
        vertical: alterna arriba<->abajo, y si mira izquierda/derecha lo pasa a
        vertical. Asi X e Y siempre hacen algo sea cual sea el lado actual."""
        if axis == "h":
            nxt = {"right": "left", "left": "right",
                   "top": "left", "bottom": "right"}
        else:
            nxt = {"top": "bottom", "bottom": "top",
                   "left": "top", "right": "bottom"}
        changed = False
        for it in self.selectedItems():
            model = getattr(it, "model", None)
            side = getattr(model, "side", None)
            if side in nxt:
                model.side = nxt[side]
                if hasattr(it, "relayout"):
                    it.relayout()
                changed = True
        if changed:
            self.changed_model.emit()

    # ----- construccion ----------------------------------------------
    def rebuild(self) -> None:
        self.clear()
        self._node_items.clear()
        self._wire_items.clear()
        self._pending = None
        for c in self.harness.connectors:
            self._add_node_item(ConnectorItem(c))
        for c in self.harness.cables:
            self._add_node_item(CableItem(c))
        for t in self.harness.terminals:
            self._add_node_item(TerminalItem(t))
        for n in self.harness.notes:
            self._add_node_item(NoteItem(n))
        for w in self.harness.wires:
            self._add_wire_item(w)
        self._refresh_ports()

    def _add_node_item(self, item):
        self.addItem(item)
        self._node_items[item.node_id] = item
        return item

    def _port_item(self, ep: Endpoint) -> PortItem | None:
        node = self._node_items.get(ep.node)
        return node.port_for(ep.port) if node else None

    def _add_wire_item(self, w: Wire) -> WireItem | None:
        src = self._port_item(w.a)
        dst = self._port_item(w.b)
        if not src or not dst:
            return None
        gauge, color = self.harness.wire_style(w)
        item = WireItem(w, src, dst, gauge, color)
        self.addItem(item)
        self._wire_items[w.id] = item
        return item

    # ----- alta de componentes ---------------------------------------
    def add_component(self, comp, pos: QPointF) -> None:
        x = round(pos.x() / 10) * 10
        y = round(pos.y() / 10) * 10
        if isinstance(comp, Part):
            conn = comp.instantiate(self.harness.next_ref(), x, y)
            self.harness.add_connector(conn)
            self._add_node_item(ConnectorItem(conn))
        elif isinstance(comp, CablePart):
            cab = comp.instantiate(self.harness.next_cable_ref(), 0.0, x, y)
            self.harness.add_cable(cab)
            self._add_node_item(CableItem(cab))
        elif isinstance(comp, TerminalPart):
            term = comp.instantiate(self.harness.next_terminal_ref(), x, y)
            self.harness.add_terminal(term)
            self._add_node_item(TerminalItem(term))
        self.changed_model.emit()

    def add_note(self, note, pos: QPointF) -> None:
        note.x = round(pos.x() / 10) * 10
        note.y = round(pos.y() / 10) * 10
        self.harness.add_note(note)
        self._add_node_item(NoteItem(note))
        self.changed_model.emit()

    def note_item(self, note_id: str):
        it = self._node_items.get(note_id)
        return it if isinstance(it, NoteItem) else None

    # ----- creacion de segmentos -------------------------------------
    def port_clicked(self, port: PortItem) -> None:
        if self._pending is None:
            self._pending = port
            port.setBrush(QColor("#ff7043"))
            return
        if port is self._pending:
            self.cancel_pending()
            return
        a, b = self._pending.endpoint, port.endpoint
        # puenteo: ambos extremos en el MISMO conector
        jumper = a.kind == "conn" and b.kind == "conn" and a.node == b.node
        wire = Wire(a=Endpoint(a.kind, a.node, a.port),
                    b=Endpoint(b.kind, b.node, b.port),
                    gauge=self.default_gauge, color=self.default_color,
                    is_jumper=jumper)
        self.harness.add_wire(wire)
        self._add_wire_item(wire)
        self.cancel_pending()
        self._refresh_ports()
        self.changed_model.emit()

    def cancel_pending(self) -> None:
        if self._pending:
            self._pending = None
        self._refresh_ports()

    # ----- sincronizacion --------------------------------------------
    def update_wires_for(self, node_id: str) -> None:
        for w in self.harness.wires_on_node(node_id):
            wi = self._wire_items.get(w.id)
            if wi:
                wi.update_path()

    def relayout_connector(self, conn_id: str) -> None:
        item = self._node_items.get(conn_id)
        if item and isinstance(item, ConnectorItem):
            item.relayout()
            self.update()

    def rebuild_node(self, node_id: str) -> None:
        """Reconstruye un nodo (p.ej. tras cambiar pines/conductores)."""
        self.rebuild()

    def refresh_styles(self) -> None:
        for w in self.harness.wires:
            wi = self._wire_items.get(w.id)
            if wi:
                gauge, color = self.harness.wire_style(w)
                wi.set_style(gauge, color)
        self.update()
        self._refresh_ports()

    def _refresh_ports(self) -> None:
        for node in self._node_items.values():
            for port in node.ports:
                on = self.harness.wires_on_port(port.endpoint.node,
                                                port.endpoint.port)
                port.set_connected(bool(on))

    # ----- borrado ----------------------------------------------------
    def delete_selected(self) -> None:
        removed = False
        for it in list(self.selectedItems()):
            if isinstance(it, WireItem):
                self.harness.remove_wire(it.wire.id)
                self._wire_items.pop(it.wire.id, None)
                self.removeItem(it)
                removed = True
            elif isinstance(it, NoteItem):
                self.harness.remove_note(it.node_id)
                self._node_items.pop(it.node_id, None)
                self.removeItem(it)
                removed = True
            elif isinstance(it, (ConnectorItem, CableItem, TerminalItem)):
                nid = it.node_id
                for w in self.harness.wires_on_node(nid):
                    wi = self._wire_items.pop(w.id, None)
                    if wi:
                        self.removeItem(wi)
                if isinstance(it, ConnectorItem):
                    self.harness.remove_connector(nid)
                elif isinstance(it, CableItem):
                    self.harness.remove_cable(nid)
                else:
                    self.harness.remove_terminal(nid)
                self._node_items.pop(nid, None)
                self.removeItem(it)
                removed = True
        if removed:
            self._refresh_ports()
            self.changed_model.emit()

    # ----- seleccion --------------------------------------------------
    def _on_selection(self) -> None:
        sel = self.selectedItems()
        if len(sel) == 1:
            it = sel[0]
            if isinstance(it, ConnectorItem):
                self.selection_info.emit(it.connector)
                return
            if isinstance(it, CableItem):
                self.selection_info.emit(it.cable)
                return
            if isinstance(it, TerminalItem):
                self.selection_info.emit(it.terminal)
                return
            if isinstance(it, WireItem):
                self.selection_info.emit(it.wire)
                return
            if isinstance(it, NoteItem):
                self.selection_info.emit(it.note)
                return
        self.selection_info.emit(None)

    # ----- tema -------------------------------------------------------
    def set_theme(self, canvas_bg: str, grid: str) -> None:
        self.bg_color = QColor(canvas_bg)
        self.grid_color = QColor(grid)
        self.setBackgroundBrush(self.bg_color)
        self.update()

    # ----- hoja / marco -----------------------------------------------
    def page_rect(self) -> QRectF:
        w, h = page_size_mm(self.page_name, self.landscape)
        return QRectF(0, 0, w * PX_PER_MM, h * PX_PER_MM)

    def set_page(self, page_name: str | None = None,
                 landscape: bool | None = None,
                 show: bool | None = None) -> None:
        if page_name is not None:
            self.page_name = page_name
        if landscape is not None:
            self.landscape = landscape
        if show is not None:
            self.show_frame = show
        self._update_scene_rect()
        self.update()

    def drawForeground(self, painter: QPainter, rect) -> None:
        super().drawForeground(painter, rect)
        if not self.show_frame:
            return
        tpl = self.frame_template or FrameTemplate.generic(
            self.frame_fields.get("logo", ""))
        fields = dict(self.frame_fields)
        fields.setdefault("page", 1)
        fields.setdefault("pages", 1)
        painter.save()
        tpl.draw(painter, self.page_rect(), PX_PER_MM * 25.4, fields)
        painter.restore()

    # ----- rejilla ----------------------------------------------------
    def drawBackground(self, painter: QPainter, rect) -> None:
        super().drawBackground(painter, rect)
        if self.show_frame:
            painter.fillRect(self.page_rect(), QColor("#fbfbf7"))
        if not self.draw_grid:
            return
        step = 50
        pen = QPen(self.grid_color); pen.setWidth(0)
        painter.setPen(pen)
        x = int(rect.left()) - (int(rect.left()) % step)
        while x < rect.right():
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
            x += step
        y = int(rect.top()) - (int(rect.top()) % step)
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
            y += step
