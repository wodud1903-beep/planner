"""고객별 심사서류 체크리스트.

어떤 서류를 받았고 무엇이 남았는지는 지금까지 머릿속에만 있었다. 하나를
빠뜨리면 심사가 반려되고 며칠이 밀린다. 그래서 고객마다 받아야 할 서류를
적어 두고 받은 것에 체크한다.

목록은 [자료검색] 의 '심사서류' 자료에서 그대로 가져온다(개인 / 개인사업자 /
법인 …). 자료를 고치면 다음에 불러올 때 그 내용이 따라온다.

저장 키는 **시트 U열 고객ID** 다. 고객명이나 순번을 바꿔도 체크가 안 끊긴다.
"""

from __future__ import annotations

import json
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)

from . import config, kb, searchcombo, theme

FILE = "customer_docs.json"
# 이 진행현황일 때만 '서류 미비' 를 브리핑에 알린다.
# 출고까지 끝났거나 취소된 건은 이제 받을 서류가 없다.
OPEN_STATUS = ("계약", "발주", "상담중", "심사중", "접수")


# ---------------------------------------------------------------------------
# 저장소
# ---------------------------------------------------------------------------
def load() -> dict:
    try:
        p = config.data_file(FILE)
        if p.exists():
            o = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(o, dict):
                return o
    except Exception:
        pass
    return {}


def save(data: dict) -> None:
    config.atomic_write(config.data_file(FILE),
                        json.dumps(data or {}, ensure_ascii=False, indent=2))


def record(data: dict, uid: str) -> dict:
    """고객 한 명의 기록. 없으면 빈 것."""
    got = (data or {}).get((uid or "").strip())
    if isinstance(got, dict):
        return {"template": str(got.get("template", "")),
                "items": [x for x in (got.get("items") or [])
                          if isinstance(x, dict) and str(x.get("name", "")).strip()]}
    return {"template": "", "items": []}


def counts(rec: dict) -> tuple:
    """(제출한 수, 전체 수)."""
    items = (rec or {}).get("items") or []
    return sum(1 for i in items if i.get("done")), len(items)


def missing(rec: dict) -> list:
    return [i.get("name", "") for i in ((rec or {}).get("items") or [])
            if not i.get("done")]


def is_open_status(status: str) -> bool:
    return (status or "").strip() in OPEN_STATUS


