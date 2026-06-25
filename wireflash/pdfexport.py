"""Exportación a PDF con plantilla de hoja (marco + cajetín).

Por cada ensamblaje: una o varias páginas de **BOM** y una página de
**diagrama**. Cada hoja lleva el marco/cajetín de la plantilla elegida
(genérica o SVG), con los datos del proyecto sobrescritos.
"""

from __future__ import annotations

import html
from datetime import date

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QTextDocument,
)

from . import reports
from .scene import HarnessScene
from .templates import PAGE_SIZES, FrameTemplate

_MAX_IMG_PX = 2400


def _mm(v: float, dpi: float) -> float:
    return v / 25.4 * dpi


# ---- diagrama del ensamblaje a imagen (fondo blanco) -------------------
def _render_harness_image(h, scale: float = 2.0) -> QImage:
    s = HarnessScene(h)
    s.setBackgroundBrush(QColor("white"))
    s.grid_color = QColor("#e3e3e3")
    rect = s.itemsBoundingRect()
    if rect.isEmpty():
        rect = QRectF(0, 0, 600, 300)
    rect = rect.adjusted(-20, -20, 20, 20)
    longest = max(rect.width(), rect.height()) or 1
    scale = min(scale, _MAX_IMG_PX / longest)
    w = max(1, int(rect.width() * scale))
    hpx = max(1, int(rect.height() * scale))
    img = QImage(w, hpx, QImage.Format_ARGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s.render(p, QRectF(0, 0, w, hpx), rect)
    p.end()
    return img


# ---- BOM como documento paginable --------------------------------------
def _bom_html(h) -> str:
    rows = reports.bill_of_materials(h)
    body = []
    for r in rows:
        ind = "&nbsp;&nbsp;&nbsp;&nbsp;" if r.level == 1 else ""
        qty = f"{r.qty:g}" if isinstance(r.qty, float) else str(r.qty)
        body.append(
            "<tr>"
            f"<td>{html.escape(r.category)}</td>"
            f"<td>{html.escape(r.sku)}</td>"
            f"<td>{ind}{html.escape(r.item)}</td>"
            f"<td>{html.escape(r.description)}</td>"
            f"<td align='right'>{qty}</td>"
            f"<td>{html.escape(r.unit)}</td>"
            "</tr>")
    head = ("<tr><th>Categoría</th><th>SKU</th><th>Item</th>"
            "<th>Descripción</th><th>Cant.</th><th>Ud</th></tr>")
    return ("<table border='1' cellspacing='0' cellpadding='4' width='100%'>"
            f"{head}{''.join(body)}</table>")


def _bom_doc(h, content: QRectF) -> QTextDocument:
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Helvetica", 9))
    doc.setPageSize(QSizeF(content.width(), content.height()))
    doc.setHtml(
        f"<h2>{html.escape(h.name)}</h2>"
        f"<h3>Lista de materiales (BOM)</h3>{_bom_html(h)}")
    return doc


def _draw_doc_page(painter, doc, content: QRectF, page_index: int) -> None:
    painter.save()
    painter.translate(content.x(), content.y())
    painter.setClipRect(QRectF(0, 0, content.width(), content.height()))
    painter.translate(0, -page_index * content.height())
    doc.drawContents(painter)
    painter.restore()


def _draw_diagram(painter, img: QImage, content: QRectF, dpi: float,
                  title: str) -> None:
    painter.save()
    head_h = _mm(8, dpi)
    f = QFont("Helvetica", 11); f.setBold(True)
    painter.setFont(f); painter.setPen(QColor("#222222"))
    painter.drawText(QRectF(content.x(), content.y(), content.width(), head_h),
                     Qt.AlignLeft | Qt.AlignVCenter, title)
    area = QRectF(content.x(), content.y() + head_h,
                  content.width(), content.height() - head_h)
    iw, ih = img.width() or 1, img.height() or 1
    scale = min(area.width() / iw, area.height() / ih)
    w, hpx = iw * scale, ih * scale
    target = QRectF(area.x() + (area.width() - w) / 2, area.y(), w, hpx)
    painter.drawImage(target, img)
    painter.restore()


def export_pdf(assemblies, path: str, fields_base: dict, *,
               page_name: str = "A4", landscape: bool = False,
               template: FrameTemplate | None = None) -> None:
    """Genera el PDF. ``fields_base`` lleva project/author/version (y opcional
    logo); ``assembly``, ``page`` y ``pages`` los completa esta función."""
    template = template or FrameTemplate.generic(fields_base.get("logo", ""))

    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(PAGE_SIZES.get(page_name, QPageSize.A4)))
    writer.setPageOrientation(
        QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    writer.setResolution(150)
    dpi = writer.resolution()
    page = QRectF(0, 0, writer.width(), writer.height())
    content = template.content_rect(page, dpi)

    base = dict(fields_base)
    base.setdefault("date", date.today().isoformat())

    # descriptores de página: (nombre_ensamblaje, doc|None, idx_pag, img|None)
    descriptors: list[tuple] = []
    for h in assemblies:
        doc = _bom_doc(h, content)
        for pi in range(max(1, doc.pageCount())):
            descriptors.append((h.name, doc, pi, None))
        descriptors.append((h.name, None, 0, _render_harness_image(h)))
    total = len(descriptors)

    painter = QPainter(writer)
    painter.setRenderHint(QPainter.Antialiasing)
    try:
        for idx, (aname, doc, pi, img) in enumerate(descriptors):
            if idx > 0:
                writer.newPage()
            fields = dict(base)
            fields.update(assembly=aname, page=idx + 1, pages=total)
            template.draw(painter, page, dpi, fields)
            if doc is not None:
                _draw_doc_page(painter, doc, content, pi)
            else:
                _draw_diagram(painter, img, content, dpi,
                              f"{aname} — Diagrama")
    finally:
        painter.end()
