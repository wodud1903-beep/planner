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
    "chip_text": "#1B2B3A",
    "chip1": "#BBD6F2",
    "chip2": "#C9E6C9",
    "chip3": "#F6DCC0",
    "chip4": "#DCD3F0",
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
    "chip_text": "#EAF1F8",
    "chip1": "#31465C",
    "chip2": "#33513A",
    "chip3": "#5A4630",
    "chip4": "#443A5E",
}

# 따뜻한 크림톤 — 가계부 앱 같은 부드러운 느낌 (오래 봐도 눈이 편하다)
WARM = {
    "topbar": "#F3E3D3",
    "topbar_text": "#5B4636",
    "window_bg": "#FBF3EA",
    "panel_bg": "#FFFBF6",
    "text": "#4A3B2F",
    "subtext": "#8A7663",
    "accent": "#E08A5C",
    "border": "#E6D5C3",
    "header_bg": "#F6E8DA",
    "select_bg": "#F8DFC8",
    "select_text": "#4A3B2F",
    "btn_bg": "#F6E9DC",
    "btn_hover": "#F0DECB",
    "btn_pressed": "#E8D2B9",
    "input_bg": "#FFFCF8",
    "grid": "#EADBCB",
    "tab_bg": "#F3E3D3",
    "today": "#F7C08A",
    "tomorrow": "#FBEAB4",
    "row_text": "#3D2F24",
    "brief_bg": "#F7ECE0",
    "brief_text": "#4A3B2F",
    "status_ok": "#4C8C4A",
    "status_bad": "#C0562F",
    "scroll": "#DFCBB6",
    "scroll_hover": "#CBB49C",
    "chip_text": "#40312A",
    "chip1": "#F6D9BE",
    "chip2": "#E9DFC7",
    "chip3": "#F3CDBF",
    "chip4": "#E2D7C4",
}

# 아이보리 — 미색 종이 톤. 흰 화면이 눈부실 때 가장 무난하다.
IVORY = {
    "topbar": "#EDE6D6",
    "topbar_text": "#4B4437",
    "window_bg": "#F7F2E6",
    "panel_bg": "#FCF9F1",
    "text": "#413B30",
    "subtext": "#7B7263",
    "accent": "#B08E4E",
    "border": "#DFD6C2",
    "header_bg": "#F0EADC",
    "select_bg": "#EBE0C4",
    "select_text": "#332E25",
    "btn_bg": "#F2ECDE",
    "btn_hover": "#EAE2D0",
    "btn_pressed": "#DED4BE",
    "input_bg": "#FDFBF5",
    "grid": "#E5DCCA",
    "tab_bg": "#EDE6D6",
    "today": "#F3C98C",
    "tomorrow": "#F7EDB4",
    "row_text": "#332E25",
    "brief_bg": "#F2EDE0",
    "brief_text": "#413B30",
    "status_ok": "#43813F",
    "status_bad": "#B4472F",
    "scroll": "#D8CEB9",
    "scroll_hover": "#C2B69C",
    "chip_text": "#332E25",
    "chip1": "#E9DEC2",
    "chip2": "#DCE5CE",
    "chip3": "#F0DEC9",
    "chip4": "#DFE0D0",
}

# 민트 — 아주 옅은 청록. 오래 봐도 눈이 시원한 쪽.
MINT = {
    "topbar": "#DCEDE7",
    "topbar_text": "#28453E",
    "window_bg": "#EDF6F2",
    "panel_bg": "#F8FCFA",
    "text": "#28453E",
    "subtext": "#5B7A72",
    "accent": "#3E9C86",
    "border": "#CBE0D9",
    "header_bg": "#E3F0EB",
    "select_bg": "#C9E6DC",
    "select_text": "#1D362F",
    "btn_bg": "#E6F2ED",
    "btn_hover": "#D9EBE4",
    "btn_pressed": "#C6E0D7",
    "input_bg": "#FBFDFC",
    "grid": "#D7E7E1",
    "tab_bg": "#DCEDE7",
    "today": "#F6C58A",
    "tomorrow": "#F7EFB2",
    "row_text": "#1D362F",
    "brief_bg": "#E5F1EC",
    "brief_text": "#28453E",
    "status_ok": "#2E7D5B",
    "status_bad": "#C0503A",
    "scroll": "#BFD8D0",
    "scroll_hover": "#A4C4BA",
    "chip_text": "#1D362F",
    "chip1": "#CBE6DC",
    "chip2": "#DCE9C9",
    "chip3": "#F0DFC8",
    "chip4": "#D3E1EE",
}

