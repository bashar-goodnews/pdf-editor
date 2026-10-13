"""PDF 에디터 — 텍스트 수정, 텍스트 상자/이미지/도형 추가, 인쇄, Word/한글 저장."""
from __future__ import annotations

import os
import sys

import pymupdf
from PySide6.QtCore import QPointF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QImage, QKeySequence, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QDoubleSpinBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QScrollArea, QSlider, QSplitter,
    QToolButton, QVBoxLayout, QWidget,
)

from canvas import MARGIN, DocumentCanvas
from core import PdfDocument, line_at
from exporters import export_docx, export_hwpx
from printing import print_document
from ribbon import STYLE, Ribbon, RibbonGroup, drawn_icon, glyph_icon

T_EDIT, T_TEXT, T_IMAGE, T_RECT, T_OVAL, T_LINE = "edit", "text", "image", "rect", "oval", "line"
DRAG_TOOLS = {T_TEXT, T_IMAGE, T_RECT, T_OVAL, T_LINE}
SHAPE_TOOLS = {T_RECT, T_OVAL, T_LINE}
MIN_DRAG_PT = 4  # 이 이상 움직여야 드래그로 인정
HINTS = {
    T_EDIT: "글자를 클릭하면 수정할 수 있습니다",
    T_TEXT: "클릭하면 그 자리에, 드래그하면 상자 안에 자동 줄바꿈으로 텍스트를 넣습니다",
    T_IMAGE: "클릭하면 기본 크기로, 드래그하면 지정한 크기로 이미지를 넣습니다",
    T_RECT: "드래그해서 사각형을 그립니다",
    T_OVAL: "드래그해서 원을 그립니다",
    T_LINE: "드래그해서 선을 그립니다",
}


