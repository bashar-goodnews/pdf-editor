"""인쇄 로직. QPrinter(실제 프린터/PDF 파일) 위에 PDF 페이지를 그린다."""
from __future__ import annotations

import pymupdf
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPrintSupport import QPrinter

RENDER_DPI = 300  # 인쇄용 렌더링 해상도 (메모리와 품질의 균형)


def _render_page(page: pymupdf.Page) -> QImage:
    zoom = RENDER_DPI / 72
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
    return img.copy()  # pix.samples 수명과 분리


def print_document(doc: pymupdf.Document, printer: QPrinter,
                   first: int | None = None, last: int | None = None) -> None:
    """doc의 first~last 페이지(0부터, 양끝 포함)를 printer로 출력. 생략하면 전체."""
    first = 0 if first is None else max(0, first)
    last = doc.page_count - 1 if last is None else min(doc.page_count - 1, last)

    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("프린터를 열 수 없습니다.")
    try:
        target_area = printer.pageRect(QPrinter.Unit.DevicePixel).toRect()
        for index in range(first, last + 1):
            if index > first:
                printer.newPage()
            img = _render_page(doc[index])
            # 용지에 맞춰 비율 유지하며 가운데 배치
            scale = min(target_area.width() / img.width(), target_area.height() / img.height())
            w, h = int(img.width() * scale), int(img.height() * scale)
            x = target_area.x() + (target_area.width() - w) // 2
            y = target_area.y() + (target_area.height() - h) // 2
            painter.drawImage(QRect(x, y, w, h), img)
    finally:
        painter.end()
