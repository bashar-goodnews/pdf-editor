"""GUI 스모크 테스트: offscreen에서 마우스 동작을 흉내 내어 편집/변환을 확인한다."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QPointF, QTimer
from PySide6.QtWidgets import QApplication

import main

app = QApplication([])
w = main.MainWindow()
w.show()
w.load("sample.pdf")
for _ in range(5):
    app.processEvents()
assert w.pdf and w.canvas._doc is not None
assert w.thumbs.count() == w.pdf.page_count

# 1) 도형 추가 (캔버스 신호를 통해 PDF 좌표로 전달)
w.tool_actions[main.T_RECT].trigger()
assert w.tool == main.T_RECT
before = len(w.pdf.page(0).get_drawings())
w._on_press(0, QPointF(100, 400))
w._on_move(0, QPointF(200, 450))
w._on_release(0, QPointF(200, 450))
assert len(w.pdf.page(0).get_drawings()) == before + 1, "도형이 추가되지 않음"
assert w._dirty

# 2) 실행 취소
w.undo()
assert len(w.pdf.page(0).get_drawings()) == before, "undo 실패"
w._dirty = False  # 종료 시 확인창 방지

# 3) 캔버스 좌표 변환: 첫 페이지 한가운데를 눌렀을 때 (0, 중앙 pt)가 나와야 함
c = w.canvas
x = c._page_x(0) + int(100 * c.zoom)
y = c.page_top(0) + int(50 * c.zoom)
idx, pt = c._locate(QPointF(x, y))
assert idx == 0 and abs(pt.x() - 100) < 1 and abs(pt.y() - 50) < 1, (idx, pt)
assert c._locate(QPointF(2, 2))[0] == -1  # 페이지 밖

# 4) 확대/축소 + 너비 맞춤
z0 = w.zoom
w.set_zoom(2.0)
assert abs(w.zoom - 2.0) < 1e-6 and abs(c.zoom - 2.0) < 1e-6
w.fit_width()
w.set_zoom(z0)

# 5) 변환 (별도 스레드)
for kind in ("docx", "hwpx"):
    out = os.path.join(tempfile.mkdtemp(), f"gui.{kind}")
    job = main.ExportJob(w.pdf.doc.tobytes(), out, kind)
    result = {}
    loop = QEventLoop()
    job.done.connect(lambda p, err, r=result, lp=loop: (r.update(path=p, err=err), lp.quit()))
    QTimer.singleShot(60000, loop.quit)
    job.start()
    loop.exec()
    job.wait()
    assert result.get("err") == "" and os.path.getsize(out) > 0, (kind, result)

# 6) 화면 캡처 (육안 확인용)
if len(sys.argv) > 1:
    w.resize(1280, 860)
    for _ in range(5):
        app.processEvents()
    w.grab().save(sys.argv[1])
print("GUI OK")
