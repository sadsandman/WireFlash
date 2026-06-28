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

from ..model import reports
from ..view import items
from ..view.scene import HarnessScene
from ..model.templates import PAGE_SIZES, FrameTemplate

def _mm(v: float, dpi: float) -> float:
    return v / 25.4 * dpi


# ---- BOM como documento paginable --------------------------------------
def _bom_html(rows) -> str:
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


def _bom_doc(h, content: QRectF, rows, title: str) -> QTextDocument:
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Helvetica", 9))
    doc.setPageSize(QSizeF(content.width(), content.height()))
    doc.setHtml(
        f"<h2>{html.escape(h.name)}</h2>"
        f"<h3>{html.escape(title)}</h3>{_bom_html(rows)}")
    return doc


def _draw_doc_page(painter, doc, content: QRectF, page_index: int) -> None:
    painter.save()
    painter.translate(content.x(), content.y())
    painter.setClipRect(QRectF(0, 0, content.width(), content.height()))
    painter.translate(0, -page_index * content.height())
    doc.drawContents(painter)
    painter.restore()


_DIAGRAM_MAX_PX = 6000  # tope de seguridad para hojas grandes (A1/A2)


def _draw_diagram(painter, h, content: QRectF, dpi: float,
                  title: str) -> None:
    """Dibuja el diagrama del ensamblaje **sin rejilla**, rasterizado a la
    resolución de destino del PDF (nítido) y con las proporciones de texto
    correctas (las fuentes en puntos no se deforman como al pintar vectorial
    sobre un dispositivo de alta resolución)."""
    painter.save()
    head_h = _mm(8, dpi)
    f = QFont("Helvetica", 11); f.setBold(True)
    painter.setFont(f); painter.setPen(QColor("#222222"))
    painter.drawText(QRectF(content.x(), content.y(), content.width(), head_h),
                     Qt.AlignLeft | Qt.AlignVCenter, title)
    area = QRectF(content.x(), content.y() + head_h,
                  content.width(), content.height() - head_h)

    s = HarnessScene(h)
    s.draw_grid = False
    s.show_frame = False
    s.setBackgroundBrush(QColor("white"))
    src = s.itemsBoundingRect()
    if src.isEmpty():
        src = QRectF(0, 0, 600, 300)
    src = src.adjusted(-20, -20, 20, 20)

    # encaje manteniendo proporción; la imagen se renderiza a los píxeles
    # reales del destino en el PDF (1:1) -> sin pixelado
    fit = min(area.width() / src.width(), area.height() / src.height())
    fit = min(fit, _DIAGRAM_MAX_PX / max(src.width(), src.height()))
    w = max(1, int(src.width() * fit))
    hpx = max(1, int(src.height() * fit))
    img = QImage(w, hpx, QImage.Format_ARGB32)
    img.fill(Qt.white)
    ip = QPainter(img)
    ip.setRenderHint(QPainter.Antialiasing)
    ip.setRenderHint(QPainter.TextAntialiasing)
    ip.setRenderHint(QPainter.SmoothPixmapTransform)
    # modo impresion: componentes con fondo claro y texto oscuro (legible en papel)
    items.set_print_mode(True)
    try:
        s.render(ip, QRectF(0, 0, w, hpx), src)
    finally:
        items.set_print_mode(False)
    ip.end()

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
    writer.setResolution(300)
    dpi = writer.resolution()
    page = QRectF(0, 0, writer.width(), writer.height())
    content = template.content_rect(page, dpi)

    base = dict(fields_base)
    base.setdefault("date", date.today().isoformat())

    # descriptores de página: (nombre_ensamblaje, doc|None, idx_pag, harness|None)
    #   1) BOM de compras (totales sumados) · 2) BOM de armado (qué va con qué,
    #   terminales bajo su conector) · 3) diagrama.
    descriptors: list[tuple] = []
    for h in assemblies:
        compras = _bom_doc(h, content, reports.purchase_bom(h),
                           "Lista de materiales — Compras (totales)")
        for pi in range(max(1, compras.pageCount())):
            descriptors.append((h.name, compras, pi, None))
        # el detalle "qué va con qué" (terminal↔conector) NO va como hoja
        # aparte: se coloca como cajetín en la hoja del diagrama (ver NoteItem).
        descriptors.append((h.name, None, 0, h))
    total = len(descriptors)

    painter = QPainter(writer)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    try:
        for idx, (aname, doc, pi, diagram_h) in enumerate(descriptors):
            if idx > 0:
                writer.newPage()
            fields = dict(base)
            fields.update(assembly=aname, page=idx + 1, pages=total)
            template.draw(painter, page, dpi, fields)
            if doc is not None:
                _draw_doc_page(painter, doc, content, pi)
            else:
                _draw_diagram(painter, diagram_h, content, dpi,
                              f"{aname} — Diagrama")
    finally:
        painter.end()
