"""라이트/다크 테마 팔레트 + 전역 스타일시트 생성.

라이트: 델파이 스킨 'Tablet Light' 톤(밝은 청회색)
다크  : 같은 톤의 어두운 버전
"""

from __future__ import annotations

LIGHT = {
    "topbar": "#DCE6F0",
    "topbar_text": "#2C3E50",
    "window_bg": "#F5F7FA",
    "panel_bg": "#FFFFFF",
    "text": "#2C3E50",
    "subtext": "#46596B",
    "accent": "#5B8FBF",
    "border": "#C6D3E0",
    "header_bg": "#E4ECF4",
    "select_bg": "#CFE0F4",
    "select_text": "#1A2A38",
    "btn_bg": "#EAF1F8",
    "btn_hover": "#DCE8F4",
    "btn_pressed": "#CCDDEE",
    "input_bg": "#FFFFFF",
    "grid": "#E3EAF1",
    "tab_bg": "#DCE6F0",
    "today": "#FFC98A",
    "tomorrow": "#FFF2A8",
    "row_text": "#000000",     # 강조행 글자색
    "brief_bg": "#EDF2F8",
    "brief_text": "#2C3E50",
    "status_ok": "#2E7D32",
    "status_bad": "#C0392B",
    "scroll": "#B8C9DA",
    "scroll_hover": "#9FB4C8",
}

DARK = {
    "topbar": "#2B3543",
    "topbar_text": "#E6ECF3",
    "window_bg": "#1F2733",
    "panel_bg": "#28313D",
    "text": "#DCE3EC",
    "subtext": "#AEBBC9",
    "accent": "#6FA8DC",
    "border": "#3B4757",
    "header_bg": "#2E3947",
    "select_bg": "#3A4E66",
    "select_text": "#EAF1F8",
    "btn_bg": "#313C4A",
    "btn_hover": "#3B4859",
    "btn_pressed": "#455467",
    "input_bg": "#232B36",
    "grid": "#333E4C",
    "tab_bg": "#28313D",
    "today": "#B5732B",       # 어두운 배경에서도 보이는 주황
    "tomorrow": "#8A7A2E",    # 어두운 노랑
    "row_text": "#FFFFFF",
    "brief_bg": "#28313D",
    "brief_text": "#DCE3EC",
    "status_ok": "#7FD18B",
    "status_bad": "#E88",
    "scroll": "#465262",
    "scroll_hover": "#586778",
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
QCalendarWidget QToolButton {{ color: {p['text']}; background: transparent; }}
QCalendarWidget QMenu {{ background: {p['panel_bg']}; color: {p['text']}; }}
"""
