"""워드 스타일 리본 메뉴(탭 + 그룹 + 큰 버튼)와 아이콘 도우미."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget,
)

ACCENT = "#1F6F78"  # 특정 상용 프로그램의 브랜드 색과 겹치지 않도록 청록 계열 사용

STYLE = f"""
#ribbonHeader {{ background: {ACCENT}; }}
#ribbonHeader QTabBar::tab {{
    background: {ACCENT}; color: white; padding: 7px 18px; border: 0; font-size: 10pt;
}}
#ribbonHeader QTabBar::tab:hover:!selected {{ background: #2E8A94; }}
#ribbonHeader QTabBar::tab:selected {{ background: #F3F3F3; color: {ACCENT}; }}
#ribbonHeader QToolButton {{ background: transparent; border: 0; padding: 4px; }}
#ribbonHeader QToolButton:hover {{ background: #2E8A94; }}
#ribbonHeader QLabel {{ color: white; padding-right: 12px; }}
#ribbonBody {{ background: #F3F3F3; border-bottom: 1px solid #D0D0D0; }}
RibbonGroup {{ border-right: 1px solid #D6D6D6; }}
RibbonGroup QLabel#groupLabel {{ color: #666; font-size: 8pt; }}
#ribbonBody QToolButton {{
    background: transparent; border: 1px solid transparent; border-radius: 3px;
    padding: 3px 4px; color: #222;
}}
#ribbonBody QToolButton:hover {{ background: #DCEEF0; border-color: #BFDDE1; }}
#ribbonBody QToolButton:checked, #ribbonBody QToolButton:pressed {{
    background: #C5E2E6; border-color: #93C7CE;
}}
#ribbonBody QLabel {{ color: #333; }}
QStatusBar {{ background: {ACCENT}; color: white; }}
QStatusBar QLabel {{ color: white; }}
QStatusBar QToolButton {{ background: transparent; border: 0; color: white; font-size: 12pt; padding: 0 6px; }}
QStatusBar QToolButton:hover {{ background: #2E8A94; }}
QListWidget#thumbs {{ background: #F0F0F0; border: 0; border-right: 1px solid #D0D0D0; outline: 0; }}
QListWidget#thumbs::item {{ color: #444; padding: 6px; }}
QListWidget#thumbs::item:selected {{ background: #DCEEF0; color: {ACCENT}; }}
QScrollArea {{ border: 0; }}
"""

_ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")


def _icon_font() -> str | None:
    families = set(QFontDatabase.families())
    return next((f for f in _ICON_FONTS if f in families), None)


def glyph_icon(code: str, color: str = ACCENT, size: int = 32, fallback: str = "•") -> QIcon:
    """Segoe 아이콘 글꼴의 글리프로 아이콘을 만든다(글꼴이 없으면 대체 문자)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    family = _icon_font()
    font = QFont(family) if family else QFont()
    font.setPixelSize(int(size * 0.78))
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, code if family else fallback)
    p.end()
    return QIcon(pm)


def drawn_icon(kind: str, color: str = ACCENT, size: int = 32) -> QIcon:
    """글리프가 없는 도구용으로 직접 그린 아이콘."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(2.2)
    p.setPen(pen)
    m = size * 0.16
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    if kind == "rect":
        p.drawRect(r)
    elif kind == "oval":
        p.drawEllipse(r)
    elif kind == "line":
        p.drawLine(int(m), int(size - m), int(size - m), int(m))
    elif kind == "textbox":
        p.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.DashLine))
        p.drawRect(r)
        f = QFont()
        f.setPixelSize(int(size * 0.5))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "T")
    elif kind.startswith("badge:"):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(1, size * 0.22, size - 2, size * 0.56), 4, 4)
        f = QFont()
        f.setPixelSize(int(size * 0.27))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(1, size * 0.22, size - 2, size * 0.56),
                   Qt.AlignmentFlag.AlignCenter, kind.split(":", 1)[1])
    elif kind == "swatch":
        p.setPen(QPen(QColor("#888"), 1))
        p.setBrush(QColor(color))
        p.drawRoundedRect(r, 3, 3)
    p.end()
    return QIcon(pm)


class RibbonGroup(QFrame):
    """리본의 한 그룹: 위쪽에 버튼들, 아래쪽에 그룹 이름."""

    def __init__(self, title: str) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 2)
        outer.setSpacing(0)
        self.row = QHBoxLayout()
        self.row.setSpacing(2)
        outer.addLayout(self.row, 1)
        label = QLabel(title)
        label.setObjectName("groupLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(label)

    def add_large(self, action: QAction) -> QToolButton:
        btn = QToolButton()
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setIconSize(QSize(32, 32))
        btn.setMinimumWidth(58)
        btn.setMinimumHeight(72)
        self.row.addWidget(btn)
        return btn

    def add_widget(self, w: QWidget) -> None:
        self.row.addWidget(w)

    def add_column(self, widgets: list[QWidget]) -> None:
        col = QVBoxLayout()
        col.setSpacing(4)
        for w in widgets:
            col.addWidget(w)
        col.addStretch(1)
        self.row.addLayout(col)


class Ribbon(QWidget):
    """위쪽 파란 탭 줄 + 아래쪽 회색 리본 본문."""

    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = QWidget()
        self.header.setObjectName("ribbonHeader")
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(6, 0, 0, 0)
        hl.setSpacing(0)
        self.quick = QHBoxLayout()
        hl.addLayout(self.quick)
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        hl.addWidget(self.tabs)
        hl.addStretch(1)
        self.title = QLabel("")
        hl.addWidget(self.title)
        outer.addWidget(self.header)

        self.stack = QStackedWidget()
        self.stack.setObjectName("ribbonBody")
        self.stack.setFixedHeight(104)
        outer.addWidget(self.stack)
        self.tabs.currentChanged.connect(self.stack.setCurrentIndex)

    def add_quick_action(self, action: QAction) -> None:
        btn = QToolButton()
        btn.setDefaultAction(action)
        btn.setIconSize(QSize(20, 20))
        self.quick.addWidget(btn)

    def add_tab(self, name: str) -> QHBoxLayout:
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(0)
        self.tabs.addTab(name)
        self.stack.addWidget(page)
        return row

    def set_title(self, text: str) -> None:
        self.title.setText(text)
