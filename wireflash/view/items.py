"""Items graficos: conector, cable (componente de paso), puerto y segmento.

Cada item es una *vista* del modelo. Las conexiones (WireItem) enlazan dos
PortItem, que pueden pertenecer a un conector (pin) o a un cable (extremo de
conductor). El cable se dibuja con sus hilos y calibre visibles.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
)

from ..model import (
    ASSEMBLY_FIELDS, Cable, Connector, Endpoint, Note, Terminal, Wire,
    WIRE_COLORS)
from ..model import reports
from ..model.library import resolve_instance_image

# escala global de los items gráficos (conectores, cables, terminales, puertos).
# 1.0 = tamaño base; se ajusta desde Configuración y se aplica por nodo con
# QGraphicsItem.setScale, de modo que TODO lo dibujado (geometría, fuentes y
# líneas) escala de forma uniforme.
GRAPHICS_SCALE = 1.0


def set_graphics_scale(s: float) -> None:
    global GRAPHICS_SCALE
    GRAPHICS_SCALE = max(0.1, float(s))


# Modo impresion: cuando esta activo, los componentes se pintan con fondo claro
# y texto oscuro (legible en papel). En pantalla se mantiene el tema oscuro.
# El exportador a PDF lo enciende mientras rasteriza el diagrama.
PRINT_MODE = False


def set_print_mode(on: bool) -> None:
    global PRINT_MODE
    PRINT_MODE = bool(on)


def _ink(screen, paper):
    """Devuelve el color de pantalla o el de impresion segun PRINT_MODE."""
    return QColor(paper if PRINT_MODE else screen)


def _print_tint(c):
    """Version pálida (clara) de un color, conservando el matiz. Se usa para el
    fondo del encabezado en impresion, para que tambien sea claro."""
    c = QColor(c)
    return QColor(round(c.red() * 0.16 + 255 * 0.84),
                  round(c.green() * 0.16 + 255 * 0.84),
                  round(c.blue() * 0.16 + 255 * 0.84))


def _text_w(text, bold=False, size=8) -> float:
    """Ancho en px de un texto con la fuente indicada (para dimensionar cajas).
    Incluye una pequeña holgura porque el ancho real al pintar suele superar
    levemente al que reporta QFontMetrics."""
    if not text:
        return 0.0
    f = QFont(); f.setBold(bold); f.setPointSize(size)
    return QFontMetrics(f).horizontalAdvance(str(text)) * 1.15


def _header_width(ref, line2, subtitle="", subtitle2="") -> float:
    """Ancho minimo para que el encabezado no se solape: en cada linea caben el
    texto de la izquierda y el de la derecha sin pisarse."""
    gap = 10
    l1 = _text_w(ref, True, 9) + (_text_w(subtitle, False, 7) + gap if subtitle else 0)
    l2 = _text_w(line2, False, 7) + (_text_w(subtitle2, False, 7) + gap if subtitle2 else 0)
    return max(l1, l2) + 12   # margenes laterales (6 + 6)


BOX_WIDTH = 140
HEADER_H = 30
IMAGE_BAND = 72          # alto de la banda de imagen (entre el nombre y los pines)
PIN_H = 22
PIN_NUB_R = 5
GRID = 10                # rejilla de posicion en X (unidades de escena)

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


def _inst_pixmap(inst) -> QPixmap | None:
    """Pixmap de una instancia, resolviendo su imagen por nickname de librería
    (portable entre PCs). Cae a ruta absoluta para archivos antiguos."""
    path = resolve_instance_image(
        getattr(inst, "library", ""), getattr(inst, "image", "") or "")
    return _pixmap(path)


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
        self._w = None              # ancho de caja calculado (cache, ver body_width)
        self.setPos(model.x, model.y)
        self.setScale(GRAPHICS_SCALE)
        self.setFlags(QGraphicsItem.ItemIsMovable
                      | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.ports: list[PortItem] = []

    @property
    def node_id(self) -> str:
        return self.model.id

    def _first_port_offset(self):
        """Y (sin escalar) del primer puerto respecto al origen del nodo.
        None = el nodo no usa rejilla de filas (se snapea a GRID normal)."""
        return None

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            x = round(value.x() / GRID) * GRID
            off = self._first_port_offset()
            if off is None:
                y = round(value.y() / GRID) * GRID
            else:
                # Snap del primer puerto a una rejilla de filas (= alto de fila
                # escalado). Como las filas estan espaciadas ese mismo alto,
                # TODOS los puertos del nodo caen en la misma rejilla Y; asi un
                # cable entre dos pines alineados sale perfectamente recto, pese
                # a que los conectores tengan distinta cabecera/imagen.
                row_h = max(1.0, self.scale() * PIN_H)
                off *= self.scale()
                y = round((value.y() + off) / row_h) * row_h - off
            return QPointF(x, y)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.model.x = self.pos().x()
            self.model.y = self.pos().y()
            sc = self.scene()
            if sc is not None and hasattr(sc, "update_wires_for"):
                sc.update_wires_for(self.node_id)
            if sc is not None and hasattr(sc, "dirtied"):
                sc.dirtied.emit()      # registra el movimiento para deshacer
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
        return HEADER_H + _band_h(_inst_pixmap(self.connector))

    def _horizontal(self) -> bool:
        """True si los pines salen por arriba/abajo (se disponen en columnas)."""
        return self.connector.side in ("top", "bottom")

    def _name_band_h(self) -> float:
        """Alto extra (modo columnas) para los nombres de pin, dibujados en
        VERTICAL. 0 si ningún pin tiene nombre."""
        if not self._horizontal():
            return 0.0
        longest = max((_text_w(p.name, True, 8)
                       for p in self.connector.pins if p.name), default=0.0)
        # + holgura para que el texto no toque el encabezado/los números
        return min(longest + 14, 160.0) if longest > 0 else 0.0

    def _first_port_offset(self):
        # en arriba/abajo los puertos no van por filas: se snapea a GRID normal
        if self._horizontal():
            return None
        return self.content_top() + PIN_H / 2

    def body_width(self):
        """Ancho de la caja segun su contenido (encabezado y nombres de pin),
        nunca menor que BOX_WIDTH. Se cachea (el item se recrea al editar)."""
        if self._w is None:
            c = self.connector
            line2 = " · ".join(x for x in (c.sku, c.part_number) if x)
            w = _header_width(c.ref, line2)
            if self._horizontal():
                # arriba/abajo: ancho mínimo por columna para que quepa el número
                total = max(1, len(c.pins))
                col = max(22, 14 + _text_w("88", True, 8))
                w = max(w, total * col)
            else:
                for pin in c.pins:
                    # numero (col izq, ~34) + nombre + holgura del circulo de
                    # contacto (~16 a la derecha); en negrita por si imprime.
                    w = max(w, 50 + _text_w(pin.name, True, 8))
            self._w = max(BOX_WIDTH, w)
        return self._w

    def _place_ports(self):
        side = self.connector.side
        total = max(1, len(self.connector.pins))
        h = self.body_height()
        top = self.content_top()
        w = self.body_width()
        for row, port in enumerate(self.ports):
            if side in ("right", "left"):
                x = w if side == "right" else 0.0
                y = top + row * PIN_H + PIN_H / 2
            else:
                x = (row + 0.5) / total * w
                y = 0.0 if side == "top" else h
            port.setPos(x, y)

    def relayout(self):
        self.prepareGeometryChange()
        self._place_ports()
        self.update()
        if self.scene() and hasattr(self.scene(), "update_wires_for"):
            self.scene().update_wires_for(self.node_id)

    def body_height(self):
        if self._horizontal():
            # arriba/abajo: banda de números + (si hay) banda de nombres vertical
            return self.content_top() + PIN_H + self._name_band_h()
        return self.content_top() + max(1, len(self.connector.pins)) * PIN_H

    def boundingRect(self):
        m = PIN_NUB_R + 2
        return QRectF(-m, -m, self.body_width() + 2 * m, self.body_height() + 2 * m)

    def port_for(self, port_id: str):
        return next((p for p in self.ports if p.endpoint.port == port_id), None)

    def _paint_pin_columns(self, p, w: float, top: float) -> None:
        """Numeración en COLUMNAS (modo arriba/abajo): cada celda queda alineada
        con su puerto. El número va junto al borde por donde salen los puertos y
        el nombre (si lo hay) en VERTICAL en la banda contigua."""
        c = self.connector
        total = max(1, len(c.pins))
        cw = w / total
        name_h = self._name_band_h()
        full_h = PIN_H + name_h
        bottom_side = c.side == "bottom"
        # número adyacente a los puertos: top -> arriba; bottom -> abajo
        num_y = top + name_h if bottom_side else top
        name_y = top if bottom_side else top + PIN_H
        for col, pin in enumerate(c.pins):
            x0 = col * cw
            cell = QRectF(x0, top, cw, full_h)
            has_term = bool(c.pin_terminal(pin))
            explicit = pin.terminal.strip() not in ("", "-")
            if col % 2:
                p.fillRect(cell, QColor(0, 0, 0, 12) if PRINT_MODE
                           else QColor(255, 255, 255, 14))
            if not has_term:
                p.fillRect(cell, QColor(0, 0, 0, 16) if PRINT_MODE
                           else QColor(0, 0, 0, 30))
            elif explicit:
                p.fillRect(cell, QColor(200, 169, 96, 38))
            if col:
                p.setPen(QPen(_ink("#0d1b22", "#37474f"), 0.5))
                p.drawLine(QPointF(x0, top), QPointF(x0, top + full_h))
            # número
            p.setPen(_ink("#eceff1" if has_term else "#546e7a", "#1b2730"))
            p.drawText(QRectF(x0, num_y, cw, PIN_H), Qt.AlignCenter, pin.number)
            # nombre en vertical (rotado) si lo hay; recortado a su celda para
            # que NUNCA invada el encabezado ni la columna vecina
            if pin.name and name_h > 0:
                p.save()
                p.setClipRect(QRectF(x0, name_y, cw, name_h))
                p.translate(x0 + cw / 2, name_y + name_h / 2)
                p.rotate(-90)
                p.setPen(_ink("#80deea" if has_term else "#455a64",
                              "#00695c" if has_term else "#5a6b73"))
                # rect un poco menor que la banda: deja margen con el borde
                p.drawText(QRectF(-name_h / 2 + 2, -cw / 2, name_h - 4, cw),
                           Qt.AlignCenter, pin.name)
                p.restore()

    def paint(self, p, option, widget=None):
        c = self.connector
        w = self.body_width()
        body = QRectF(0, 0, w, self.body_height())
        base = QColor(c.color)
        p.setPen(QPen(_ink("#0d1b22", "#37474f"), 1.5))
        p.setBrush(QBrush(QColor("#ffffff") if PRINT_MODE else base.darker(115)))
        p.drawRoundedRect(body, 6, 6)

        pm = _inst_pixmap(c)
        if pm:
            _draw_image_band(p, pm, QRectF(1, HEADER_H, w - 2, IMAGE_BAND))

        _paint_header(p, base, c.ref, c.part_number, c.sku, width=w)

        top = self.content_top()
        # en impresion el texto va en negrita para que se lea/imprima mejor
        f = QFont(); f.setPointSize(8); f.setBold(PRINT_MODE); p.setFont(f)
        if self._horizontal():
            self._paint_pin_columns(p, w, top)
            _paint_selection(p, self, body)
            return
        left_side = c.side == "left"
        for row, pin in enumerate(c.pins):
            y = top + row * PIN_H
            has_term = bool(c.pin_terminal(pin))
            # terminal elegido en ESTE pin (no heredado del conector)
            explicit = pin.terminal.strip() not in ("", "-")
            if row % 2:
                p.fillRect(QRectF(1, y, w - 2, PIN_H),
                           QColor(0, 0, 0, 12) if PRINT_MODE
                           else QColor(255, 255, 255, 14))
            if not has_term:
                # cavidad vacía: fondo levemente oscurecido
                p.fillRect(QRectF(1, y, w - 2, PIN_H),
                           QColor(0, 0, 0, 16) if PRINT_MODE else QColor(0, 0, 0, 30))
            elif explicit:
                # terminal asignado a propósito en este pin: banda dorada tenue
                p.fillRect(QRectF(1, y, w - 2, PIN_H),
                           QColor(200, 169, 96, 38))
            num_rect = QRectF(8, y, 26, PIN_H)
            name_rect = QRectF(34, y, w - 40, PIN_H)
            na, ma = Qt.AlignLeft, Qt.AlignLeft
            if left_side:
                num_rect = QRectF(w - 34, y, 26, PIN_H)
                name_rect = QRectF(6, y, w - 40, PIN_H)
                na = ma = Qt.AlignRight
            if c.side in ("right", "left"):
                cir_sz = 8
                cir_x = (w - 5 - cir_sz) if not left_side else 5
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
            # numero: en papel SIEMPRE oscuro (consistente entre conectores;
            # la presencia de terminal ya la indica el circulo solido/punteado).
            p.setPen(_ink("#eceff1" if has_term else "#546e7a", "#1b2730"))
            p.drawText(num_rect, Qt.AlignVCenter | na, pin.number)
            if pin.name:
                p.setPen(_ink("#80deea" if has_term else "#455a64",
                              "#00695c" if has_term else "#5a6b73"))
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
        return HEADER_H + _band_h(_inst_pixmap(self.cable))

    def _first_port_offset(self):
        return self.content_top() + PIN_H / 2

    def body_width(self):
        """Ancho de la caja segun el encabezado (ref · longitud · PN · tipo) y
        los codigos de conductor, nunca menor que BOX_WIDTH."""
        if self._w is None:
            cab = self.cable
            line2 = " · ".join(x for x in (cab.sku, cab.part_number) if x)
            w = _header_width(f"⎓ {cab.ref}", line2,
                              _fmt_len(cab.length_mm), cab.type_label())
            for code in cab.conductor_colors:
                # numero (izq) + swatch (centro) + codigo (der)
                w = max(w, 30 + _text_w(code, True, 8) + 30)
            self._w = max(BOX_WIDTH, w)
        return self._w

    def _build_ports(self):
        for p in self.ports:
            if p.scene():
                p.scene().removeItem(p)
        self.ports = []
        n = self.cable.conductor_count
        top = self.content_top()
        w = self.body_width()
        for i in range(n):
            y = top + i * PIN_H + PIN_H / 2
            lp = PortItem(self, Endpoint("cable", self.cable.id, f"{i}:L"),
                          QPointF(-1, 0))
            lp.setPos(0, y)
            rp = PortItem(self, Endpoint("cable", self.cable.id, f"{i}:R"),
                          QPointF(1, 0))
            rp.setPos(w, y)
            self.ports += [lp, rp]

    def body_height(self):
        return self.content_top() + max(1, self.cable.conductor_count) * PIN_H

    def boundingRect(self):
        m = PIN_NUB_R + 2
        return QRectF(-m, -m, self.body_width() + 2 * m, self.body_height() + 2 * m)

    def port_for(self, port_id: str):
        return next((p for p in self.ports if p.endpoint.port == port_id), None)

    def paint(self, p, option, widget=None):
        cab = self.cable
        w = self.body_width()
        body = QRectF(0, 0, w, self.body_height())
        p.setPen(QPen(_ink("#0d1b22", "#37474f"), 1.5))
        p.setBrush(QBrush(_ink("#212b33", "#ffffff")))
        p.drawRoundedRect(body, 6, 6)

        pm = _inst_pixmap(cab)
        if pm:
            _draw_image_band(p, pm, QRectF(1, HEADER_H, w - 2, IMAGE_BAND))

        # cabecera: ref + longitud (apartado) en linea 1, AWG/hilos en linea 2
        _paint_header(p, QColor("#37474f"), f"⎓ {cab.ref}",
                      cab.part_number, cab.sku,
                      subtitle=_fmt_len(cab.length_mm),
                      subtitle2=cab.type_label(), width=w)

        # filas de conductores con swatch de color
        top = self.content_top()
        f = QFont(); f.setPointSize(8); f.setBold(PRINT_MODE); p.setFont(f)
        for i, code in enumerate(cab.conductor_colors):
            y = top + i * PIN_H
            col = QColor(WIRE_COLORS.get(code, "#888888"))
            # franja de color del conductor de extremo a extremo
            p.fillRect(QRectF(14, y + PIN_H / 2 - 2, w - 28, 4), col)
            # swatch
            p.setBrush(QBrush(col)); p.setPen(QPen(QColor("#0d1b22"), 1))
            p.drawRect(QRectF(w / 2 - 9, y + 4, 18, PIN_H - 8))
            p.setPen(_ink("#eceff1", "#1b2730"))
            p.drawText(QRectF(2, y, 14, PIN_H),
                       Qt.AlignVCenter | Qt.AlignHCenter, str(i + 1))
            p.drawText(QRectF(w - 26, y, 24, PIN_H),
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
        p.setPen(QPen(_ink("#0d1b22", "#37474f"), 1.5))
        p.setBrush(QBrush(_ink(accent.darker(130), "#ffffff")))
        p.drawRoundedRect(body, 4, 4)
        pm = _inst_pixmap(t)
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
        p.setPen(_ink("#eceff1", "#1b2730"))
        p.drawText(QRectF(tx, 2, available * 0.45, TERM_H_H / 2),
                   Qt.AlignVCenter | Qt.AlignLeft, t.ref)

        code = t.sku or t.part_number
        f.setBold(False); f.setPointSize(7); p.setFont(f)
        p.setPen(_ink("#80deea", "#00695c"))
        p.drawText(QRectF(tx + available * 0.45, 2, available * 0.55, TERM_H_H / 2),
                   Qt.AlignVCenter | Qt.AlignRight, code)

        name = t.description or t.part_number
        p.setPen(_ink("#b0bec5", "#546e7a"))
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
        p.setPen(_ink("#eceff1", "#1b2730"))
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
        p.setPen(_ink("#b0bec5", "#546e7a"))
        p.drawText(QRectF(2, y_text, TERM_V_W - 4, 14),
                   Qt.AlignVCenter | Qt.AlignHCenter, name)
        code = t.sku or t.part_number
        p.setPen(_ink("#80deea", "#00695c"))
        p.drawText(QRectF(2, y_text + 14, TERM_V_W - 4, 14),
                   Qt.AlignVCenter | Qt.AlignHCenter, code)


# ===================================================================
#  Cajetin de ensamblaje (tabla terminal<->conector + comentario)
# ===================================================================
NOTE_TITLE_H = 22
NOTE_HEAD_H = 18
NOTE_ROW_H = 16
NOTE_CELL_PAD = 8
NOTE_PAD = 8
NOTE_COMMENT_LH = 13

# etiquetas por defecto de las columnas del cajetin (clave -> nombre visible)
_NOTE_DEF_LABELS = {"item": "Ítem"}
_NOTE_DEF_LABELS.update(dict(ASSEMBLY_FIELDS))


class NoteItem(_NodeMixin, QGraphicsObject):
    """Cajetin colocable: tabla de qué terminal va con qué conector, con
    columnas seleccionables y un comentario libre. Como vive en el lienzo,
    aparece en la hoja del diagrama y en el PDF."""

    def __init__(self, note: Note):
        super().__init__()
        self._init_node(note)
        self.note = note
        self.setZValue(2)

    def refresh(self):
        self.prepareGeometryChange()
        self.update()

    def _label(self, key):
        return self.note.labels.get(key) or _NOTE_DEF_LABELS.get(key, key)

    def _cols(self):
        # "Ítem" siempre primero; luego campos de fábrica seleccionados en su
        # orden, y al final los parámetros personalizados seleccionados.
        sel = self.note.fields or []
        builtin = {k for k, _ in ASSEMBLY_FIELDS}
        keys = ["item"]
        keys += [k for k, _ in ASSEMBLY_FIELDS if k in sel]
        keys += [k for k in sel if k not in builtin and k != "item"]
        return [(k, self._label(k)) for k in keys]

    def _rows(self):
        h = getattr(self.scene(), "harness", None)
        return reports.assembly_block_rows(h) if h is not None else []

    def _comment_lines(self):
        return self.note.comment.splitlines() if self.note.comment else []

    def _layout(self):
        cols = self._cols()
        rows = self._rows()
        widths = []
        for k, lbl in cols:
            w = _text_w(lbl, True, 7)
            for r in rows:
                indent = 10 if (k == "item" and r.get("level")) else 0
                w = max(w, _text_w(str(r.get(k, "")), True, 7) + indent)
            widths.append(w + 2 * NOTE_CELL_PAD)
        table_w = sum(widths)
        clines = self._comment_lines()
        comment_w = max([_text_w(l, False, 7) for l in clines], default=0)
        title_w = _text_w(self.note.title, True, 9)
        w = max(140.0, table_w, comment_w + 2 * NOTE_PAD, title_w + 2 * NOTE_PAD)
        n = max(1, len(rows))
        h = NOTE_TITLE_H + NOTE_HEAD_H + n * NOTE_ROW_H
        if clines:
            h += NOTE_PAD + len(clines) * NOTE_COMMENT_LH + NOTE_PAD // 2
        return w, h, cols, rows, widths, clines

    def boundingRect(self):
        w, h, *_ = self._layout()
        m = 3
        return QRectF(-m, -m, w + 2 * m, h + 2 * m)

    def paint(self, p, option, widget=None):
        w, h, cols, rows, widths, clines = self._layout()
        bg = QColor("#ffffff") if PRINT_MODE else QColor("#16202a")
        edge = _ink("#0d1b22", "#37474f")
        p.setPen(QPen(edge, 1.2))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(QRectF(0, 0, w, h), 4, 4)

        # barra de titulo
        title_fill = _print_tint(QColor("#37474f")) if PRINT_MODE else QColor("#37474f")
        p.setPen(Qt.NoPen)
        path = QPainterPath(); path.addRoundedRect(QRectF(0, 0, w, NOTE_TITLE_H), 4, 4)
        p.fillPath(path, title_fill)
        p.fillRect(QRectF(0, NOTE_TITLE_H - 6, w, 6), title_fill)
        light = title_fill.lightnessF() > 0.6
        p.setPen(QColor("#11181f") if light else QColor("#ffffff"))
        f = QFont(); f.setBold(True); f.setPointSize(9); p.setFont(f)
        p.drawText(QRectF(NOTE_PAD, 0, w - 2 * NOTE_PAD, NOTE_TITLE_H),
                   Qt.AlignVCenter | Qt.AlignLeft, self.note.title)

        # cabecera de columnas
        y = NOTE_TITLE_H
        head_bg = QColor(0, 0, 0, 25) if PRINT_MODE else QColor(255, 255, 255, 18)
        p.fillRect(QRectF(0, y, w, NOTE_HEAD_H), head_bg)
        f.setBold(True); f.setPointSize(7); p.setFont(f)
        p.setPen(_ink("#cfd8dc", "#1b2730"))
        x = 0.0
        for (k, lbl), cw in zip(cols, widths):
            p.drawText(QRectF(x + NOTE_CELL_PAD, y, cw - NOTE_CELL_PAD, NOTE_HEAD_H),
                       Qt.AlignVCenter | Qt.AlignLeft, lbl)
            x += cw
        # filas (conector/cable en negrita; terminal indentado y atenuado)
        y += NOTE_HEAD_H
        grid = _ink("#26323c", "#cfd8dc")
        for i, r in enumerate(rows or [{}]):
            lvl = r.get("level", 0)
            if i % 2:
                p.fillRect(QRectF(0, y, w, NOTE_ROW_H),
                           QColor(0, 0, 0, 10) if PRINT_MODE else QColor(255, 255, 255, 10))
            x = 0.0
            for (k, lbl), cw in zip(cols, widths):
                f.setBold(lvl == 0 or PRINT_MODE); p.setFont(f)
                if lvl == 0:
                    p.setPen(_ink("#e0e6eb", "#11181f"))
                else:
                    p.setPen(_ink("#90a4ae", "#37474f"))
                indent = NOTE_CELL_PAD + (10 if (k == "item" and lvl) else 0)
                p.drawText(QRectF(x + indent, y, cw - indent - 2, NOTE_ROW_H),
                           Qt.AlignVCenter | Qt.AlignLeft, str(r.get(k, "")))
                x += cw
            y += NOTE_ROW_H
        # separadores verticales de columna
        p.setPen(QPen(grid, 0.6))
        x = 0.0
        for cw in widths[:-1]:
            x += cw
            p.drawLine(int(x), NOTE_TITLE_H, int(x), int(y))

        # comentario
        if clines:
            p.setPen(QPen(grid, 0.6))
            p.drawLine(0, int(y), int(w), int(y))
            cy = y + NOTE_PAD // 2
            f.setBold(False); f.setItalic(True); f.setPointSize(7); p.setFont(f)
            p.setPen(_ink("#90a4ae", "#50606a"))
            for line in clines:
                p.drawText(QRectF(NOTE_PAD, cy, w - 2 * NOTE_PAD, NOTE_COMMENT_LH),
                           Qt.AlignVCenter | Qt.AlignLeft, line)
                cy += NOTE_COMMENT_LH
            f.setItalic(False); p.setFont(f)

        _paint_selection(p, self, QRectF(0, 0, w, h))

    def mouseDoubleClickEvent(self, e):
        w, h, cols, rows, widths, clines = self._layout()
        pos = e.pos()
        # doble clic en la fila de cabecera -> renombrar esa columna (estilo KiCad)
        if NOTE_TITLE_H <= pos.y() < NOTE_TITLE_H + NOTE_HEAD_H:
            x = 0.0
            for (k, lbl), cw in zip(cols, widths):
                if x <= pos.x() < x + cw:
                    self._rename_column(k)
                    e.accept()
                    return
                x += cw
        # en cualquier otra parte -> editar el cajetin (campos / título / comentario)
        views = self.scene().views() if self.scene() else []
        if views:
            win = views[0].window()
            if hasattr(win, "edit_note"):
                win.edit_note(self.note)
                e.accept()
                return
        super().mouseDoubleClickEvent(e)

    def _rename_column(self, key):
        from PySide6.QtWidgets import QInputDialog
        cur = self._label(key)
        text, ok = QInputDialog.getText(
            None, "Renombrar columna", f"Nombre de la columna «{key}»:", text=cur)
        if not ok:
            return
        text = text.strip()
        if text and text != _NOTE_DEF_LABELS.get(key, key):
            self.note.labels[key] = text
        else:
            self.note.labels.pop(key, None)
        self.refresh()
        sc = self.scene()
        if sc is not None and hasattr(sc, "changed_model"):
            sc.changed_model.emit()


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


def _paint_header(p, base, ref, part_number, sku, subtitle="", subtitle2="",
                  width=BOX_WIDTH):
    header = QRectF(0, 0, width, HEADER_H)
    # en impresion el encabezado va con fondo claro (tinte del color del
    # componente) y texto oscuro; en pantalla conserva el color pleno.
    fill = _print_tint(base) if PRINT_MODE else QColor(base)
    p.setPen(Qt.NoPen)
    path = QPainterPath()
    path.addRoundedRect(header, 6, 6)
    p.fillPath(path, fill)
    p.fillRect(QRectF(0, HEADER_H - 8, width, 8), fill)
    if PRINT_MODE:
        # linea de acento con el color del componente, para conservar identidad
        p.fillRect(QRectF(0, HEADER_H - 2, width, 2), base)
    # color de texto segun la luminancia del fondo del encabezado, para que el
    # nombre sea legible tanto sobre colores oscuros como claros (y en papel).
    light_fill = fill.lightnessF() > 0.6
    ref_col = QColor("#11181f") if light_fill else QColor("#ffffff")
    line2_col = QColor("#33424c") if light_fill else QColor("#b7c2c9")
    sub_col = QColor("#7a5600") if light_fill else QColor("#ffd180")
    sub2_col = QColor("#4a5a64") if light_fill else QColor("#90a4ae")
    f = QFont(); f.setBold(True); f.setPointSize(9); p.setFont(f)
    p.setPen(ref_col)
    p.drawText(QRectF(6, 1, width - 12, 15), Qt.AlignVCenter | Qt.AlignLeft, ref)
    f.setBold(False); f.setPointSize(7); p.setFont(f)
    if subtitle:
        # badge de longitud, como apartado del nombre
        p.setPen(sub_col)
        p.drawText(QRectF(6, 1, width - 12, 15),
                   Qt.AlignVCenter | Qt.AlignRight, subtitle)
    line2 = " · ".join(x for x in (sku, part_number) if x)
    p.setPen(line2_col)
    p.drawText(QRectF(6, 14, width - 12, 14),
               Qt.AlignVCenter | Qt.AlignLeft, line2)
    if subtitle2:
        p.setPen(sub2_col)
        p.drawText(QRectF(6, 14, width - 12, 14),
                   Qt.AlignVCenter | Qt.AlignRight, subtitle2)


def _paint_selection(p, item, body):
    if not item.isSelected():
        return
    # relleno tenue + borde resaltado para que la seleccion se note de un vistazo
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 179, 0, 45))
    p.drawRoundedRect(body, 6, 6)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor("#ffb300"), 2.5))
    p.drawRoundedRect(body.adjusted(-1.5, -1.5, 1.5, 1.5), 7, 7)


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
        self._outline = None
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
        width = max(2.0, 6.0 - g * 0.15)
        self._pen = QPen(col, width,
                         Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        self.setPen(self._pen)
        # contorno oscuro para hilos muy claros (p.ej. blanco), que si no se
        # pierden sobre el fondo blanco de la hoja
        if col.lightnessF() > 0.7:
            self._outline = QPen(QColor("#222222"), width + 1.6,
                                 Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

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
        # tramo de salida = la MITAD del hueco horizontal: así el control del
        # origen y el del destino se encuentran en el medio sin sobrepasarse
        # (el sobrepaso era lo que doblaba la curva y cruzaba hilos paralelos).
        # Un mínimo pequeño hace que el hilo salga recto del puerto.
        dx = abs(b.x() - a.x())
        off = max(16.0, dx * 0.5)
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
        if getattr(self, "_outline", None) is not None:
            p.setPen(self._outline)
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
