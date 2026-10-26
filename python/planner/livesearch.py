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

from PySide6.QtCore import Signal
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
        if self._emit() and self._preedit:
            self.composing.emit(self.live_text())

    def setText(self, text):        # noqa: N802 — Qt 이름 그대로
        self._preedit = ""          # 코드가 바꾼 글에는 조합 중 글자가 없다
        super().setText(text)

    def clear(self):
        self._preedit = ""
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

    def _emit(self) -> bool:
        s = self.live_text()
        if s == self._last:
            return False
        self._last = s
        self.liveText.emit(s)
        return True
