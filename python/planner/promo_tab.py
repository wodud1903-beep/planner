"""'수입차 프로모션' 화면(v1.34) — 브랜드별 할인표를 시트 4행 제목 그대로, 모델명은 치는 대로 찾는다.

  · 위: 검색칸(자료검색과 같은 실시간 · 초성 · 한글 끝 글자 조합 중도) + [전체·벤츠·BMW·아우디] + [새로고침] [시트 열기]
  · 표 하나에 브랜드마다 — 제목 줄(2~3행) · 묶음 제목(기본값 변동 X | 11월 프로모션) · 열 제목(4행) · 모델 줄.
    브랜드마다 열 제목이 달라서(벤츠 MBF·프로모션 / BMW 현금·제휴사 …) 표 머리 대신 줄로 그린다.
  · 줄을 고르고 Ctrl+C(또는 오른쪽 단추 → 복사) — '모델 · 차량가 … · 현금 …' 한 줄로 카톡에 붙인다.
  · 탭을 처음 열 때 저장본부터 보여 주고 뒤에서 새로 읽는다. 10분 지나 다시 열면 또 새로 읽는다.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont, QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QHBoxLayout, QLabel, QMenu, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import config, promo, sheets, theme
from .livesearch import LiveLineEdit
from .models import promo_where

ROLE = Qt.UserRole + 1


class PromoTab(QWidget):
    """수입차 프로모션 조건표."""

    SEARCH_DELAY_MS = 120
    _sig_done = Signal(object, str, bool)      # (받은 값 | None, 오류, 손으로 눌렀나)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth = None
        self.sheet_id = config.PROMO_DEF_SHEET_ID
        self.tab = config.PROMO_DEF_TAB
        self.raw = None             # 시트에서 받은 그대로(저장본 포함)
        self.blocks: list = []
        self._fresh_at = None       # 이번에 켠 뒤 시트에서 새로 읽은 때(time.monotonic)
        self._cache_tried = False
        self._loading = False
        self._err = ""
        self._brand = ""            # 고른 브랜드("" = 전체)
        self._rows: list = []       # 표의 줄 → (종류, 블록, 줄)
        self._sig_done.connect(self._on_done)

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        top = QHBoxLayout()
        self.ed_find = LiveLineEdit()
        self.ed_find.setPlaceholderText("모델명을 치세요  —  예: E300 · X5 · Q5 스포트백 · 전기차 · 벤츠 GLC")
        self.ed_find.setClearButtonEnabled(True)
        self._find_timer = QTimer(self)
        self._find_timer.setSingleShot(True)
        self._find_timer.setInterval(self.SEARCH_DELAY_MS)
        self._find_timer.timeout.connect(self._paint)
        self.ed_find.liveText.connect(lambda _t: self._find_timer.start())
        top.addWidget(self.ed_find, 1)
        self._brand_box = QHBoxLayout()
        self._brand_box.setSpacing(4)
        top.addLayout(self._brand_box)
        self._brand_group = QButtonGroup(self)
        self._brand_group.setExclusive(True)
        self._brand_btns: dict = {}
        self.btn_reload = QPushButton("새로고침")
        self.btn_reload.setToolTip("프로모션 시트를 지금 다시 읽습니다")
        self.btn_reload.clicked.connect(lambda: self.reload(manual=True))
        top.addWidget(self.btn_reload)
        self.btn_open = QPushButton("시트 열기")
        self.btn_open.clicked.connect(self.open_sheet)
        top.addWidget(self.btn_open)
        v.addLayout(top)

        self.stack = QStackedWidget()
        self.tbl = QTableWidget(0, 6)
        self.tbl.verticalHeader().hide()
        self.tbl.horizontalHeader().hide()
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tbl.setWordWrap(True)
        self.tbl.setShowGrid(True)
        self.tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._menu)
        self.tbl.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tbl.setStyleSheet("QTableWidget { font-size: 10.5pt; }")
        QShortcut(QKeySequence.Copy, self.tbl, activated=self.copy_selected,
                  context=Qt.WidgetShortcut)
        # 창 폭이 바뀌면 안내 글(여러 줄) 높이를 다시 맞춘다
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(60)
        self._fit_timer.timeout.connect(self._fit_spans)
        self.tbl.horizontalHeader().sectionResized.connect(lambda *_a: self._fit_timer.start())
        self.stack.addWidget(self.tbl)
        self.lbl_empty = QLabel("")
        self.lbl_empty.setAlignment(Qt.AlignCenter)
        self.lbl_empty.setWordWrap(True)
        self.stack.addWidget(self.lbl_empty)
        v.addWidget(self.stack, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        v.addWidget(self.lbl_status)

        self._rebuild_brands()
        self._paint()

    # ------------------------------------------------------------ 바깥에서 부르는 것
    def set_auth(self, auth) -> None:
        self.auth = auth

    def set_where(self, sheet_id: str, tab: str) -> None:
        """설정의 시트·탭. 바뀌면 들고 있던 표를 버리고(보고 있으면) 새로 읽는다."""
        sid, t = promo_where(sheet_id, tab)     # 비우면 회사 프로모션 시트(탭도)
        if (sid, t) == (self.sheet_id, self.tab):
            return
        self.sheet_id, self.tab = sid, t
        self.reset()

    def reset(self) -> None:
        """계정·시트가 바뀌었다 — 처음 상태로(저장본도 그 계정 폴더 것을 다시 본다)."""
        self.raw, self.blocks, self._fresh_at, self._err = None, [], None, ""
        self._cache_tried = False
        self._rebuild_brands()
        self._paint()
        if self.isVisible():
            self.on_shown()

    def on_shown(self) -> None:
        """탭을 열었다 — 저장본부터 보여 주고, 오래됐으면(또는 처음) 새로 읽는다."""
        if not self._cache_tried:
            self._cache_tried = True
            raw = promo.load_cache(self.sheet_id, self.tab)
            if raw and not self.blocks:
                self._take(raw)
        stale = self._fresh_at is None or time.monotonic() - self._fresh_at > promo.STALE_SEC
        # 시트 한도(1분)에 걸려 쉬는 중이면 저장본만 보여 주고 다음에 — 단, 보여 줄 것이 없으면 그래도 읽는다
        if stale and (not self.blocks or sheets.quota_left() <= 0):
            self.reload(manual=False)
        self.ed_find.setFocus()

    def focus_search(self) -> None:
        self.ed_find.setFocus()
        self.ed_find.selectAll()

    def search_for(self, query: str) -> None:
        self.ed_find.setText(query)
        self._paint()

    # ------------------------------------------------------------ 읽기
    def reload(self, manual: bool = True) -> None:
        if self._loading:
            return
        if self.auth is None or not self.auth.is_connected():
            self._err = "구글 로그인 후 볼 수 있습니다 — [설정] 에서 Google 로그인을 해 주세요."
            self._paint()
            return
        self._loading = True
        self.btn_reload.setEnabled(False)
        self._paint_status()
        auth, sid, tab = self.auth, self.sheet_id, self.tab

        def worker():
            raw, err = None, ""
            try:
                raw = promo.read(auth, sid, tab)
            except Exception as e:          # noqa: BLE001 — 무엇이든 화면에 알린다
                err = str(e) or e.__class__.__name__
            try:
                self._sig_done.emit((sid, tab, raw), err, manual)
            except RuntimeError:
                pass                        # 창이 먼저 닫혔다

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, got, err: str, manual: bool) -> None:
        self._loading = False
        self.btn_reload.setEnabled(True)
        sid, tab, raw = got
        if (sid, tab) != (self.sheet_id, self.tab):
            return                          # 그사이 설정이 바뀌었다 — 옛 시트 것은 버린다
        if raw is not None:
            self._err = ""
            self._fresh_at = time.monotonic()
            promo.save_cache(sid, tab, raw)
            self._take(raw)
        else:
            self._err = err
            self._paint()

    def _take(self, raw: dict) -> None:
        self.raw = raw
        self.blocks = promo.parse(raw.get("values") or [], raw.get("merges") or [])
        self._rebuild_brands()
        self._paint()

    def open_sheet(self) -> None:
        gid = (self.raw or {}).get("gid")
        QDesktopServices.openUrl(QUrl(promo.sheet_url(self.sheet_id, gid)))

    # ------------------------------------------------------------ 브랜드 단추
    def _rebuild_brands(self) -> None:
        keep = self._brand
        names = [("", "전체")] + [(b["key"], b["brand"]) for b in self.blocks]
        if [(k, btn.property("brandName")) for k, btn in self._brand_btns.items()] == names:
            return                          # 브랜드가 그대로면 단추도 그대로(새로 읽을 때마다 깜빡이지 않게)
        for b in list(self._brand_btns.values()):
            self._brand_group.removeButton(b)
            self._brand_box.removeWidget(b)
            b.hide()                        # ⚠️ 지워지기(deleteLater) 전까지 왼쪽 위에 떠 보이지 않게
            b.setParent(None)
            b.deleteLater()
        self._brand_btns = {}
        for key, name in names:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setProperty("brandName", name)
            btn.clicked.connect(lambda _c=False, k=key: self._pick_brand(k))
            self._brand_group.addButton(btn)
            self._brand_box.addWidget(btn)
            self._brand_btns[key] = btn
        if keep not in self._brand_btns:
            keep = ""
        self._brand = keep
        self._brand_btns[keep].setChecked(True)
        self._style_brands()

    def _style_brands(self) -> None:
        css = (f"QPushButton:checked {{ background:{theme.c('select_bg')};"
               f" color:{theme.c('nav_sel_text')}; border-color:{theme.c('accent')}; font-weight:bold; }}")
        for b in self._brand_btns.values():
            b.setStyleSheet(css)

    def _pick_brand(self, key: str) -> None:
        self._brand = key
        self._paint()

    # ------------------------------------------------------------ 그리기
    def _paint(self) -> None:
        q = self.ed_find.live_text().strip()
        found = promo.search(self.blocks, q, self._brand)
        counts = promo.hit_count(promo.search(self.blocks, q, "")) if q else {}
        for key, btn in self._brand_btns.items():
            name = btn.property("brandName") or btn.text()
            if q and key:
                btn.setText(f"{name} {counts.get(key, 0)}")
            elif q:
                btn.setText(f"{name} {sum(counts.values())}")
            else:
                btn.setText(name)
        if not self.blocks:
            if self._loading or (not self._err and not self._cache_tried):
                msg = "프로모션 시트를 불러오는 중…"
            else:
                msg = self._err or "프로모션 시트에 표가 없습니다."
            self._show_empty(msg)
        elif not found:
            typed, _t = promo.split_query(q)
            others = sum(counts.values())
            if self._brand and not typed and others:
                where = " · ".join(f"{b['brand']} {counts.get(b['key'], 0)}" for b in self.blocks
                                   if counts.get(b["key"]))
                self._show_empty(f"'{q}' — 이 브랜드에는 없습니다.\n다른 브랜드에 있습니다: {where}"
                                 "\n위 [전체] 를 누르면 함께 보입니다.")
            else:
                self._show_empty(f"'{q}' 에 맞는 모델이 없습니다.\n모델명 일부(예: E300 · X5 · Q5)나 초성으로 찾아 보세요.")
        else:
            self.stack.setCurrentWidget(self.tbl)
            self._fill(found)
        self._paint_status(counts if q else None)

    def _show_empty(self, msg: str) -> None:
        self._rows = []
        self.tbl.setRowCount(0)
        self.lbl_empty.setText(msg)
        self.lbl_empty.setStyleSheet(f"color:{theme.c('subtext')}; font-size:11pt;")
        self.stack.setCurrentWidget(self.lbl_empty)

    def _paint_status(self, counts=None) -> None:
        bits = []
        if self.blocks:
            if counts is not None:
                bits.append(f"찾은 모델 {sum(counts.values())}개")
            else:
                bits.append(f"모델 {promo.model_count(self.blocks)}개")
            at = (self.raw or {}).get("at", "")
            if at:
                bits.append(("시트에서 " if self._fresh_at else "저장본 · ") + at[5:].replace("-", "/") + " 읽음")
            bits.append("줄을 고르고 Ctrl+C 로 복사")
        if self._loading:
            bits.append("새로 읽는 중…")
        if self._err and self.blocks:
            bits.append("⚠ " + " ".join(self._err.split()))
        self.lbl_status.setText(" · ".join(bits))
        bad = bool(self._err and self.blocks)
        self.lbl_status.setStyleSheet(f"color:{theme.strong('red') if bad else theme.c('subtext')};")

    def _fill(self, found: list) -> None:
        tbl = self.tbl
        ncol = max([len(b["headers"]) for b, _r in found] + [1])
        rows = []
        for b, rs in found:
            rows.append(("title", b, None))
            if b["groups"]:
                rows.append(("groups", b, None))
            rows.append(("head", b, None))
            for r in rs:
                rows.append((r["kind"], b, r))
        self._rows = rows
        tbl.setUpdatesEnabled(False)
        try:
            tbl.clearSpans()
            tbl.setRowCount(0)
            tbl.setColumnCount(ncol)
            tbl.setRowCount(len(rows))
            base = tbl.font()
            bold = QFont(base)
            bold.setBold(True)
            big = QFont(bold)
            big.setPointSizeF((base.pointSizeF() if base.pointSizeF() > 0 else 10.5) + 1.5)
            c_title, bg_title = QColor(theme.strong("violet")), QColor(theme.strong_bg("violet"))
            c_sub, bg_head = QColor(theme.c("subtext")), QColor(theme.c("header_bg"))
            c_text = QColor(theme.c("text"))
            bg_sec = QColor(theme.strong_bg("blue"))
            bg_note = QColor(theme.strong_bg("orange"))
            tones = {"red": QColor(theme.strong("red")), "blue": QColor(theme.strong("blue"))}

            def put(i, k, text, font=None, fg=None, bg=None, align=None, tip=""):
                it = QTableWidgetItem(text)
                if font is not None:
                    it.setFont(font)
                if fg is not None:
                    it.setForeground(QBrush(fg))
                if bg is not None:
                    it.setBackground(QBrush(bg))
                if align is not None:
                    it.setTextAlignment(align)
                if tip:
                    it.setToolTip(tip)
                it.setData(ROLE, i)
                tbl.setItem(i, k, it)
                return it

            for i, (kind, b, r) in enumerate(rows):
                if kind == "title":
                    # 제목에 브랜드가 이미 있으면('BENZ · 벤츠 11월 …') 앞에 또 붙이지 않는다
                    named = (promo.brand_of(b["title"]) or ("",))[0] == b["key"]
                    put(i, 0, b["title"] if named else f"{b['brand']}   {b['title']}".strip(),
                        big, c_title, bg_title, Qt.AlignLeft | Qt.AlignVCenter)
                    tbl.setSpan(i, 0, 1, ncol)
                elif kind == "groups":
                    taken = set()
                    for k0, w, t in b["groups"]:
                        w = max(1, min(w, ncol - k0))
                        put(i, k0, t, bold, c_sub, bg_head, Qt.AlignCenter)
                        if w > 1:
                            tbl.setSpan(i, k0, 1, w)
                        taken.update(range(k0, k0 + w))
                    for k in range(ncol):
                        if k not in taken:
                            put(i, k, "", None, None, bg_head)
                elif kind == "head":
                    for k in range(ncol):
                        h = b["headers"][k] if k < len(b["headers"]) else ""
                        put(i, k, h, bold, c_text, bg_head, Qt.AlignCenter)
                elif kind == "section":
                    put(i, 0, r["cells"][0], bold, c_text, bg_sec, Qt.AlignLeft | Qt.AlignVCenter)
                    tbl.setSpan(i, 0, 1, ncol)
                elif kind == "note":
                    put(i, 0, r["cells"][0], None, c_text, bg_note, Qt.AlignLeft | Qt.AlignTop)
                    tbl.setSpan(i, 0, 1, ncol)
                else:
                    cells = r["cells"]
                    for k in range(ncol):
                        t = cells[k] if k < len(cells) else ""
                        tone = promo.tone_of(t) if k else ""
                        if k == 0:
                            put(i, k, t, bold, c_text, None, Qt.AlignLeft | Qt.AlignVCenter,
                                tip=f"시트 {r['row']}행")
                        elif promo.is_number(t):
                            put(i, k, t, None, c_text, None, Qt.AlignRight | Qt.AlignVCenter)
                        else:
                            put(i, k, t, bold if tone else None, tones.get(tone, c_text), None,
                                Qt.AlignCenter if len(t) <= 8 else Qt.AlignLeft | Qt.AlignVCenter)
            self._fit_columns(rows, ncol, bold)
            tbl.resizeRowsToContents()
            self._fit_spans()
        finally:
            tbl.setUpdatesEnabled(True)

    def _fit_columns(self, rows: list, ncol: int, bold: QFont) -> None:
        """열 폭을 글에 맞춘다(병합 줄은 빼고) — 모델 칸은 넉넉히, 나머지는 너무 넓지 않게."""
        fm, fb = QFontMetrics(self.tbl.font()), QFontMetrics(bold)
        want = [0] * ncol
        for kind, b, r in rows:
            if kind == "head":
                for k in range(min(ncol, len(b["headers"]))):
                    want[k] = max(want[k], fb.horizontalAdvance(b["headers"][k]))
            elif kind == "model":
                for k, t in enumerate(r["cells"][:ncol]):
                    longest = max((t or "").split("\n"), key=len) if t else ""
                    want[k] = max(want[k], (fb if k == 0 else fm).horizontalAdvance(longest))
        for k in range(ncol):
            lo, hi = (180, 380) if k == 0 else (90, 230)
            self.tbl.setColumnWidth(k, max(lo, min(hi, want[k] + 26)))

    def _fit_spans(self) -> None:
        """병합 줄(제목·구역·안내) 높이 — 표 폭 전체로 줄바꿈해 잰다."""
        if not self._rows:
            return
        total = sum(self.tbl.columnWidth(k) for k in range(self.tbl.columnCount()))
        total = max(total, self.tbl.viewport().width())
        fm = QFontMetrics(self.tbl.font())
        for i, (kind, _b, r) in enumerate(self._rows):
            if kind == "title":
                self.tbl.setRowHeight(i, fm.height() + 20)
            elif kind in ("section", "groups", "head"):
                self.tbl.setRowHeight(i, fm.height() + 12)
            elif kind == "note":
                rect = fm.boundingRect(0, 0, max(200, total - 24), 100000,
                                       int(Qt.TextWordWrap), r["cells"][0])
                self.tbl.setRowHeight(i, rect.height() + 18)

    # ------------------------------------------------------------ 복사
    def selected_text(self) -> str:
        seen, out = set(), []
        for it in self.tbl.selectedItems():
            i = it.row()
            if i in seen or i >= len(self._rows):
                continue
            seen.add(i)
        for i in sorted(seen):
            kind, b, r = self._rows[i]
            if kind == "model":
                out.append(promo.row_text(b, r))
            elif kind in ("section", "note"):
                out.append(r["cells"][0])
            elif kind == "title":
                out.append(f"[{b['brand']}] {b['title']}".strip())
        return "\n".join(x for x in out if x)

    def copy_selected(self) -> None:
        txt = self.selected_text()
        if not txt:
            return
        QApplication.clipboard().setText(txt)
        n = txt.count("\n") + 1
        self.lbl_status.setText(f"{n}줄 복사했습니다 — 카톡 창에서 Ctrl+V")
        self.lbl_status.setStyleSheet(f"color:{theme.strong('green')};")
        QTimer.singleShot(4000, lambda: self._paint_status())

    def _menu(self, pos) -> None:
        m = QMenu(self)
        a_copy = m.addAction("복사 (Ctrl+C)")
        a_copy.setEnabled(bool(self.tbl.selectedItems()))
        a_copy.triggered.connect(self.copy_selected)
        m.addSeparator()
        m.addAction("시트 열기").triggered.connect(self.open_sheet)
        m.addAction("새로고침").triggered.connect(lambda: self.reload(manual=True))
        m.exec(self.tbl.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------ 테마
    def apply_theme(self) -> None:
        self._style_brands()
        self._paint()

    def keyPressEvent(self, ev):                  # noqa: N802 — Qt 이름
        if ev.key() == Qt.Key_Escape and self.ed_find.text():
            self.ed_find.clear()
            self._paint()
            return
        super().keyPressEvent(ev)
