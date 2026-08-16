"""세부 설정 대화상자 (델파이 uGSettings 이식).

- 구글 로그인/로그아웃 (여기로 이동)
- 계약 후 팔로업: 감지 키워드 / 개월수 / 알람 시각 / 알람 여부 / 메모 템플릿
- 휴대폰 알림: 구글 캘린더 리마인더 자동 설정
- 구글 시트 고객관리 연동
- 전역 단축키: 사용 / Ctrl·Alt·Shift / 키
"""

from __future__ import annotations

import threading
from datetime import time

from PySide6.QtCore import Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTextEdit, QTimeEdit,
    QVBoxLayout, QWidget,
)

from . import config, sheets
from .models import AppSettings


class SettingsDialog(QDialog):
    _sig_login = Signal(bool, str)

    def __init__(self, gauth, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("세부 설정")
        self.setMinimumWidth(560)
        self.gauth = gauth
        self.settings = settings
        self.tasks_changed = False  # 로그인/로그아웃 발생 여부

        # 항목이 늘어 작은 화면에서 잘리지 않도록 스크롤 안에 담는다
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        _inner = QWidget()
        # 이름 없는 QWidget 은 스타일시트 배경을 칠하지 않는다 → 이름 + 속성을 줘서
        # 테마 배경이 확실히 적용되게 한다(캘린더 창의 #calwin 과 동일한 패턴).
        _inner.setObjectName("dlgbody")
        _inner.setAttribute(Qt.WA_StyledBackground, True)
        root = QVBoxLayout(_inner)
        scroll.setWidget(_inner)
        outer.addWidget(scroll, 1)
        # 메인 프로그램과 같은 높이로 열어 스크롤을 최소화한다
        from PySide6.QtGui import QGuiApplication
        _avail = QGuiApplication.primaryScreen().availableGeometry()
        _h = min(920, _avail.height() - 60)
        if parent is not None:
            _h = max(_h, parent.height())
            _h = min(_h, _avail.height() - 40)
        self.resize(620, _h)

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

        # ---- 휴대폰 알림 (구글 캘린더 리마인더) ----
        gb_r = QGroupBox("휴대폰 알림 (구글 캘린더 알림 자동 설정)")
        rl = QFormLayout(gb_r)
        self.chk_reminder = QCheckBox("이 프로그램에서 등록하는 일정에 알림을 자동으로 넣기")
        rl.addRow(self.chk_reminder)
        self.sp_reminder = QSpinBox()
        self.sp_reminder.setRange(0, 1440)
        self.sp_reminder.setSuffix(" 분 전")
        rl.addRow("알림 시점", self.sp_reminder)
        rl.addRow(QLabel("PC 를 꺼 두어도 휴대폰 구글 캘린더 앱이 알림을 띄웁니다."))
        root.addWidget(gb_r)

        # ---- 구글 시트 고객관리 ----
        gb_s = QGroupBox("구글 시트 고객관리 연동")
        sl = QFormLayout(gb_s)
        self.chk_sheet = QCheckBox("사용")
        sl.addRow(self.chk_sheet)
        self.ed_sheet_id = QLineEdit()
        self.ed_sheet_id.setPlaceholderText("스프레드시트 주소를 붙여넣으세요")
        sl.addRow("시트 주소", self.ed_sheet_id)
        self.ed_sheet_name = QLineEdit()
        sl.addRow("시트(탭) 이름", self.ed_sheet_name)
        sl.addRow(QLabel(
            "함수 칸(순번·합계·고객센터번호·사고접수연락처·고객안내멘트)은\n"
            "프로그램이 건드리지 않고 시트 수식 그대로 둡니다.\n"
            "⚠ 처음 사용할 때 [Google 로그아웃] 후 다시 로그인해야 합니다(권한 추가)."))
        root.addWidget(gb_s)

        # ---- 화면 ----
        gb_v = QGroupBox("화면")
        vl = QHBoxLayout(gb_v)
        self.chk_dark = QCheckBox("다크 모드")
        vl.addWidget(self.chk_dark)
        vl.addStretch()
        root.addWidget(gb_v)

        # ---- 창 닫기 동작 ----
        gb_c = QGroupBox("창 닫기(X) 버튼")
        cl = QVBoxLayout(gb_c)
        self.cmb_close = QComboBox()
        self.cmb_close.addItem("트레이로 내리기 (알람 계속 동작)", True)
        self.cmb_close.addItem("완전 종료", False)
        cl.addWidget(self.cmb_close)
        cl.addWidget(QLabel("완전히 끄려면 트레이 아이콘 우클릭 → [종료] 를 쓰세요."))
        root.addWidget(gb_c)

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

        root.addStretch()

        # ---- 버튼 (스크롤 밖에 고정) ----
        brow = QHBoxLayout()
        brow.addStretch()
        btn_ok = QPushButton("확인")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        brow.addWidget(btn_ok)
        brow.addWidget(btn_cancel)
        outer.addLayout(brow)

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
        self.chk_reminder.setChecked(s.cal_reminder_on)
        self.sp_reminder.setValue(s.cal_reminder_min)
        self.chk_sheet.setChecked(s.sheet_on)
        self.ed_sheet_id.setText(s.sheet_id)
        self.ed_sheet_name.setText(s.sheet_name)
        self.chk_dark.setChecked(s.dark_mode)
        self.cmb_close.setCurrentIndex(0 if s.close_to_tray else 1)
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
        s.cal_reminder_on = self.chk_reminder.isChecked()
        s.cal_reminder_min = self.sp_reminder.value()
        s.sheet_on = self.chk_sheet.isChecked()
        # 주소를 통째로 붙여넣어도 ID 만 뽑아 저장 (사용자가 ID 를 찾을 필요 없게)
        s.sheet_id = sheets.parse_sheet_id(self.ed_sheet_id.text())
        s.sheet_name = self.ed_sheet_name.text().strip() or config.DEF_SHEET_NAME
        s.dark_mode = self.chk_dark.isChecked()
        s.close_to_tray = bool(self.cmb_close.currentData())
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
        if not ok:
            QMessageBox.warning(self, config.APP_NAME, "로그인 실패:\n" + err)
            return
        self.tasks_changed = True
        # 동의는 했는데 스프레드시트 권한이 실제로는 안 붙는 경우가 있어 바로 알려준다
        if not self.gauth.has_scope(config.SCOPE_SHEETS):
            QMessageBox.information(
                self, config.APP_NAME,
                "로그인은 되었지만 스프레드시트 권한이 부여되지 않았습니다.\n\n"
                "구글 클라우드 → API 및 서비스 → OAuth 동의 화면 → 데이터 액세스에\n"
                "아래 권한을 추가하고 저장한 뒤, 다시 로그인해 주세요.\n\n"
                + config.SCOPE_SHEETS)
