"""문서 표시 영역: 워드처럼 페이지가 세로로 이어지고, 보이는 페이지만 렌더링한다."""
from __future__ import annotations

from collections import OrderedDict

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from core import TextLine

MARGIN = 28  # 문서 영역 바깥 여백(px)
GAP = 16     # 페이지 사이 간격(px)
CACHE_PAGES = 10
BG = QColor("#E3E3E3")


class DocumentCanvas(QWidget):
    hovered = Signal(int, QPointF)   # (페이지, PDF 좌표 pt) — 페이지 밖이면 -1
    pressed = Signal(int, QPointF)
    moved = Signal(int, QPointF)
    released = Signal(int, QPointF)
    zoomWheel = Signal(int)          # Ctrl+휠: +1 확대 / -1 축소

    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.zoom = 1.25
        self.hover_line: tuple[int, TextLine] | None = None
        self.drag: dict | None = None  # {page, kind, a, b, color, width}
        self._doc: pymupdf.Document | None = None
        self._sizes: list[tuple[float, float]] = []
        self._tops: list[int] = []
        self._cache: OrderedDict[int, QPixmap] = OrderedDict()
        self._press_page: int | None = None

    # ---------- 문서/레이아웃 ----------
    def set_document(self, doc: pymupdf.Document | None) -> None:
        self._doc = doc
        self._sizes = [(p.rect.width, p.rect.height) for p in doc] if doc else []
        self._cache.clear()
        self.hover_line = None
        self.drag = None
        self.relayout()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = zoom
        self._cache.clear()
        self.relayout()

    def invalidate(self, page: int | None = None) -> None:
        if page is None:
            self._cache.clear()
        else:
            self._cache.pop(page, None)
        self.update()

    def relayout(self) -> None:
        y, tops = MARGIN, []
        for _, h in self._sizes:
            tops.append(y)
            y += int(h * self.zoom) + GAP
        self._tops = tops
        max_w = max((w for w, _ in self._sizes), default=0)
        self.setMinimumSize(int(max_w * self.zoom) + 2 * MARGIN, y + MARGIN - GAP)
        self.update()

    def page_top(self, index: int) -> int:
        return self._tops[index] if 0 <= index < len(self._tops) else 0

    def page_at_y(self, y: int) -> int:
        """y(px) 위치에 가장 가까운 페이지 번호."""
        found = 0
        for i, top in enumerate(self._tops):
            if top - GAP // 2 <= y:
                found = i
        return found

    def _page_x(self, index: int) -> int:
        pw = int(self._sizes[index][0] * self.zoom)
        return max(MARGIN, (self.width() - pw) // 2)

    # ---------- 좌표 변환 ----------
    def _locate(self, pos: QPointF) -> tuple[int, QPointF]:
        """화면 좌표 → (페이지, PDF 좌표). 페이지 위가 아니면 (-1, ...)."""
        for i, top in enumerate(self._tops):
            h = int(self._sizes[i][1] * self.zoom)
            if top <= pos.y() <= top + h:
                x0 = self._page_x(i)
                w = int(self._sizes[i][0] * self.zoom)
                if x0 <= pos.x() <= x0 + w:
                    return i, QPointF((pos.x() - x0) / self.zoom, (pos.y() - top) / self.zoom)
                break
        return -1, QPointF()

    def _to_page_point(self, index: int, pos: QPointF) -> QPointF:
        return QPointF((pos.x() - self._page_x(index)) / self.zoom,
                       (pos.y() - self._tops[index]) / self.zoom)

    # ---------- 그리기 ----------
    def _pixmap(self, index: int) -> QPixmap:
        pm = self._cache.get(index)
        if pm is not None:
            self._cache.move_to_end(index)
            return pm
        pix = self._doc[index].get_pixmap(matrix=pymupdf.Matrix(self.zoom, self.zoom), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        pm = QPixmap.fromImage(img.copy())
        self._cache[index] = pm
        while len(self._cache) > CACHE_PAGES:
            self._cache.popitem(last=False)
        return pm

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.fillRect(event.rect(), BG)
        if not self._doc:
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "PDF 파일을 열어주세요 (Ctrl+O)")
            return
        view = event.rect()
        for i, top in enumerate(self._tops):
            h = int(self._sizes[i][1] * self.zoom)
            if top + h < view.top() - 2 or top > view.bottom() + 2:
                continue
            x = self._page_x(i)
            w = int(self._sizes[i][0] * self.zoom)
            # 그림자 + 페이지
            p.fillRect(x + 3, top + 3, w, h, QColor(0, 0, 0, 45))
            p.drawPixmap(x, top, self._pixmap(i))
            p.setPen(QColor("#C8C8C8"))
            p.drawRect(x, top, w - 1, h - 1)
            self._paint_overlay(p, i, x, top)
        p.end()

    def _paint_overlay(self, p: QPainter, index: int, x: int, top: int) -> None:
        p.save()
        p.translate(x, top)
        p.scale(self.zoom, self.zoom)
        if self.hover_line and self.hover_line[0] == index:
            r = self.hover_line[1].rect
            rect = QRectF(r.x0, r.y0, r.width, r.height)
            p.fillRect(rect, QColor(80, 140, 255, 60))
            pen = QPen(QColor(40, 100, 230))
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawRect(rect)
        d = self.drag
        if d and d["page"] == index:
            a, b = d["a"], d["b"]
            if d["kind"] in ("rect", "oval", "line"):
                pen = QPen(d["color"])
                pen.setWidthF(d["width"])
            else:
                pen = QPen(QColor(40, 100, 230))
                pen.setCosmetic(True)
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            if d["kind"] == "line":
                p.drawLine(QPointF(a.x, a.y), QPointF(b.x, b.y))
            else:
                r = QRectF(a.x, a.y, b.x - a.x, b.y - a.y).normalized()
                p.drawEllipse(r) if d["kind"] == "oval" else p.drawRect(r)
        p.restore()

    # ---------- 마우스 ----------
    def mouseMoveEvent(self, e):  # noqa: N802
        pos = e.position()
        if self._press_page is not None:
            self.moved.emit(self._press_page, self._to_page_point(self._press_page, pos))
        else:
            idx, pt = self._locate(pos)
            self.hovered.emit(idx, pt)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton:
            return
        idx, pt = self._locate(e.position())
        if idx >= 0:
            self._press_page = idx
            self.pressed.emit(idx, pt)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self._press_page is not None:
            idx, self._press_page = self._press_page, None
            self.released.emit(idx, self._to_page_point(idx, e.position()))

    def wheelEvent(self, e):  # noqa: N802
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoomWheel.emit(1 if e.angleDelta().y() > 0 else -1)
            e.accept()
        else:
            e.ignore()  # 스크롤 영역이 처리
