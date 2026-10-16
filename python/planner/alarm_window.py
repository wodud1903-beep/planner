"""화면 최상단 중앙에 뜨는 알람 팝업 (델파이 uAlarm 이식 + 둥근 디자인).

- 항상 위 + 포커스를 뺏지 않고 표시
- 메모가 있으면 [메모 복사] 버튼으로 클립보드에 복사
- 사이렌 모드: 빨강/어둠 깜빡임 + 비프음, [5분 뒤 다시]
- 조용한 모드(브리핑): 깜빡임·소리 없음, 메모가 내용에 맞춰 커져 스크롤 불필요
- 여러 개가 동시에 뜨면 아래로 쌓인다. 화면 아래가 모자라면 계단식으로 겹친다
- ⚠️ 창은 **언제나 화면(작업표시줄 제외) 안**에 둔다. 예전에는 쌓는 칸 번호를
  알람마다 하나씩 올리기만 하고 닫아도 줄이지 않아, 혼자 뜬 알람도 화면 아래
  밖에 떠서 [확인] 을 누를 수 없었다(강제종료밖에 방법이 없었다).
  그래서 위 막대에도 [✕] 를 두고, 막대를 잡아 끌 수 있게 했다.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from . import config, theme

_open_alarms: list["AlarmWindow"] = []

# 메모 기본 높이의 약 4배
_MEMO_SIREN = 340
_MEMO_QUIET_MIN = 340
_MEMO_MIN = 80          # 화면이 아주 작아도 메모는 이만큼은 보인다(나머지는 스크롤)

_TOP = 20               # 화면 위에서 띄우는 거리
_GAP = 10               # 쌓을 때 창 사이
_CASCADE = 30           # 아래가 모자랄 때 계단식으로 비키는 거리
_EDGE = 8               # 화면 가장자리에서 최소한 띄우는 거리


def _pick_screen():
    """알람을 띄울 모니터 — 마우스가 있는 화면, 모르면 주 모니터."""
    try:
        s = QGuiApplication.screenAt(QCursor.pos())
    except Exception:
        s = None
    return s or QGuiApplication.primaryScreen()


class AlarmWindow(QWidget):
    def __init__(self, title: str, ment: str, stack_index: int, siren: bool = True,
                 html: str = "", action: tuple = ()):
        """action = (단추이름, 누르면 할 일) — 없으면 단추가 안 생긴다.

        알람에서 바로 무언가를 열어 볼 때 쓴다. 무엇을 보여 줄지는 알람이 모르고
        부르는 쪽이 안다(file_preview.set_send_action 과 같은 방식).
        """
        super().__init__()
        self._siren = siren
        self._action = action
        self._blink = 0
        self._snooze_left = 0
        self._moved = False             # 손으로 끌어 옮겼으면 자동 정렬에서 뺀다
        self._screen = _pick_screen()
        self._drag_from: QPoint | None = None

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # 브리핑은 훑어보는 화면이라 조금 넓게 잡는다
        self.setFixedWidth(640 if siren else 720)

        # 색상: 사이렌(알람)은 진한 남회색, 조용한 안내(브리핑)는 밝은 Tablet Light 톤
        if siren:
            card_bg = config.COLOR_ALARM_DARK
            title_color = config.COLOR_ALARM_YELLOW
            memo_css = ("QTextEdit{background:#2f3947;color:#f0f3f7;"
                        "border:1px solid #556;border-radius:10px;padding:8px;}")
            btn_css = ("QPushButton{background:#4a5563;color:#fff;border:none;border-radius:10px;"
                       "padding:6px 14px;font-weight:bold;} QPushButton:hover{background:#5a6675;}")
            bar_text = "일정 알람"
        else:
            card_bg = theme.c("brief_bg")
            title_color = theme.c("accent")
            memo_css = (f"QTextEdit{{background:{theme.c('input_bg')};color:{theme.c('brief_text')};"
                        f"border:1px solid {theme.c('border')};border-radius:10px;padding:8px;}}")
            btn_css = (f"QPushButton{{background:{theme.c('btn_bg')};color:{theme.c('brief_text')};"
                       f"border:1px solid {theme.c('border')};border-radius:10px;"
                       f"padding:6px 14px;font-weight:bold;}} QPushButton:hover{{background:{theme.c('btn_hover')}}}")
            bar_text = "안내"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # 둥근 카드
        self.card = QWidget()
        self.card.setObjectName("card")
        self._set_card_bg(card_bg)
        outer.addWidget(self.card)

        root = QVBoxLayout(self.card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 상단 바 (둥근 윗모서리)
        # 위 막대 — 가운데 제목, 오른쪽 [✕]. 막대를 잡고 끌면 창이 옮겨진다.
        # [✕] 는 [확인] 과 같다. 창 맨 위는 늘 화면 안이라 여기서는 꼭 닫을 수 있다.
        self.bar = QWidget()
        self.bar.setObjectName("bar")
        self.bar.setAttribute(Qt.WA_StyledBackground, True)
        self.bar.setFixedHeight(34)
        self.bar.setCursor(Qt.SizeAllCursor)
        bar_row = QHBoxLayout(self.bar)
        bar_row.setContentsMargins(8, 0, 6, 0)
        bar_row.setSpacing(0)
        self.bar_lbl = QLabel(bar_text)
        self.bar_lbl.setAlignment(Qt.AlignCenter)
        self.btn_x = QPushButton("✕")
        self.btn_x.setFixedSize(30, 26)
        self.btn_x.setCursor(Qt.PointingHandCursor)
        self.btn_x.setToolTip("닫기 (확인과 같음)")
        self.btn_x.clicked.connect(self._dismiss)
        bar_row.addSpacing(30)                  # [✕] 만큼 비워 제목을 가운데에 둔다
        bar_row.addWidget(self.bar_lbl, 1)
        bar_row.addWidget(self.btn_x)
        self.bar.installEventFilter(self)
        self.bar_lbl.installEventFilter(self)
        self._bar_text_color = "#dfe6ef" if siren else theme.c("topbar_text")
        self._set_bar_bg(card_bg)
        root.addWidget(self.bar)

        body = QVBoxLayout()
        body.setContentsMargins(20, 16, 20, 18)
        body.setSpacing(12)

        self.lbl_title = QLabel(title)
        self.lbl_title.setWordWrap(True)
        self._title_color_normal = title_color
        self.lbl_title.setStyleSheet(
            f"color:{title_color};font-size:17px;font-weight:bold;background:transparent;")
        body.addWidget(self.lbl_title)

        self.txt = QTextEdit()
        self.txt.setReadOnly(True)
        # 브리핑은 색·크기를 입힌 HTML 로 온다. 복사(toPlainText)는 그대로 된다.
        if html:
            self.txt.setHtml(html)
        else:
            self.txt.setPlainText(ment)
        self.txt.setStyleSheet(memo_css)
        if ment.strip():
            self.txt.setFixedHeight(self._memo_height(ment, siren, bool(html)))
            body.addWidget(self.txt)
        else:
            self.txt.hide()

        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.btn_copy = QPushButton("메모 복사")
        self.btn_copy.clicked.connect(self._copy)
        self.btn_snooze = QPushButton("5분 뒤 다시")
        self.btn_snooze.clicked.connect(self._snooze)
        self.btn_ok = QPushButton("확인")
        self.btn_ok.clicked.connect(self._dismiss)
        # 눌러서 바로 열어 보는 단추
        self.btn_act = QPushButton(action[0] if action else "")
        self.btn_act.clicked.connect(self._do_action)
        self.btn_act.setVisible(bool(action))
        for b in (self.btn_copy, self.btn_snooze, self.btn_ok, self.btn_act):
            b.setFixedHeight(38)
            b.setStyleSheet(btn_css)
        if ment.strip():
            btns.addWidget(self.btn_copy)
        else:
            self.btn_copy.hide()
        if action:
            btns.addWidget(self.btn_act)
        if siren:
            btns.addWidget(self.btn_snooze)
        else:
            self.btn_snooze.hide()
        btns.addWidget(self.btn_ok)
        body.addLayout(btns)

        root.addLayout(body)

        # 키가 화면보다 크면 메모를 줄인다 — [확인] 이 화면 밖으로 밀려나지 않게.
        # 자리는 popup() 이 열린 알람 전체를 보고 정한다(_layout_all).
        self.adjustSize()
        self._shrink_to_screen()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if siren:
            self._timer.start(500)
            QApplication.beep()

        self._snooze_timer = QTimer(self)
        self._snooze_timer.timeout.connect(self._snooze_tick)

    # ---- 메모 높이 계산 ----
    def _memo_height(self, ment: str, siren: bool, rich: bool = False) -> int:
        if siren:
            return _MEMO_SIREN
        # 브리핑: 내용에 맞춰 늘려 스크롤 없이 다 보이게 하되, 화면 높이로 제한.
        # HTML 은 머리글·여백 때문에 줄 수로 어림하면 자꾸 모자란다.
        # 그래서 문서에 실제 폭을 알려 주고 렌더 높이를 직접 물어본다.
        screen = self._geo()
        if rich:
            doc = self.txt.document()
            doc.setTextWidth(self.width() - 60)
            needed = int(doc.size().height()) + 28
        else:
            needed = 40 + (ment.count("\n") + 1) * 22
        return max(_MEMO_QUIET_MIN, min(needed, screen.height() - 220))

    # ---- 스타일 헬퍼 ----
    def _set_card_bg(self, color: str):
        self.card.setStyleSheet(
            f"#card{{background:{color};border-radius:16px;}}")

    def _set_bar_bg(self, color: str):
        txt = getattr(self, "_bar_text_color", "#dfe6ef")
        self.bar.setStyleSheet(
            f"#bar{{background:{color};"
            "border-top-left-radius:16px;border-top-right-radius:16px;}"
            f"#bar QLabel{{color:{txt};font-weight:bold;background:transparent;}}"
            f"#bar QPushButton{{color:{txt};background:transparent;border:none;"
            "font-size:15px;font-weight:bold;border-radius:8px;}"
            "#bar QPushButton:hover{background:rgba(255,255,255,0.22);}")

    # ---- 화면 안에 두기 ----
    def _geo(self):
        """이 알람이 뜬 모니터의 작업 영역(작업표시줄 제외). 모니터가 빠졌으면 주 모니터."""
        scr = self._screen
        try:
            if scr is None or scr not in QGuiApplication.screens():
                scr = self._screen = QGuiApplication.primaryScreen()
        except Exception:
            scr = QGuiApplication.primaryScreen()
        return scr.availableGeometry()

    def _shrink_to_screen(self):
        """창 키가 화면보다 크면 메모 칸을 줄인다(넘치는 메모는 스크롤로 본다)."""
        room = self._geo().height() - 2 * _EDGE
        over = self.sizeHint().height() - room
        if over > 0 and not self.txt.isHidden():
            self.txt.setFixedHeight(max(_MEMO_MIN, self.txt.height() - over))
        self.adjustSize()

    def _fit(self):
        """창 전체가 화면 안에 들도록 자리를 잘라 넣는다. 그래도 크면 위를 맞춘다."""
        g = self._geo()
        x = min(max(self.x(), g.left() + _EDGE), g.right() + 1 - _EDGE - self.width())
        y = min(max(self.y(), g.top() + _EDGE), g.bottom() + 1 - _EDGE - self.height())
        self.move(max(x, g.left()), max(y, g.top()))

    # ---- 위 막대를 잡고 끌기 ----
    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        t = ev.type()
        if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
            self._drag_from = ev.globalPosition().toPoint() - self.pos()
            return True
        if t == QEvent.MouseMove and self._drag_from is not None:
            self.move(ev.globalPosition().toPoint() - self._drag_from)
            self._fit()
            self._moved = True
            return True
        if t == QEvent.MouseButtonRelease and self._drag_from is not None:
            self._drag_from = None
            return True
        return super().eventFilter(obj, ev)

    # ---- 사이렌 깜빡임 ----
    def _tick(self):
        self._blink += 1
        if self._blink % 2 == 1:
            self._set_card_bg(config.COLOR_ALARM_RED)
            self._set_bar_bg(config.COLOR_ALARM_RED)
            self.lbl_title.setStyleSheet(
                "color:#fff;font-size:17px;font-weight:bold;background:transparent;")
        else:
            self._set_card_bg(config.COLOR_ALARM_DARK)
            self._set_bar_bg(config.COLOR_ALARM_DARK)
            self.lbl_title.setStyleSheet(
                f"color:{config.COLOR_ALARM_YELLOW};font-size:17px;font-weight:bold;background:transparent;")
        self.raise_()
        if self._blink % 3 == 0:
            QApplication.beep()

    def _copy(self):
        try:
            QApplication.clipboard().setText(self.txt.toPlainText())
            self.btn_copy.setText("복사됨 ✔")
        except Exception:
            self.btn_copy.setText("복사 실패")

    def _snooze(self):
        self._timer.stop()
        self._snooze_left = 5 * 60
        self._snooze_timer.start(1000)
        self.hide()

    def _snooze_tick(self):
        self._snooze_left -= 1
        if self._snooze_left > 0:
            return
        self._snooze_timer.stop()
        self._blink = 0
        self.show_no_activate()
        _layout_all()
        if self._siren:
            self._timer.start(500)
            QApplication.beep()

    def stop(self):
        self._timer.stop()
        self._snooze_timer.stop()

    def _do_action(self):
        """[보기] 같은 단추 — 시킨 일을 하고 팝업을 닫는다.

        일을 하다 탈이 나도 팝업은 닫는다. 안 그러면 못 닫는 창이 화면에 남는다.
        """
        fn = self._action[1] if len(self._action) > 1 else None
        try:
            if callable(fn):
                fn()
        except Exception:
            pass
        self._dismiss()

    def _dismiss(self):
        self.stop()
        self.close()

    def show_no_activate(self):
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.show()
        self.raise_()

    def closeEvent(self, event):
        self.stop()
        if self in _open_alarms:
            _open_alarms.remove(self)
        super().closeEvent(event)
        QTimer.singleShot(0, _layout_all)       # 남은 알람을 위로 당긴다


def _layout_all():
    """열려 있는 알람을 화면 위 가운데부터 아래로 쌓는다.

    아래가 모자라면 더 내려가지 않고 위쪽에서 오른쪽·아래로 조금씩 비켜 겹친다.
    손으로 옮긴 창은 그 자리에 두되 화면 안으로만 넣는다.
    """
    y_next: dict = {}           # 모니터별 다음 칸
    cascade: dict = {}          # 모니터별 겹친 수
    for w in list(_open_alarms):
        try:
            if not w.isVisible():
                continue        # 5분 뒤 다시 — 숨어 있는 동안은 칸을 차지하지 않는다
            if w._moved:
                w._fit()
                continue
            g = w._geo()
            key = (g.x(), g.y(), g.width(), g.height())
            x = g.left() + (g.width() - w.width()) // 2
            y = y_next.get(key, g.top() + _TOP)
            if y + w.height() > g.bottom() + 1 - _EDGE and y > g.top() + _TOP:
                k = cascade.get(key, 0) + 1
                cascade[key] = k
                x += _CASCADE * k
                y = g.top() + _TOP + _CASCADE * k
            else:
                y_next[key] = y + w.height() + _GAP
            w.move(x, y)
            w._fit()
        except RuntimeError:
            continue            # 이미 지워진 창


def popup(title: str, ment: str, stack_index: int = 0, siren: bool = True,
          html: str = "", action: tuple = ()) -> AlarmWindow:
    """알람을 띄운다. stack_index 는 옛 호출 호환용 — 자리는 _layout_all 이 정한다."""
    _hook_screens()
    w = AlarmWindow(title, ment, stack_index, siren, html, action)
    _open_alarms.append(w)
    w.show_no_activate()
    _layout_all()
    return w


def _on_screens_changed(*_a):
    QTimer.singleShot(0, _layout_all)       # 해상도·모니터가 바뀌면 다시 화면 안으로


_hooked = False


def _hook_screens():
    global _hooked
    app = QGuiApplication.instance()
    if _hooked or app is None:
        return
    _hooked = True
    app.screenAdded.connect(_on_screens_changed)
    app.screenRemoved.connect(_on_screens_changed)
    for s in app.screens():
        s.availableGeometryChanged.connect(_on_screens_changed)


def close_all():
    for w in list(_open_alarms):
        w.stop()
        w.close()
