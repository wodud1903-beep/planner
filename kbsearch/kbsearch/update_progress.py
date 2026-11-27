"""업데이트 진행 창 — 받는 정도(막대·%·MB)와 단계를 보여 준다(kb-v1.5.0, 지점장 요청).

일정관리기(python/planner/update_progress.py, v1.27)와 같은 창이다. 다른 점: 변경 이력 창이 없어
'완료' 에는 이번에 달라진 것(릴리스 안내 몇 줄)을 그대로 보여 준다.

지점장: "업데이트 할 때에는 프로그레스바를 만들어서 업데이트 하고 있다는 내용을 시각적으로
보이게 해줘". 예전(kb-v1.4)엔 켤 때만 작은 창이 뜨고, PC 시작(트레이)·켜 둔 동안 바꿀 때는
아무것도 안 보여 꺼진 줄 알기 쉬웠다. 이제 어느 때나 보인다.

  ① 받는 중   — 막대 0→100% · '19.6 / 53.4 MB'
  ② 바꾸는 중 — 막대 가득 · '잠시 뒤(10초쯤) 새 버전이 저절로 켜집니다' → 이 창이 닫히고 다시 켜진다
  ③ 완료      — 새 판이 켜지면 'v1.5.0 으로 바뀌었습니다' 와 달라진 것 몇 줄을 보여 주고 닫힌다
  · 실패      — 까닭을 몇 초 보여 주고 닫힌다(몇 시간 뒤 저절로 다시 해 본다)

켜 둔 동안은 화면 오른쪽 아래, 켤 때(창이 뜨기 전)는 화면 가운데. **포커스를 빼앗지 않는다**.
단추가 없다(묻지 않는 업데이트 — v1.26).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget

from . import config, theme

WIDTH = 380
MARGIN = 18
DONE_SHOW_MS = 7000          # 완료를 보여 주는 시간
FAIL_SHOW_MS = 8000          # 실패 까닭을 보여 주는 시간


def mb(n) -> str:
    return f"{(n or 0) / (1 << 20):.1f}"


def notes_lines(notes: str, n: int = 3, width: int = 60) -> str:
    """릴리스 안내(변경 이력 절)의 앞 몇 줄 — '· …' 줄만, 길면 자른다."""
    out = []
    for ln in str(notes or "").splitlines():
        t = ln.strip()
        if not t.startswith("·"):
            continue
        out.append(t if len(t) <= width else t[:width - 1] + "…")
        if len(out) >= n:
            break
    return "\n".join(out)


class UpdateProgress(QWidget):
    """업데이트 진행 창(단추 없음 · 오른쪽 아래 · 포커스를 빼앗지 않음)."""

    clicked = Signal()

    def __init__(self, version: str = "", parent=None, corner: bool = True):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.corner = corner
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle(f"{config.APP_NAME} 업데이트")
        self.version = str(version or "").lstrip("v")
        self.state = "download"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.card = QFrame()
        self.card.setObjectName("updCard")
        outer.addWidget(self.card)
        v = QVBoxLayout(self.card)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(7)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("updTitle")
        v.addWidget(self.lbl_title)
        self.lbl_msg = QLabel()
        self.lbl_msg.setObjectName("updMsg")
        self.lbl_msg.setWordWrap(True)
        v.addWidget(self.lbl_msg)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        # 막대 안 글자는 쓰지 않는다 — 가득 차면 보라 바탕에 검은 글씨라 안 읽혔다. % 는 위 문장에.
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        v.addWidget(self.bar)
        self.lbl_sub = QLabel()
        self.lbl_sub.setObjectName("updSub")
        self.lbl_sub.setWordWrap(True)
        v.addWidget(self.lbl_sub)
        self.setFixedWidth(WIDTH)
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self.close)
        self.apply_theme()
        self.downloading()

    # ------------------------------------------------------------ 모양
    def apply_theme(self) -> None:
        bad = theme.c("status_bad")
        self.card.setStyleSheet(
            f"#updCard {{ background:{theme.c('panel_bg')}; border:1px solid {theme.c('border')};"
            " border-radius:14px; }"
            f"#updCard QLabel {{ background:transparent; color:{theme.c('text')}; }}"
            "#updTitle { font-weight:bold; }"
            f"#updSub {{ color:{theme.c('subtext')}; }}"
            f"#updMsg[bad=\"true\"] {{ color:{bad}; }}"
            f"QProgressBar {{ border:none; border-radius:5px; background:{theme.c('grid')}; }}"
            f"QProgressBar::chunk {{ background:{theme.c('accent')}; border-radius:5px; }}")

    def _set_bad(self, bad: bool) -> None:
        self.lbl_msg.setProperty("bad", "true" if bad else "false")
        self.lbl_msg.style().unpolish(self.lbl_msg)
        self.lbl_msg.style().polish(self.lbl_msg)

    def place(self) -> None:
        """켜 둔 동안은 화면 오른쪽 아래(작업 표시줄 위), 켤 때는 가운데(self.corner)."""
        # 글이 짧아지면(완료·실패) 높이를 다시 잰다 — 안 그러면 앞 단계 높이로 남아 줄 사이가 벌어졌다
        for lay in (self.card.layout(), self.layout()):
            lay.invalidate()
            lay.activate()
        self.setFixedHeight(self.layout().totalHeightForWidth(WIDTH)
                            if self.layout().hasHeightForWidth() else self.sizeHint().height())
        scr = QGuiApplication.primaryScreen()
        if scr is None:
            return
        g = scr.availableGeometry()
        if self.corner:
            self.move(g.right() - self.width() - MARGIN + 1, g.bottom() - self.height() - MARGIN + 1)
        else:
            self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)

    def pop(self) -> None:
        self.place()
        self.show()
        self.raise_()

    # ------------------------------------------------------------ 단계
    def _ver(self) -> str:
        return f" v{self.version}" if self.version else ""

    def downloading(self) -> None:
        self.state = "download"
        self._close_timer.stop()
        self._set_bad(False)
        self.lbl_title.setText(f"{config.APP_NAME} 업데이트 — 새 버전{self._ver()}")
        self.lbl_msg.setText("새 버전을 받는 중입니다…")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.lbl_sub.setText("다 받으면 저절로 바꾸고 다시 켜집니다. 그동안 그대로 쓰셔도 됩니다.")

    def progress(self, got, total) -> None:
        """받은 바이트 / 전체 바이트(모르면 0 — 그때는 움직이는 막대)."""
        if self.state != "download":
            return
        got, total = int(got or 0), int(total or 0)
        if total > 0:
            if self.bar.maximum() == 0:
                self.bar.setRange(0, 100)
            pct = max(0, min(100, int(got * 100 / total)))
            self.bar.setValue(pct)
            self.lbl_msg.setText(f"새 버전을 받는 중입니다…  {pct}%  ({mb(got)} / {mb(total)} MB)")
        else:
            self.bar.setRange(0, 0)               # 크기를 모르면 오가는 막대
            self.lbl_msg.setText(f"새 버전을 받는 중입니다…  {mb(got)} MB")

    def applying(self) -> None:
        """다 받았다 — 바꾸는 중(곧 이 프로그램이 닫히고 새 판이 켜진다)."""
        self.state = "apply"
        self._close_timer.stop()
        self._set_bad(False)
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.lbl_title.setText(f"{config.APP_NAME} 업데이트 — 새 버전{self._ver()}")
        self.lbl_msg.setText("다 받았습니다. 새 버전으로 바꾸는 중입니다…")
        self.lbl_sub.setText("잠시 뒤(10초쯤) 새 버전이 저절로 켜집니다. 그동안 프로그램을 다시 켜지 마세요.")
        self.pop()

    def failed(self, why: str) -> None:
        """받지 못했다 — 까닭을 잠깐 보여 주고 닫는다."""
        self.state = "fail"
        self._set_bad(True)
        self.bar.setRange(0, 100)
        first = (why or "").strip().splitlines()[0][:90] if (why or "").strip() else "알 수 없는 오류"
        self.lbl_msg.setText(f"새 버전을 받지 못했습니다 — {first}")
        self.lbl_sub.setText("지금 판으로 계속 쓰시면 됩니다. 몇 시간 뒤 저절로 다시 해 봅니다.")
        self.pop()
        self._close_timer.start(FAIL_SHOW_MS)

    def done(self, version: str = "", notes: str = "") -> None:
        """(새 판에서) 업데이트를 마쳤다 — 달라진 것 몇 줄과 함께 잠깐 보여 주고 닫는다."""
        if version:
            self.version = str(version).lstrip("v")
        self.state = "done"
        self._set_bad(False)
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.lbl_title.setText(f"{config.APP_NAME} 업데이트 완료")
        self.lbl_msg.setText(f"새 버전{self._ver()} 으로 바뀌었습니다.")
        self.lbl_sub.setText(notes_lines(notes) or "이제 새 버전으로 쓰시면 됩니다.")
        self.pop()
        self._close_timer.start(DONE_SHOW_MS)

    def mousePressEvent(self, ev):          # noqa: N802 (Qt)
        self.clicked.emit()
        if self.state in ("done", "fail"):
            self.close()
        super().mousePressEvent(ev)
