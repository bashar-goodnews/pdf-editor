"""테스트용 샘플 PDF 생성 (한글 + 영문)."""
import sys

import pymupdf

out = sys.argv[1] if len(sys.argv) > 1 else "sample.pdf"
doc = pymupdf.open()
page = doc.new_page()
font = r"C:\Windows\Fonts\malgun.ttf"
page.insert_text((72, 100), "PDF 에디터 테스트 문서", fontsize=22, fontname="k", fontfile=font)
page.insert_text((72, 150), "이 줄을 클릭해서 수정해 보세요.", fontsize=14, fontname="k", fontfile=font)
page.insert_text((72, 180), "Hello, this is an English line.", fontsize=14, fontname="k", fontfile=font)
page.insert_text((72, 210), "계약금: 1,000,000원 / 날짜: 2026-10-12", fontsize=12, fontname="k",
                 fontfile=font, color=(0.8, 0, 0))
doc.save(out)
print("created", out)
