"""고객 등록/수정 대화상자 (구글 시트 '미출고차량' 연동).

직접기재 항목만 입력받는다. 수식으로 자동 계산되는 항목
(순번·합계·고객센터 번호·사고접수연락처·고객안내멘트·등록완료)은 건드리지 않는다.

- 계약일/출고일: 달력에서 고르고, 시트 서식(2026. 8. 14)으로 저장
- 견적서/계약서: Ctrl+V 로 이미지를 붙여넣어 셀 안 그림으로 등록
- 고객안내멘트: 시트 R열 내용을 클립보드로 복사
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTextEdit,
    QVBoxLayout, QWidget,
)

from . import config, sheets


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


class ImagePasteBox(QFrame):
    """Ctrl+V 로 이미지를 붙여넣는 상자. 미리보기 + 지우기."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(120)
        self.setFocusPolicy(Qt.StrongFocus)
        self._png: bytes = b""          # 새로 붙여넣은 이미지
        self._existing: str = ""        # 시트에 이미 들어있는 값(수식/텍스트)
        self._cleared: bool = False     # [지우기] 로 기존 이미지를 없앴는지

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        self.lbl = QLabel("여기를 클릭하고 Ctrl+V 로 견적서/계약서 이미지를 붙여넣으세요")
        self.lbl.setWordWrap(True)
        self.lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(self.lbl)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.hide()
        v.addWidget(self.preview)

        row = QHBoxLayout()
        self.btn_paste = QPushButton("붙여넣기 (Ctrl+V)")
        self.btn_paste.clicked.connect(self.paste_from_clipboard)
        self.btn_clear = QPushButton("지우기")
        self.btn_clear.clicked.connect(self.clear_image)
        row.addWidget(self.btn_paste)
        row.addWidget(self.btn_clear)
        row.addStretch()
        v.addLayout(row)

        sc = QShortcut(QKeySequence.Paste, self)
        sc.activated.connect(self.paste_from_clipboard)

    def set_existing(self, value: str):
        self._existing = value or ""
        if self._existing and not self._png:
            self.lbl.setText("이미 등록된 이미지가 있습니다. 바꾸려면 새로 붙여넣으세요.")

    def paste_from_clipboard(self):
        img = QGuiApplication.clipboard().image()
        if img.isNull():
            QMessageBox.information(
                self, config.APP_NAME,
                "클립보드에 이미지가 없습니다.\n"
                "캡처 도구나 이미지 프로그램에서 복사한 뒤 다시 시도하세요.")
            return
        from PySide6.QtCore import QBuffer, QByteArray
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.WriteOnly)
        img.save(buf, "PNG")
        buf.close()
        self._png = bytes(ba)
        pm = QPixmap.fromImage(img).scaledToWidth(
            min(360, img.width()), Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
        self.preview.show()
        self.lbl.setText(f"새 이미지 준비됨 ({img.width()}×{img.height()}, "
                         f"{len(self._png) // 1024}KB) — 저장하면 시트에 올라갑니다")

    def clear_image(self):
        self._png = b""
        # 이미 시트에 등록돼 있던 이미지도 함께 지우겠다는 뜻으로 본다.
        # (예전엔 _existing 을 그대로 둬서 [지우기] 가 아무 일도 하지 않았다)
        if self._existing:
            self._cleared = True
            self._existing = ""
        self.preview.clear()
        self.preview.hide()
        self.lbl.setText("여기를 클릭하고 Ctrl+V 로 견적서/계약서 이미지를 붙여넣으세요")

    def was_cleared(self) -> bool:
        """등록돼 있던 이미지를 [지우기] 로 없앴는지."""
        return bool(getattr(self, "_cleared", False)) and not self._png

    def png_bytes(self) -> bytes:
        return self._png

    def existing(self) -> str:
        return self._existing


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
        ("doc", "견적서/계약서", "image"),
    ]

    def __init__(self, caption: str, values: dict, choices: dict,
                 ment: str = "", parent=None, terms_map: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(caption)
        self.resize(600, 760)
        self.widgets: dict = {}
        self._ment = ment or ""
        self._terms_map = terms_map or {}     # 금융사 → 자주 쓴 계약조건

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
                w.setEditable(True)
                w.addItem("")
                for it in (choices or {}).get(key, []):
                    w.addItem(it)
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
                chk.setChecked(d is None)      # 값이 없거나 못 읽으면 '미정'
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
            elif kind == "image":
                w = ImagePasteBox()
                w.set_existing(cur)
                form.addRow(label, w)
            elif kind == "money":
                w = MoneyEdit(cur)
                form.addRow(label, w)
            elif kind == "text":
                w = QTextEdit()
                w.setMinimumHeight(64)
                w.setPlainText(cur)
                # Tab 으로 다음 입력창으로 넘어가게 (기본은 Tab 문자가 입력됨)
                w.setTabChangesFocus(True)
                if key == "terms":
                    # 금융사별로 자주 쓴 계약조건을 골라 넣을 수 있게
                    holder = QWidget()
                    vl = QVBoxLayout(holder)
                    vl.setContentsMargins(0, 0, 0, 0)
                    vl.setSpacing(3)
                    self.cmb_terms = QComboBox()
                    self.cmb_terms.setToolTip("이 금융사로 자주 쓴 계약조건")
                    self.cmb_terms.activated.connect(self._pick_terms)
                    vl.addWidget(self.cmb_terms)
                    vl.addWidget(w)
                    form.addRow(label, holder)
                else:
                    form.addRow(label, w)
            else:
                w = QLineEdit()
                w.setText(cur)
                form.addRow(label, w)
            self.widgets[key] = (w, kind)

        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # 금융사가 바뀌면 계약조건 후보를 그 금융사 것으로 교체
        fin_w = self.widgets.get("finance", (None, ""))[0]
        if fin_w is not None and hasattr(self, "cmb_terms"):
            fin_w.currentTextChanged.connect(self._reload_terms)
            self._reload_terms(fin_w.currentText())

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

    def _reload_terms(self, finance: str):
        """선택한 금융사로 자주 쓴 계약조건을 목록에 채운다."""
        items = self._terms_map.get((finance or "").strip(), [])
        self.cmb_terms.blockSignals(True)
        self.cmb_terms.clear()
        if items:
            self.cmb_terms.addItem(f"↓ 자주 쓴 계약조건 {len(items)}개 — 골라서 넣기")
            for t in items[:12]:
                self.cmb_terms.addItem(t)
            self.cmb_terms.setEnabled(True)
        else:
            self.cmb_terms.addItem("(이 금융사로 저장된 계약조건이 아직 없습니다)")
            self.cmb_terms.setEnabled(False)
        self.cmb_terms.setCurrentIndex(0)
        self.cmb_terms.blockSignals(False)

    def _pick_terms(self, idx: int):
        if idx <= 0:
            return
        w, _k = self.widgets["terms"]
        w.setPlainText(self.cmb_terms.itemText(idx))
        self.cmb_terms.setCurrentIndex(0)

    def _copy_ment(self):
        QGuiApplication.clipboard().setText(self._ment)
        self.lbl_ment.setText("복사했습니다 ✅")

    def _ok(self):
        if not self.values().get("customer", "").strip():
            QMessageBox.information(self, config.APP_NAME, "고객명을 입력하세요.")
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
            elif kind == "image":
                # 견적서/계약서(S열)는 여기서 절대 내보내지 않는다.
                # 표시값이 빈 문자열인 =IMAGE() 수식을 되돌려 써서 그림을 지웠었다.
                # 새 이미지는 new_image(), 지우기는 doc_cleared() 로 따로 전달한다.
                continue
            elif kind == "text":
                out[key] = w.toPlainText().strip()
            else:
                out[key] = w.text().strip()
        return out

    def new_image(self) -> bytes:
        """새로 붙여넣은 이미지(PNG). 없으면 빈 바이트."""
        w, _kind = self.widgets["doc"]
        return w.png_bytes()

    def doc_cleared(self) -> bool:
        """등록돼 있던 견적서/계약서를 [지우기] 로 없앴는지."""
        w, _kind = self.widgets["doc"]
        return w.was_cleared()

    @classmethod
    def run(cls, caption: str, values: dict, choices: dict, ment: str = "",
            parent=None, terms_map: dict | None = None):
        """반환: (값 dict, 새 이미지 bytes, 기존 이미지 지움 여부) 또는 None(취소)."""
        d = cls(caption, values, choices, ment, parent, terms_map)
        if d.exec() != QDialog.Accepted:
            return None
        return d.values(), d.new_image(), d.doc_cleared()
