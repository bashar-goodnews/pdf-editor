"""core.py / printing.py 동작 확인 (GUI 없이)."""
import os
import tempfile

import pymupdf
from PySide6.QtGui import QColor, QImage
from PySide6.QtPrintSupport import QPrinter

from PySide6.QtWidgets import QApplication

from core import PdfDocument, line_at
from printing import print_document

app = QApplication([])  # QPrinter/QImage 사용에 필요
tmp = tempfile.mkdtemp()

# --- 텍스트 수정 / 실행 취소 ---
d = PdfDocument("sample.pdf")
ln = line_at(d.page(0), pymupdf.Point(100, 146))
assert ln is not None, "줄을 찾지 못함"
d.edit_line(0, ln, "수정된 문장입니다. Edited!")
text = d.page(0).get_text()
assert "수정된 문장입니다" in text and "이 줄을 클릭" not in text
assert "Hello, this is an English line." in text
d.undo()
assert "이 줄을 클릭" in d.page(0).get_text()
print("텍스트 수정/undo OK")

# --- 요소 추가 ---
img_path = os.path.join(tmp, "red.png")
img = QImage(80, 40, QImage.Format.Format_RGB888)
img.fill(QColor(220, 30, 30))
img.save(img_path)

assert d.add_text(0, pymupdf.Rect(72, 300, 300, 360), "클릭 위치 텍스트", 14, (0, 0, 1), wrap=False)
assert d.add_text(0, pymupdf.Rect(72, 380, 250, 450),
                  "드래그로 만든 상자입니다. 길면 자동으로 줄바꿈이 됩니다.", 12, (0, 0.5, 0), wrap=True)
assert not d.add_text(0, pymupdf.Rect(0, 0, 5, 5), "너무 작은 상자", 20, (0, 0, 0), wrap=True)
d.add_image(0, pymupdf.Rect(320, 300, 400, 340), img_path)
d.add_shape(0, "rect", pymupdf.Point(72, 480), pymupdf.Point(200, 540), (1, 0, 0), 2)
d.add_shape(0, "oval", pymupdf.Point(220, 480), pymupdf.Point(340, 540), (0, 0, 1), 2)
d.add_shape(0, "line", pymupdf.Point(72, 560), pymupdf.Point(340, 600), (0, 0, 0), 1.5)
t = d.page(0).get_text()
assert "클릭 위치 텍스트" in t and "드래그로 만든 상자" in t
assert len(d.page(0).get_images()) == 1
assert len(d.page(0).get_drawings()) >= 3
assert d.image_size_pt(img_path) == (80.0, 40.0)
out = os.path.join(tmp, "edited.pdf")
d.save_as(out)
pymupdf.open(out)[0].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2)).save("check_elements.png")
print("요소 추가 OK")

# --- 인쇄 (PDF 파일로 출력) ---
multi = pymupdf.open("sample.pdf")
multi.insert_pdf(pymupdf.open("sample.pdf"))  # 2페이지
printed = os.path.join(tmp, "printed.pdf")
printer = QPrinter(QPrinter.PrinterMode.HighResolution)
printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
printer.setOutputFileName(printed)
print_document(multi, printer)
assert pymupdf.open(printed).page_count == 2
printed1 = os.path.join(tmp, "printed1.pdf")
printer = QPrinter(QPrinter.PrinterMode.HighResolution)
printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
printer.setOutputFileName(printed1)
print_document(multi, printer, 1, 1)
assert pymupdf.open(printed1).page_count == 1
print("인쇄 OK")
print("ALL OK")
