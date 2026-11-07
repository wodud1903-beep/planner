"""설정 창 — 딱 세 가지만 둔다.

  1. PC 시작 시 자동 실행
  2. 화면 테마
  3. 업무자료 빠른검색 단축키
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout,
    QLabel, QVBoxLayout,
)

from . import config, searchcombo, startup, theme
from .settings import Settings

KEYS = [chr(c) for c in range(ord("A"), ord("Z") + 1)] + [f"F{i}" for i in range(1, 13)]


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, hot_ok: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{config.APP_NAME} 설정")
        self.setMinimumWidth(480)
        self.s = settings
        root = QVBoxLayout(self)

        # ---- 1. 시작 프로그램 ----
        gb_s = QGroupBox("시작 프로그램")
        sl = QVBoxLayout(gb_s)
        self.chk_startup = QCheckBox("PC 를 켤 때 자동으로 실행")
        self.chk_startup.setChecked(startup.is_on())
        sl.addWidget(self.chk_startup)
        lbl = QLabel("켜 두면 창 없이 트레이(작업 표시줄 오른쪽 아래)에서 조용히 시작합니다.\n"
                     "빠른검색 단축키를 바로 쓸 수 있습니다.")
        lbl.setStyleSheet(f"color:{theme.c('subtext')};")
        sl.addWidget(lbl)
        root.addWidget(gb_s)

        # ---- 2. 화면 테마 ----
        gb_t = QGroupBox("화면 테마")
        tl = QHBoxLayout(gb_t)
        self.cmb_theme = QComboBox()
        searchcombo.install(self.cmb_theme)
        for key in theme.THEME_ORDER:
            self.cmb_theme.addItem(theme.THEMES[key][0], key)
        i = self.cmb_theme.findData((settings.theme or "light").lower())
        self.cmb_theme.setCurrentIndex(i if i >= 0 else 0)
        tl.addWidget(self.cmb_theme, 1)
        root.addWidget(gb_t)

        # ---- 3. 빠른검색 단축키 ----
        gb_h = QGroupBox("업무자료 빠른검색 단축키")
        hl = QVBoxLayout(gb_h)
        self.chk_hot = QCheckBox("단축키 사용")
        self.chk_hot.setChecked(settings.kb_hot_on)
        hl.addWidget(self.chk_hot)
        krow = QHBoxLayout()
        self.chk_ctrl = QCheckBox("Ctrl")
        self.chk_alt = QCheckBox("Alt")
        self.chk_shift = QCheckBox("Shift")
        self.chk_ctrl.setChecked(settings.kb_hot_ctrl)
        self.chk_alt.setChecked(settings.kb_hot_alt)
        self.chk_shift.setChecked(settings.kb_hot_shift)
        self.cmb_key = QComboBox()
        searchcombo.install(self.cmb_key)
        self.cmb_key.addItems(KEYS)
        k = self.cmb_key.findText((settings.kb_hot_key or "F").upper())
        self.cmb_key.setCurrentIndex(k if k >= 0 else KEYS.index("F"))
        for w in (self.chk_ctrl, self.chk_alt, self.chk_shift):
            krow.addWidget(w)
        krow.addWidget(QLabel("+"))
        krow.addWidget(self.cmb_key)
        krow.addStretch()
        hl.addLayout(krow)
        tip = QLabel("다른 프로그램을 쓰는 중에도 이 키를 누르면 검색창이 바로 뜹니다.\n"
                     "Enter 를 누르면 본문이 복사되고 창이 닫힙니다.")
        tip.setStyleSheet(f"color:{theme.c('subtext')};")
        hl.addWidget(tip)
        self.lbl_hot = QLabel("")
        self.lbl_hot.setWordWrap(True)
        if settings.kb_hot_on and not hot_ok:
            self.lbl_hot.setText(
                f"⚠ 지금 {settings.hotkey_text()} 를 등록하지 못했습니다 — 다른 프로그램"
                "(일정관리기 등)이 같은 조합을 쓰고 있을 수 있습니다. 키를 바꿔 보세요.")
            self.lbl_hot.setStyleSheet(f"color:{theme.strong('orange')};")
        hl.addWidget(self.lbl_hot)
        root.addWidget(gb_h)

        self.chk_hot.toggled.connect(self._sync_enabled)
        self._sync_enabled()

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("확인")
        bb.button(QDialogButtonBox.Cancel).setText("취소")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _sync_enabled(self, *_a) -> None:
        on = self.chk_hot.isChecked()
        for w in (self.chk_ctrl, self.chk_alt, self.chk_shift, self.cmb_key):
            w.setEnabled(on)

    def _ok(self) -> None:
        if self.chk_hot.isChecked() and not (self.chk_ctrl.isChecked() or self.chk_alt.isChecked()
                                             or self.chk_shift.isChecked()):
            self.lbl_hot.setText("Ctrl·Alt·Shift 중 하나는 함께 눌러야 합니다"
                                 "(글자 하나만으로는 다른 프로그램에서 타자를 칠 수 없게 됩니다).")
            self.lbl_hot.setStyleSheet(f"color:{theme.strong('red')};")
            return
        s = self.s
        s.theme = self.cmb_theme.currentData() or "light"
        s.kb_hot_on = self.chk_hot.isChecked()
        s.kb_hot_ctrl = self.chk_ctrl.isChecked()
        s.kb_hot_alt = self.chk_alt.isChecked()
        s.kb_hot_shift = self.chk_shift.isChecked()
        s.kb_hot_key = self.cmb_key.currentText() or "F"
        want = self.chk_startup.isChecked()
        if want != startup.is_on():
            startup.set_on(want)
        self.accept()
