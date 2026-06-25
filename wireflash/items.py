"""Items graficos: conector, cable (componente de paso), puerto y segmento.

Cada item es una *vista* del modelo. Las conexiones (WireItem) enlazan dos
PortItem, que pueden pertenecer a un conector (pin) o a un cable (extremo de
conductor). El cable se dibuja con sus hilos y calibre visibles.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
)

from .model import Cable, Connector, Endpoint, Terminal, Wire, WIRE_COLORS

BOX_WIDTH = 140
HEADER_H = 30
IMAGE_BAND = 72          # alto de la banda de imagen (entre el nombre y los pines)
PIN_H = 22
PIN_NUB_R = 5

# Terminal item constants
TERM_H_W = 190    # ancho en orientacion horizontal
TERM_H_H = 40     # alto en orientacion horizontal
TERM_V_W = 90     # ancho en orientacion vertical
TERM_V_H = 102    # alto en orientacion vertical (18+56+14+14)
TERM_V_IMG = 56   # alto de la imagen en layout vertical

_SIDE_DIR = {
    "right": QPointF(1, 0), "left": QPointF(-1, 0),
    "top": QPointF(0, -1), "bottom": QPointF(0, 1),
}

_PIXMAP_CACHE: dict[str, QPixmap] = {}


def _pixmap(path: str) -> QPixmap | None:
    if not path:
        return None
    pm = _PIXMAP_CACHE.get(path)
    if pm is None:
        pm = QPixmap(path) if os.path.exists(path) else QPixmap()
        _PIXMAP_CACHE[path] = pm
    return pm if not pm.isNull() else None


def _band_h(pm) -> float:
    """Alto de la banda de imagen (0 si el componente no tiene imagen)."""
    return IMAGE_BAND if pm is not None else 0.0


def _draw_image_band(p, pm, area):
    """Dibuja la imagen en su PROPIA banda, entre el encabezado y los pines."""
    p.save()
    clip = QPainterPath()
    clip.addRect(area)
    p.setClipPath(clip)
    p.fillRect(area, QColor("#11181d"))
    scaled = pm.scaled(area.size().toSize(), Qt.KeepAspectRatio,
                       Qt.SmoothTransformation)
    dx = area.x() + (area.width() - scaled.width()) / 2
    dy = area.y() + (area.height() - scaled.height()) / 2
    p.drawPixmap(QPointF(dx, dy), scaled)
    p.restore()
    p.setPen(QPen(QColor("#0d1b22"), 1))
    p.drawLine(int(area.left()), int(area.bottom()),
               int(area.right()), int(area.bottom()))


# ===================================================================
#  Puerto generico (pin de conector o extremo de conductor)
# ===================================================================
class PortItem(QGraphicsEllipseItem):
    def __init__(self, host, endpoint: Endpoint, fixed_dir: QPointF | None = None):
        super().__init__(-PIN_NUB_R, -PIN_NUB_R, 2 * PIN_NUB_R, 2 * PIN_NUB_R,
                         parent=host)
        self.host = host
        self.endpoint = endpoint
        self._dir = fixed_dir
        self.setBrush(QBrush(QColor("#cfd8dc")))
        self.setPen(QPen(QColor("#263238"), 1.5))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)
        self.setZValue(3)

    def scene_nub(self) -> QPointF:
        return self.mapToScene(QPointF(0, 0))

    def exit_dir(self) -> QPointF:
        if self._dir is not None:
            return self._dir
        return _SIDE_DIR.get(getattr(self.host.model, "side", "right"),
                             QPointF(1, 0))

    def set_connected(self, on: bool) -> None:
        self.setBrush(QBrush(QColor("#26c6da" if on else "#cfd8dc")))

    def hoverEnterEvent(self, e):
        self.setBrush(QBrush(QColor("#ffd54f")))
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        sc = self.scene()
        on = bool(sc.harness.wires_on_port(self.endpoint.node, self.endpoint.port)) \
            if hasattr(sc, "harness") else False
        self.set_connected(on)
        super().hoverLeaveEvent(e)

    def is_connected(self) -> bool:
        sc = self.scene()
        if sc and hasattr(sc, "harness"):
            return bool(sc.harness.wires_on_port(self.endpoint.node, self.endpoint.port))
        return False

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and hasattr(self.scene(), "port_clicked"):
            self.scene().port_clicked(self)
            e.accept()
            return
        super().mousePressEvent(e)


# ===================================================================
#  Mixin de nodo movible
# ===================================================================
class _NodeMixin:
    def _init_node(self, model):
        self.model = model
        self.setPos(model.x, model.y)
        self.setFlags(QGraphicsItem.ItemIsMovable
                      | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.ports: list[PortItem] = []

    @property
    def node_id(self) -> str:
        return self.model.id

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            value = QPointF(round(value.x() / 10) * 10, round(value.y() / 10) * 10)
            return value
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.model.x = self.pos().x()
            self.model.y = self.pos().y()
            if hasattr(self.scene(), "update_wires_for"):
                self.scene().update_wires_for(self.node_id)
        return super().itemChange(change, value)


# ===================================================================
#  Conector
# ===================================================================
class ConnectorItem(_NodeMixin, QGraphicsObject):
    def __init__(self, connector: Connector):
        super().__init__()
        self._init_node(connector)
        self.connector = connector
        self.setZValue(1)
        self._build_ports()

    def _build_ports(self):
        for p in self.ports:
            if p.scene():
                p.scene().removeItem(p)
        self.ports = [PortItem(self, Endpoint("conn", self.connector.id, pin.id))
                      for pin in self.connector.pins]
        self._place_ports()

    def content_top(self):
        return HEADER_H + _band_h(_pixmap(self.connector.image))

    def _place_ports(self):
        side = self.connector.side
        total = max(1, len(self.connector.pins))
        h = self.body_height()
        top = self.content_top()
        for row, port in enumerate(self.ports):
            if side in ("right", "left"):
                x = BOX_WIDTH if side == "right" else 0.0
                y = top + row * PIN_H + PIN_H / 2
            else:
                x = (row + 0.5) / total * BOX_WIDTH
                y = 0.0 if side == "top" else h
            port.setPos(x, y)

    def relayout(self):
        self.prepareGeometryChange()
        self._place_ports()
        self.update()
        if self.scene() and hasattr(self.scene(), "update_wires_for"):
            self.scene().update_wires_for(self.node_id)

    def body_height(self):
        return self.content_top() + max(1, len(self.connector.pins)) * PIN_H

    def boundingRect(self):
        m = PIN_NUB_R + 2
        return QRectF(-m, -m, BOX_WIDTH + 2 * m, self.body_height() + 2 * m)

    def port_for(self, port_id: str):
        return next((p for p in self.ports if p.endpoint.port == port_id), None)

    def paint(self, p, option, widget=None):
        c = self.connector
        body = QRectF(0, 0, BOX_WIDTH, self.body_height())
        base = QColor(c.color)
        p.setPen(QPen(QColor("#0d1b22"), 1.5))
        p.setBrush(QBrush(base.darker(115)))
        p.drawRoundedRect(body, 6, 6)

        pm = _pixmap(c.image)
        if pm:
            _draw_image_band(p, pm, QRectF(1, HEADER_H, BOX_WIDTH - 2, IMAGE_BAND))

        _paint_header(p, base, c.ref, c.part_number, c.sku)

        top = self.content_top()
        f = QFont(); f.setPointSize(8); p.setFont(f)
        left_side = c.side == "left"
        for row, pin in enumerate(c.pins):
            y = top + row * PIN_H
            has_term = bool(c.pin_terminal(pin))
            # terminal elegido en ESTE pin (no heredado del conector)
            explicit = pin.terminal.strip() not in ("", "-")
            if row % 2:
                p.fillRect(QRectF(1, y, BOX_WIDTH - 2, PIN_H),
                           QColor(255, 255, 255, 14))
            if not has_term:
                # cavidad vacía: fondo levemente oscurecido
                p.fillRect(QRectF(1, y, BOX_WIDTH - 2, PIN_H), QColor(0, 0, 0, 30))
            elif explicit:
                # terminal asignado a propósito en este pin: banda dorada tenue
                p.fillRect(QRectF(1, y, BOX_WIDTH - 2, PIN_H),
                           QColor(200, 169, 96, 38))
            num_rect = QRectF(8, y, 26, PIN_H)
            name_rect = QRectF(34, y, BOX_WIDTH - 40, PIN_H)
            na, ma = Qt.AlignLeft, Qt.AlignLeft
            if left_side:
                num_rect = QRectF(BOX_WIDTH - 34, y, 26, PIN_H)
                name_rect = QRectF(6, y, BOX_WIDTH - 40, PIN_H)
                na = ma = Qt.AlignRight
            if c.side in ("right", "left"):
                cir_sz = 8
                cir_x = (BOX_WIDTH - 5 - cir_sz) if not left_side else 5
                cir_y = y + (PIN_H - cir_sz) / 2
                if has_term:
                    # contacto presente: círculo sólido metálico.
                    # terminal explícito de este pin -> aro dorado para resaltar.
                    p.setBrush(QBrush(QColor("#78909c")))
                    p.setPen(QPen(QColor("#c8a960" if explicit else "#37474f"),
                                  1.4 if explicit else 0.5))
                    p.drawEllipse(QRectF(cir_x, cir_y, cir_sz, cir_sz))
                    # punto central dorado (contacto)
                    c_sz = 4
                    p.setBrush(QBrush(QColor("#c8a960")))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(QRectF(cir_x + (cir_sz - c_sz) / 2,
                                         cir_y + (cir_sz - c_sz) / 2, c_sz, c_sz))
                else:
                    # cavidad vacía: círculo hueco punteado
                    p.setBrush(Qt.NoBrush)
                    p.setPen(QPen(QColor("#455a64"), 1.0, Qt.DashLine))
                    p.drawEllipse(QRectF(cir_x, cir_y, cir_sz, cir_sz))
            p.setPen(QColor("#eceff1" if has_term else "#546e7a"))
            p.drawText(num_rect, Qt.AlignVCenter | na, pin.number)
            if pin.name:
                p.setPen(QColor("#80deea" if has_term else "#455a64"))
                p.drawText(name_rect, Qt.AlignVCenter | ma, pin.name)

        _paint_selection(p, self, body)


# ===================================================================
#  Cable (componente de paso con hilos visibles)
# ===================================================================
class CableItem(_NodeMixin, QGraphicsObject):
    def __init__(self, cable: Cable):
        super().__init__()
        self._init_node(cable)
        self.cable = cable
        self.setZValue(1)
        self._build_ports()

    def content_top(self):
        return HEADER_H + _band_h(_pixmap(self.cable.image))

    def _build_ports(self):
        for p in self.ports:
            if p.scene():
                p.scene().removeItem(p)
        self.ports = []
        n = self.cable.conductor_count
        top = self.content_top()
        for i in range(n):
            y = top + i * PIN_H + PIN_H / 2
            lp = PortItem(self, Endpoint("cable", self.cable.id, f"{i}:L"),
                          QPointF(-1, 0))
            lp.setPos(0, y)
            rp = PortItem(self, Endpoint("cable", self.cable.id, f"{i}:R"),
                          QPointF(1, 0))
            rp.setPos(BOX_WIDTH, y)
            self.ports += [lp, rp]

    def body_height(self):
        return self.content_top() + max(1, self.cable.conductor_count) * PIN_H

    def boundingRect(self):
        m = PIN_NUB_R + 2
        return QRectF(-m, -m, BOX_WIDTH + 2 * m, self.body_height() + 2 * m)

    def port_for(self, port_id: str):
        return next((p for p in self.ports if p.endpoint.port == port_id), None)

    def paint(self, p, option, widget=None):
        cab = self.cable
        body = QRectF(0, 0, BOX_WIDTH, self.body_height())
        p.setPen(QPen(QColor("#0d1b22"), 1.5))
        p.setBrush(QBrush(QColor("#212b33")))
        p.drawRoundedRect(body, 6, 6)

        pm = _pixmap(cab.image)
        if pm:
            _draw_image_band(p, pm, QRectF(1, HEADER_H, BOX_WIDTH - 2, IMAGE_BAND))

        # cabecera: ref + longitud (apartado) en linea 1, AWG/hilos en linea 2
        _paint_header(p, QColor("#37474f"), f"⎓ {cab.ref}",
                      cab.part_number, cab.sku,
                      subtitle=_fmt_len(cab.length_mm),
                      subtitle2=cab.type_label())

        # filas de conductores con swatch de color
        top = self.content_top()
        f = QFont(); f.setPointSize(8); p.setFont(f)
        for i, code in enumerate(cab.conductor_colors):
            y = top + i * PIN_H
            col = QColor(WIRE_COLORS.get(code, "#888888"))
            # franja de color del conductor de extremo a extremo
            p.fillRect(QRectF(14, y + PIN_H / 2 - 2, BOX_WIDTH - 28, 4), col)
            # swatch
            p.setBrush(QBrush(col)); p.setPen(QPen(QColor("#0d1b22"), 1))
            p.drawRect(QRectF(BOX_WIDTH / 2 - 9, y + 4, 18, PIN_H - 8))
            p.setPen(QColor("#eceff1"))
            p.drawText(QRectF(2, y, 14, PIN_H),
                       Qt.AlignVCenter | Qt.AlignHCenter, str(i + 1))
            p.drawText(QRectF(BOX_WIDTH - 26, y, 24, PIN_H),
                       Qt.AlignVCenter | Qt.AlignHCenter, code)

        _paint_selection(p, self, body)


# ===================================================================
#  Terminal / contacto crimpado (pin tubular, pin Deutsch, etc.)
# ===================================================================
class TerminalItem(_NodeMixin, QGraphicsObject):
    def __init__(self, terminal: Terminal):
        super().__init__()
        self._init_node(terminal)
        self.terminal = terminal
        self.setZValue(1)
        self._build_ports()

    def _body_rect(self) -> QRectF:
        if self.terminal.orientation == "v":
            return QRectF(0, 0, TERM_V_W, TERM_V_H)
        return QRectF(0, 0, TERM_H_W, TERM_H_H)

    def _build_ports(self):
        for port in self.ports:
            if port.scene():
                port.scene().removeItem(port)
        self.ports = []
        t = self.terminal
        if t.orientation == "v":
            dp = PortItem(self, Endpoint("terminal", t.id, "dock"),
                          QPointF(0, -1))
            dp.setPos(TERM_V_W / 2, 0)
            wp = PortItem(self, Endpoint("terminal", t.id, "wire"),
                          QPointF(0, 1))
            wp.setPos(TERM_V_W / 2, TERM_V_H)
        else:
            dp = PortItem(self, Endpoint("terminal", t.id, "dock"),
                          QPointF(-1, 0))
            dp.setPos(0, TERM_H_H / 2)
            wp = PortItem(self, Endpoint("terminal", t.id, "wire"),
                          QPointF(1, 0))
            wp.setPos(TERM_H_W, TERM_H_H / 2)
        self.ports = [dp, wp]

    def relayout(self):
        self.prepareGeometryChange()
        self._build_ports()
        self.update()
        if self.scene() and hasattr(self.scene(), "update_wires_for"):
            self.scene().update_wires_for(self.node_id)

    def boundingRect(self):
        m = PIN_NUB_R + 2
        return self._body_rect().adjusted(-m, -m, m, m)

    def port_for(self, port_id: str):
        return next((p for p in self.ports if p.endpoint.port == port_id), None)

    def paint(self, p, option, widget=None):
        t = self.terminal
        body = self._body_rect()
        accent = QColor("#546e7a")
        p.setPen(QPen(QColor("#0d1b22"), 1.5))
        p.setBrush(QBrush(accent.darker(130)))
        p.drawRoundedRect(body, 4, 4)
        pm = _pixmap(t.image)
        if t.orientation == "v":
            self._paint_v(p, body, pm, accent)
        else:
            self._paint_h(p, body, pm, accent)
        _paint_selection(p, self, body)

    def _paint_h(self, p, body, pm, accent):
        t = self.terminal
        # franja de dock (lado conector)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(accent))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 6, TERM_H_H), 3, 3)
        p.fillPath(path, accent)
        p.fillRect(QRectF(3, 0, 3, TERM_H_H), accent)

        img_zone = TERM_H_H
        if pm:
            img_rect = QRectF(7, 2, img_zone - 8, TERM_H_H - 4)
            p.save()
            clip = QPainterPath()
            clip.addRect(img_rect)
            p.setClipPath(clip)
            scaled = pm.scaled(img_rect.size().toSize(), Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
            dx = img_rect.x() + (img_rect.width() - scaled.width()) / 2
            dy = img_rect.y() + (img_rect.height() - scaled.height()) / 2
            p.drawPixmap(QPointF(dx, dy), scaled)
            p.restore()

        tx = img_zone + 6
        available = TERM_H_W - tx - 4

        f = QFont(); f.setBold(True); f.setPointSize(8); p.setFont(f)
        p.setPen(QColor("#eceff1"))
        p.drawText(QRectF(tx, 2, available * 0.45, TERM_H_H / 2),
                   Qt.AlignVCenter | Qt.AlignLeft, t.ref)

        code = t.sku or t.part_number
        f.setBold(False); f.setPointSize(7); p.setFont(f)
        p.setPen(QColor("#80deea"))
        p.drawText(QRectF(tx + available * 0.45, 2, available * 0.55, TERM_H_H / 2),
                   Qt.AlignVCenter | Qt.AlignRight, code)

        name = t.description or t.part_number
        p.setPen(QColor("#b0bec5"))
        p.drawText(QRectF(tx, TERM_H_H / 2, available, TERM_H_H / 2 - 2),
                   Qt.AlignVCenter | Qt.AlignLeft, name)

    def _paint_v(self, p, body, pm, accent):
        t = self.terminal
        # franja de dock (lado superior)
        p.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, TERM_V_W, 6), 3, 3)
        p.fillPath(path, accent)
        p.fillRect(QRectF(0, 3, TERM_V_W, 3), accent)

        f = QFont(); f.setBold(True); f.setPointSize(8); p.setFont(f)
        p.setPen(QColor("#eceff1"))
        p.drawText(QRectF(4, 6, TERM_V_W - 8, 16),
                   Qt.AlignVCenter | Qt.AlignHCenter, t.ref)

        if pm:
            img_rect = QRectF(4, 23, TERM_V_W - 8, TERM_V_IMG)
            p.save()
            clip = QPainterPath()
            clip.addRect(img_rect)
            p.setClipPath(clip)
            scaled = pm.scaled(img_rect.size().toSize(), Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
            dx = img_rect.x() + (img_rect.width() - scaled.width()) / 2
            dy = img_rect.y() + (img_rect.height() - scaled.height()) / 2
            p.drawPixmap(QPointF(dx, dy), scaled)
            p.restore()

        y_text = 23 + TERM_V_IMG + 1
        f.setBold(False); f.setPointSize(7); p.setFont(f)
        name = t.description or t.part_number
        p.setPen(QColor("#b0bec5"))
        p.drawText(QRectF(2, y_text, TERM_V_W - 4, 14),
                   Qt.AlignVCenter | Qt.AlignHCenter, name)
        code = t.sku or t.part_number
        p.setPen(QColor("#80deea"))
        p.drawText(QRectF(2, y_text + 14, TERM_V_W - 4, 14),
                   Qt.AlignVCenter | Qt.AlignHCenter, code)


# ===================================================================
#  Helpers de dibujo de cabecera / seleccion
# ===================================================================
def _fmt_len(mm: float) -> str:
    if not mm:
        return ""
    if mm >= 1000:
        return f"{mm / 1000:.2f} m"
    if mm >= 10:
        return f"{mm / 10:.1f} cm"
    return f"{mm:.0f} mm"


def _paint_header(p, base, ref, part_number, sku, subtitle="", subtitle2=""):
    header = QRectF(0, 0, BOX_WIDTH, HEADER_H)
    p.setPen(Qt.NoPen)
    path = QPainterPath()
    path.addRoundedRect(header, 6, 6)
    p.fillPath(path, base)
    p.fillRect(QRectF(0, HEADER_H - 8, BOX_WIDTH, 8), base)
    f = QFont(); f.setBold(True); f.setPointSize(9); p.setFont(f)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(6, 1, BOX_WIDTH - 12, 15), Qt.AlignVCenter | Qt.AlignLeft, ref)
    f.setBold(False); f.setPointSize(7); p.setFont(f)
    if subtitle:
        # badge de longitud, como apartado del nombre
        p.setPen(QColor("#ffd180"))
        p.drawText(QRectF(6, 1, BOX_WIDTH - 12, 15),
                   Qt.AlignVCenter | Qt.AlignRight, subtitle)
    p.setPen(QColor("#dfe6ea"))
    line2 = " · ".join(x for x in (sku, part_number) if x)
    p.setPen(QColor("#b7c2c9"))
    p.drawText(QRectF(6, 14, BOX_WIDTH - 12, 14),
               Qt.AlignVCenter | Qt.AlignLeft, line2)
    if subtitle2:
        p.setPen(QColor("#90a4ae"))
        p.drawText(QRectF(6, 14, BOX_WIDTH - 12, 14),
                   Qt.AlignVCenter | Qt.AlignRight, subtitle2)


def _paint_selection(p, item, body):
    if item.isSelected():
        p.setPen(QPen(QColor("#ffb300"), 2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(body, 6, 6)


# ===================================================================
#  Segmento de cable (wire)
# ===================================================================
class WireItem(QGraphicsPathItem):
    def __init__(self, wire: Wire, src: PortItem, dst: PortItem,
                 gauge: str, color: str):
        super().__init__()
        self.wire = wire
        self.src = src
        self.dst = dst
        self.setZValue(0)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._mid = None
        self.set_style(gauge, color)
        self.update_path()

    def boundingRect(self):
        return super().boundingRect().adjusted(-40, -14, 40, 14)

    @property
    def is_dock(self) -> bool:
        a, b = self.src.endpoint, self.dst.endpoint
        return (a.kind == "terminal" and a.port == "dock") or \
               (b.kind == "terminal" and b.port == "dock")

    def set_style(self, gauge: str, color: str):
        if self.is_dock:
            self._pen = QPen(QColor("#78909c"), 3.0,
                             Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin)
            self.setPen(self._pen)
            return
        col = QColor(WIRE_COLORS.get(color, "#000000"))
        try:
            g = int(gauge)
        except (TypeError, ValueError):
            g = 20
        self._pen = QPen(col, max(2.0, 6.0 - g * 0.15),
                         Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        self.setPen(self._pen)

    def update_path(self):
        a = self.src.scene_nub()
        b = self.dst.scene_nub()
        if self.is_dock:
            path = QPainterPath(a)
            path.lineTo(b)
            self.setPath(path)
            self._mid = None
            return
        da, db = self.src.exit_dir(), self.dst.exit_dir()
        off = max(40.0, (abs(b.x() - a.x()) + abs(b.y() - a.y())) * 0.35)
        c1 = QPointF(a.x() + da.x() * off, a.y() + da.y() * off)
        c2 = QPointF(b.x() + db.x() * off, b.y() + db.y() * off)
        path = QPainterPath(a)
        path.cubicTo(c1, c2, b)
        self.setPath(path)
        self._mid = path.pointAtPercent(0.5)

    def _length_label(self) -> str:
        """Etiqueta de longitud para hilos sueltos / puenteos (no conductores
        de cable, cuya longitud la lleva el cable)."""
        w = self.wire
        if not w.is_loose:
            return ""
        txt = _fmt_len(w.total_length_mm)
        if w.is_jumper:
            txt = ("⟲ " + txt) if txt else "⟲ puenteo"
        return txt

    def paint(self, p, option, widget=None):
        if self.isSelected():
            hl = QPen(QColor("#ffb300"), self._pen.widthF() + 4)
            hl.setCapStyle(Qt.RoundCap)
            p.setPen(hl)
            p.drawPath(self.path())
        super().paint(p, option, widget)
        label = self._length_label()
        if label and getattr(self, "_mid", None) is not None:
            f = QFont(); f.setPointSize(7); p.setFont(f)
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(label) + 8
            rect = QRectF(self._mid.x() - w / 2, self._mid.y() - 9, w, 16)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(15, 20, 25, 210)))
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QColor("#ffd180") if self.wire.is_jumper else QColor("#cfd8dc"))
            p.drawText(rect, Qt.AlignCenter, label)
