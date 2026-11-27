"""치는 대로 찾는 검색칸 — 한글 **마지막 글자까지** 바로 찾는다.

한글 입력기는 마지막 글자를 다 치기 전까지 '조합 중'(preedit)으로 들고 있다.
Qt 의 `textChanged` 는 조합 중인 글자를 **빼고** 알려 준다. 그래서 "전자약정" 을
치면 "전자약" 으로 찾고, 스페이스나 방향키를 한 번 더 눌러 조합이 끝나야 "정" 이
들어갔다 — "다 쳤는데 키를 한 번 더 눌러야 검색이 끝난다" 는 그 증상이다.

`LiveLineEdit` 은 조합 중인 글자까지 넣은 글(`live_text()`)을 `liveText` 신호로 준다.
검색은 이 신호에 건다. 끝 글자가 아직 "저" 처럼 덜 된 상태여도 걸리게 하는 일은
hangul._tail_ranges 가 맡는다("저" → 정).
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QLineEdit


class LiveLineEdit(QLineEdit):
    """조합 중인 한글까지 넣어 알려 주는 입력칸."""

    liveText = Signal(str)       # 화면에 보이는 그대로의 글(조합 중 글자 포함)
    composing = Signal(str)      # 조합 중에 글이 바뀔 때만 (검색 드롭다운이 쓴다)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._preedit = ""
        self._last = None
        self._in_ime = False
        # 입력기 이벤트 안에서는 알리지 않고 이 타이머로 미룬다(바로 다음 차례에 한 번).
        # 내 자식 타이머라 칸이 없어지면 같이 없어진다 — 없어진 칸을 부르지 않는다.
        self._later = QTimer(self)
        self._later.setSingleShot(True)
        self._later.setInterval(0)
        self._later.timeout.connect(self._flush)
        self.textChanged.connect(self._on_text)

    def live_text(self) -> str:
        """지금 칸에 보이는 글 — 조합 중인 글자를 커서 자리에 끼워 넣은 것."""
        t = self.text()
        if not self._preedit:
            return t
        c = self.cursorPosition()
        return t[:c] + self._preedit + t[c:]

    def is_composing(self) -> bool:
        return bool(self._preedit)

    # ---- Qt ----
    def inputMethodEvent(self, ev):
        # ⚠️ 조합을 끝내며(commit) 새 조합을 시작하는 한 번의 이벤트 안에서
        #    textChanged 가 먼저 나온다. 그때는 아직 옛 조합 글자를 들고 있어
        #    "전자약정정" 처럼 두 번 들어간 글을 알리게 된다. 끝난 뒤에 한 번만 알린다.
        self._in_ime = True
        try:
            super().inputMethodEvent(ev)
        finally:
            self._in_ime = False
        self._preedit = ev.preeditString() or ""
        # ⚠️ 여기서 바로 알리지 않는다. 알림을 받은 쪽이 목록을 다시 그리고 그림을
        #    푸는 무거운 일을 하는데, 그걸 **입력기 처리 도중에** 하면 윈도에서 입력이
        #    밀리고 화면이 멈췄다. 이벤트가 끝난 바로 다음에 한 번만 알린다.
        self._later.start()

    def setText(self, text):        # noqa: N802 — Qt 이름 그대로
        self._preedit = ""          # 코드가 바꾼 글에는 조합 중 글자가 없다
        self._last = None           # 신호를 막고 바꿔도 다음 글자에서 다시 찾게
        super().setText(text)

    def clear(self):
        self._preedit = ""
        self._last = None
        super().clear()

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        if self._preedit:           # 입력기가 조합을 버리고 나가는 경우
            self._preedit = ""
            self._emit()

    # ---- 안 ----
    def _on_text(self, _t):
        if not self._in_ime:
            self._emit()

    def _flush(self):
        if self._emit() and self._preedit:
            self.composing.emit(self.live_text())

    def _emit(self) -> bool:
        s = self.live_text()
        if s == self._last:
            return False
        self._last = s
        self.liveText.emit(s)
        return True
