"""PDF 편집 핵심 로직 (GUI와 분리). PyMuPDF 기반."""
from __future__ import annotations

import os
from dataclasses import dataclass

import pymupdf

# 새로 입력하는 글자에 쓸 폰트 후보 (사용자 PC에 설치된 폰트를 호출만 하고 포함/배포하지 않음)
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\NanumGothic.ttf",
    r"C:\Windows\Fonts\batang.ttc",
]


def find_fallback_font() -> str | None:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


@dataclass
class TextLine:
    """페이지 위의 한 줄 텍스트."""
    rect: pymupdf.Rect
    text: str
    size: float
    color: tuple[float, float, float]
    origin: pymupdf.Point  # 첫 글자의 기준선(baseline) 위치
    font: str


def _int_to_rgb(value: int) -> tuple[float, float, float]:
    return ((value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255)


def page_lines(page: pymupdf.Page) -> list[TextLine]:
    """페이지의 모든 텍스트 줄을 반환."""
    result: list[TextLine] = []
    data = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
    for block in data["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            first = spans[0]
            result.append(
                TextLine(
                    rect=pymupdf.Rect(line["bbox"]),
                    text="".join(s["text"] for s in line["spans"]),
                    size=first["size"],
                    color=_int_to_rgb(first["color"]),
                    origin=pymupdf.Point(first["origin"]),
                    font=first["font"],
                )
            )
    return result


def line_at(page: pymupdf.Page, point: pymupdf.Point) -> TextLine | None:
    """주어진 좌표(PDF 좌표계)에 있는 텍스트 줄을 찾는다."""
    for line in page_lines(page):
        if line.rect.contains(point):
            return line
    return None


def replace_line(page: pymupdf.Page, line: TextLine, new_text: str) -> None:
    """기존 한 줄을 지우고 새 텍스트를 같은 위치에 넣는다."""
    # 1) 기존 글자 제거 (이미지/선은 건드리지 않음)
    redact_rect = line.rect + (-0.5, -0.5, 0.5, 0.5)
    page.add_redact_annot(redact_rect, fill=(1, 1, 1))
    kwargs = {"images": pymupdf.PDF_REDACT_IMAGE_NONE}
    if hasattr(pymupdf, "PDF_REDACT_LINE_ART_NONE"):
        kwargs["graphics"] = pymupdf.PDF_REDACT_LINE_ART_NONE
    page.apply_redactions(**kwargs)

    if not new_text:
        return

    # 2) 새 텍스트 삽입
    fontfile = find_fallback_font()
    if fontfile:
        page.insert_text(
            line.origin, new_text, fontsize=line.size, color=line.color,
            fontname="kofont", fontfile=fontfile,
        )
    else:
        page.insert_text(line.origin, new_text, fontsize=line.size, color=line.color)


class PdfDocument:
    """열린 PDF 문서 + 실행 취소 스택."""

    def __init__(self, path: str):
        self.path = path
        self.doc = pymupdf.open(path)
        self._undo: list[bytes] = []

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    def page(self, index: int) -> pymupdf.Page:
        return self.doc[index]

    def edit_line(self, page_index: int, line: TextLine, new_text: str) -> None:
        self._undo.append(self.doc.tobytes())
        replace_line(self.doc[page_index], line, new_text)

    # ---------- 요소 추가 ----------
    def add_text(self, page_index: int, rect: pymupdf.Rect, text: str, size: float,
                 color: tuple[float, float, float], wrap: bool) -> bool:
        """텍스트 추가. wrap=True면 rect 안에서 자동 줄바꿈, False면 rect 왼쪽 위에서 시작."""
        page = self.doc[page_index]
        fontfile = find_fallback_font()
        font_kwargs = {"fontname": "kofont", "fontfile": fontfile} if fontfile else {}
        self._undo.append(self.doc.tobytes())
        if wrap:
            rc = page.insert_textbox(rect, text, fontsize=size, color=color, **font_kwargs)
            if rc < 0:  # 상자가 너무 작아 글자가 들어가지 않음
                self.undo()
                return False
        else:
            origin = pymupdf.Point(rect.x0, rect.y0 + size)
            page.insert_text(origin, text, fontsize=size, color=color, **font_kwargs)
        return True

    def add_image(self, page_index: int, rect: pymupdf.Rect, image_path: str) -> None:
        self._undo.append(self.doc.tobytes())
        self.doc[page_index].insert_image(rect, filename=image_path, keep_proportion=True)

    def add_shape(self, page_index: int, kind: str, p1: pymupdf.Point, p2: pymupdf.Point,
                  color: tuple[float, float, float], width: float) -> None:
        """kind: 'rect' | 'oval' | 'line'"""
        self._undo.append(self.doc.tobytes())
        page = self.doc[page_index]
        if kind == "line":
            page.draw_line(p1, p2, color=color, width=width)
            return
        rect = pymupdf.Rect(p1, p2).normalize()
        if kind == "rect":
            page.draw_rect(rect, color=color, width=width)
        elif kind == "oval":
            page.draw_oval(rect, color=color, width=width)
        else:
            raise ValueError(f"알 수 없는 도형: {kind}")

    def image_size_pt(self, image_path: str, max_width: float = 200) -> tuple[float, float]:
        """이미지를 기본 크기로 넣을 때의 (가로, 세로) 포인트."""
        pix = pymupdf.Pixmap(image_path)
        w, h = float(pix.width), float(pix.height)
        scale = min(1.0, max_width / w)
        return w * scale, h * scale

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    def undo(self) -> None:
        if not self._undo:
            return
        data = self._undo.pop()
        self.doc.close()
        self.doc = pymupdf.open(stream=data, filetype="pdf")

    def save_as(self, path: str) -> None:
        self.doc.save(path, garbage=3, deflate=True)

    def close(self) -> None:
        self.doc.close()