# 세이지 — 연둣빛 회색. 초록 계열 중 가장 차분하다.
SAGE = {
    "topbar": "#E1E7D8",
    "topbar_text": "#3B4433",
    "window_bg": "#F0F3E9",
    "panel_bg": "#FAFBF5",
    "text": "#3B4433",
    "subtext": "#6C7660",
    "accent": "#6E8E4E",
    "border": "#D5DCC7",
    "header_bg": "#E7EDDD",
    "select_bg": "#D9E4C6",
    "select_text": "#2C3427",
    "btn_bg": "#EAEFE1",
    "btn_hover": "#DFE6D3",
    "btn_pressed": "#CFD9C0",
    "input_bg": "#FCFDF8",
    "grid": "#DDE4D2",
    "tab_bg": "#E1E7D8",
    "today": "#F3C68B",
    "tomorrow": "#F5EDAE",
    "row_text": "#2C3427",
    "brief_bg": "#E9EEE0",
    "brief_text": "#3B4433",
    "status_ok": "#417A3C",
    "status_bad": "#B94E34",
    "scroll": "#CCD5BE",
    "scroll_hover": "#B3BFA1",
    "chip_text": "#2C3427",
    "chip1": "#DCE6C8",
    "chip2": "#CFE2D6",
    "chip3": "#EEE0C6",
    "chip4": "#DDDCEA",
}

# 살구 — 연분홍빛 크림. '따뜻한 크림' 보다 더 밝고 부드럽다.
PEACH = {
    "topbar": "#F6E2DC",
    "topbar_text": "#553D38",
    "window_bg": "#FCF2EE",
    "panel_bg": "#FFFAF8",
    "text": "#4B362F",
    "subtext": "#8B6F66",
    "accent": "#D07A5E",
    "border": "#EDD6CD",
    "header_bg": "#F8E8E2",
    "select_bg": "#F7DACE",
    "select_text": "#42302A",
    "btn_bg": "#F9EAE4",
    "btn_hover": "#F4DED6",
    "btn_pressed": "#EBCCC1",
    "input_bg": "#FFFCFB",
    "grid": "#EFDBD3",
    "tab_bg": "#F6E2DC",
    "today": "#F7C193",
    "tomorrow": "#FAECB6",
    "row_text": "#42302A",
    "brief_bg": "#F8EBE6",
    "brief_text": "#4B362F",
    "status_ok": "#4B8A52",
    "status_bad": "#C24A3E",
    "scroll": "#E3C9C0",
    "scroll_hover": "#D0AFA4",
    "chip_text": "#42302A",
    "chip1": "#F6D8CB",
    "chip2": "#E4E3CC",
    "chip3": "#F2DDE6",
    "chip4": "#D8E2E6",
}

# 바이올렛 — 금융앱 같은 산뜻한 보라 포인트
VIOLET = {
    "topbar": "#E7E3FB",
    "topbar_text": "#2E2A45",
    "window_bg": "#F5F3FE",
    "panel_bg": "#FFFFFF",
    "text": "#2E2A45",
    "subtext": "#6B6688",
    "accent": "#6C5CE7",
    "border": "#DEDAF3",
    "header_bg": "#EDEAFC",
    "select_bg": "#DED8FB",
    "select_text": "#241F3D",
    "btn_bg": "#EFECFD",
    "btn_hover": "#E4DFFB",
    "btn_pressed": "#D5CDF8",
    "input_bg": "#FFFFFF",
    "grid": "#E5E1F6",
    "tab_bg": "#E7E3FB",
    "today": "#FFD08A",
    "tomorrow": "#FFF0B0",
    "row_text": "#241F3D",
    "brief_bg": "#EFECFD",
    "brief_text": "#2E2A45",
    "status_ok": "#2E9E6B",
    "status_bad": "#D6455D",
    "scroll": "#CFC8EE",
    "scroll_hover": "#B7ADE6",
    "chip_text": "#241F3D",
    "chip1": "#D8D0FA",
    "chip2": "#CFE3FB",
    "chip3": "#DCEFD9",
    "chip4": "#F7DCE8",
}

# 미드나잇 — 다크의 보라 계열 변형
MIDNIGHT = {
    "topbar": "#1E1B2E",
    "topbar_text": "#E6E2F5",
    "window_bg": "#15131F",
    "panel_bg": "#1E1B2E",
    "text": "#D8D3EC",
    "subtext": "#9791B5",
    "accent": "#9B8CFF",
    "border": "#2E2A45",
    "header_bg": "#252135",
    "select_bg": "#332C50",
    "select_text": "#F0EDFF",
    "btn_bg": "#272338",
    "btn_hover": "#312B47",
    "btn_pressed": "#3C3556",
    "input_bg": "#191627",
    "grid": "#2B2740",
    "tab_bg": "#1E1B2E",
    "today": "#8A5A2B",
    "tomorrow": "#6E6224",
    "row_text": "#F2EFFF",
    "brief_bg": "#1E1B2E",
    "brief_text": "#D8D3EC",
    "status_ok": "#7FD1A6",
    "status_bad": "#FF8A9B",
    "scroll": "#332E4A",
    "scroll_hover": "#443D60",
    "chip_text": "#F0EDFF",
    "chip1": "#3B3363",
    "chip2": "#2F4759",
    "chip3": "#4A3A5F",
    "chip4": "#334A3E",
}

