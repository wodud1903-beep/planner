"""라이트/다크 테마 팔레트 + 전역 스타일시트 생성.

라이트: 델파이 스킨 'Tablet Light' 톤(밝은 청회색)
다크  : 같은 톤의 어두운 버전
"""

from __future__ import annotations

# 라이트: 눈이 편하도록 순백(#FFF) 대신 은은한 오프화이트 톤 사용
LIGHT = {
    "topbar": "#D7E1EC",
    "topbar_text": "#2C3E50",
    "window_bg": "#E7ECF2",     # 전체 배경(약간 낮춘 밝기)
    "panel_bg": "#F3F6FA",      # 패널(순백 아님)
    "text": "#2C3E50",
    "subtext": "#4A5B6C",
    "accent": "#5B8FBF",
    "border": "#C3D0DE",
    "header_bg": "#DDE7F1",
    "select_bg": "#CDE0F4",
    "select_text": "#1A2A38",
    "btn_bg": "#E4EDF6",
    "btn_hover": "#D6E3F1",
    "btn_pressed": "#C6D9EC",
    "input_bg": "#F7F9FC",      # 입력창(순백 아님)
    "grid": "#D8E1EB",
    "tab_bg": "#D7E1EC",
    "today": "#FFC98A",
    "tomorrow": "#FFF2A8",
    "row_text": "#1A2430",     # 강조행 글자색
    "brief_bg": "#E4EBF3",
    "brief_text": "#2C3E50",
    "status_ok": "#2E7D32",
    "status_bad": "#C0392B",
    "scroll": "#B3C4D6",
    "scroll_hover": "#98AEC3",
}

# 다크: 남색빛을 빼고 더 어두운 차콜 계열로
DARK = {
    "topbar": "#191C21",
    "topbar_text": "#E4E9EF",
    "window_bg": "#121417",     # 전체 배경(더 어둡게)
    "panel_bg": "#1B1E23",      # 패널
    "text": "#D4DAE1",
    "subtext": "#8E98A3",
    "accent": "#6FA8DC",
    "border": "#2B2F36",
    "header_bg": "#20242A",
    "select_bg": "#2C3742",
    "select_text": "#EAF1F8",
    "btn_bg": "#23272D",
    "btn_hover": "#2C3138",
    "btn_pressed": "#363C44",
    "input_bg": "#16181C",
    "grid": "#282C32",
    "tab_bg": "#1B1E23",
    "today": "#9C5F22",       # 어두운 배경에서도 보이는 주황
    "tomorrow": "#6E6224",    # 어두운 노랑
    "row_text": "#F0F3F7",
    "brief_bg": "#1B1E23",
    "brief_text": "#D4DAE1",
    "status_ok": "#7FD18B",
    "status_bad": "#E88",
    "scroll": "#333941",
    "scroll_hover": "#434A54",
}

_current = LIGHT
_is_dark = False


def set_theme(dark: bool) -> None:
    global _current, _is_dark
    _is_dark = bool(dark)
    _current = DARK if dark else LIGHT


def is_dark() -> bool:
    return _is_dark


def c(key: str) -> str:
    return _current.get(key, "#000000")


