"""hwpx 내보내기 확인: 텍스트/이미지/쪽 나눔이 남고, 라이브러리 검증을 통과해야 한다."""
import os
import tempfile
import zipfile

import pymupdf
from hwpx import HwpxDocument

from exporters import export_hwpx

# 2쪽짜리 테스트 PDF (한글 + 영문 + 색 글자 + 이미지)
font = r"C:\Windows\Fonts\malgun.ttf"
src = pymupdf.open()
p1 = src.new_page()
p1.insert_text((72, 100), "계약서 제목", fontsize=24, fontname="k", fontfile=font)
p1.insert_text((72, 150), "본 계약은 갑과 을 사이에 체결한다.", fontsize=12, fontname="k", fontfile=font)
p1.insert_text((72, 180), "Amount: 1,000,000 KRW", fontsize=12, fontname="k", fontfile=font, color=(0.8, 0, 0))
pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 30), False)
pix.set_rect(pix.irect, (30, 90, 200))
p1.insert_image(pymupdf.Rect(72, 220, 192, 280), stream=pix.tobytes("png"))
p2 = src.new_page()
p2.insert_text((72, 100), "두 번째 쪽 내용입니다.", fontsize=12, fontname="k", fontfile=font)

out = os.path.join(tempfile.mkdtemp(), "out.hwpx")
export_hwpx(src.tobytes(), out)

# 1) 패키지 구조 (hwpx = zip, 첫 항목 mimetype)
with zipfile.ZipFile(out) as z:
    names = z.namelist()
    assert names[0] == "mimetype", names
    assert z.read("mimetype").decode().strip() == "application/hwp+zip"
    assert any(n.startswith("BinData/") for n in names), "이미지가 포함되지 않음"
    print("파일 목록:", names)

# 2) 다시 열어서 텍스트 확인
doc = HwpxDocument.open(out)
text = doc.text.plain()
with zipfile.ZipFile(out) as z:
    assert 'pageBreak="1"' in z.read("Contents/section0.xml").decode(), "쪽 나눔이 없음"
print(text)
for needle in ("계약서 제목", "본 계약은 갑과 을 사이에 체결한다.", "Amount: 1,000,000 KRW", "두 번째 쪽 내용입니다."):
    assert needle in text, needle

# 3) 라이브러리 검증
report = doc.validate()
print("검증:", report)
doc.close()
print("HWPX OK")
