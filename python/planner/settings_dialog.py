"""세부 설정 대화상자 (델파이 uGSettings 이식).

- 구글 로그인/로그아웃 (여기로 이동)
- 계약 후 팔로업: 감지 키워드 / 개월수 / 알람 시각 / 알람 여부 / 메모 템플릿
- 전역 단축키: 사용 / Ctrl·Alt·Shift / 키
"""

from __future__ import annotations

import threading
from datetime import time

from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTextEdit, QTimeEdit, QVBoxLayout,
)

from . import config
from .models import AppSettings


class SettingsDialog(QDialog):
    _sig_login = Signal(bool, str)

    def __init__(self, gauth, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("세부 설정")
        self.setMinimumWidth(520)
        self.gauth = gauth
        self.settings = settings
        self.tasks_changed = False  # 로그인/로그아웃 발생 여부

        root = QVBoxLayout(self)

        # ---- 구글 연동 ----
        gb_g = QGroupBox("구글 연동")
        gl = QHBoxLayout(gb_g)
        self.lbl_gstatus = QLabel()
        self.btn_login = QPushButton()
        self.btn_login.clicked.connect(self._on_login_click)
        gl.addWidget(self.lbl_gstatus, 1)
        gl.addWidget(self.btn_login)
        root.addWidget(gb_g)

        # ---- 계약 후 팔로업 ----
        gb_f = QGroupBox("계약 후 팔로업 (내 할일 자동 등록)")
        fl = QFormLayout(gb_f)
        self.chk_follow = QCheckBox("사용")
        fl.addRow(self.chk_follow)
        self.ed_keyword = QLineEdit()
        fl.addRow("감지 키워드", self.ed_keyword)
        self.sp_months = QSpinBox()
        self.sp_months.setRange(1, 60)
        self.sp_months.setSuffix(" 개월 뒤")
        fl.addRow("팔로업 시점", self.sp_months)
        self.dt_ftime = QTimeEdit()
        self.dt_ftime.setDisplayFormat("HH:mm")
        fl.addRow("알람 시각", self.dt_ftime)
        self.chk_falarm = QCheckBox("알람도 울림 (끄면 목록에만 추가)")
        fl.addRow(self.chk_falarm)
        self.chk_follow_cal = QCheckBox("팔로업을 구글 캘린더에도 등록")
        fl.addRow(self.chk_follow_cal)
        self.txt_ment = QTextEdit()
        self.txt_ment.setMinimumHeight(120)
        fl.addRow("메모 템플릿\n(%s = 고객명)", self.txt_ment)
        root.addWidget(gb_f)

        # ---- 화면 ----
        gb_v = QGroupBox("화면")
        vl = QHBoxLayout(gb_v)
        self.chk_dark = QCheckBox("다크 모드")
        vl.addWidget(self.chk_dark)
        vl.addStretch()
        root.addWidget(gb_v)

        # ---- 전역 단축키 ----
        gb_h = QGroupBox("전역 단축키 (창 빠르게 열기)")
        hl = QVBoxLayout(gb_h)
        self.chk_hot = QCheckBox("사용")
        hl.addWidget(self.chk_hot)
        krow = QHBoxLayout()
        self.chk_ctrl = QCheckBox("Ctrl")
        self.chk_alt = QCheckBox("Alt")
        self.chk_shift = QCheckBox("Shift")
        self.cmb_key = QComboBox()
        self.cmb_key.addItems([chr(c) for c in range(ord("A"), ord("Z") + 1)]
                              + [f"F{i}" for i in range(1, 13)])
        krow.addWidget(self.chk_ctrl)
        krow.addWidget(self.chk_alt)
        krow.addWidget(self.chk_shift)
        krow.addWidget(QLabel("+"))
        krow.addWidget(self.cmb_key)
        krow.addStretch()
        hl.addLayout(krow)
        root.addWidget(gb_h)

        # ---- 버튼 ----
        brow = QHBoxLayout()
        brow.addStretch()
        btn_ok = QPushButton("확인")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        brow.addWidget(btn_ok)
        brow.addWidget(btn_cancel)
        root.addLayout(brow)

        self._sig_login.connect(self._on_login_done)
        self._load()
        self._update_gstatus()

    # ---- 값 로드/저장 ----
    def _load(self):
        s = self.settings
        self.chk_follow.setChecked(s.follow_on)
        self.ed_keyword.setText(s.follow_keyword)
        self.sp_months.setValue(s.follow_months)
        self.dt_ftime.setTime(QTime(s.follow_time.hour, s.follow_time.minute))
        self.chk_falarm.setChecked(s.follow_alarm)
        self.chk_follow_cal.setChecked(s.follow_to_calendar)
        self.txt_ment.setPlainText(s.follow_ment)
        self.chk_dark.setChecked(s.dark_mode)
        self.chk_hot.setChecked(s.hot_on)
        self.chk_ctrl.setChecked(s.hot_ctrl)
        self.chk_alt.setChecked(s.hot_alt)
        self.chk_shift.setChecked(s.hot_shift)
        idx = self.cmb_key.findText((s.hot_key or "A").upper())
        self.cmb_key.setCurrentIndex(idx if idx >= 0 else 0)

    def _on_ok(self):
        s = self.settings
        s.follow_on = self.chk_follow.isChecked()
        s.follow_keyword = self.ed_keyword.text().strip() or "출고"
        s.follow_months = self.sp_months.value()
        qt = self.dt_ftime.time()
        s.follow_time = time(qt.hour(), qt.minute())
        s.follow_alarm = self.chk_falarm.isChecked()
        s.follow_to_calendar = self.chk_follow_cal.isChecked()
        s.follow_ment = self.txt_ment.toPlainText()
        s.dark_mode = self.chk_dark.isChecked()
        s.hot_on = self.chk_hot.isChecked()
        s.hot_ctrl = self.chk_ctrl.isChecked()
        s.hot_alt = self.chk_alt.isChecked()
        s.hot_shift = self.chk_shift.isChecked()
        s.hot_key = self.cmb_key.currentText()
        self.accept()

    # ---- 구글 로그인 ----
    def _update_gstatus(self):
        if self.gauth.is_connected():
            self.lbl_gstatus.setText("구글: 연결됨")
            self.lbl_gstatus.setStyleSheet("color:green;")
            self.btn_login.setText("Google 로그아웃")
        else:
            self.lbl_gstatus.setText("구글: 로그인 필요")
            self.lbl_gstatus.setStyleSheet("color:#c00;")
            self.btn_login.setText("Google 로그인")

    def _on_login_click(self):
        if self.gauth.is_connected():
            if QMessageBox.question(self, config.APP_NAME, "구글 연결을 해제할까요?") == QMessageBox.Yes:
                self.gauth.disconnect()
                self.tasks_changed = True
                self._update_gstatus()
            return
        self.btn_login.setEnabled(False)
        self.btn_login.setText("로그인 중...")

        def worker():
            try:
                self.gauth.authorize()
                self._sig_login.emit(True, "")
            except Exception as e:
                self._sig_login.emit(False, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_login_done(self, ok: bool, err: str):
        self.btn_login.setEnabled(True)
        self._update_gstatus()
        if ok:
            self.tasks_changed = True
        else:
            QMessageBox.warning(self, config.APP_NAME, "로그인 실패:\n" + err)
