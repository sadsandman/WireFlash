"""Plantillas de hoja para el PDF: marco (bordes) + cajetín empresarial.

Dos modos:
  * **Genérica** (dibujada por código): borde + cajetín en la esquina inferior
    con Proyecto / Ensamblaje / Autor / Versión / Fecha / Hoja y logo opcional.
    Se adapta a cualquier tamaño y orientación sin deformarse.
  * **SVG** importado por el usuario: se renderiza estirado a la hoja. El
    programa **sobreescribe** ciertos textos del SVG con los datos del proyecto
    mediante *placeholders* (ver NORMA abajo).

NORMA de la plantilla SVG (placeholders de texto, sustituidos antes de dibujar):
    {{project}}   nombre del proyecto
    {{assembly}}  nombre del ensamblaje (cable)
    {{author}}    autor (del proyecto)
    {{version}}   versión (del proyecto)
    {{date}}      fecha de exportación
    {{page}}      número de hoja
    {{pages}}     total de hojas
Coloca cada token como contenido de un elemento <text> en tu SVG; el programa
lo reemplaza por el valor configurado en el proyecto.

Área de contenido del SVG (dónde van el BOM o el diagrama): dibuja en tu SVG un
  <rect id="content" x=".." y=".." width=".." height=".."/>
(invisible: fill="none" stroke="none"). El programa usa ese rectángulo como
zona útil. Si no existe, usa márgenes por defecto.
"""

from __future__ import annotations

import html as _html
import os
import xml.etree.ElementTree as ET

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPen

# Tamaños soportados -> id de QPageSize (acceso plano, como el resto del código)
from PySide6.QtGui import QPageSize

PAGE_SIZES: dict[str, object] = {
    "A4": QPageSize.A4,
    "A3": QPageSize.A3,
    "A2": QPageSize.A2,
    "A1": QPageSize.A1,
}

# márgenes por defecto (mm) del área de contenido cuando no se especifica
_DEF_TOP, _DEF_SIDE, _DEF_BOTTOM = 12.0, 12.0, 40.0
# marco genérico
_BORDER_MM = 8.0
_TITLE_MM = 30.0

_PLACEHOLDERS = ("project", "assembly", "author", "version", "date", "page", "pages")


def _mm(v: float, dpi: float) -> float:
    return v / 25.4 * dpi


def page_size_mm(page_name: str, landscape: bool = False) -> tuple[float, float]:
    """Tamaño (ancho, alto) en milímetros de una hoja, según orientación."""
    qs = QPageSize(PAGE_SIZES.get(page_name, QPageSize.A4))
    s = qs.size(QPageSize.Millimeter)
    w, h = s.width(), s.height()
    if landscape:
        w, h = h, w
    return w, h


def substitute_svg(svg_text: str, fields: dict) -> str:
    """Reemplaza los placeholders {{token}} por los valores (XML-escapados)."""
    out = svg_text
    for key in _PLACEHOLDERS:
        val = _html.escape(str(fields.get(key, "")))
        out = out.replace("{{%s}}" % key, val).replace("{{ %s }}" % key, val)
    return out