# 이름 → (표시이름, 팔레트, 어두운 테마인가)
THEMES = {
    "light": ("기본 (밝은 청회색)", LIGHT, False),
    "warm": ("따뜻한 크림", WARM, False),
    "ivory": ("아이보리 (미색 종이)", IVORY, False),
    "peach": ("살구 (연한 크림핑크)", PEACH, False),
    "sage": ("세이지 (연한 연둣빛)", SAGE, False),
    "mint": ("민트 (연한 청록)", MINT, False),
    "violet": ("바이올렛", VIOLET, False),
    "dark": ("다크", DARK, True),
    "midnight": ("미드나잇 (다크 보라)", MIDNIGHT, True),
}
THEME_ORDER = ("light", "warm", "ivory", "peach", "sage", "mint",
               "violet", "dark", "midnight")

_current = LIGHT
_is_dark = False
_name = "light"


def set_theme(theme) -> None:
    """테마 지정. 이름(str) 또는 예전 방식의 다크 여부(bool) 를 받는다."""
    global _current, _is_dark, _name
    if isinstance(theme, bool):                 # 구버전 호출 호환
        theme = "dark" if theme else "light"
    key = str(theme or "light").strip().lower()
    if key not in THEMES:
        key = "light"
    _name, (_disp, pal, dark) = key, THEMES[key]
    _current = pal
    _is_dark = dark


def theme_name() -> str:
    return _name


def is_dark() -> bool:
    return _is_dark


def chip_colors() -> list:
    """캘린더 칸에 일정을 칠할 때 쓰는 색 (여러 개면 번갈아 쓴다)."""
    return [_current.get(f"chip{i}", _current.get("select_bg", "#DDD"))
            for i in range(1, 5)]


# 브리핑처럼 '한눈에 들어와야 하는' 화면에서 쓰는 진한 강조색.
# 팔레트마다 따로 두면 5벌을 관리해야 해서, 밝은/어두운 두 벌만 둔다.
_STRONG = {
    False: {"blue": "#2C6FB5", "green": "#2E7D32", "red": "#C0392B",
            "orange": "#B4690E", "violet": "#6247D6", "gray": "#5A6B7C"},
    True: {"blue": "#7FB3E8", "green": "#7FD18B", "red": "#FF8A9B",
           "orange": "#E8A34A", "violet": "#9B8CFF", "gray": "#9AA7B4"},
}
_STRONG_BG = {
    False: {"blue": "#DCEAF8", "green": "#DDF0DE", "red": "#FBE0DC",
            "orange": "#FAE8CE", "violet": "#E6E1FB", "gray": "#E4E9EF"},
    True: {"blue": "#22384D", "green": "#20402A", "red": "#4A2830",
           "orange": "#4A3620", "violet": "#332C50", "gray": "#2A2F36"},
}


def strong(name: str) -> str:
    """진한 강조 글자색 (blue/green/red/orange/violet/gray)."""
    return _STRONG[_is_dark].get(name, c("text"))


def strong_bg(name: str) -> str:
    """강조색과 짝이 되는 옅은 배경색 (건수 배지 등)."""
    return _STRONG_BG[_is_dark].get(name, c("panel_bg"))


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
/* 콤보 안의 입력칸 — 테두리를 또 그리면 이중선이 된다 */
QComboBox QLineEdit {{ border: none; background: transparent; padding: 0; }}
/* 검색형 드롭다운의 목록 (QCompleter 팝업 — 콤보의 자식이 아니라 별도 창이다) */
QListView#searchpopup {{
    background: {p['panel_bg']}; color: {p['text']};
    border: 1px solid {p['accent']}; border-radius: 8px;
    padding: 3px; outline: none;
}}
QListView#searchpopup::item {{ padding: 5px 8px; border-radius: 5px; }}
QListView#searchpopup::item:selected {{ background: {p['select_bg']}; color: {p['select_text']}; }}
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
/* 좌우로 나눈 화면의 손잡이 — 규칙이 없으면 시스템 기본이 검은 선으로 그려진다 */
QSplitter {{ background: transparent; }}
QSplitter::handle {{ background: transparent; border: none; image: none; }}
QSplitter::handle:horizontal {{ width: 8px; }}
QSplitter::handle:vertical {{ height: 8px; }}
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