def palette():
    """현재 테마에 맞는 QPalette.

    스타일시트가 닿지 않는 표면(스크롤 영역 뷰포트, 툴팁, 일부 기본 대화상자 등)은
    팔레트 색으로 그려진다. 이걸 지정하지 않으면 **윈도우 시스템 테마(다크)** 가
    그대로 새어 나와 밝은 테마인데 배경만 어두워지는 문제가 생긴다.
    """
    from PySide6.QtGui import QColor, QPalette

    p = _current
    pal = QPalette()
    win = QColor(p["window_bg"])
    base = QColor(p["input_bg"])
    text = QColor(p["text"])
    btn = QColor(p["btn_bg"])
    sel = QColor(p["select_bg"])
    seltxt = QColor(p["select_text"])

    pal.setColor(QPalette.Window, win)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, base)
    pal.setColor(QPalette.AlternateBase, QColor(p["panel_bg"]))
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, btn)
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.Highlight, sel)
    pal.setColor(QPalette.HighlightedText, seltxt)
    pal.setColor(QPalette.ToolTipBase, QColor(p["panel_bg"]))
    pal.setColor(QPalette.ToolTipText, text)
    pal.setColor(QPalette.PlaceholderText, QColor(p["subtext"]))
    pal.setColor(QPalette.Link, QColor(p["accent"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(p["subtext"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(p["subtext"]))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(p["subtext"]))
    return pal


def apply_to_app(app) -> None:
    """앱 전체에 현재 테마(스타일시트 + 팔레트 + 색상 스킴)를 적용."""
    app.setStyleSheet(qss())
    app.setPalette(palette())
    # Qt 6.8+ : 창 제목표시줄까지 테마에 맞춘다(없는 버전이면 조용히 넘어감)
    try:
        from PySide6.QtCore import Qt
        scheme = Qt.ColorScheme.Dark if _is_dark else Qt.ColorScheme.Light
        app.styleHints().setColorScheme(scheme)
    except Exception:
        pass


def qss() -> str:
    p = _current
    return f"""
QWidget {{ font-family: 'Malgun Gothic'; color: {p['text']}; }}
QMainWindow, QWidget#central {{ background: {p['window_bg']}; }}
QPushButton {{
    background: {p['btn_bg']};
    border: 1px solid {p['border']};
    border-radius: 7px;
    padding: 5px 14px;
    color: {p['text']};
}}
QPushButton:hover {{ background: {p['btn_hover']}; }}
QPushButton:pressed {{ background: {p['btn_pressed']}; }}
QPushButton:default {{ border: 1px solid {p['accent']}; }}
QPushButton:disabled {{ color: {p['subtext']}; background: {p['panel_bg']}; }}
QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QTextEdit {{
    border: 1px solid {p['border']};
    border-radius: 7px;
    padding: 4px 8px;
    background: {p['input_bg']};
    color: {p['text']};
    selection-background-color: {p['accent']};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QTextEdit:focus {{ border: 1px solid {p['accent']}; }}
QComboBox QAbstractItemView {{ background: {p['input_bg']}; color: {p['text']};
    selection-background-color: {p['select_bg']}; selection-color: {p['select_text']}; }}
QGroupBox {{
    border: 1px solid {p['border']};
    border-radius: 10px;
    margin-top: 10px;
    padding: 10px;
    background: {p['panel_bg']};
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 5px;
    color: {p['subtext']}; font-weight: bold;
}}
QTabWidget::pane {{ border: 1px solid {p['border']}; border-radius: 9px; top: -1px; background: {p['panel_bg']}; }}
QTabBar::tab {{
    background: {p['tab_bg']};
    border: 1px solid {p['border']};
    border-top-left-radius: 9px; border-top-right-radius: 9px;
    padding: 7px 18px; margin-right: 3px; color: {p['subtext']};
}}
QTabBar::tab:selected {{ background: {p['panel_bg']}; color: {p['text']}; border-bottom-color: {p['panel_bg']}; }}
QTableWidget {{
    border: 1px solid {p['border']};
    border-radius: 9px;
    background: {p['panel_bg']};
    gridline-color: {p['grid']};
    selection-background-color: {p['select_bg']};
    selection-color: {p['select_text']};
    alternate-background-color: {p['window_bg']};
}}
QHeaderView::section {{
    background: {p['header_bg']}; color: {p['subtext']};
    border: none; border-right: 1px solid {p['border']}; border-bottom: 1px solid {p['border']};
    padding: 6px;
}}
QCheckBox {{ spacing: 6px; }}
QLabel {{ background: transparent; }}
QListWidget {{
    background: {p['panel_bg']}; color: {p['text']};
    border: 1px solid {p['border']}; border-radius: 8px;
}}
QListWidget::item:selected {{ background: {p['select_bg']}; color: {p['select_text']}; }}
QDialog, QMessageBox {{ background: {p['window_bg']}; }}
/* 스크롤 영역 — 규칙이 없으면 윈도우 시스템(다크) 테마가 배경으로 새어 나온다 */
QScrollArea {{ background: {p['window_bg']}; border: none; }}
QScrollArea > QWidget > QWidget {{ background: {p['window_bg']}; }}
QScrollArea > QWidget#dlgbody {{ background: {p['window_bg']}; }}
QWidget#dlgbody {{ background: {p['window_bg']}; }}
QAbstractScrollArea::corner {{ background: {p['window_bg']}; }}
QScrollBar:vertical {{ border: none; background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['scroll']}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {p['scroll_hover']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ border: none; background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['scroll']}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QCalendarWidget QWidget {{ alternate-background-color: {p['window_bg']}; }}
QCalendarWidget QAbstractItemView:enabled {{
    background: {p['panel_bg']}; color: {p['text']};
    selection-background-color: {p['select_bg']}; selection-color: {p['select_text']};
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {p['header_bg']}; }}
QCalendarWidget QToolButton {{ color: {p['text']}; background: transparent; border-radius: 6px; padding: 3px 8px; }}
QCalendarWidget QToolButton:hover {{ background: {p['btn_hover']}; }}
QCalendarWidget QToolButton::menu-indicator {{ image: none; }}
QCalendarWidget QSpinBox {{ background: {p['input_bg']}; color: {p['text']}; }}
QCalendarWidget QMenu {{ background: {p['panel_bg']}; color: {p['text']}; }}
QMenu {{
    background: {p['panel_bg']}; color: {p['text']};
    border: 1px solid {p['border']}; border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 5px 22px; border-radius: 5px; color: {p['text']}; }}
QMenu::item:selected {{ background: {p['select_bg']}; color: {p['select_text']}; }}
QMenu::separator {{ height: 1px; background: {p['border']}; margin: 4px 8px; }}
"""
