"""검색형 드롭다운 — 초성·낱말 몇 글자만 쳐도 골라지는 QComboBox.

기본 QComboBox 는 목록을 편 뒤 방향키로 찾아야 하고, 글자를 쳐도 '첫 글자'
로만 건너뛴다. 차종처럼 40개가 넘는 목록에서는 이게 매우 느리다.

여기서 하는 일:
  · 흰칸을 클릭하든 오른쪽 화살표를 누르든 **목록이 바로 열린다**
  · 치는 대로 목록이 걸러진다 — "ㅅㄴㅌ"(초성), "디엣지"(낱말 일부) 모두 됨
  · ↑↓ 로 옮기고 Enter 로 선택 (마우스 없이 끝난다)
  · 목록에 없는 값은 되돌린다(allow_free=True 면 그대로 둔다 — 금융사처럼
    시트에 없던 값을 새로 적을 수 있어야 하는 칸)

목록은 콤보 자신의 모델을 그대로 본다. 그래서 addItem/clear 로 항목이 바뀌면
따로 갱신할 필요가 없다.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QStringListModel, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QCompleter, QLineEdit

from . import hangul

POPUP_NAME = "searchpopup"     # 테마 스타일시트가 이 이름으로 팝업을 칠한다


class _Completer(QCompleter):
    """직접 거른 목록을 그대로 보여주는 완성기.

    QCompleter 의 기본 필터(앞글자 일치)는 초성 검색을 못 한다. 그래서 Unfiltered
    모드로 두고, 글자가 바뀔 때마다(splitPath) 우리가 고른 항목만 담은 모델을
    다시 세운 뒤 빈 경로를 돌려준다 — 완성기는 '전부 일치' 로 보고 그대로 띄운다.

    목록은 그때그때 콤보에서 읽는다(캐시하지 않는다). 콤보 모델의 변경 신호를
    엿듣다가 프록시가 어긋나는 문제를 아예 만들지 않으려는 것이다.
    """

    def __init__(self, source, parent=None):
        self._model = QStringListModel([])
        super().__init__(self._model, parent)
        self._source = source          # () -> list[str]
        self.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.setCaseSensitivity(Qt.CaseInsensitive)
        self.setMaxVisibleItems(14)
        self.popup().setObjectName(POPUP_NAME)

    def splitPath(self, path):
        self._model.setStringList(hangul.filter_items(self._source(), path or ""))
        return [""]


class ComboSearch(QObject):
    """콤보 하나에 붙는 검색 동작. `install()` 로 만든다."""

    def __init__(self, combo: QComboBox, allow_free: bool = False):
        super().__init__(combo)
        self.combo = combo
        self.allow_free = allow_free

        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)

        self._comp = _Completer(self._texts, self)
        self._comp.activated[str].connect(self._pick)
        combo.setCompleter(self._comp)

        le = combo.lineEdit()
        le.installEventFilter(self)
        combo.installEventFilter(self)
        le.editingFinished.connect(self._resolve)

        self._last = combo.currentText()
        combo.currentIndexChanged.connect(self._remember)

    # ------------------------------------------------------------ 내부
    def _texts(self) -> list:
        return [self.combo.itemText(i) for i in range(self.combo.count())]

    def _remember(self, _i: int) -> None:
        self._last = self.combo.currentText()

    def _popup_open(self) -> bool:
        p = self._comp.popup()
        return bool(p and p.isVisible())

    def show_all(self) -> None:
        """지금 친 글자와 상관없이 전체 목록을 편다 (칸을 클릭했을 때)."""
        if not self.combo.isEnabled() or self.combo.count() == 0:
            return
        self._comp.setCompletionPrefix("")
        self._comp.complete()

    def show_filtered(self) -> None:
        self._comp.setCompletionPrefix(self.combo.lineEdit().text())
        self._comp.complete()

    def _pick(self, text: str) -> None:
        i = self.combo.findText(text, Qt.MatchFixedString)
        if i >= 0:
            self.combo.setCurrentIndex(i)
            # 기본 목록을 가로챘으므로 activated 가 저절로 나오지 않는다.
            # 이 신호를 듣고 동작하는 칸(계약조건 템플릿)이 있어서 직접 낸다.
            try:
                self.combo.activated.emit(i)
            except Exception:
                pass
        self._last = self.combo.currentText()

    def _resolve(self) -> None:
        """칸에서 빠져나갈 때 값을 확정한다.

        완전일치가 있으면 그 항목으로, 후보가 딱 하나면 그것으로 자동 완성한다.
        (이게 '한두 글자만 치고 Tab' 이 되게 하는 부분)
        """
        txt = self.combo.currentText()
        i = self.combo.findText(txt, Qt.MatchFixedString)
        if i >= 0:
            if i != self.combo.currentIndex():
                self.combo.setCurrentIndex(i)
            self._last = self.combo.currentText()
            return
        hits = [t for t in self._texts() if t and hangul.matches(t, txt)]
        if txt.strip() and len(hits) == 1:
            self._pick(hits[0])
            return
        if not self.allow_free:
            self.combo.setCurrentText(self._last)

    # ------------------------------------------------------------ 이벤트
    def eventFilter(self, obj, ev):
        et = ev.type()
        if et == QEvent.MouseButtonPress:
            if obj is self.combo:
                # 오른쪽 화살표 영역 — 기본 팝업 대신 검색 목록을 연다
                if self._popup_open():
                    self._comp.popup().hide()
                else:
                    self.combo.lineEdit().setFocus()
                    self.show_all()
                return True
            if isinstance(obj, QLineEdit):
                # 흰칸 클릭 — 커서 위치는 그대로 두고 목록만 펼친다
                if not self._popup_open():
                    QTimer.singleShot(0, self.show_all)
                return False
        elif et == QEvent.KeyPress and isinstance(obj, QLineEdit):
            if ev.key() in (Qt.Key_Down, Qt.Key_Up) and not self._popup_open():
                self.show_all()
                return True
            if ev.key() == Qt.Key_Escape and self._popup_open():
                self._comp.popup().hide()
                return True
        elif et == QEvent.FocusOut and isinstance(obj, QLineEdit):
            # 목록이 열려 있는 동안의 포커스 이동은 확정이 아니다
            if not self._popup_open():
                self._resolve()
        return super().eventFilter(obj, ev)


def install(combo: QComboBox, allow_free: bool = False) -> ComboSearch:
    """콤보에 검색 기능을 붙인다(이미 붙어 있으면 그대로 돌려준다)."""
    old = getattr(combo, "_combo_search", None)
    if isinstance(old, ComboSearch):
        return old
    cs = ComboSearch(combo, allow_free)
    combo._combo_search = cs        # 콤보가 사라질 때 같이 사라지도록 붙여만 둔다
    return cs
