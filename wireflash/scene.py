"""Escena del lienzo: puente entre el modelo Harness y los items graficos."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene

from .items import CableItem, ConnectorItem, PortItem, TerminalItem, WireItem
from .library import CablePart, Part, TerminalPart
from .model import Cable, Endpoint, Harness, Terminal, Wire


class HarnessScene(QGraphicsScene):
    changed_model = Signal()
    selection_info = Signal(object)

    def __init__(self, harness: Harness) -> None:
        super().__init__()
        self.harness = harness
        self.setSceneRect(-300, -300, 3000, 2200)
        self.bg_color = QColor("#0f1419")
        self.grid_color = QColor("#1b2630")
        self.setBackgroundBrush(self.bg_color)
        self._node_items: dict[str, object] = {}      # node_id -> Connector/CableItem
        self._wire_items: dict[str, WireItem] = {}
        self._pending: PortItem | None = None
        self.default_gauge = "20"
        self.default_color = "BK"
        self.selectionChanged.connect(self._on_selection)
        self.rebuild()

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
        self.selection_info.emit(None)

    # ----- tema -------------------------------------------------------
    def set_theme(self, canvas_bg: str, grid: str) -> None:
        self.bg_color = QColor(canvas_bg)
        self.grid_color = QColor(grid)
        self.setBackgroundBrush(self.bg_color)
        self.update()

    # ----- rejilla ----------------------------------------------------
    def drawBackground(self, painter: QPainter, rect) -> None:
        super().drawBackground(painter, rect)
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
