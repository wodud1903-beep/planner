"""고객 등록/수정 대화상자 (구글 시트 '미출고차량' 연동).

직접기재 항목만 입력받는다. 수식으로 자동 계산되는 항목
(순번·합계·고객센터 번호·사고접수연락처·고객안내멘트·등록완료)은 건드리지 않는다.

- 계약일/출고일: 달력에서 고르고, 시트 서식(2026. 8. 14)으로 저장
- 서류(견적서·등록증·계약확인서 등, v1.33): 여러 개 — Ctrl+V · 끌어다 놓기 · [파일 추가…]
  (customer_attach.CustomerFilesBox — 자료검색 첨부와 같은 부품)
- 고객안내멘트: 시트 R열 내용을 클립보드로 복사
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTextEdit,
    QVBoxLayout, QWidget,
)

from . import config, searchcombo, sheets
from .customer_attach import CustomerFilesBox, legacy_att
from .incentive_box import IncentiveBox


class MoneyEdit(QLineEdit):
    """금액 입력 — 타이핑하는 즉시 1,000 단위로 콤마를 넣어준다."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignRight)
        self.setPlaceholderText("0")
        self._guard = False
        self.textChanged.connect(self._reformat)
        self.setText(sheets.fmt_money(text))

    def _reformat(self, _t: str):
        if self._guard:
            return
        self._guard = True
        try:
            raw = self.text()
            # 커서 뒤에 남은 '숫자 개수' 를 기준으로 위치를 복원한다
            tail_digits = sum(1 for ch in raw[self.cursorPosition():] if ch.isdigit())
            new = sheets.fmt_money(raw)
            if new != raw:
                self.setText(new)
                pos = len(new)
                seen = 0
                for i in range(len(new) - 1, -1, -1):
                    if new[i].isdigit():
                        seen += 1
                        if seen == tail_digits:
                            pos = i
                            break
                else:
                    pos = len(new) if tail_digits == 0 else pos
                self.setCursorPosition(max(0, min(pos, len(new))))
        finally:
            self._guard = False

    def value(self) -> str:
        return sheets.digits_only(self.text())


