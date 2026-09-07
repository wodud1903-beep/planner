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

# 다크: **남색빛을 뺀 중성 회색**. R·G·B 를 같은 값으로 두어 어느 화면에서도
# 푸른 기가 돌지 않는다(예전 #101216 은 B 가 R 보다 6 높아 남색으로 보였다).
# 파랑은 포인트(accent)와 선택 배경에만 남긴다.
#
# 이 정도로 어두우면 배경끼리의 밝기 차가 물리적으로 압축된다. 그래서 면 구분은
# 밝기 대신 **테두리**가 맡는다 — border 를 패널 대비 1.40 으로 뒀다.
# 글자 대비는 본문 7:1(17:1 나옴), 나머지 4.5:1 을 지킨다.
DARK = {
    "topbar": "#141414",
    "topbar_text": "#F5F5F5",
    "window_bg": "#0A0A0A",     # 가장 아래 바탕
    "panel_bg": "#141414",      # 그 위에 뜨는 패널·카드
    "text": "#F5F5F5",
    "subtext": "#9A9A9A",
    "accent": "#4593FC",        # 포인트 파랑 — 포커스·선택·링크
    "border": "#303030",        # 면을 가르는 몫이라 뚜렷하게
    "header_bg": "#1F1F1F",
    "select_bg": "#1E3A5F",     # 선택만 파란 기가 돌게
    "select_text": "#DCEBFF",
    "btn_bg": "#1F1F1F",
    "btn_hover": "#2A2A2A",
    "btn_pressed": "#353535",
    "input_bg": "#0A0A0A",
    "grid": "#242424",
    "tab_bg": "#141414",
    "today": "#A05716",
    "tomorrow": "#7A6A1E",
    "row_text": "#FFFFFF",
    "brief_bg": "#141414",
    "brief_text": "#F5F5F5",
    "status_ok": "#2BC47D",
    "status_bad": "#FF5A66",
    "scroll": "#333333",
    "scroll_hover": "#454545",
    "chip_text": "#F5F5F5",
    "chip1": "#1E3A5F",
    "chip2": "#1A4038",
    "chip3": "#4A3620",
    "chip4": "#332C50",
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







# 이름 → (표시이름, 팔레트, 어두운 테마인가)
# 세 가지만 둔다. 여러 벌을 늘려 봐야 고르는 데 시간만 들고, 화면마다 대비를
# 다시 재야 해서 손이 많이 간다.
THEMES = {
    "light": ("기본 (밝은 청회색)", LIGHT, False),
    "warm": ("따뜻한 크림", WARM, False),
    "dark": ("다크", DARK, True),
}
THEME_ORDER = ("light", "warm", "dark")

# 없앤 테마를 쓰던 설정 파일이 들어와도 화면이 안 깨지게 갈아탈 곳을 정해 둔다.
# (설정은 다른 PC 로도 동기화돼서, 아직 옛 버전을 쓰는 PC 가 보낼 수 있다)
_RETIRED = {"ivory": "warm", "peach": "warm", "sage": "light",
            "mint": "light", "violet": "light", "midnight": "dark"}

_current = LIGHT
_is_dark = False
_name = "light"


def set_theme(theme) -> None:
    """테마 지정. 이름(str) 또는 예전 방식의 다크 여부(bool) 를 받는다."""
    global _current, _is_dark, _name
    if isinstance(theme, bool):                 # 구버전 호출 호환
        theme = "dark" if theme else "light"
    key = str(theme or "light").strip().lower()
    key = _RETIRED.get(key, key)            # 없앤 테마는 가장 가까운 것으로
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
    # 밝은 테마: 주황만 한 단계 낮췄다 — 배지 위에서 3.5:1 밖에 안 나왔다
    False: {"blue": "#2C6FB5", "green": "#2E7D32", "red": "#C0392B",
            "orange": "#A35F0D", "violet": "#6247D6", "gray": "#5A6B7C"},
    # 다크는 어두운 바탕에 얹히므로 밝은 쪽으로 올린다(패널 대비 6:1 이상).
    True: {"blue": "#5AA0FF", "green": "#3FD69A", "red": "#FF6B78",
           "orange": "#FFB55C", "violet": "#A78BFA", "gray": "#A5AEBA"},
}
_STRONG_BG = {
    # 배지를 조금 밝혀 그 위의 글자가 4.5:1 을 넘게 했다(예전엔 3.5~4.5)
    False: {"blue": "#EBF3FB", "green": "#EBF6EC", "red": "#FCE8E5",
            "orange": "#FDF5EA", "violet": "#E6E1FB", "gray": "#E7ECF1"},
    True: {"blue": "#16324F", "green": "#123A2C", "red": "#40202A",
           "orange": "#402C15", "violet": "#2C2545", "gray": "#262B33"},
}


