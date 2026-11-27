"""카톡 매크로 화면 — A1Auto 창(Unit1.dfm) · 환경설정(Unit2) · 자주 쓰는 문구(Unit3)를 Qt 로(v1.37).

일정관리기('카톡 매크로' 메뉴)와 업무자료검색([카톡 매크로] 창)이 이 파일을 **그대로** 쓴다(사본).
앱마다 다른 것은 밖에서 넣는다:
  · tray        — 그 앱의 트레이 아이콘. 끝나면 풍선 알림('A1Auto — 정상 종료'), 도는 동안 풍선말에 진행.
  · io_getter() — (내 구글 계정 앱 전용 공간 io, 계정 이메일). 로그인 전 · 계정 확인 전이면 (None, "").
  · armed()     — Insert · Delete 를 볼 때인가. 일정관리기: 이 메뉴가 지금 화면 · 업무자료검색: 창이 열려 있음.
                  (A1Auto 를 켜 둔 상태와 같다 — 다른 화면에서 Delete 로 지울 때 '중단' 이 찍히지 않게)
자리 · 글자는 A1Auto 그대로, 색은 앱 테마(팔레트)를 따른다. 동작은 kakao_macro.MacroEngine 이 한다.
v1.38: 도구 → 발송 기록(고객 목록 · 발송 로그를 내 구글 계정과 맞춰 보여 준다 — kakao_history) · 수정로그(CHANGE_LOG).
"""

from __future__ import annotations

import csv
import html
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QEventLoop, QModelIndex, QObject, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPalette, QPixmap, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QMenu, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea, QSizePolicy, QTableView, QTabWidget,
    QTextBrowser, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from . import kakao_history as kh
from . import kakao_macro as km
from . import kakao_win as kw
from . import theme                    # 일정관리기 · 업무자료검색 모두 같은 theme 사본을 가진다

TITLE = km.APP_TITLE                   # 알림 창 제목 — A1Auto 의 ShowMessage 처럼
START_TONE, STOP_TONE = "green", "amber"   # 시작 · 중지 단추 채움색(theme.fill — 흰 글자 4.5:1 이상, 어느 테마든)
HISTORY_EVERY_MS = 10 * 60 * 1000          # 쉬는 동안 발송 기록을 계정과 맞추는 간격(바뀐 게 없으면 판만 묻는다)


# ---------------------------------------------------------------------------
# 엔진이 바깥과 닿는 곳(진짜)
# ---------------------------------------------------------------------------
class QtEnv:
    """시계(GetTickCount) · Delay(기다리는 동안 화면이 돈다) · 클립보드 · 1ms 타이머 · 윈도 API."""

    def __init__(self, win=None):
        self.win = win or kw.default()
        self.closing = False           # 앱을 끄는 중 — 남은 기다림을 건너뛴다

    @staticmethod
    def tick() -> int:
        return int(time.monotonic() * 1000) + 1

    def delay(self, ms: int) -> None:
        """델파이 Delay — GetTickCount 가 지날 때까지 Application.ProcessMessages + Sleep(1)."""
        end = self.tick() + int(ms)
        while not self.closing and self.tick() < end:
            QApplication.processEvents(QEventLoop.AllEvents, 5)
            time.sleep(0.001)

    @staticmethod
    def now() -> datetime:
        return datetime.now()

    @staticmethod
    def clip_get():
        md = QGuiApplication.clipboard().mimeData()
        if md is None or not md.hasText():
            return None
        return md.text()

    def clip_set(self, s: str) -> None:
        """Clipboard.AsText := S — 다른 프로그램이 클립보드를 쥐고 있어 못 넣었으면 오류(엔진이 100ms 뒤 다시)."""
        QGuiApplication.clipboard().setText(s)
        got = self.clip_get()
        if (got or "").replace("\r\n", "\n") != (s or "").replace("\r\n", "\n"):
            raise RuntimeError("클립보드에 넣지 못함")

    @staticmethod
    def later(fn) -> None:
        QTimer.singleShot(1, fn)


class _Sync(QObject):
    """발송 간격 · 자주 쓰는 문구를 계정과 맞춘다(뒤에서 — 화면이 안 멈춘다)."""

    done = Signal(bool)

    def __init__(self, prefs, parent=None):
        super().__init__(parent)
        self.prefs = prefs
        self._lock = threading.Lock()
        self._busy = False
        self._again = None
        self.done.connect(self._finished)
        self.on_changed = None

    def start(self, io, account: str) -> None:
        with self._lock:
            if self._busy:
                self._again = (io, account)
                return
            self._busy = True
            self._again = None
        threading.Thread(target=self._run, args=(io, account), daemon=True).start()

    def busy(self) -> bool:
        return self._busy

    def _run(self, io, account):
        try:
            ch = self.prefs.sync_once(io, account)
        except Exception:
            ch = False                  # 인터넷이 없거나 계정 오류 — 이 PC 사본으로 계속, 다음에 다시
        self.done.emit(bool(ch))

    def _finished(self, changed: bool):
        with self._lock:
            self._busy = False
            again = self._again
            self._again = None
        if changed and self.on_changed:
            self.on_changed()
        if again is not None:
            self.start(*again)


class _HistorySync(QObject):
    """발송 기록 · 발송 로그를 계정과 맞춘다 — 읽기 · 합치기 · 올리기는 뒤에서, 이 PC 파일 쓰기는 매크로가 쉴 때."""

    done = Signal(object, str)

    def __init__(self, book, view):
        super().__init__(view)
        self.book, self.view = book, view
        self._busy = False
        self._again = None
        self._stale = 0
        self.state = ("idle", "")      # idle · run · ok(맞춘 시각) · local(로그인 전) · err(까닭)
        self.done.connect(self._finished)

    def busy(self) -> bool:
        return self._busy

    def start(self, io, account: str) -> None:
        if self._busy:
            self._again = (io, account)
            return
        self._busy = True
        self.state = ("run", "")
        self.view.history_synced.emit()
        threading.Thread(target=self._run, args=(io, account), daemon=True).start()

    def _run(self, io, account):
        try:
            plan, err = self.book.prepare(io, account), ""
        except Exception as e:          # 인터넷 · 계정 오류 · 깨진 파일 — 이 PC 기록으로 계속, 다음에 다시
            plan, err = None, (str(e).strip() or e.__class__.__name__)
        self.done.emit(plan, err)

    def _finished(self, plan, err: str):
        self._busy = False
        res = ""
        if plan is not None:
            if self.view.busy():
                self.view._history_wanted = True       # 매크로가 도는 중 — 이 PC 파일은 끝난 뒤에
                res = "later"
            else:
                try:
                    res = self.book.apply(plan)
                except Exception as e:
                    plan, err = None, (str(e).strip() or e.__class__.__name__)
        if plan is None:
            self.state = ("err", err[:200])
        elif res == "later":
            self.state = ("idle", "")                  # 끝난 뒤 다시 맞춘다 — '맞추는 중' 으로 남겨 두지 않는다
        else:
            self.state = ("ok", datetime.now().strftime("%H:%M")) if plan.online else ("local", "")
            if res == "stale" and self._stale < 3:
                self._stale += 1
                self.view._history_wanted = True       # 그사이 이 PC 에서 바뀌었다(보냄 · 옆 프로그램) — 곧 다시
            else:
                self._stale = 0
            if res == "applied":
                try:
                    self.view.store.load()              # 매크로 색인도 합친 것으로(다른 PC 에서 보낸 사람 건너뛰기)
                except Exception:
                    pass
        self.view.history_synced.emit()
        again, self._again = self._again, None
        if again is not None:
            self.start(*again)