class CustomerDialog(QDialog):
    #  key            라벨            위젯종류
    LAYOUT = [
        ("customer", "고객명 / 사업자", "line"),
        ("finance", "금융사", "combo"),
        ("model", "차종", "line"),
        ("price", "차량가격", "money"),
        ("fee", "금융수수료", "money"),
        ("incentive", "대리점 수당", "money"),
        ("channel", "특판 / 대리점", "combo"),
        ("contract_date", "계약일(발주)", "date"),
        ("deliver_date", "출고일", "date"),
        ("status", "진행현황", "combo"),
        ("terms", "계약조건", "text"),
        ("note", "내용", "text"),
        ("kind", "출고유형", "combo"),
        ("doc", "첨부 서류", "files"),
    ]

    # 시트에 아직 그 값이 안 쓰였어도 항상 고를 수 있어야 하는 항목.
    # 시트에서 뽑은 값(choices)보다 **앞에** 놓아, 새 시트로 시작해도
    # 매번 손으로 치지 않게 한다.
    FIXED_CHOICES = {
        "channel": ["특판", "대리점"],
        "status": ["출고", "취소", "발주", "진행보류"],
    }

    # 새 고객을 등록할 때 날짜칸의 '미정' 기본값.
    # 계약일은 오늘 적는 것이 보통이고(체크 해제 = 오늘 날짜),
    # 출고일은 아직 안 잡힌 것이 보통이다(체크 = 미정).
    # ⚠️ 기존 고객을 수정할 때는 쓰지 않는다 — 비어 있던 계약일이 창을 열었다
    #    저장하기만 해도 오늘 날짜로 채워진다.
    NEW_DATE_UNSET = {"contract_date": False, "deliver_date": True}

    # 이 창은 하루에도 여러 번 채워 넣는 화면이라 글자를 앱 기본(10pt)보다 키운다
    FONT_PT = 12

    def __init__(self, caption: str, values: dict, choices: dict,
                 ment: str = "", parent=None, files: list | None = None, auth=None):
        super().__init__(parent)
        self.setWindowTitle(caption)
        self.resize(680, 820)
        # 라벨·입력칸·드롭다운을 한꺼번에 키운다(창 전체에 걸어 두면 스크롤 안쪽
        # 위젯까지 따라온다). 단추는 기본 크기를 그대로 둔다.
        self.setStyleSheet(
            f"QLabel, QLineEdit, QComboBox, QTextEdit, QDateEdit, QCheckBox,"
            f" QSpinBox {{ font-size: {self.FONT_PT}pt; }}")
        self.widgets: dict = {}
        self._ment = ment or ""
        # 값이 하나도 안 넘어오면 '고객 등록' 이다
        self._is_new = not (values or {})

        root = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("dlgbody")
        inner.setAttribute(Qt.WA_StyledBackground, True)
        form = QFormLayout(inner)

        for key, label, kind in self.LAYOUT:
            cur = (values or {}).get(key, "")
            if kind == "combo":
                w = QComboBox()
                w.addItem("")
                fixed = self.FIXED_CHOICES.get(key, [])
                for it in fixed:
                    w.addItem(it)
                for it in (choices or {}).get(key, []):
                    if it not in fixed:
                        w.addItem(it)
                # 초성/낱말 검색 — 목록에 없는 값(새 금융사 등)도 그대로 쓸 수 있게
                searchcombo.install(w, allow_free=True)
                w.setCurrentText(cur)
                form.addRow(label, w)
            elif kind == "date":
                # 달력에서 고르되, 아직 안 정해진 날짜(출고 전)는 '미정' 으로 비워둔다
                holder = QWidget()
                hl = QHBoxLayout(holder)
                hl.setContentsMargins(0, 0, 0, 0)
                de = QDateEdit()
                de.setCalendarPopup(True)
                de.setDisplayFormat("yyyy. M. d")
                d = sheets.parse_date(cur)
                de.setDate(QDate(d.year, d.month, d.day) if d else QDate.currentDate())
                chk = QCheckBox("미정")
                if self._is_new:
                    # 등록 창은 칸마다 기본값이 다르다 (계약일=오늘 / 출고일=미정)
                    chk.setChecked(self.NEW_DATE_UNSET.get(key, True))
                else:
                    chk.setChecked(d is None)  # 값이 없거나 못 읽으면 '미정'
                chk.toggled.connect(lambda on, e=de: e.setEnabled(not on))
                de.setEnabled(not chk.isChecked())
                # 앱이 못 읽는 형식(예: '8/14 예정')이 들어있으면, 사용자가 날짜를
                # 직접 건드리지 않는 한 그 칸을 건드리지 않는다.
                # (예전엔 '미정' 과 똑같이 취급해 저장 한 번에 날짜가 지워졌다)
                unreadable = bool(cur.strip()) and d is None
                de.dateChanged.connect(
                    lambda _v, h=holder: h.setProperty("touched", True))
                chk.toggled.connect(
                    lambda _v, h=holder: h.setProperty("touched", True))
                holder.setProperty("touched", False)
                holder.setProperty("unreadable", unreadable)
                hl.addWidget(de, 1)
                hl.addWidget(chk)
                w = (de, chk, holder)
                form.addRow(label, holder)
            elif kind == "files":
                # 시트 V열 목록 + (거기 없으면) S열 옛 견적서 그림을 맨 앞에
                fl = [dict(f) for f in (files or [])]
                old = legacy_att(cur)
                self._legacy_id = old["id"] if old else ""
                if old and old["id"] not in {f.get("id") for f in fl}:
                    fl.insert(0, old)
                w = CustomerFilesBox(fl, auth=auth)
                self.files_box = w
                form.addRow(label, w)
            elif kind == "money":
                w = MoneyEdit(cur)
                form.addRow(label, w)
                if key == "incentive":
                    # 수당계산기 탭으로 옮겨 다니지 않게, 바로 아래에 미니계산기를 둔다
                    self.inc_box = IncentiveBox()
                    self.inc_box.applied.connect(self._apply_incentive)
                    form.addRow("", self.inc_box)
            elif kind == "text":
                w = QTextEdit()
                w.setMinimumHeight(64)
                w.setPlainText(cur)
                # Tab 으로 다음 입력창으로 넘어가게 (기본은 Tab 문자가 입력됨)
                w.setTabChangesFocus(True)
                # 계약조건도 그냥 손으로 적는다 — '골라서 넣기' 드롭다운은 뺐다
                form.addRow(label, w)
            else:
                w = QLineEdit()
                w.setText(cur)
                form.addRow(label, w)
            self.widgets[key] = (w, kind)

        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # 미니계산기에 차량가격·차종을 물려 준다 (칸이 바뀌면 즉시 다시 계산)
        if hasattr(self, "inc_box"):
            price_w = self.widgets.get("price", (None, ""))[0]
            model_w = self.widgets.get("model", (None, ""))[0]
            if price_w is not None:
                price_w.textChanged.connect(
                    lambda _t, w=price_w: self.inc_box.set_price(w.value()))
                self.inc_box.set_price(price_w.value())
            if model_w is not None:
                model_w.textChanged.connect(self.inc_box.suggest_model)
                self.inc_box.suggest_model(model_w.text())

        # 고객안내멘트 복사 (시트 R열 — 자동 계산되는 값)
        mrow = QHBoxLayout()
        self.btn_copy_ment = QPushButton("고객안내멘트 복사")
        self.btn_copy_ment.clicked.connect(self._copy_ment)
        self.btn_copy_ment.setEnabled(bool(self._ment.strip()))
        mrow.addWidget(self.btn_copy_ment)
        self.lbl_ment = QLabel(
            self._ment.strip().splitlines()[0][:48] + " …" if self._ment.strip()
            else "(저장 후 시트에서 자동 생성됩니다)")
        mrow.addWidget(self.lbl_ment, 1)
        root.addLayout(mrow)

        row = QHBoxLayout()
        row.addStretch()
        ok = QPushButton("저장")
        ok.setDefault(True)
        ok.clicked.connect(self._ok)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        root.addLayout(row)


    def _apply_incentive(self, amount: str):
        """미니계산기의 [적용] — 대리점 수당 칸에 넣는다."""
        w, _kind = self.widgets.get("incentive", (None, ""))
        if w is not None:
            w.setText(sheets.fmt_money(amount))

    def _copy_ment(self):
        QGuiApplication.clipboard().setText(self._ment)
        self.lbl_ment.setText("복사했습니다 ✅")

    def _ok(self):
        name = self.values().get("customer", "").strip()
        if not name:
            QMessageBox.information(self, config.APP_NAME, "고객명을 입력하세요.")
            return
        # 새로 넣은 서류부터 올린다 — 못 올리면 창을 닫지 않는다(넣은 것을 잃지 않게)
        if hasattr(self, "files_box") and not self.files_box.upload_pending(name):
            return
        self.accept()

    def values(self) -> dict:
        out = {}
        for key, (w, kind) in self.widgets.items():
            if kind == "combo":
                out[key] = w.currentText().strip()
            elif kind == "money":
                out[key] = w.value()          # 콤마 없는 숫자
            elif kind == "date":
                de, chk, holder = w
                if holder.property("unreadable") and not holder.property("touched"):
                    continue      # 못 읽은 원래 값을 그대로 둔다 (키를 안 넣는다)
                out[key] = "" if chk.isChecked() else sheets.fmt_date(de.date().toPython())
            elif kind in ("image", "files"):
                # 견적서/계약서(S열)는 여기서 절대 내보내지 않는다.
                # 표시값이 빈 문자열인 =IMAGE() 수식을 되돌려 써서 그림을 지웠었다.
                # 서류는 files_result(), S열 그림을 뺐는지는 doc_cleared() 로 따로 전달한다.
                continue
            elif kind == "text":
                out[key] = w.toPlainText().strip()
            else:
                out[key] = w.text().strip()
        return out

    def files_result(self) -> dict:
        """서류 — {files, changed, removed, renamed} (customer_attach.CustomerFilesBox.result)."""
        return self.files_box.result()

    def doc_cleared(self) -> bool:
        """S열 옛 견적서 그림을 서류 목록에서 뺐는지 — 그러면 S열도 비운다."""
        lid = getattr(self, "_legacy_id", "")
        return bool(lid) and lid not in {f["id"] for f in self.files_result()["files"]}

    @classmethod
    def run(cls, caption: str, values: dict, choices: dict, ment: str = "",
            parent=None, files: list | None = None, auth=None):
        """반환: (값 dict, 서류 결과 dict, S열 그림 뺌 여부) 또는 None(취소)."""
        d = cls(caption, values, choices, ment, parent, files=files, auth=auth)
        if d.exec() != QDialog.Accepted:
            return None
        return d.values(), d.files_result(), d.doc_cleared()
