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


def _bom_doc(h, content: QRectF, rows, title: str, pt: int = 9) -> QTextDocument:
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Helvetica", pt))
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
# Resolución de referencia del diseño: las unidades de la escena se tratan como
# píxeles a 96 dpi. Así cada componente se imprime SIEMPRE al mismo tamaño
# físico sin importar cuántos haya: un diagrama pequeño ya no se amplía para
# llenar la hoja (solo se reduce si no cabe).
_DESIGN_DPI = 96.0


def _draw_diagram(painter, h, page: QRectF, content: QRectF, dpi: float,
                  title: str, page_name: str = "A4", landscape: bool = False,
                  diagram_scale: float = 1.0) -> None:
    """Dibuja el diagrama del ensamblaje **sin rejilla**, rasterizado a la
    resolución de destino del PDF (nítido) y con las proporciones de texto
    correctas (las fuentes en puntos no se deforman como al pintar vectorial
    sobre un dispositivo de alta resolución).

    WYSIWYG: la HOJA del diseño (``page_rect``) se mapea **1:1** sobre la página
    del PDF, de modo que cada componente sale en la MISMA posición y tamaño
    (relativos a la hoja) que en el software, sin depender de cuántos haya. Los
    componentes se pintan con fondo transparente ENCIMA del marco/cajetín que ya
    dibujó la plantilla, igual que en el lienzo."""
    painter.save()
    head_h = _mm(8, dpi)
    f = QFont("Helvetica", 11); f.setBold(True)
    painter.setFont(f); painter.setPen(QColor("#222222"))
    painter.drawText(QRectF(content.x(), content.y(), content.width(), head_h),
                     Qt.AlignLeft | Qt.AlignVCenter, title)

    s = HarnessScene(h)
    s.draw_grid = False
    s.show_frame = False
    s.page_name = page_name
    s.landscape = landscape
    # fondo transparente: solo se rasterizan los componentes (el papel blanco del
    # PDF y el marco/cajetín ya dibujados quedan debajo).
    s.setBackgroundBrush(QColor(0, 0, 0, 0))
    # región fuente = la hoja completa del diseño (constante).
    src = s.page_rect()

    # escala de PRESENTACIÓN: la hoja del diseño se mapea a la página del PDF
    # (1:1). El % del diagrama actúa como zoom adicional (puede recortar bordes).
    disp = min(page.width() / src.width(),
               page.height() / src.height()) * diagram_scale
    tw = src.width() * disp
    th = src.height() * disp

    # resolución del RASTER, independiente del tamaño en página: se limita para no
    # crear imágenes gigantes en dispositivos de alto dpi (p.ej. la vista previa a
    # 1200 dpi), SIN afectar el tamaño impreso (la imagen se escala al target).
    raster = min(disp, _DIAGRAM_MAX_PX / max(src.width(), src.height()))
    w = max(1, int(src.width() * raster))
    hpx = max(1, int(src.height() * raster))
    img = QImage(w, hpx, QImage.Format_ARGB32)
    img.fill(Qt.transparent)   # solo los componentes; el marco/cajetín va debajo
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

    # centrado en la página; recortado a la página para no salirse del papel.
    painter.setClipRect(page)
    target = QRectF(page.x() + (page.width() - tw) / 2,
                    page.y() + (page.height() - th) / 2, tw, th)
    painter.drawImage(target, img)
    painter.restore()


def _render_to_device(device, assemblies, fields_base: dict, *,
                      page_name: str, landscape: bool,
                      template: FrameTemplate | None,
                      bom_pt: int = 9, title_scale: float = 1.0,
                      diagram_scale: float = 1.0) -> None:
    """Pinta todas las páginas (BOM + diagrama) en ``device`` (un QPdfWriter o
    un QPrinter): así el PDF y la vista previa de impresión comparten el mismo
    render. El llamador ya debe haber fijado tamaño/orientación de página."""
    template = template or FrameTemplate.generic(fields_base.get("logo", ""))
    dpi = device.resolution()
    page = QRectF(0, 0, device.width(), device.height())
    content = template.content_rect(page, dpi)

    base = dict(fields_base)
    base.setdefault("date", date.today().isoformat())

    # descriptores de página: (nombre_ensamblaje, doc|None, idx_pag, harness|None)
    #   1) BOM de compras (totales sumados) · 2) diagrama (con cajetín de armado).
    descriptors: list[tuple] = []
    for h in assemblies:
        compras = _bom_doc(h, content, reports.purchase_bom(h),
                           "Lista de materiales — Compras (totales)", bom_pt)
        for pi in range(max(1, compras.pageCount())):
            descriptors.append((h.name, compras, pi, None))
        descriptors.append((h.name, None, 0, h))
    total = len(descriptors)

    painter = QPainter(device)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    try:
        for idx, (aname, doc, pi, diagram_h) in enumerate(descriptors):
            if idx > 0:
                device.newPage()
            fields = dict(base)
            fields.update(assembly=aname, page=idx + 1, pages=total)
            template.draw(painter, page, dpi, fields, title_scale)
            if doc is not None:
                _draw_doc_page(painter, doc, content, pi)
            else:
                _draw_diagram(painter, diagram_h, page, content, dpi,
                              f"{aname} — Diagrama", page_name, landscape,
                              diagram_scale)
    finally:
        painter.end()


def _apply_page(device, page_name: str, landscape: bool) -> None:
    device.setPageSize(QPageSize(PAGE_SIZES.get(page_name, QPageSize.A4)))
    device.setPageOrientation(
        QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    device.setPageMargins(QMarginsF(0, 0, 0, 0))


def export_pdf(assemblies, path: str, fields_base: dict, *,
               page_name: str = "A4", landscape: bool = False,
               template: FrameTemplate | None = None,
               bom_pt: int = 9, title_scale: float = 1.0,
               diagram_scale: float = 1.0) -> None:
    """Genera el PDF. ``fields_base`` lleva project/author/version (y opcional
    logo); ``assembly``, ``page`` y ``pages`` los completa esta función."""
    writer = QPdfWriter(path)
    _apply_page(writer, page_name, landscape)
    writer.setResolution(300)
    _render_to_device(writer, assemblies, fields_base,
                       page_name=page_name, landscape=landscape,
                       template=template, bom_pt=bom_pt,
                       title_scale=title_scale, diagram_scale=diagram_scale)


def preview_pdf(parent, assemblies, fields_base: dict, *,
                page_name: str = "A4", landscape: bool = False,
                template: FrameTemplate | None = None,
                bom_pt: int = 9, title_scale: float = 1.0,
                diagram_scale: float = 1.0) -> None:
    """Abre una vista previa de impresión (mismas páginas que el PDF). Desde el
    diálogo se puede imprimir o guardar como PDF con el botón de impresora."""
    from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog

    printer = QPrinter(QPrinter.HighResolution)
    _apply_page(printer, page_name, landscape)

    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle("Vista previa de impresión")
    dlg.paintRequested.connect(
        lambda pr: _render_to_device(pr, assemblies, fields_base,
                                     page_name=page_name, landscape=landscape,
                                     template=template, bom_pt=bom_pt,
                                     title_scale=title_scale,
                                     diagram_scale=diagram_scale))
    try:
        dlg.resize(int(parent.width() * 0.8), int(parent.height() * 0.85))
    except Exception:
        pass
    dlg.exec()