# ---------------------------------------------------------------------------
# 작은 부품
# ---------------------------------------------------------------------------
class _Preview(QLabel):
    """ImageDisplay — 가운데 · 비율 유지 · 칸에 맞춰 늘리고 줄인다(Center · Proportional · Stretch)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix = QPixmap()
        self.setMinimumSize(120, 120)
        self.setObjectName("kmPreview")

    def set_pixmap(self, pix: QPixmap) -> None:
        self._pix = pix if pix is not None else QPixmap()
        self.update()

    def has_image(self) -> bool:
        return not self._pix.isNull()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._pix.isNull():
            return
        r = self.contentsRect()
        sz = self._pix.size().scaled(r.size(), Qt.KeepAspectRatio)
        x = r.x() + (r.width() - sz.width()) / 2
        y = r.y() + (r.height() - sz.height()) / 2
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawPixmap(QRectF(x, y, sz.width(), sz.height()).toRect(), self._pix)
        p.end()


def _card(caption: str) -> tuple:
    fr = QFrame()
    fr.setObjectName("kmCard")
    fr.setFixedSize(112, 64)
    lay = QVBoxLayout(fr)
    lay.setContentsMargins(10, 0, 6, 0)
    lb = QLabel(caption)
    lb.setObjectName("kmCardText")
    lay.addWidget(lb, 0, Qt.AlignVCenter)
    return fr, lb


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    """a 를 t 만큼 b 위에 섞은 색(테두리 · 막대 바탕 — 테마 팔레트에서 만든다)."""
    return QColor(round(a.red() * t + b.red() * (1 - t)), round(a.green() * t + b.green() * (1 - t)),
                  round(a.blue() * t + b.blue() * (1 - t)))


# ---------------------------------------------------------------------------
# 화면(TForm1)
# ---------------------------------------------------------------------------
class KakaoMacroView(QWidget):
    """A1Auto 본 창 — 전송방식 · 이미지 · 전송 메시지 · 시작/중지 · 카드 · 진행 · 로그 · 도구 메뉴."""

    history_synced = Signal()           # 발송 기록을 맞추기 시작했다 · 끝났다(발송 기록 창이 다시 그린다)

    def __init__(self, parent=None, tray=None, io_getter=None, armed=None, prefs=None, store=None, env=None,
                 need_login=None, history=None):
        super().__init__(parent)
        self.setObjectName("kakaoMacro")
        self.tray = tray
        # 로그인 안 했으면 그 안내 글, 했으면 "" — 매크로는 구글 로그인을 해야만 시작한다(v1.37)
        self.need_login = need_login or (lambda: "")
        self.io_getter = io_getter or (lambda: (None, ""))
        self.armed = armed or (lambda: not self.isHidden())
        self.prefs = prefs if prefs is not None else km.Prefs()
        try:
            self.prefs.seed_from_ini()   # A1Auto 를 쓰던 PC 면 C:\jy.ini 값으로 시작(처음 한 번)
        except Exception:
            pass
        self.env = env if env is not None else QtEnv()
        self.store = store if store is not None else km.CustomerStore()
        self._image_path = ""            # imageurl(A1Auto 의 숨은 칸)
        self._tip_idle = None
        self._dlg_phrases = None
        self._dlg_env = None
        self._dlg_hist = None
        self._dlg_log = None
        self._history_wanted = False
        # 발송 기록(v1.38) — customers.tsv 옆 파일 · 계정 kakao_history.json
        self.history = history if history is not None else kh.HistoryBook(tsv=self.store.path)
        self._build()
        self.engine = km.MacroEngine(self, self.env, self.store, self.prefs)
        self.sync_worker = _Sync(self.prefs, self)
        self.sync_worker.on_changed = self._on_prefs_changed
        self.hist_worker = _HistorySync(self.history, self)
        # HotkeyTimer(1초) · CurrentProgress(Timer2, 1초) — A1Auto 기본 간격 그대로
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.setInterval(1000)
        self.hotkey_timer.timeout.connect(self._on_hotkey)
        self.hotkey_timer.start()
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(1000)
        self.progress_timer.timeout.connect(self._on_progress_tick)
        self.progress_timer.start()
        self.hist_timer = QTimer(self)
        self.hist_timer.setInterval(HISTORY_EVERY_MS)
        self.hist_timer.timeout.connect(self.sync_history)
        self.hist_timer.start()
        self.engine.update_progress_ui()

    # ------------------------------------------------------------ 만들기
    def _build(self):
        self.setStyleSheet(self._css())
        # 내용은 스크롤 안에 — 창이 낮아도(노트북 768) 이 화면이 앱 창의 최소 높이를 끌어올리지 않게.
        # ⚠️ 색 규칙은 안쪽 바탕(#kmBody) 기준이다 — 일정관리기는 쪽마다 이름을 'pagecard' 로 바꿔 흰 카드로 칠하므로
        #    이 화면 자신의 이름(#kakaoMacro)으로 걸면 시작 · 중지 단추 색이 사라졌다.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("kmScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.body = QWidget()
        self.body.setObjectName("kmBody")
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll)
        root = QVBoxLayout(self.body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # 도구 메뉴(A1Auto 메뉴줄 '도구')
        top = QHBoxLayout()
        self.btn_tools = QToolButton()
        self.btn_tools.setObjectName("kmTools")
        self.btn_tools.setText("도구 ▾")
        self.btn_tools.setPopupMode(QToolButton.InstantPopup)
        self.btn_tools.setToolButtonStyle(Qt.ToolButtonTextOnly)
        m = QMenu(self.btn_tools)
        self.act_phrases = m.addAction("자주 쓰는 문구", self.open_phrases)      # N4
        self.act_hist = m.addAction("발송 기록", self.open_history)             # v1.38 — 고객 목록 · 발송 로그
        self.act_env = m.addAction("환경설정", self.open_env)                   # N2
        self.act_log = m.addAction("수정로그", self.show_change_log)            # N3
        self.btn_tools.setMenu(m)
        top.addWidget(self.btn_tools)
        top.addStretch(1)
        self.lbl_where = QLabel("")
        self.lbl_where.setObjectName("kmWhere")
        top.addWidget(self.lbl_where)
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(12)
        # ---- 왼쪽: 전송방식 · 이미지 불러오기 · 미리보기 ----
        left = QVBoxLayout()
        left.setSpacing(8)
        self.grp_mode = QGroupBox("전송방식")
        self.grp_mode.setFixedWidth(192)
        gl = QVBoxLayout(self.grp_mode)
        gl.setContentsMargins(12, 8, 8, 8)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.rb_modes = []
        for i, t in enumerate(km.MODES):
            rb = QRadioButton(t)
            self.mode_group.addButton(rb, i)
            gl.addWidget(rb)
            self.rb_modes.append(rb)
        self.mode_group.idClicked.connect(self._on_mode_clicked)       # RadioGroup1Click
        left.addWidget(self.grp_mode)
        self.btn_image = QPushButton("이미지 불러오기")
        self.btn_image.setFixedSize(192, 30)
        self.btn_image.clicked.connect(self.pick_image)                # imageClick
        left.addWidget(self.btn_image)
        self.preview = _Preview()
        self.preview.setFixedWidth(192)
        self.preview.setMinimumHeight(100)       # 남는 높이를 받아 A1Auto 의 200 보다 커진다(낮은 노트북 화면에서도 맞게)
        left.addWidget(self.preview, 1)
        body.addLayout(left)

        # ---- 오른쪽: 전송 메시지 · 시작/중지 ----
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(QLabel("전송 메시지"))
        self.memo = QPlainTextEdit()
        self.memo.setObjectName("kmMemo")
        f = self.memo.font()
        f.setPixelSize(13)
        self.memo.setFont(f)
        self.memo.setMinimumHeight(180)
        right.addWidget(self.memo, 1)
        btns = QHBoxLayout()
        btns.setSpacing(12)
        self.btn_start = QPushButton("매크로 시작 (INSERT)")
        self.btn_start.setObjectName("kmStart")
        self.btn_start.setFixedHeight(48)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(lambda: self.engine.button1_click())     # Panel2Click
        self.btn_stop = QPushButton("매크로 중지 (DELETE)")
        self.btn_stop.setObjectName("kmStop")
        self.btn_stop.setFixedHeight(48)
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.clicked.connect(lambda: self.engine.button2_click())      # Panel1Click
        btns.addWidget(self.btn_start, 1)
        btns.addWidget(self.btn_stop, 1)
        right.addLayout(btns)
        body.addLayout(right, 1)
        root.addLayout(body, 3)                  # 남는 높이는 메시지 쪽 3 : 로그 1(A1Auto 의 284 : 148 쯤)

        # ---- 카드 · 발송인원수 ----
        cards = QHBoxLayout()
        cards.setSpacing(6)
        self.card_success, self.lbl_success = _card("성공횟수")
        self.card_stop, self.lbl_stop = _card("중단횟수")
        self.card_speed, self.lbl_speed = _card("속도:")
        self.card_skip, self.lbl_skip = _card("건너뜀")
        for fr in (self.card_success, self.card_stop, self.card_speed, self.card_skip):
            cards.addWidget(fr)
        cards.addStretch(1)
        cards.addWidget(QLabel("발송인원수"))
        self.ed_count = QLineEdit("0")
        self.ed_count.setFixedWidth(64)
        self.ed_count.setAlignment(Qt.AlignCenter)
        self.ed_count.setToolTip("0 = 끝까지")
        cards.addWidget(self.ed_count)
        root.addLayout(cards)

        # ---- 진행 막대 · 진행 글(Label3) ----
        self.prog = QProgressBar()
        self.prog.setObjectName("kmProg")
        self.prog.setRange(0, 1000)
        self.prog.setValue(0)
        self.prog.setTextVisible(False)
        self.prog.setFixedHeight(14)
        root.addWidget(self.prog)
        self.lbl_progress = QLabel("")
        root.addWidget(self.lbl_progress)

        # ---- 로그 · 로그 불러오기 ----
        logs = QHBoxLayout()
        logs.setSpacing(8)
        self.log = QTextEdit()
        self.log.setObjectName("kmLog")
        self.log.setReadOnly(True)
        self.log.setAcceptRichText(False)
        self.log.setLineWrapMode(QTextEdit.NoWrap)
        lf = QFont("Consolas")
        lf.setStyleHint(QFont.Monospace)
        lf.setPixelSize(12)
        self.log.setFont(lf)
        self.log.setMinimumHeight(100)
        logs.addWidget(self.log, 1)
        self.btn_loadlog = QPushButton("로그\n불러오기")
        self.btn_loadlog.setFixedWidth(98)
        self.btn_loadlog.setMinimumHeight(100)
        self.btn_loadlog.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.btn_loadlog.clicked.connect(self.load_log)                # BtnLoadLogClick
        logs.addWidget(self.btn_loadlog)
        root.addLayout(logs, 1)
        self._paint_where()

    def _css(self) -> str:
        """색은 지금 앱 팔레트에서 — 테마를 바꾸면 apply_theme 가 다시 부른다."""
        pal = QApplication.palette()
        win, base = pal.color(QPalette.Window), pal.color(QPalette.Base)
        text, btn = pal.color(QPalette.Text), pal.color(QPalette.Button)
        border = _mix(text, win, 0.22).name()
        track = _mix(text, win, 0.12).name()
        hover = _mix(text, btn, 0.08).name()
        sub = pal.color(QPalette.PlaceholderText).name()
        return f"""
            QScrollArea#kmScroll {{ background: transparent; border: none; }}
            QScrollArea#kmScroll > QWidget#qt_scrollarea_viewport {{ background: transparent; }}
            QWidget#kmBody {{ background: transparent; }}
            #kmBody QFrame#kmCard {{ border: 1px solid {border}; border-radius: 8px; background: {base.name()}; }}
            #kmBody QLabel#kmCardText {{ font-size: 16px; }}
            #kmBody QLabel#kmPreview {{ border: 1px solid {border}; border-radius: 6px; background: {base.name()}; }}
            #kmBody QLabel#kmWhere {{ color: {sub}; }}
            #kmBody QPlainTextEdit#kmMemo, #kmBody QTextEdit#kmLog {{
                border: 1px solid {border}; border-radius: 7px; background: {base.name()}; color: {text.name()};
                padding: 4px 6px; }}
            #kmBody QToolButton#kmTools {{ border: 1px solid {border}; border-radius: 6px; padding: 3px 12px;
                background: {btn.name()}; color: {text.name()}; }}
            #kmBody QToolButton#kmTools:hover {{ background: {hover}; }}
            #kmBody QToolButton#kmTools::menu-indicator {{ image: none; width: 0px; }}
            #kmBody QPushButton#kmStart, #kmBody QPushButton#kmStop {{
                color: {theme.fill_text()}; border: none; border-radius: 8px; font-size: 14px; font-weight: 700;
                padding: 0 8px; }}
            #kmBody QPushButton#kmStart {{ background: {theme.fill(START_TONE)}; }}
            #kmBody QPushButton#kmStart:hover {{ background: {theme.fill_hover(START_TONE)}; }}
            #kmBody QPushButton#kmStart:disabled {{ background: {track}; color: {sub}; }}
            #kmBody QPushButton#kmStop {{ background: {theme.fill(STOP_TONE)}; }}
            #kmBody QPushButton#kmStop:hover {{ background: {theme.fill_hover(STOP_TONE)}; }}
            #kmBody QProgressBar#kmProg {{ border: none; border-radius: 4px; background: {track}; }}
            #kmBody QProgressBar#kmProg::chunk {{ border-radius: 4px; background: {theme.strong("green")}; }}
        """

    def apply_theme(self) -> None:
        """앱 테마를 바꿨다 — 칸 · 카드 · 막대 색을 새 팔레트로."""
        self.setStyleSheet(self._css())
        for d in (self._dlg_phrases, self._dlg_env, self._dlg_hist, self._dlg_log):
            if d is not None:
                d.setPalette(QApplication.palette())

    # ------------------------------------------------------------ 엔진이 부르는 것(Ui)
    def start_block(self) -> str:
        """시작하면 안 되는 까닭(로그인 전) — 없으면 ""."""
        try:
            why = self.need_login() or ""
        except Exception:
            why = ""
        self._paint_where()
        return why

    def message_text(self) -> str:
        return self.memo.toPlainText()

    def image_path(self) -> str:
        return self._image_path

    def mode(self) -> int:
        return self.mode_group.checkedId()          # 안 골랐으면 -1

    def count_text(self) -> str:
        return self.ed_count.text()

    def set_running(self, on: bool) -> None:
        # button1.Enabled · RadioGroup1.Enabled := not on (메시지 · 이미지 · 인원수 칸은 A1Auto 처럼 그대로 둔다)
        self.btn_start.setEnabled(not on)
        self.grp_mode.setEnabled(not on)
        if not on:
            self._history_wanted = True        # 끝났다 — 방금 보낸 것을 계정에 올린다(1초 타이머가 쉬는 걸 보고)
        if self.tray is not None:
            try:
                if on:
                    self._tip_idle = self.tray.toolTip()
                elif self._tip_idle is not None:
                    self.tray.setToolTip(self._tip_idle)
                    self._tip_idle = None
            except Exception:
                pass

    def set_stats(self, success, stop, skip, speed) -> None:
        for lb, v in ((self.lbl_success, success), (self.lbl_stop, stop), (self.lbl_skip, skip),
                      (self.lbl_speed, speed)):
            if v is not None and lb.text() != v:
                lb.setText(v)

    def set_progress(self, pct: float, text: str) -> None:
        self.prog.setValue(int(round(max(0.0, min(1.0, pct)) * 1000)))
        if self.lbl_progress.text() != text:
            self.lbl_progress.setText(text)

    def _log_color(self, kind: str):
        if kind == "stop":                          # CLR_STOP — 빨강
            return QColor(theme.strong("red"))
        if kind == "skip":                          # CLR_SKIP — 호박색
            return QColor(theme.strong("orange"))
        return None                                      # CLR_OK — 바탕 글자색(테마를 바꾸면 따라간다)

    def add_log(self, text: str, kind: str) -> None:
        """AddLogLine — 끝에 색을 정해 한 줄 · 맨 아래로. 발송 기록에도 한 줄(계정에 올릴 것 — v1.38)."""
        self._append(text, self._log_color(kind))
        try:
            self.history.note(text)
        except Exception:
            pass

    def _append(self, text: str, color) -> None:
        cur = self.log.textCursor()
        cur.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        if color is not None:
            fmt.setForeground(color)
        if not self.log.document().isEmpty():
            cur.insertText("\n", fmt)
        cur.insertText(text, fmt)
        self.log.setTextCursor(cur)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def log_text(self) -> str:
        t = self.log.toPlainText()
        return (t + "\n") if t else ""

    def show_message(self, text: str) -> None:
        QMessageBox.information(self, TITLE, text)

    def tray_hint(self, text: str) -> None:
        # TrayIcon1.Hint — 앱 트레이를 함께 쓰므로 도는 동안만 진행을 보인다(끝나면 앱 이름으로)
        if self.tray is not None and self.engine.running:
            try:
                if self.tray.toolTip() != text:
                    self.tray.setToolTip(text)
            except Exception:
                pass

    def tray_balloon(self, title: str, text: str) -> None:
        if self.tray is not None and self.tray.isVisible():
            self.tray.showMessage(title, text, self.tray.icon(), 4000)

    # ------------------------------------------------------------ 단추 · 메뉴
    def _on_mode_clicked(self, idx: int) -> None:
        self.btn_image.setEnabled(idx != km.MODE_TEXT)           # image.Enabled := ItemIndex <> 0

    def pick_image(self) -> None:
        fn, _f = QFileDialog.getOpenFileName(self, "이미지 불러오기", str(Path(self._image_path).parent)
                                             if self._image_path else "")
        if fn:
            self.set_image(fn)

    def set_image(self, path: str) -> None:
        self._image_path = path
        pix = QPixmap(path)
        self.preview.set_pixmap(pix)            # 못 읽는 그림이면 미리보기만 비운다(경로는 그대로)
        self.preview.setToolTip(path)

    def load_log(self) -> None:
        """[로그 불러오기] — '===== 불러오기: 파일 =====' 아래에 이어 붙인다."""
        fn, _f = QFileDialog.getOpenFileName(self, "로그 불러오기", str(km.logs_dir()),
                                             "Log files (*.txt);;All files (*.*)")
        if not fn:
            return
        try:
            text = km.load_log_text(fn)
        except OSError as e:
            QMessageBox.warning(self, TITLE, f"로그를 읽지 못했습니다: {e}")
            return
        if not self.log.document().isEmpty():
            self._append("", None)
        self._append(f"===== 불러오기: {Path(fn).name} =====", None)
        for line in km._lines(text):
            self._append(line, None)

    def show_change_log(self) -> None:
        """N3Click — A1Auto 는 '도움말 내용 생략' 이었다. 이제 실제 수정로그(kakao_macro.CHANGE_LOG)."""
        if self._dlg_log is None:
            self._dlg_log = ChangeLogDialog(self)
        self._dlg_log.show()
        self._dlg_log.raise_()
        self._dlg_log.activateWindow()

    def open_history(self) -> None:
        """도구 → 발송 기록 — 고객 목록 · 발송 로그(내 구글 계정과 맞춘 것)."""
        if self._dlg_hist is None:
            self._dlg_hist = HistoryDialog(self)
        self._dlg_hist.reload()
        self._dlg_hist.show()
        self._dlg_hist.raise_()
        self._dlg_hist.activateWindow()
        self.sync_history()

    def open_phrases(self) -> None:
        if self._dlg_phrases is None:
            self._dlg_phrases = PhrasesDialog(self)
        self._dlg_phrases.show()
        self._dlg_phrases.raise_()
        self._dlg_phrases.activateWindow()
        self._dlg_phrases.refresh_list()                               # FormShow → RefreshList

    def open_env(self) -> None:
        if self._dlg_env is None:
            self._dlg_env = EnvDialog(self)
        self._dlg_env.load_values()                                    # N2Click — 지금 값을 칸에
        self._dlg_env.show()
        self._dlg_env.raise_()
        self._dlg_env.activateWindow()

    # ------------------------------------------------------------ 계정과 맞추기
    def sync(self) -> None:
        """발송 간격 · 자주 쓰는 문구 · 발송 기록을 내 구글 계정과 맞춘다(로그인 · 계정 확인 뒤 · [새로고침])."""
        self._paint_where()
        try:
            io, account = self.io_getter()
        except Exception:
            io, account = None, ""
        if io is None:
            return
        self.sync_worker.start(io, account)
        self.sync_history()

    def sync_history(self) -> None:
        """발송 기록 · 발송 로그를 맞춘다 — 로그인 전이면 이 PC 것만 정리(로그 파일 읽기 등). 도는 중이면 끝난 뒤."""
        if self.busy():
            self._history_wanted = True
            return
        self._history_wanted = False
        try:
            io, account = self.io_getter()
        except Exception:
            io, account = None, ""
        self.hist_worker.start(io, account)

    def _on_progress_tick(self) -> None:
        self.engine.timer2_timer()                 # Timer2Timer
        if self._history_wanted and not self.busy() and not self.hist_worker.busy():
            self.sync_history()

    def _paint_where(self) -> None:
        try:
            locked = bool(self.need_login())
        except Exception:
            locked = False
        if locked:
            self.lbl_where.setText("⚠ 구글 로그인을 해야 매크로를 시작할 수 있습니다")
            return
        try:
            io, _acct = self.io_getter()
        except Exception:
            io = None
        self.lbl_where.setText("설정 · 문구 · 발송 기록: 내 구글 계정에 저장" if io is not None
                               else "설정 · 문구 · 발송 기록: 이 PC 에 저장(로그인하면 구글 계정에)")

    def _on_prefs_changed(self) -> None:
        if self._dlg_phrases is not None and self._dlg_phrases.isVisible():
            self._dlg_phrases.refresh_list(sync=False)

    # ------------------------------------------------------------ 단축키 · 끄기
    def _on_hotkey(self) -> None:
        # 도는 중이면 어느 화면에 있든 본다 — 다른 메뉴로 옮겨 가도 Delete 로 멈출 수 있어야 한다(A1Auto 처럼)
        if self.armed() or self.busy():
            self.engine.hotkey_timer()
        else:
            # 안 볼 때도 '그사이 눌렸음' 표시를 비워 둔다 — 화면에 돌아오자마자 예전 Delete 가 잡히지 않게
            self.env.win.async_key(kw.VK_INSERT)
            self.env.win.async_key(kw.VK_DELETE)

    def busy(self) -> bool:
        """매크로가 도는 중(또는 멈추며 지금 사람 차례를 마치는 중)."""
        return bool(self.engine.running or self.engine._in_step)

    def shutdown(self) -> str:
        """앱을 끌 때(FormClose) — 클립보드 되돌리기 · 색인 저장 · 로그 파일. 도는 중이면 멈추고 남은 키를 막는다."""
        self.hotkey_timer.stop()
        self.progress_timer.stop()
        self.hist_timer.stop()
        if self.busy():
            self.env.closing = True                # 남은 기다림은 건너뛰고
            self.engine.win = kw.NullWin()          # 키는 더 보내지 않는다(카톡 창이 아니라고 보고 멈춘다)
            if self.engine.running:
                self.engine.fatal_stop("프로그램 종료")
        try:
            return self.engine.form_close(self.log_text())
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# 자주 쓰는 문구(TForm3) — 예전엔 서버, 이제 내 구글 계정
# ---------------------------------------------------------------------------
class PhrasesDialog(QDialog):
    def __init__(self, view: KakaoMacroView):
        super().__init__(view.window())
        self.view = view
        self.setWindowTitle("자주 쓰는 문구")
        self.resize(360, 380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        self.lbl_title = QLabel("자주 쓰는 문구")
        lay.addWidget(self.lbl_title)
        self.list = QListWidget()
        f = self.list.font()
        f.setPixelSize(13)
        self.list.setFont(f)
        self.list.itemDoubleClicked.connect(lambda _it: self.on_load())      # ListBox1DblClick
        lay.addWidget(self.list, 1)
        g = QGridLayout()
        g.setSpacing(6)
        self.btn_load = QPushButton("불러오기")
        self.btn_save = QPushButton("저장")
        self.btn_delete = QPushButton("삭제")
        self.btn_refresh = QPushButton("새로고침")
        self.btn_close = QPushButton("닫기")
        for b in (self.btn_load, self.btn_save, self.btn_delete, self.btn_refresh, self.btn_close):
            b.setFixedHeight(32)
        g.addWidget(self.btn_load, 0, 0, 1, 2)
        g.addWidget(self.btn_save, 0, 2, 1, 2)
        g.addWidget(self.btn_delete, 0, 4, 1, 2)
        g.addWidget(self.btn_refresh, 1, 0, 1, 3)
        g.addWidget(self.btn_close, 1, 3, 1, 3)
        lay.addLayout(g)
        self.btn_load.clicked.connect(self.on_load)
        self.btn_save.clicked.connect(self.on_save)
        self.btn_delete.clicked.connect(self.on_delete)
        self.btn_refresh.clicked.connect(lambda: self.refresh_list())
        self.btn_close.clicked.connect(self.close)

    def _msg(self, text: str) -> None:
        QMessageBox.information(self, TITLE, text)

    def _ask(self, text: str) -> bool:
        return QMessageBox.question(self, TITLE, text, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes

    def selected(self) -> str:
        it = self.list.currentItem()
        return it.text() if (it is not None and self.list.currentRow() >= 0) else ""

    def refresh_list(self, sync: bool = True) -> None:
        """RefreshList — 목록을 다시(이 PC 사본) · 계정과도 맞춘다(끝나면 저절로 다시 그린다)."""
        keep = self.selected()
        self.list.clear()
        for t in self.view.prefs.titles():
            self.list.addItem(t)
        if keep:
            hits = self.list.findItems(keep, Qt.MatchExactly)
            if hits:
                self.list.setCurrentItem(hits[0])
        if sync:
            self.view.sync()

    def on_load(self) -> None:
        title = self.selected()
        if not title:
            self._msg("불러올 문구를 목록에서 선택해주세요.")
            return
        self.view.memo.setPlainText(self.view.prefs.get(title))
        self._msg("불러왔습니다: " + title)
        self.close()

    def on_save(self) -> None:
        if self.view.memo.toPlainText().strip() == "":
            self._msg("저장할 메시지 내용이 비어 있습니다.")
            return
        title, okk = QInputDialog.getText(self, "문구 저장", "저장할 제목을 입력하세요:", QLineEdit.Normal,
                                          self.selected())
        if not okk:
            return
        title = km.clean_title(title)
        if title == "":
            self._msg("제목을 입력해주세요.")
            return
        if len(title) > km.TITLE_MAX:
            self._msg(f"저장 실패: 제목은 {km.TITLE_MAX}자까지입니다.")
            return
        if title in self.view.prefs.titles():
            if not self._ask("같은 제목의 문구가 이미 있습니다. 덮어쓸까요?"):
                return
        self.view.prefs.put(title, self.view.memo.toPlainText())
        self._msg("저장되었습니다: " + title)
        self.refresh_list()

    def on_delete(self) -> None:
        title = self.selected()
        if not title:
            self._msg("삭제할 문구를 목록에서 선택해주세요.")
            return
        if not self._ask(f'"{title}" 문구를 삭제할까요?'):
            return
        self.view.prefs.delete(title)
        self.refresh_list()


# ---------------------------------------------------------------------------
# 환경설정(TForm2) — 지연(ms) 셋 + 중복 발송 일수(jy.ini 를 손으로 고치던 것) + A1Auto 기록 가져오기
# ---------------------------------------------------------------------------
class EnvDialog(QDialog):
    def __init__(self, view: KakaoMacroView):
        super().__init__(view.window())
        self.view = view
        self.setWindowTitle("환경설정")
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 14, 12, 12)
        lay.setSpacing(4)

        def row(text, sub, width=60):
            h = QHBoxLayout()
            lb = QLabel(text)
            ed = QLineEdit()
            ed.setFixedWidth(width)
            ed.setAlignment(Qt.AlignCenter)
            h.addWidget(lb)
            h.addStretch(1)
            h.addWidget(ed)
            lay.addLayout(h)
            sl = QLabel(sub)
            f = sl.font()
            f.setPixelSize(11)
            sl.setFont(f)
            sl.setObjectName("kmSub")
            sl.setContentsMargins(4, 0, 0, 10)
            lay.addWidget(sl)
            return ed

        self.ed1 = row("텍스트 입력 전 지연시간(ms) :", "└ 채팅창이 열리고 텍스트가 입력되기 전 지연시간")
        self.ed2 = row("다음 채팅창을 열기 전 지연시간(ms) : ", "└ 이번 채팅창이 닫히고 다음 채팅창이 열리기 전 지연시간")
        self.ed3 = row("이미지 전송 후 지연시간(ms) :", "└ 이미지 전송 후 다음 작업을 수행하기 전 지연시간")
        self.ed4 = row("중복 발송 막기(일) :", "└ 이 일수 안에 보낸 사람은 건너뜀 (0 = 검사 안 함)")
        self.btn_import = QPushButton("A1Auto 기록 가져오기")
        self.btn_import.setToolTip("예전 A1Auto 폴더의 발송 기록(data\\customers.tsv)과 로그(logs)를 옮겨 옵니다")
        self.btn_import.clicked.connect(self.on_import)
        lay.addWidget(self.btn_import)
        lay.addSpacing(8)
        bot = QHBoxLayout()
        self.btn_default = QPushButton("기본값")
        self.btn_default.setFixedSize(60, 32)
        self.btn_apply = QPushButton("닫기(적용)")
        self.btn_apply.setFixedHeight(32)
        bot.addWidget(self.btn_default)
        bot.addWidget(self.btn_apply, 1)
        lay.addLayout(bot)
        self.btn_default.clicked.connect(self.on_default)
        self.btn_apply.clicked.connect(self.on_apply)

    def load_values(self) -> None:
        p = self.view.prefs
        self.ed1.setText(str(p.interval1))
        self.ed2.setText(str(p.interval2))
        self.ed3.setText(str(p.interval3))
        self.ed4.setText(str(p.dupdays))

    def on_default(self) -> None:
        d = km.DEFAULT_BUTTON
        self.ed1.setText(str(d["textsleep"]))
        self.ed2.setText(str(d["nextsleep"]))
        self.ed3.setText(str(d["imagesleep"]))

    def on_apply(self) -> None:
        """[닫기(적용)] — 잘못 적은 칸은 700 · 700 · 1200(· 1) 로, 칸도 실제 값으로 고쳐 보이고 저장."""
        d = km.DEFAULTS
        v1 = km.str_to_int_def(self.ed1.text(), d["textsleep"])
        v2 = km.str_to_int_def(self.ed2.text(), d["nextsleep"])
        v3 = km.str_to_int_def(self.ed3.text(), d["imagesleep"])
        v4 = km.str_to_int_def(self.ed4.text(), d["dupdays"])
        for ed, v in ((self.ed1, v1), (self.ed2, v2), (self.ed3, v3), (self.ed4, v4)):
            ed.setText(str(v))
        self.view.prefs.set_intervals(v1, v2, v3, dupdays=v4)
        self.view.sync()
        self.close()

    def on_import(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "A1Auto.exe 가 있던 폴더를 고르세요")
        if not d:
            return
        n_cu, n_log = km.import_a1auto(self.view.store, d)
        if n_cu < 0:
            QMessageBox.information(self, TITLE, "그 폴더에는 A1Auto 기록(data · logs 폴더)이 없습니다.")
            return
        QMessageBox.information(self, TITLE, f"가져왔습니다 — 고객 {n_cu}명 · 로그 {n_log}개")


# ---------------------------------------------------------------------------
# 수정로그(N3) — kakao_macro.CHANGE_LOG
# ---------------------------------------------------------------------------
def change_log_html() -> str:
    out = []
    for day, ver, lines in km.CHANGE_LOG:
        out.append(f"<p style='margin:10px 0 2px 0'><b>{html.escape(day)}</b> &nbsp; {html.escape(ver)}</p>")
        out.append("<ul style='margin-top:0'>" + "".join(f"<li>{html.escape(t)}</li>" for t in lines) + "</ul>")
    return "".join(out)


class ChangeLogDialog(QDialog):
    def __init__(self, view: KakaoMacroView):
        super().__init__(view.window())
        self.setWindowTitle("수정로그")
        self.resize(600, 480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.setHtml(change_log_html())
        lay.addWidget(self.text, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_close = QPushButton("닫기")
        self.btn_close.setFixedHeight(32)
        self.btn_close.clicked.connect(self.close)
        row.addWidget(self.btn_close)
        lay.addLayout(row)


# ---------------------------------------------------------------------------
# 발송 기록(v1.38) — 발송 로그 · 고객 목록
# ---------------------------------------------------------------------------
def _sort_key(v):
    if isinstance(v, int):
        return (0, v, "")
    return (1, 0, str(v or "").lower())


class _Rows(QAbstractTableModel):
    """줄 목록 표 — 머리 글 수만큼 보이고, 뒤에 붙인 값은 색 · 풍선 도움말에 쓴다. 머리를 누르면 그 칸으로 정렬."""

    def __init__(self, heads, parent=None, align=None, color_of=None, tip_of=None):
        super().__init__(parent)
        self.heads = tuple(heads)
        self.rows = []
        self.align = align or {}
        self.color_of = color_of
        self.tip_of = tip_of
        self._sort = (-1, Qt.AscendingOrder)

    def set_rows(self, rows) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self._apply_sort()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.heads)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < len(self.heads):
            return self.heads[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        r, c = self.rows[index.row()], index.column()
        if role == Qt.DisplayRole:
            v = r[c]
            return "" if v is None else str(v)
        if role == Qt.TextAlignmentRole and c in self.align:
            return int(self.align[c])
        if role == Qt.ForegroundRole and self.color_of is not None:
            return self.color_of(r, c)
        if role == Qt.ToolTipRole and self.tip_of is not None:
            return self.tip_of(r, c)
        return None

    def sort(self, column, order=Qt.AscendingOrder):
        self.beginResetModel()
        self._sort = (column, order)
        self._apply_sort()
        self.endResetModel()

    def _apply_sort(self):
        col, order = self._sort
        if 0 <= col < len(self.heads):
            self.rows.sort(key=lambda r: _sort_key(r[col]), reverse=(order == Qt.DescendingOrder))


def _safe_cell(v) -> str:
    """엑셀이 수식으로 읽지 않게 — 카톡 방 이름이 '=' · '+' 등으로 시작해도 글자로."""
    t = "" if v is None else str(v)
    return ("'" + t) if t[:1] in ("=", "+", "-", "@", "\t", "\r") else t


class HistoryDialog(QDialog):
    PERIODS = (("오늘", 0), ("최근 7일", 7), ("최근 30일", 30), ("최근 1년", 365), ("전체", -1))
    RESULTS = (("전체", ""), ("발송", "ok"), ("건너뜀", "skip"), ("중단", "stop"))

    def __init__(self, view: KakaoMacroView):
        super().__init__(view.window())
        self.view = view
        self.doc = kh.empty()
        self.setWindowTitle("발송 기록")
        self.resize(820, 580)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        self.tabs = QTabWidget()

        # ---- 발송 로그 ----
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        top.addWidget(QLabel("기간"))
        self.cb_period = QComboBox()
        for t, _d in self.PERIODS:
            self.cb_period.addItem(t)
        self.cb_period.setCurrentIndex(2)
        top.addWidget(self.cb_period)
        top.addSpacing(8)
        top.addWidget(QLabel("결과"))
        self.cb_kind = QComboBox()
        for t, _k in self.RESULTS:
            self.cb_kind.addItem(t)
        top.addWidget(self.cb_kind)
        top.addSpacing(8)
        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText("이름 · 내용 찾기")
        self.ed_find.setClearButtonEnabled(True)
        top.addWidget(self.ed_find, 1)
        self.lbl_log = QLabel("")
        top.addWidget(self.lbl_log)
        l1.addLayout(top)
        self.m_log = _Rows(("시각", "결과", "이름", "내용", "PC"), self, align={1: Qt.AlignCenter},
                           color_of=self._log_color)
        self.t_log = self._table(self.m_log, 0)
        l1.addWidget(self.t_log, 1)
        self.tabs.addTab(w1, "발송 로그")

        # ---- 고객 목록 ----
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.setContentsMargins(8, 8, 8, 8)
        top2 = QHBoxLayout()
        self.ed_find2 = QLineEdit()
        self.ed_find2.setPlaceholderText("이름 · 메모 찾기")
        self.ed_find2.setClearButtonEnabled(True)
        top2.addWidget(self.ed_find2, 1)
        self.chk_sent = QCheckBox("보낸 적 있는 사람만")
        self.chk_sent.setChecked(True)
        top2.addWidget(self.chk_sent)
        self.lbl_cu = QLabel("")
        top2.addWidget(self.lbl_cu)
        l2.addLayout(top2)
        self.m_cu = _Rows(("이름", "마지막 발송", "발송 횟수", "처음 본 날", "수신거부", "메모"), self,
                          align={2: Qt.AlignCenter, 4: Qt.AlignCenter}, tip_of=self._cu_tip)
        self.t_cu = self._table(self.m_cu, 1)
        self.t_cu.setToolTip("두 번 누르면 그 사람의 발송 로그")
        self.t_cu.doubleClicked.connect(self._show_person)
        l2.addWidget(self.t_cu, 1)
        self.tabs.addTab(w2, "고객 목록")
        lay.addWidget(self.tabs, 1)

        # ---- 아래 ----
        bot = QHBoxLayout()
        self.lbl_state = QLabel("")
        self.lbl_state.setObjectName("kmSub")
        self.lbl_state.setWordWrap(True)
        bot.addWidget(self.lbl_state, 1)
        self.btn_reload = QPushButton("새로고침")
        self.btn_export = QPushButton("엑셀로 저장")
        self.btn_close = QPushButton("닫기")
        for b in (self.btn_reload, self.btn_export, self.btn_close):
            b.setFixedHeight(32)
            bot.addWidget(b)
        lay.addLayout(bot)

        self._find_timer = QTimer(self)
        self._find_timer.setSingleShot(True)
        self._find_timer.setInterval(200)
        self._find_timer.timeout.connect(self._fill)
        self.cb_period.currentIndexChanged.connect(lambda _i: self._fill_log())
        self.cb_kind.currentIndexChanged.connect(lambda _i: self._fill_log())
        self.chk_sent.toggled.connect(lambda _b: self._fill_cu())
        self.ed_find.textChanged.connect(lambda _t: self._find_timer.start())
        self.ed_find2.textChanged.connect(lambda _t: self._find_timer.start())
        self.btn_reload.clicked.connect(self.on_reload)
        self.btn_export.clicked.connect(self.export)
        self.btn_close.clicked.connect(self.close)
        view.history_synced.connect(self._on_synced)

    def _table(self, model, sort_col: int) -> QTableView:
        t = QTableView()
        t.setModel(model)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.setWordWrap(False)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(24)
        h = t.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        t.setSortingEnabled(True)
        t.sortByColumn(sort_col, Qt.DescendingOrder)
        for c, wdt in enumerate((150, 120, 150, 150, 100, 120)[:model.columnCount()]):
            t.setColumnWidth(c, wdt)
        return t

    @staticmethod
    def _log_color(r, c):
        if c != 1:
            return None
        if r[5] == "stop":
            return QColor(theme.strong("red"))
        if r[5] == "skip":
            return QColor(theme.strong("orange"))
        return None

    def _cu_tip(self, r, c):
        if c != 2 or not r[6]:
            return None
        return " · ".join(f"{self.view.history.pc_name(self.doc, d)} {n}번" for d, n in r[6].items())

    # ---- 채우기 ----
    def reload(self) -> None:
        try:
            self.doc = self.view.history.snapshot()
        except Exception:
            self.doc = kh.empty()
        self._fill()
        self._paint_state()

    def _fill(self) -> None:
        self._fill_log()
        self._fill_cu()

    def _cutoff(self) -> str:
        days = self.PERIODS[self.cb_period.currentIndex()][1]
        if days < 0:
            return ""
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) if days == 0 else now - timedelta(days=days)
        return km.stamp(start)

    def _fill_log(self) -> None:
        cut = self._cutoff()
        kind = self.RESULTS[self.cb_kind.currentIndex()][1]
        q = self.ed_find.text().strip().lower()
        rows = []
        for e in self.doc["events"]:                 # 새것이 앞 — 기간 밖이면 거기서 끝
            if cut and e[1] < cut:
                break
            if kind and e[2] != kind:
                continue
            if q and q not in (e[3] + " " + e[4]).lower():
                continue
            rows.append((e[1], kh.KIND_TEXT.get(e[2], e[2]), e[3], e[4], self.view.history.pc_name(self.doc, e[5]),
                         e[2]))
        self.m_log.set_rows(rows)
        n_ok = sum(1 for r in rows if r[5] == "ok")
        self.lbl_log.setText(f"{len(rows)}줄 · 발송 {n_ok}건")

    def _fill_cu(self) -> None:
        q = self.ed_find2.text().strip().lower()
        only_sent = self.chk_sent.isChecked()
        rows = []
        for nm, r in self.doc["customers"].items():
            total = sum(r[2].values())
            if only_sent and total == 0 and not r[1]:
                continue
            if q and q not in (nm + " " + r[4]).lower():
                continue
            rows.append((nm, r[1], total, r[0], "예" if r[3] else "", r[4], r[2]))
        self.m_cu.set_rows(rows)
        self.lbl_cu.setText(f"{len(rows)}명")

    def _paint_state(self) -> None:
        st, arg = self.view.hist_worker.state
        try:
            io, _acct = self.view.io_getter()
        except Exception:
            io = None
        if st == "run":
            t = "내 구글 계정과 맞추는 중…"
        elif st == "err":
            t = f"구글 계정과 맞추지 못했습니다 — 이 PC 기록만 보입니다({arg})"
        elif io is None:
            t = "이 PC 기록만 — 구글 로그인하면 계정에 올려 다른 PC 에서도 봅니다"
        elif st == "ok":
            t = f"내 구글 계정과 맞췄습니다 · {arg}"
        else:
            t = "내 구글 계정에 저장"
        self.lbl_state.setText(t)

    def _on_synced(self) -> None:
        if self.isVisible() and self.view.hist_worker.state[0] != "run":
            self.reload()
        else:
            self._paint_state()

    def on_reload(self) -> None:
        self.reload()
        self.view.sync_history()

    def _show_person(self, index) -> None:
        if not index.isValid():
            return
        name = self.m_cu.rows[index.row()][0]
        self.tabs.setCurrentIndex(0)
        self.cb_period.setCurrentIndex(len(self.PERIODS) - 1)
        self.cb_kind.setCurrentIndex(0)
        self.ed_find.setText(name)
        self._find_timer.stop()
        self._fill_log()

    def export(self) -> None:
        """[엑셀로 저장] — 지금 탭에 보이는 줄 그대로(CSV · UTF-8 BOM — 엑셀에서 바로 열림)."""
        on_log = self.tabs.currentIndex() == 0
        m = self.m_log if on_log else self.m_cu
        name = f"{'카톡발송로그' if on_log else '카톡고객목록'}_{datetime.now():%y%m%d}.csv"
        down = Path.home() / "Downloads"
        start = str((down if down.is_dir() else Path.home()) / name)
        path, _f = QFileDialog.getSaveFileName(self, "엑셀로 저장", start, "CSV (*.csv)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".csv"                             # 확장자를 지웠으면 붙인다(엑셀로 바로 열리게)
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(m.heads)
                for r in m.rows:
                    w.writerow([_safe_cell(v) for v in r[:len(m.heads)]])
        except OSError as e:
            QMessageBox.warning(self, TITLE, f"저장하지 못했습니다: {e}")
            return
        QMessageBox.information(self, TITLE, f"저장했습니다 — {len(m.rows)}줄\n{path}")


# ---------------------------------------------------------------------------
# 따로 띄우는 창(업무자료검색)
# ---------------------------------------------------------------------------
class KakaoMacroWindow(QWidget):
    """업무자료검색의 [카톡 매크로] — A1Auto 창처럼 따로 뜬다. 닫으면 A1Auto 를 끈 것과 같다(멈춤 · 로그 저장)."""

    def __init__(self, tray=None, io_getter=None, icon=None, parent=None, need_login=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle(TITLE)
        if icon is not None:
            self.setWindowIcon(icon)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        self.view = KakaoMacroView(self, tray=tray, io_getter=io_getter, armed=self._armed, need_login=need_login)
        lay.addWidget(self.view)
        self.resize(QSize(720, 720))

    def _armed(self) -> bool:
        return self.isVisible() or self.isMinimized()

    def closeEvent(self, ev):
        if self.view.busy():
            if QMessageBox.question(self, TITLE, "매크로가 도는 중입니다. 멈추고 닫을까요?",
                                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                ev.ignore()
                return
            self.view.engine.fatal_stop("사용자 중단")
        self.view.engine.form_close(self.view.log_text())   # FormClose — 클립보드 · 색인 · 로그 파일
        self.view.log.clear()                              # 같은 로그를 다음에 닫을 때 또 쓰지 않게
        super().closeEvent(ev)
