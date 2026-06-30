"""Iconos vectoriales generados en runtime (sin archivos externos).

Cada funcion devuelve un QIcon dibujado con QPainter sobre un QPixmap
transparente, con estilo plano tipo KiCad. Se usan colores de tono medio para
que contrasten tanto en una barra clara como oscura. Asi la barra de
herramientas no depende de recursos en disco y es facil agregar mas iconos.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF)

_SZ = 24


def _make(draw) -> QIcon:
    pm = QPixmap(_SZ, _SZ)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw(p)
    p.end()
    return QIcon(pm)


def _stroke(p, color, w=1.7):
    pen = QPen(QColor(color), w)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)


# --- archivo / proyecto ---------------------------------------------------
def new_icon() -> QIcon:
    def d(p):
        _stroke(p, "#1976d2")
        path = QPainterPath()
        path.moveTo(6, 3); path.lineTo(14, 3); path.lineTo(18, 7)
        path.lineTo(18, 21); path.lineTo(6, 21); path.closeSubpath()
        p.drawPath(path)
        p.drawLine(14, 3, 14, 7); p.drawLine(14, 7, 18, 7)
    return _make(d)


def open_icon() -> QIcon:
    def d(p):
        p.setPen(QPen(QColor("#ef6c00"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QBrush(QColor("#ffb74d")))
        path = QPainterPath()
        path.moveTo(3, 7); path.lineTo(9, 7); path.lineTo(11, 9)
        path.lineTo(21, 9); path.lineTo(21, 19); path.lineTo(3, 19)
        path.closeSubpath()
        p.drawPath(path)
    return _make(d)


def save_icon() -> QIcon:
    def d(p):
        p.setPen(QPen(QColor("#00838f"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QBrush(QColor("#4dd0e1")))
        path = QPainterPath()
        path.moveTo(4, 4); path.lineTo(18, 4); path.lineTo(20, 6)
        path.lineTo(20, 20); path.lineTo(4, 20); path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawRect(QRectF(8, 4, 8, 6))      # obturador
        p.drawRect(QRectF(7, 13, 10, 7))    # etiqueta
    return _make(d)


def pdf_icon() -> QIcon:
    def d(p):
        p.setPen(QPen(QColor("#c62828"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QBrush(QColor("#ef9a9a")))
        path = QPainterPath()
        path.moveTo(6, 3); path.lineTo(14, 3); path.lineTo(18, 7)
        path.lineTo(18, 21); path.lineTo(6, 21); path.closeSubpath()
        p.drawPath(path)
        f = p.font(); f.setPointSize(6); f.setBold(True); p.setFont(f)
        p.setPen(QColor("#b71c1c"))
        p.drawText(QRectF(4, 11, 16, 9), Qt.AlignCenter, "PDF")
    return _make(d)


# --- vista previa de impresión -------------------------------------------
def preview_icon() -> QIcon:
    def d(p):
        # hoja
        p.setPen(QPen(QColor("#455a64"), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QBrush(QColor("#eceff1")))
        path = QPainterPath()
        path.moveTo(5, 3); path.lineTo(13, 3); path.lineTo(17, 7)
        path.lineTo(17, 20); path.lineTo(5, 20); path.closeSubpath()
        p.drawPath(path)
        # lupa
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#1976d2"), 1.8))
        p.drawEllipse(QRectF(11, 11, 7, 7))
        p.setPen(QPen(QColor("#1976d2"), 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(17, 17, 21, 21)
    return _make(d)


# --- voltear (mirror) -----------------------------------------------------
def _flip(p, horizontal: bool):
    p.setPen(QPen(QColor("#90a4ae"), 1.0, Qt.DashLine))
    if horizontal:
        p.drawLine(12, 3, 12, 21)
    else:
        p.drawLine(3, 12, 21, 12)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#2e7d32")))
    if horizontal:
        p.drawPolygon(QPolygonF([QPointF(10, 7), QPointF(10, 17), QPointF(3, 12)]))
        p.drawPolygon(QPolygonF([QPointF(14, 7), QPointF(14, 17), QPointF(21, 12)]))
    else:
        p.drawPolygon(QPolygonF([QPointF(7, 10), QPointF(17, 10), QPointF(12, 3)]))
        p.drawPolygon(QPolygonF([QPointF(7, 14), QPointF(17, 14), QPointF(12, 21)]))


# --- actualizar / sincronizar desde librerías ----------------------------
def sync_icon() -> QIcon:
    def d(p):
        p.setPen(QPen(QColor("#00838f"), 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        rect = QRectF(5, 5, 14, 14)
        p.drawArc(rect, 55 * 16, 150 * 16)     # arco superior
        p.drawArc(rect, 235 * 16, 150 * 16)    # arco inferior
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#00838f")))
        # puntas de flecha en los extremos para sugerir el giro
        p.drawPolygon(QPolygonF([QPointF(18.5, 6.0), QPointF(20.0, 11.0),
                                 QPointF(14.8, 9.6)]))
        p.drawPolygon(QPolygonF([QPointF(5.5, 18.0), QPointF(4.0, 13.0),
                                 QPointF(9.2, 14.4)]))
    return _make(d)


def flip_h_icon() -> QIcon:
    return _make(lambda p: _flip(p, True))


def flip_v_icon() -> QIcon:
    return _make(lambda p: _flip(p, False))


# --- encajar hoja ---------------------------------------------------------
def fit_icon() -> QIcon:
    def d(p):
        _stroke(p, "#455a64", 1.6)
        p.drawRect(QRectF(4, 5, 16, 14))
        p.setPen(QPen(QColor("#2e7d32"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        # flechas hacia las esquinas
        p.drawLine(8, 9, 11, 12); p.drawLine(8, 9, 8, 11); p.drawLine(8, 9, 10, 9)
        p.drawLine(16, 15, 13, 12); p.drawLine(16, 15, 16, 13); p.drawLine(16, 15, 14, 15)
    return _make(d)