class FrameTemplate:
    def __init__(self, svg_text: str | None = None, logo_path: str = "") -> None:
        self.svg_text = svg_text          # None -> plantilla genérica
        self.logo_path = logo_path

    @classmethod
    def generic(cls, logo_path: str = "") -> "FrameTemplate":
        return cls(None, logo_path)

    @classmethod
    def from_svg(cls, path: str) -> "FrameTemplate":
        with open(path, encoding="utf-8") as f:
            return cls(f.read())

    # ---- zona útil para el contenido (BOM/diagrama) -----------------
    def content_rect(self, page: QRectF, dpi: float) -> QRectF:
        if self.svg_text is None:
            x = page.x() + _mm(_BORDER_MM + 3, dpi)
            y = page.y() + _mm(_BORDER_MM + 3, dpi)
            w = page.width() - 2 * _mm(_BORDER_MM + 3, dpi)
            h = page.height() - _mm(_BORDER_MM + 3, dpi) - _mm(_TITLE_MM + 6, dpi)
            return QRectF(x, y, w, h)
        rc = self._svg_content_rect(page)
        if rc is not None:
            return rc
        x = page.x() + _mm(_DEF_SIDE, dpi)
        y = page.y() + _mm(_DEF_TOP, dpi)
        w = page.width() - 2 * _mm(_DEF_SIDE, dpi)
        h = page.height() - _mm(_DEF_TOP, dpi) - _mm(_DEF_BOTTOM, dpi)
        return QRectF(x, y, w, h)

    def _svg_content_rect(self, page: QRectF) -> QRectF | None:
        try:
            root = ET.fromstring(self.svg_text)
        except ET.ParseError:
            return None
        vb = root.get("viewBox")
        if vb:
            minx, miny, vw, vh = (float(t) for t in vb.replace(",", " ").split())
        else:
            vw = float(root.get("width", "0") or 0)
            vh = float(root.get("height", "0") or 0)
            minx = miny = 0.0
        if not vw or not vh:
            return None
        node = None
        for el in root.iter():
            if el.get("id") == "content":
                node = el
                break
        if node is None:
            return None
        try:
            x = float(node.get("x", "0")); y = float(node.get("y", "0"))
            w = float(node.get("width", "0")); h = float(node.get("height", "0"))
        except ValueError:
            return None
        sx = page.width() / vw
        sy = page.height() / vh
        return QRectF(page.x() + (x - minx) * sx, page.y() + (y - miny) * sy,
                      w * sx, h * sy)

    # ---- dibujo del marco -------------------------------------------
    def draw(self, painter, page: QRectF, dpi: float, fields: dict,
             text_scale: float = 1.0) -> None:
        if self.svg_text is None:
            self._draw_generic(painter, page, dpi, fields, text_scale)
        else:
            from PySide6.QtCore import QByteArray
            from PySide6.QtSvg import QSvgRenderer
            svg = substitute_svg(self.svg_text, fields).encode("utf-8")
            renderer = QSvgRenderer(QByteArray(svg))
            if renderer.isValid():
                renderer.render(painter, page)

    def _draw_generic(self, painter, page: QRectF, dpi: float, fields: dict,
                      text_scale: float = 1.0) -> None:
        painter.save()
        ink = QColor("#222222")
        painter.setPen(QPen(ink, max(1.0, _mm(0.4, dpi))))
        painter.setBrush(Qt.NoBrush)
        b = _mm(_BORDER_MM, dpi)
        border = QRectF(page.x() + b, page.y() + b,
                        page.width() - 2 * b, page.height() - 2 * b)
        painter.drawRect(border)

        # ---- cajetín (esquina inferior, ancho completo del marco) ----
        th = _mm(_TITLE_MM, dpi)
        tb = QRectF(border.x(), border.bottom() - th, border.width(), th)
        painter.drawRect(tb)

        logo_w = th  # celda cuadrada para el logo
        # líneas verticales: logo | bloque de campos
        painter.drawLine(int(tb.x() + logo_w), int(tb.y()),
                         int(tb.x() + logo_w), int(tb.bottom()))

        # logo
        logo = self.logo_path or fields.get("logo", "")
        if logo and os.path.exists(logo):
            img = QImage(logo)
            if not img.isNull():
                pad = _mm(2, dpi)
                cell = QRectF(tb.x() + pad, tb.y() + pad,
                              logo_w - 2 * pad, th - 2 * pad)
                scaled = img.scaled(int(cell.width()), int(cell.height()),
                                    Qt.KeepAspectRatio, Qt.SmoothTransformation)
                painter.drawImage(
                    QRectF(cell.x() + (cell.width() - scaled.width()) / 2,
                           cell.y() + (cell.height() - scaled.height()) / 2,
                           scaled.width(), scaled.height()), scaled)
        else:
            f = QFont(); f.setPointSizeF(8 * text_scale); painter.setFont(f)
            painter.drawText(QRectF(tb.x(), tb.y(), logo_w, th),
                             Qt.AlignCenter, "LOGO")

        # ---- campos del cajetín ----
        fields_area = QRectF(tb.x() + logo_w, tb.y(),
                             tb.width() - logo_w, th)
        rows = [
            [("Proyecto", fields.get("project", "")),
             ("Ensamblaje", fields.get("assembly", ""))],
            [("Autor", fields.get("author", "")),
             ("Versión", fields.get("version", ""))],
            [("Fecha", fields.get("date", "")),
             ("Hoja", f"{fields.get('page', '')}/{fields.get('pages', '')}")],
        ]
        rh = fields_area.height() / len(rows)
        for ri, row in enumerate(rows):
            cy = fields_area.y() + ri * rh
            if ri:
                painter.setPen(QPen(ink, max(0.5, _mm(0.2, dpi))))
                painter.drawLine(int(fields_area.x()), int(cy),
                                 int(fields_area.right()), int(cy))
            cw = fields_area.width() / len(row)
            for ci, (label, value) in enumerate(row):
                cx = fields_area.x() + ci * cw
                if ci:
                    painter.drawLine(int(cx), int(cy), int(cx), int(cy + rh))
                lf = QFont(); lf.setPointSizeF(6 * text_scale)
                painter.setPen(QColor("#555555")); painter.setFont(lf)
                painter.drawText(
                    QRectF(cx + _mm(1.5, dpi), cy + _mm(0.5, dpi), cw, rh / 2),
                    Qt.AlignLeft | Qt.AlignVCenter, label)
                vf = QFont(); vf.setPointSizeF(9 * text_scale)
                painter.setPen(ink); painter.setFont(vf)
                painter.drawText(
                    QRectF(cx + _mm(1.5, dpi), cy + rh / 2 - _mm(0.5, dpi),
                           cw - _mm(2, dpi), rh / 2),
                    Qt.AlignLeft | Qt.AlignVCenter, str(value))
        painter.restore()
