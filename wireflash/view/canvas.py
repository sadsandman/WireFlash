"""Vista del lienzo: QGraphicsView con zoom de rueda y paneo."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsView


class HarnessView(QGraphicsView):
    def __init__(self, scene) -> None:
        super().__init__(scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self._panning = False
        self._pan_start = None
        # auto-encaje: mantiene la hoja encajada/centrada en cada resize (al
        # iniciar, al maximizar, etc.) hasta que el usuario haga zoom o paneo.
        self._auto_fit = True
        self._rb_origin = None          # inicio del rectángulo de selección
        # por defecto: selección por toque (estilo "cruce")
        self.setRubberBandSelectionMode(Qt.IntersectsItemShape)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._auto_fit_now)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._auto_fit_now()

    def _auto_fit_now(self):
        if self._auto_fit and self.viewport().width() > 50 \
                and self.viewport().height() > 50:
            self.fit_page()

    def request_fit(self):
        """Encaja la hoja y reactiva el auto-encaje. Se llama al iniciar, al
        cambiar de hoja/ensamblaje y con la tecla Espacio."""
        self._auto_fit = True
        self.fit_page()

    def _page_rect(self):
        scene = self.scene()
        if scene is None:
            return None
        rect = scene.page_rect() if hasattr(scene, "page_rect") else scene.sceneRect()
        return rect if not rect.isEmpty() else scene.sceneRect()

    def center_on_page(self):
        rect = self._page_rect()
        if rect is not None:
            self.centerOn(rect.center())

    def fit_page(self):
        """Encaja la hoja completa en la vista (centrada y visible)."""
        rect = self._page_rect()
        if rect is not None:
            self.fitInView(rect.adjusted(-40, -40, 40, 40), Qt.KeepAspectRatio)

    def wheelEvent(self, e):
        self._auto_fit = False          # el usuario tomó control del zoom
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._panning = True
            self._auto_fit = False      # el usuario tomó control de la vista (paneo)
            self._pan_start = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            e.accept()
            return
        if e.button() == Qt.LeftButton:
            self._rb_origin = e.position()   # posible inicio de rectángulo
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._panning and self._pan_start is not None:
            delta = e.position() - self._pan_start
            self._pan_start = e.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            e.accept()
            return
        # rectángulo de selección direccional (estilo CAD):
        #   arrastre a la DERECHA  -> solo lo que quede COMPLETAMENTE dentro
        #   arrastre a la IZQUIERDA -> todo lo que TOQUE el rectángulo
        if self._rb_origin is not None and (e.buttons() & Qt.LeftButton):
            if e.position().x() >= self._rb_origin.x():
                self.setRubberBandSelectionMode(Qt.ContainsItemBoundingRect)
            else:
                self.setRubberBandSelectionMode(Qt.IntersectsItemShape)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            e.accept()
            return
        if e.button() == Qt.LeftButton:
            self._rb_origin = None
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        sc = self.scene()
        if e.key() == Qt.Key_Escape:
            sc.cancel_pending()            # cancela conexión en curso...
            sc.clearSelection()            # ...y deselecciona todo
        elif e.key() == Qt.Key_Space:
            self.request_fit()             # encajar la hoja y reactivar auto-encaje
        elif e.key() == Qt.Key_X and hasattr(sc, "flip_selected"):
            sc.flip_selected("h")          # voltear izquierda <-> derecha
        elif e.key() == Qt.Key_Y and hasattr(sc, "flip_selected"):
            sc.flip_selected("v")          # voltear arriba <-> abajo
        elif e.key() == Qt.Key_E:
            win = self.window()            # E -> editar/propiedades del seleccionado
            if hasattr(win, "edit_selected"):
                win.edit_selected()
        elif e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and \
                hasattr(sc, "delete_selected"):
            sc.delete_selected()           # Supr -> borra lo seleccionado
        else:
            super().keyPressEvent(e)
            return
        e.accept()

    # --- drag & drop desde la libreria ---
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat("application/x-rh-part"):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat("application/x-rh-part"):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasFormat("application/x-rh-part"):
            spec = bytes(e.mimeData().data("application/x-rh-part")).decode()
            pos = self.mapToScene(e.position().toPoint())
            self.window().drop_component(spec, pos)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)