class ExportJob(QThread):
    """문서 변환을 별도 스레드에서 실행해 창이 멈추지 않게 한다."""
    done = Signal(str, str)  # (저장 경로, 오류 메시지 — 성공이면 빈 문자열)

    def __init__(self, data: bytes, path: str, kind: str = "docx") -> None:
        super().__init__()
        self._data, self._path, self._kind = data, path, kind

    def run(self) -> None:
        try:
            {"docx": export_docx, "hwpx": export_hwpx}[self._kind](self._data, self._path)
        except Exception as exc:  # noqa: BLE001
            self.done.emit(self._path, str(exc) or exc.__class__.__name__)
        else:
            self.done.emit(self._path, "")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF 에디터")
        self.resize(1280, 860)
        self.setStyleSheet(STYLE)

        self.pdf: PdfDocument | None = None
        self.zoom = 1.25
        self.tool = T_EDIT
        self.color = QColor(0, 0, 0)
        self.pending_image: str | None = None
        self.tool_actions: dict[str, QAction] = {}
        self._drag: tuple[int, pymupdf.Point] | None = None  # (페이지, 시작점)
        self._current_page = 0
        self._dirty = False
        self._thumb_queue: list[int] = []

        self.canvas = DocumentCanvas()
        self.canvas.hovered.connect(self._on_hover)
        self.canvas.pressed.connect(self._on_press)
        self.canvas.moved.connect(self._on_move)
        self.canvas.released.connect(self._on_release)
        self.canvas.zoomWheel.connect(lambda d: self.set_zoom(self.zoom * (1.1 if d > 0 else 1 / 1.1)))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.canvas)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.thumbs = QListWidget()
        self.thumbs.setObjectName("thumbs")
        self.thumbs.setIconSize(QSize(110, 150))
        self.thumbs.setSpacing(4)
        self.thumbs.setUniformItemSizes(True)
        self.thumbs.currentRowChanged.connect(self._on_thumb_selected)

        self.splitter = QSplitter()
        self.splitter.addWidget(self.thumbs)
        self.splitter.addWidget(self.scroll)
        self.splitter.setSizes([170, 1000])
        self.splitter.setCollapsible(1, False)

        self.ribbon = Ribbon()
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.ribbon)
        lay.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

        self._build_actions()
        self._build_ribbon()
        self._build_statusbar()
        self.statusBar().showMessage("PDF 파일을 열어주세요 (Ctrl+O)")

    # ---------- 액션 / 리본 ----------
    def _action(self, text, icon: QIcon | None, shortcut, slot, checkable=False, tip="") -> QAction:
        a = QAction(text, self)
        if icon is not None:
            a.setIcon(icon)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        a.setToolTip(tip or text)
        a.triggered.connect(slot)
        return a

    def _build_actions(self) -> None:
        g = glyph_icon
        self.act_open = self._action("열기", g(""), "Ctrl+O", self.open_file)
        self.act_save = self._action("다른 이름으로\n저장", g(""), "Ctrl+Shift+S", self.save_as,
                                     tip="다른 이름으로 저장 (Ctrl+Shift+S)")
        self.act_undo = self._action("실행 취소", g(""), "Ctrl+Z", self.undo)
        self.act_print = self._action("인쇄", g(""), "Ctrl+P", self.print_pdf)
        self.act_preview = self._action("인쇄\n미리보기", g(""), "", self.print_preview)
        self.act_word = self._action("Word 문서\n(.docx)", drawn_icon("badge:DOCX", "#2F6EBA"),
                                     "Ctrl+Shift+W", self.export_word, tip="Word(.docx)로 저장")
        self.act_hwpx = self._action("한글 문서\n(.hwpx)", drawn_icon("badge:HWPX", "#C0392B"),
                                     "Ctrl+Shift+H", self.export_hwpx, tip="한글(.hwpx)로 저장")
        self.act_zoom_in = self._action("확대", g(""), "Ctrl+=", lambda: self.set_zoom(self.zoom * 1.2))
        self.act_zoom_out = self._action("축소", g(""), "Ctrl+-", lambda: self.set_zoom(self.zoom / 1.2))
        self.act_zoom_100 = self._action("100%", g(""), "Ctrl+0", lambda: self.set_zoom(1.0))
        self.act_fit = self._action("너비 맞춤", g(""), "", self.fit_width)
        self.act_prev = self._action("이전 쪽", g(""), "PgUp", lambda: self.goto(self._current_page - 1))
        self.act_next = self._action("다음 쪽", g(""), "PgDown", lambda: self.goto(self._current_page + 1))
        self.act_thumbs = self._action("쪽 미리보기\n창", g(""), "F4", self.toggle_thumbs, checkable=True)
        self.act_thumbs.setChecked(True)

        group = QActionGroup(self)
        group.setExclusive(True)
        defs = [
            (T_EDIT, "텍스트\n수정", g("")),
            (T_TEXT, "텍스트\n상자", drawn_icon("textbox")),
            (T_IMAGE, "그림", g("")),
            (T_RECT, "사각형", drawn_icon("rect")),
            (T_OVAL, "원", drawn_icon("oval")),
            (T_LINE, "선", drawn_icon("line")),
        ]
        for name, label, icon in defs:
            a = self._action(label, icon, "", lambda _=False, n=name: self.set_tool(n), checkable=True,
                             tip=HINTS[name])
            a.setChecked(name == T_EDIT)
            group.addAction(a)
            self.tool_actions[name] = a

        self.act_color = self._action("글자·선\n색", drawn_icon("swatch", "#000000"), "", self.pick_color)

    def _build_ribbon(self) -> None:
        r = self.ribbon
        r.add_quick_action(self._quick(self.act_save))
        r.add_quick_action(self._quick(self.act_undo))

        # --- 홈 ---
        home = r.add_tab("홈")
        grp = RibbonGroup("파일")
        for a in (self.act_open, self.act_save, self.act_print):
            grp.add_large(a)
        home.addWidget(grp)
        grp = RibbonGroup("실행 취소")
        grp.add_large(self.act_undo)
        home.addWidget(grp)
        grp = RibbonGroup("편집")
        grp.add_large(self.tool_actions[T_EDIT])
        home.addWidget(grp)
        grp = RibbonGroup("서식")
        self.size_box = QDoubleSpinBox()
        self.size_box.setRange(6, 144)
        self.size_box.setValue(14)
        self.size_box.setSuffix(" pt")
        self.width_box = QDoubleSpinBox()
        self.width_box.setRange(0.5, 20)
        self.width_box.setSingleStep(0.5)
        self.width_box.setValue(1.5)
        self.width_box.setSuffix(" pt")
        grp.add_column([self._labeled("글자 크기", self.size_box), self._labeled("선 굵기", self.width_box)])
        grp.add_large(self.act_color)
        home.addWidget(grp)
        home.addStretch(1)

        # --- 삽입 ---
        ins = r.add_tab("삽입")
        grp = RibbonGroup("텍스트")
        grp.add_large(self.tool_actions[T_TEXT])
        ins.addWidget(grp)
        grp = RibbonGroup("그림")
        grp.add_large(self.tool_actions[T_IMAGE])
        ins.addWidget(grp)
        grp = RibbonGroup("도형")
        for n in (T_RECT, T_OVAL, T_LINE):
            grp.add_large(self.tool_actions[n])
        ins.addWidget(grp)
        ins.addStretch(1)

        # --- 내보내기 ---
        exp = r.add_tab("내보내기")
        grp = RibbonGroup("다른 형식으로 저장")
        grp.add_large(self.act_word)
        grp.add_large(self.act_hwpx)
        exp.addWidget(grp)
        grp = RibbonGroup("인쇄")
        grp.add_large(self.act_print)
        grp.add_large(self.act_preview)
        exp.addWidget(grp)
        exp.addStretch(1)

        # --- 보기 ---
        view = r.add_tab("보기")
        grp = RibbonGroup("확대/축소")
        for a in (self.act_zoom_in, self.act_zoom_out, self.act_zoom_100, self.act_fit):
            grp.add_large(a)
        view.addWidget(grp)
        grp = RibbonGroup("쪽 이동")
        grp.add_large(self.act_prev)
        grp.add_large(self.act_next)
        view.addWidget(grp)
        grp = RibbonGroup("창")
        grp.add_large(self.act_thumbs)
        view.addWidget(grp)
        view.addStretch(1)

        # 단축키가 탭이 바뀌어도 동작하도록 창 전체에 등록
        for a in (self.act_open, self.act_save, self.act_undo, self.act_print, self.act_word,
                  self.act_hwpx, self.act_zoom_in, self.act_zoom_out, self.act_zoom_100,
                  self.act_prev, self.act_next, self.act_thumbs):
            self.addAction(a)

    def _quick(self, action: QAction) -> QAction:
        """빠른 실행 도구 모음용: 흰색 아이콘 사본."""
        a = QAction(action.toolTip().split("\n")[0], self)
        glyph = {self.act_save: "", self.act_undo: ""}[action]
        a.setIcon(glyph_icon(glyph, "#FFFFFF", 24))
        a.triggered.connect(action.trigger)
        return a

    @staticmethod
    def _labeled(text: str, widget: QWidget) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        label.setMinimumWidth(56)
        h.addWidget(label)
        h.addWidget(widget)
        return w

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.page_label = QLabel("")
        sb.addPermanentWidget(self.page_label)
        sb.addPermanentWidget(QLabel("    "))

        minus = QToolButton()
        minus.setText("−")
        minus.clicked.connect(lambda: self.set_zoom(self.zoom / 1.1))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(30, 400)
        self.slider.setFixedWidth(160)
        self.slider.setValue(int(self.zoom * 100))
        self.slider.valueChanged.connect(lambda v: self.set_zoom(v / 100))
        plus = QToolButton()
        plus.setText("+")
        plus.clicked.connect(lambda: self.set_zoom(self.zoom * 1.1))
        self.zoom_label = QLabel("")
        self.zoom_label.setMinimumWidth(48)
        for w in (minus, self.slider, plus, self.zoom_label):
            sb.addPermanentWidget(w)
        self._refresh_zoom_ui()

    def toggle_thumbs(self) -> None:
        self.thumbs.setVisible(self.act_thumbs.isChecked())

    # ---------- 도구 / 색 ----------
    def pick_color(self) -> None:
        c = QColorDialog.getColor(self.color, self, "색상 선택")
        if c.isValid():
            self.color = c
            self.act_color.setIcon(drawn_icon("swatch", c.name()))

    def set_tool(self, name: str) -> None:
        if name == T_IMAGE:
            path, _ = QFileDialog.getOpenFileName(
                self, "삽입할 이미지", "", "이미지 (*.png *.jpg *.jpeg *.bmp *.gif)"
            )
            if not path:  # 취소 → 수정 도구로 복귀
                self.tool_actions[T_EDIT].setChecked(True)
                self.set_tool(T_EDIT)
                return
            self.pending_image = path
        self.tool = name
        self.canvas.hover_line = None
        self.canvas.update()
        self.canvas.setCursor(Qt.CursorShape.ArrowCursor if name == T_EDIT else Qt.CursorShape.CrossCursor)
        self.statusBar().showMessage(HINTS[name])

    # ---------- 파일 ----------
    def open_file(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "PDF 열기", "", "PDF (*.pdf)")
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        try:
            doc = PdfDocument(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "열기 실패", str(exc))
            return
        if self.pdf:
            self.pdf.close()
        self.pdf = doc
        self._dirty = False
        self._current_page = 0
        self.canvas.set_document(doc.doc)
        self._fill_thumbs()
        self._refresh_title()
        self.scroll.verticalScrollBar().setValue(0)
        QTimer.singleShot(0, self.fit_width)
        self._update_page_label()
        self.statusBar().showMessage(HINTS[self.tool])

    def save_as(self) -> None:
        if not self.pdf:
            return
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            self.pdf.save_as(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "저장 실패", str(exc))
            return
        self._dirty = False
        self._refresh_title()
        self.statusBar().showMessage(f"저장됨: {path}", 5000)

    def export_word(self) -> None:
        self._export("docx", "Word", "Word 문서 (*.docx)")

    def export_hwpx(self) -> None:
        self._export("hwpx", "한글", "한글 문서 (*.hwpx)")

    def _export(self, kind: str, label: str, file_filter: str) -> None:
        if not self.pdf:
            return
        path, _ = QFileDialog.getSaveFileName(self, f"{label}로 저장", "", file_filter)
        if not path:
            return
        if not path.lower().endswith(f".{kind}"):
            path += f".{kind}"
        data = self.pdf.doc.tobytes()  # 저장하지 않은 편집 내용 포함
        self.statusBar().showMessage(f"{label} 변환 중입니다...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._export_job = ExportJob(data, path, kind)  # 참조를 유지해야 스레드가 끝까지 실행됨
        self._export_job.done.connect(self._on_export_done)
        self._export_job.start()

    def _on_export_done(self, path: str, error: str) -> None:
        QApplication.restoreOverrideCursor()
        if error:
            QMessageBox.critical(self, "변환 실패", error)
            self.statusBar().clearMessage()
        else:
            self.statusBar().showMessage(f"저장됨: {path}", 8000)

    def _confirm_discard(self) -> bool:
        if not (self.pdf and self._dirty):
            return True
        r = QMessageBox.question(
            self, "저장하지 않은 변경", "저장하지 않은 변경 사항이 있습니다. 버리고 계속할까요?"
        )
        return r == QMessageBox.StandardButton.Yes

    def closeEvent(self, e):  # noqa: N802
        e.accept() if self._confirm_discard() else e.ignore()

    def _refresh_title(self) -> None:
        if not self.pdf:
            return
        name = os.path.basename(self.pdf.path) + (" *" if self._dirty else "")
        self.ribbon.set_title(name)
        self.setWindowTitle(f"{name} — PDF 에디터")

    # ---------- 인쇄 ----------
    def print_pdf(self) -> None:
        if not self.pdf:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setFromTo(1, self.pdf.page_count)
        dlg = QPrintDialog(printer, self)
        dlg.setOption(QPrintDialog.PrintDialogOption.PrintPageRange, True)
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return
        first = last = None
        if printer.printRange() == QPrinter.PrintRange.PageRange:
            first, last = printer.fromPage() - 1, printer.toPage() - 1
        try:
            print_document(self.pdf.doc, printer, first, last)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "인쇄 실패", str(exc))
            return
        self.statusBar().showMessage("인쇄 작업을 보냈습니다", 5000)

    def print_preview(self) -> None:
        if not self.pdf:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintPreviewDialog(printer, self)
        dlg.paintRequested.connect(lambda p: print_document(self.pdf.doc, p))
        dlg.resize(900, 800)
        dlg.exec()

    # ---------- 썸네일 ----------
    def _fill_thumbs(self) -> None:
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        for i in range(self.pdf.page_count if self.pdf else 0):
            item = QListWidgetItem(str(i + 1))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self.thumbs.addItem(item)
        self.thumbs.blockSignals(False)
        self._thumb_queue = list(range(self.thumbs.count()))
        QTimer.singleShot(0, self._render_thumbs)

    def _render_thumbs(self) -> None:
        """한 번에 몇 쪽씩만 렌더링해서 창이 멈추지 않게 한다."""
        for _ in range(4):
            if not self._thumb_queue or not self.pdf:
                return
            self._set_thumb(self._thumb_queue.pop(0))
        QTimer.singleShot(0, self._render_thumbs)

    def _set_thumb(self, index: int) -> None:
        if not self.pdf or index >= self.thumbs.count():
            return
        page = self.pdf.page(index)
        z = 140 / max(page.rect.width, 1)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        self.thumbs.item(index).setIcon(QIcon(QPixmap.fromImage(img.copy())))

    def _on_thumb_selected(self, row: int) -> None:
        if row >= 0:
            self.goto(row)

    # ---------- 이동 / 확대 ----------
    def goto(self, index: int) -> None:
        if not self.pdf or not 0 <= index < self.pdf.page_count:
            return
        self.scroll.verticalScrollBar().setValue(max(0, self.canvas.page_top(index) - MARGIN // 2))

    def _on_scroll(self, value: int) -> None:
        if not self.pdf:
            return
        probe = value + self.scroll.viewport().height() // 3
        page = self.canvas.page_at_y(probe)
        if page != self._current_page:
            self._current_page = page
            self._update_page_label()
            self.thumbs.blockSignals(True)
            self.thumbs.setCurrentRow(page)
            self.thumbs.blockSignals(False)

    def _update_page_label(self) -> None:
        if self.pdf:
            self.page_label.setText(f"{self._current_page + 1} / {self.pdf.page_count} 쪽")
        else:
            self.page_label.setText("")

    def _refresh_zoom_ui(self) -> None:
        self.zoom_label.setText(f"{round(self.zoom * 100)}%")
        self.slider.blockSignals(True)
        self.slider.setValue(round(self.zoom * 100))
        self.slider.blockSignals(False)

    def set_zoom(self, zoom: float) -> None:
        zoom = max(0.3, min(4.0, zoom))
        if abs(zoom - self.zoom) < 1e-3:
            return
        sb = self.scroll.verticalScrollBar()
        anchor = self.canvas.page_at_y(sb.value())
        offset = (sb.value() - self.canvas.page_top(anchor)) / self.zoom
        self.zoom = zoom
        self.canvas.set_zoom(zoom)
        self._refresh_zoom_ui()
        # 레이아웃이 갱신된 뒤 같은 위치로 스크롤
        QTimer.singleShot(0, lambda: sb.setValue(int(self.canvas.page_top(anchor) + offset * zoom)))

    def fit_width(self) -> None:
        if not self.pdf:
            return
        widest = max(p.rect.width for p in self.pdf.doc)
        avail = self.scroll.viewport().width() - 2 * MARGIN
        if avail > 0 and widest > 0:
            self.set_zoom(avail / widest)

    # ---------- 마우스 → 편집 ----------
    @staticmethod
    def _pt(p: QPointF) -> pymupdf.Point:
        return pymupdf.Point(p.x(), p.y())

    def _rgb(self) -> tuple[float, float, float]:
        return self.color.redF(), self.color.greenF(), self.color.blueF()

    def _on_hover(self, idx: int, p: QPointF) -> None:
        if not self.pdf or self.tool != T_EDIT:
            return
        line = line_at(self.pdf.page(idx), self._pt(p)) if idx >= 0 else None
        old = self.canvas.hover_line
        same = (line is None and old is None) or (
            line is not None and old is not None and old[0] == idx and old[1].rect == line.rect
        )
        if not same:
            self.canvas.hover_line = (idx, line) if line else None
            self.canvas.setCursor(Qt.CursorShape.IBeamCursor if line else Qt.CursorShape.ArrowCursor)
            self.canvas.update()

    def _on_press(self, idx: int, p: QPointF) -> None:
        if not self.pdf:
            return
        if self.tool == T_EDIT:
            self._edit_text_at(idx, self._pt(p))
        elif self.tool in DRAG_TOOLS:
            start = self._pt(p)
            self._drag = (idx, start)
            self.canvas.drag = {
                "page": idx, "kind": self.tool, "a": start, "b": start,
                "color": self.color, "width": self.width_box.value(),
            }

    def _on_move(self, idx: int, p: QPointF) -> None:
        if self.canvas.drag is not None:
            self.canvas.drag["b"] = self._pt(p)
            self.canvas.update()

    def _on_release(self, idx: int, p: QPointF) -> None:
        if self._drag is None or not self.pdf:
            return
        page, start = self._drag
        end = self._pt(p)
        self._drag = None
        self.canvas.drag = None
        dragged = abs(end.x - start.x) + abs(end.y - start.y) >= MIN_DRAG_PT
        self._finish_drag(page, start, end, dragged)
        self.canvas.update()

    def _finish_drag(self, idx: int, a: pymupdf.Point, b: pymupdf.Point, dragged: bool) -> None:
        tool = self.tool
        if tool == T_TEXT:
            text, ok = QInputDialog.getMultiLineText(self, "텍스트 상자", "내용:")
            if not ok or not text.strip():
                return
            rect = pymupdf.Rect(a, b).normalize() if dragged else pymupdf.Rect(a, a)
            if not self.pdf.add_text(idx, rect, text, self.size_box.value(), self._rgb(), wrap=dragged):
                QMessageBox.warning(self, "텍스트 상자", "상자가 너무 작아 글자가 들어가지 않습니다.")
                return
        elif tool == T_IMAGE and self.pending_image:
            if dragged:
                rect = pymupdf.Rect(a, b).normalize()
            else:
                w, h = self.pdf.image_size_pt(self.pending_image)
                rect = pymupdf.Rect(a.x, a.y, a.x + w, a.y + h)
            self.pdf.add_image(idx, rect, self.pending_image)
        elif tool in SHAPE_TOOLS:
            if not dragged:
                return
            self.pdf.add_shape(idx, tool, a, b, self._rgb(), self.width_box.value())
        else:
            return
        self._after_edit(idx)

    def _edit_text_at(self, idx: int, pt: pymupdf.Point) -> None:
        line = line_at(self.pdf.page(idx), pt)
        if line is None:
            return
        new_text, ok = QInputDialog.getText(self, "텍스트 수정", "내용:", text=line.text)
        if not ok or new_text == line.text:
            return
        self.canvas.hover_line = None
        self.pdf.edit_line(idx, line, new_text)
        self._after_edit(idx)

    def _after_edit(self, idx: int) -> None:
        self._dirty = True
        self.canvas.invalidate(idx)
        self._set_thumb(idx)
        self._refresh_title()

    def undo(self) -> None:
        if self.pdf and self.pdf.can_undo:
            self.pdf.undo()  # 내부적으로 문서 객체가 교체됨
            self._dirty = True
            self.canvas.set_document(self.pdf.doc)
            self._thumb_queue = list(range(self.thumbs.count()))
            QTimer.singleShot(0, self._render_thumbs)
            self._refresh_title()


def selftest(report_path: str) -> int:
    """exe 배포본 점검용: 변환 라이브러리가 제대로 포함됐는지 확인하고 결과를 파일에 기록."""
    import tempfile
    lines, ok = [], True
    try:
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 100), "selftest 12345", fontsize=14)
        data = doc.tobytes()
        tmp = tempfile.mkdtemp()
        for kind, fn in (("docx", export_docx), ("hwpx", export_hwpx)):
            out = os.path.join(tmp, f"t.{kind}")
            fn(data, out)
            lines.append(f"{kind}: {os.path.getsize(out)} bytes")
    except Exception as exc:  # noqa: BLE001
        ok = False
        lines.append(f"ERROR: {exc!r}")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(("OK\n" if ok else "FAIL\n") + "\n".join(lines) + "\n")
    return 0 if ok else 1


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        return selftest(sys.argv[2])
    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 9))
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.load(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
