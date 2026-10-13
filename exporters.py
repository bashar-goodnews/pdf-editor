"""다른 형식으로 내보내기 (docx, hwpx)."""
from __future__ import annotations

import re

import pymupdf

_HWPUNIT_PER_PT = 100  # HWPX 길이 단위: 1pt = 100
_CJK = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯一-鿿぀-ヿ]")


def _join_lines(lines: list[str]) -> str:
    """줄바꿈으로 나뉜 줄을 한 문단으로 합친다. 한글/한자 줄 끝은 공백 없이, 그 외는 공백 하나로."""
    out = ""
    for line in lines:
        line = line.rstrip()
        if not line:
            continue
        if out and not _CJK.match(out[-1]):
            out += " "
        out += line
    return out


def export_hwpx(pdf_bytes: bytes, out_path: str) -> None:
    """PDF를 한글(.hwpx)로 저장한다. 문단 단위 텍스트(크기/굵기/색 유지)와 이미지를 옮긴다.

    PDF에는 문단 구조가 없어, 같은 블록의 줄들을 한 문단으로 묶어 재구성한다.
    표나 다단 레이아웃은 문단 순서로 펼쳐진다.
    """
    from hwpx import HwpxDocument

    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    doc = HwpxDocument.new()
    try:
        first = src[0].rect if src.page_count else pymupdf.Rect(0, 0, 595, 842)
        doc.set_page_size(width=round(first.width * _HWPUNIT_PER_PT),
                          height=round(first.height * _HWPUNIT_PER_PT))
        style_cache: dict[tuple, str] = {}

        def run_style(size: float, bold: bool, color: int) -> str:
            key = (round(size * 2) / 2, bold, color)
            if key not in style_cache:
                style_cache[key] = doc.ensure_run_style(
                    size=key[0], bold=bold,
                    color=None if color == 0 else f"#{color:06X}",
                )
            return style_cache[key]

        for page_no, page in enumerate(src):
            new_page = page_no > 0
            content_width = page.rect.width
            for block in page.get_text("dict", sort=True)["blocks"]:
                extra = {"pageBreak": "1"} if new_page else {}
                if block["type"] == 0:
                    lines = ["".join(s["text"] for s in ln["spans"]) for ln in block["lines"]]
                    text = _join_lines(lines)
                    spans = [s for ln in block["lines"] for s in ln["spans"] if s["text"].strip()]
                    if not text or not spans:
                        continue
                    lead = spans[0]
                    bold = bool(lead["flags"] & 16) or "bold" in lead["font"].lower()
                    doc.add_paragraph(
                        text,
                        char_pr_id_ref=run_style(lead["size"], bold, lead["color"]),
                        **extra,
                    )
                    new_page = False
                elif block["type"] == 1 and block.get("image"):
                    x0, y0, x1, y1 = block["bbox"]
                    w = min(x1 - x0, content_width)
                    h = (y1 - y0) * (w / (x1 - x0)) if x1 > x0 else y1 - y0
                    doc.add_picture(
                        block["image"], block.get("ext", "png"),
                        width_mm=w / 72 * 25.4, height_mm=h / 72 * 25.4, **extra,
                    )
                    new_page = False
        if not doc.paragraphs:
            doc.add_paragraph("")
        doc.save_to_path(out_path)
    finally:
        src.close()
        doc.close()


def export_docx(pdf_bytes: bytes, out_path: str,
                start: int = 0, end: int | None = None) -> None:
    """PDF 데이터(바이트)를 Word(.docx)로 저장한다.

    편집 중인 문서는 doc.tobytes()로 넘기면 저장하지 않은 변경도 반영된다.
    pdf2docx를 사용하며, 스캔(이미지) PDF는 글자 대신 이미지로 변환된다.
    """
    from pdf2docx import Converter  # 무거운 import는 필요할 때만

    cv = Converter(stream=pdf_bytes)
    try:
        cv.convert(out_path, start=start, end=end)
    finally:
        cv.close()