# ---------------------------------------------------------------------------
# 창
# ---------------------------------------------------------------------------
class CustomerDocsDialog(QDialog):
    """고객 한 명의 서류 체크리스트."""

    def __init__(self, cr, rec: dict, templates: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"심사서류 · {cr.get('customer')}")
        self.resize(520, 600)
        self._cr = cr
        self._rec = {"template": (rec or {}).get("template", ""),
                     "items": [dict(x) for x in ((rec or {}).get("items") or [])]}
        self._templates = list(templates or [])

        root = QVBoxLayout(self)

        self.lbl_head = QLabel(
            f"<b style='font-size:15px;'>{cr.get('customer')}</b><br>"
            f"<span style='color:{theme.c('subtext')};'>"
            f"{cr.get('finance')} · {cr.get('model')} · {cr.get('status')}</span>")
        self.lbl_head.setWordWrap(True)
        root.addWidget(self.lbl_head)

        # ---- 템플릿 불러오기 ----
        trow = QHBoxLayout()
        trow.addWidget(QLabel("서류 목록"))
        self.cmb_tpl = QComboBox()
        self.cmb_tpl.addItem("고를 서류 목록", "")
        for t in self._templates:
            tail = f" ({t.get('finance')})" if t.get("finance") else ""
            self.cmb_tpl.addItem(t.get("title", "") + tail, t.get("title", ""))
        searchcombo.install(self.cmb_tpl)
        trow.addWidget(self.cmb_tpl, 1)
        self.btn_load = QPushButton("불러오기")
        self.btn_load.clicked.connect(self._load_template)
        trow.addWidget(self.btn_load)
        root.addLayout(trow)

        if not self._templates:
            lbl = QLabel("[자료검색] 에서 분류를 '심사서류' 로 자료를 만들면\n"
                         "여기서 그 목록을 바로 불러올 수 있습니다.")
            lbl.setStyleSheet(f"color:{theme.c('subtext')};")
            root.addWidget(lbl)

        # ---- 체크리스트 ----
        self.lst = QListWidget()
        self.lst.itemChanged.connect(self._on_check)
        root.addWidget(self.lst, 1)

        self.lbl_count = QLabel("")
        root.addWidget(self.lbl_count)

        # ---- 항목 추가 ----
        arow = QHBoxLayout()
        self.ed_new = QLineEdit()
        self.ed_new.setPlaceholderText("서류를 직접 추가하고 Enter (예: 차량등록증 사본)")
        self.ed_new.returnPressed.connect(self._add)
        btn_add = QPushButton("추가")
        btn_add.clicked.connect(self._add)
        arow.addWidget(self.ed_new, 1)
        arow.addWidget(btn_add)
        root.addLayout(arow)

        brow = QHBoxLayout()
        btn_del = QPushButton("선택 항목 삭제")
        btn_del.clicked.connect(self._del)
        self.btn_copy = QPushButton("미제출 목록 복사")
        self.btn_copy.clicked.connect(self._copy_missing)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        brow.addWidget(btn_del)
        brow.addWidget(self.btn_copy)
        brow.addStretch()
        brow.addWidget(btn_close)
        root.addLayout(brow)

        # 저장된 목록이 없으면 고객의 금융사와 맞는 템플릿을 먼저 보여준다
        if not self._rec["items"]:
            self._preselect()
        self._refresh()

    # ---- 템플릿 ----
    def _preselect(self):
        fin = (self._cr.get("finance") or "").strip()
        for i, t in enumerate(self._templates):
            if fin and t.get("finance", "").strip() == fin:
                self.cmb_tpl.setCurrentIndex(i + 1)
                return

    def _load_template(self):
        title = self.cmb_tpl.currentData()
        tpl = next((t for t in self._templates if t.get("title") == title), None)
        if not tpl:
            QMessageBox.information(self, config.APP_NAME, "불러올 서류 목록을 고르세요.")
            return
        names = list(tpl.get("checklist") or [])
        have = {i.get("name") for i in self._rec["items"]}
        added = 0
        for n in names:
            if n not in have:
                self._rec["items"].append({"name": n, "done": False, "date": ""})
                added += 1
        self._rec["template"] = tpl.get("title", "")
        self._refresh()
        if added == 0:
            QMessageBox.information(self, config.APP_NAME,
                                    "이미 다 들어 있는 목록입니다.")

    # ---- 목록 ----
    def _refresh(self):
        self.lst.blockSignals(True)
        self.lst.clear()
        for i, it in enumerate(self._rec["items"]):
            text = it.get("name", "")
            if it.get("done") and it.get("date"):
                text += f"    ({it['date']} 받음)"
            li = QListWidgetItem(text)
            li.setFlags(li.flags() | Qt.ItemIsUserCheckable)
            li.setCheckState(Qt.Checked if it.get("done") else Qt.Unchecked)
            li.setData(Qt.UserRole, i)
            self.lst.addItem(li)
        self.lst.blockSignals(False)

        done, total = counts(self._rec)
        if total:
            left = total - done
            self.lbl_count.setText(
                f"{done} / {total} 제출" + (f"   ·   {left}건 남음" if left else "   ·   완료 ✓"))
            self.lbl_count.setStyleSheet(
                f"color:{theme.strong('green') if not left else theme.strong('orange')};"
                "font-weight:bold;")
        else:
            self.lbl_count.setText("아직 서류 목록이 없습니다. 위에서 불러오거나 직접 추가하세요.")
            self.lbl_count.setStyleSheet(f"color:{theme.c('subtext')};")
        self.btn_copy.setEnabled(bool(missing(self._rec)))

    def _on_check(self, li: QListWidgetItem):
        i = li.data(Qt.UserRole)
        if not isinstance(i, int) or not (0 <= i < len(self._rec["items"])):
            return
        done = li.checkState() == Qt.Checked
        it = self._rec["items"][i]
        it["done"] = done
        # 받은 날짜를 남긴다. 체크를 풀면 지운다.
        it["date"] = date.today().strftime("%Y-%m-%d") if done else ""
        self._refresh()

    def _add(self):
        t = self.ed_new.text().strip()
        if not t:
            return
        if any(i.get("name") == t for i in self._rec["items"]):
            QMessageBox.information(self, config.APP_NAME, "이미 있는 항목입니다.")
            return
        self._rec["items"].append({"name": t, "done": False, "date": ""})
        self.ed_new.clear()
        self._refresh()

    def _del(self):
        li = self.lst.currentItem()
        i = li.data(Qt.UserRole) if li else None
        if not isinstance(i, int) or not (0 <= i < len(self._rec["items"])):
            QMessageBox.information(self, config.APP_NAME, "삭제할 항목을 고르세요.")
            return
        self._rec["items"].pop(i)
        self._refresh()

    def _copy_missing(self):
        left = missing(self._rec)
        if not left:
            return
        from PySide6.QtGui import QGuiApplication
        text = ("아래 서류를 준비해 주시면 심사 진행하겠습니다.\n"
                + "\n".join("· " + n for n in left))
        try:
            QGuiApplication.clipboard().setText(text)
            self.btn_copy.setText("복사됨 ✓")
        except Exception:
            self.btn_copy.setText("복사 실패")

    def value(self) -> dict:
        return {"template": self._rec["template"],
                "items": [dict(x) for x in self._rec["items"]]}

    @classmethod
    def run(cls, cr, rec: dict, templates: list, parent=None) -> dict:
        """반환: 바뀐 기록 (창을 닫으면 항상 반영)."""
        d = cls(cr, rec, templates, parent)
        d.exec()
        return d.value()