def strong(name: str) -> str:
    """진한 강조 글자색 (blue/green/red/orange/violet/gray)."""
    return _STRONG[_is_dark].get(name, c("text"))


def strong_bg(name: str) -> str:
    """강조색과 짝이 되는 옅은 배경색 (건수 배지 등)."""
    return _STRONG_BG[_is_dark].get(name, c("panel_bg"))


# 색을 가득 채운 단추(멘트복사의 [상담후]·[부재중] 등)에 쓰는 바탕색.
#
# strong() 을 그대로 못 쓴다 — strong() 은 '패널 위에 얹는 글자색' 이라 밝은데,
# 그 위에 흰 글자를 올리면 3:1 대로 떨어져 안 읽힌다. 채움색은 반대로 **충분히
# 진해야** 한다. 그래서 테마별로 나누지 않고 한 벌만 둔다 — 9가지 테마 모두에서
# 흰 글자 4.5:1 이상, 패널과도 3:1 이상 떨어지는 값으로 골랐다.
# 빨강·보라는 넣지 않았다. 두 조건(흰 글자 4.5 / 어두운 패널과 3.0)을 같이
# 만족하는 폭이 4.50 언저리로 아주 좁아, 조금만 손봐도 깨진다. 지금 쓰는 곳도
# 없다. 필요해지면 그때 그 화면의 바탕에 맞춰 고르는 편이 안전하다.
_FILL = {"blue": "#2563EB", "teal": "#0F766E", "green": "#15803D"}
_FILL_HOVER = {"blue": "#1D4ED8", "teal": "#0B6E66", "green": "#146B33"}


def fill(name: str) -> str:
    """색을 채운 단추의 바탕색 (그 위에는 흰 글자를 올린다)."""
    return _FILL.get(name, c("accent"))


def fill_hover(name: str) -> str:
    return _FILL_HOVER.get(name, c("btn_hover"))


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
/* 기본 글자를 굵게 — 맑은 고딕은 Regular 와 Bold 두 벌뿐이라 600 이상이어야
   실제로 Bold 로 그려진다. 어두운 화면에서 가는 획이 번져 보이던 것이 걷힌다. */
QWidget {{ font-family: 'Malgun Gothic'; font-weight: 600; color: {p['text']}; }}
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
/* 기본 동작(저장·확인) 단추는 포인트색 테두리를 두껍게 — 어두운 화면에서
   1px 은 거의 안 보였다. 안을 채우지 않는 이유: 밝은 파랑 위의 흰 글자는
   대비가 3:1대로 떨어져 되레 읽기 나빠진다. */
QPushButton:default {{ border: 2px solid {p['accent']}; padding: 4px 13px; }}
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
/* 고른 탭에 포인트색 띠를 얹는다 — 어느 탭에 있는지 글자색만으로는 약하다.
   테마마다 자기 accent 를 쓰므로 밝은 테마에서도 어색하지 않다.
   위쪽을 2px 로 키운 만큼 padding-top 을 1 줄여 글자가 안 밀리게 한다. */
QTabBar::tab:selected {{
    background: {p['panel_bg']}; color: {p['text']};
    border-bottom-color: {p['panel_bg']};
    border-top: 2px solid {p['accent']}; padding-top: 6px;
}}
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
