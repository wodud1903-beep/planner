"""세부 설정 대화상자 (델파이 uGSettings 이식).

- 구글 로그인/로그아웃 (여기로 이동)
- 계약 후 팔로업: 감지 키워드 / 개월수 / 알람 시각 / 알람 여부 / 메모 템플릿
- 휴대폰 알림: 구글 캘린더 리마인더 자동 설정
- 구글 시트 고객관리 연동
- 전역 단축키: 사용 / Ctrl·Alt·Shift / 키
"""

from __future__ import annotations

import json
import os

import threading
from datetime import time

from PySide6.QtCore import Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTabWidget, QTextEdit, QTimeEdit,
    QVBoxLayout, QWidget,
)

from . import config, drive_path, searchcombo, sheets, theme, weekly
from .models import AppSettings, otp_where, promo_where


TERMS_FILE = "terms_presets.json"


def _hline() -> QFrame:
    """설정 묶음 안을 가르는 얇은 선."""
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


def load_terms_presets() -> dict:
    """직접 적어 둔 금융사별 계약조건."""
    try:
        p = config.data_file(TERMS_FILE)
        if p.exists():
            o = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(o, dict):
                return {k: list(v) for k, v in o.items() if isinstance(v, list)}
    except Exception:
        pass
    return {}


def save_terms_presets(presets: dict) -> None:
    try:
        config.atomic_write(config.data_file(TERMS_FILE),
                            json.dumps(presets or {}, ensure_ascii=False, indent=2))
    except Exception:
        pass


class SettingsDialog(QDialog):
    _sig_login = Signal(bool, str)

    def __init__(self, gauth, settings: AppSettings, parent=None, account: str = "",
                 on_backup=None, on_sync=None, on_status=None, on_auth=None):
        super().__init__(parent)
        self.setWindowTitle("세부 설정")
        # 안내문이 여러 줄이라 좁으면 줄이 자꾸 접힌다 → 예전(560/620)보다 30% 넓게
        self.setMinimumWidth(728)
        self.gauth = gauth
        self.settings = settings
        # 백업/복원·동기화는 파일을 되돌린 뒤 화면까지 다시 그려야 해서 메인 창이 맡는다
        self._on_backup = on_backup
        self._on_sync = on_sync
        self._on_status = on_status
        # 이 창 안에서 로그인·로그아웃했나(v1.32.1) — 메인 창이 닫힌 뒤 계정 폴더를 다시 정한다
        self._on_auth = on_auth
        self.logged_in = False
        self.logged_out = False
        self.account = (account or "").strip().lower()
        self.tasks_changed = False  # 로그인/로그아웃 발생 여부

        # 항목이 늘어 한 줄로 길게 내려가던 것을 탭으로 나눈다(v1.32 — 찾기 쉽게). 탭마다 스크롤.
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self._pages = {}

        def P(title: str) -> QVBoxLayout:
            if title not in self._pages:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.NoFrame)
                inner = QWidget()
                # 이름 없는 QWidget 은 스타일시트 배경을 칠하지 않는다 → 이름 + 속성을 준다
                inner.setObjectName("dlgbody")
                inner.setAttribute(Qt.WA_StyledBackground, True)
                lay = QVBoxLayout(inner)
                scroll.setWidget(inner)
                self.tabs.addTab(scroll, title)
                self._pages[title] = lay
            return self._pages[title]

        for _t in ("계정·동기화", "고객관리", "알림·일정", "인증번호", "화면·기타"):
            P(_t)
        # 메인 프로그램과 같은 높이로 열어 스크롤을 최소화한다
        from PySide6.QtGui import QGuiApplication
        _avail = QGuiApplication.primaryScreen().availableGeometry()
        _h = min(920, _avail.height() - 60)
        if parent is not None:
            _h = max(_h, parent.height())
            _h = min(_h, _avail.height() - 40)
        # 화면이 좁으면 창이 화면 밖으로 나가지 않게 거기서 멈춘다
        self.resize(min(806, _avail.width() - 40), _h)

        # ---- 구글 연동 ----
        gb_g = QGroupBox("구글 연동")
        gl = QHBoxLayout(gb_g)
        self.lbl_gstatus = QLabel()
        self.btn_login = QPushButton()
        self.btn_login.clicked.connect(self._on_login_click)
        gl.addWidget(self.lbl_gstatus, 1)
        gl.addWidget(self.btn_login)
        P("계정·동기화").addWidget(gb_g)

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
        P("알림·일정").addWidget(gb_f)

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
        P("알림·일정").addWidget(gb_r)

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
        self.sp_expiry = QSpinBox()
        self.sp_expiry.setRange(0, 24)
        self.sp_expiry.setSuffix(" 개월 전부터 (0 = 끔)")
        sl.addRow("만기 재계약 알림", self.sp_expiry)
        sl.addRow(QLabel(
            "계약조건의 '60개월' 같은 표기로 만기일을 계산해\n"
            "시작 브리핑에 재계약 대상 고객을 알려줍니다."))

        self.chk_weekly = QCheckBox("시작 화면에 주간 요약도 함께 보기")
        sl.addRow("주간 요약", self.chk_weekly)
        sl.addRow(QLabel(
            "프로그램을 켜면 오늘 브리핑과 주간 요약이 한 화면에 같이 나옵니다.\n"
            f"이번 주 출고·계약, 아직 안 나온 건, {weekly.EXPIRY_MONTHS}개월 이내 "
            "만기 예정 고객을 한 장으로 보여 줍니다.\n"
            "체크를 풀면 브리핑만 나옵니다. [대시보드] 의 [주간 요약]\n"
            "버튼으로 언제든 다시 볼 수 있습니다."))

        # 수당율은 회사 공통 기준값이라 관리자 계정에서만 고칠 수 있다.
        btn_rates = QPushButton("차종별 수당율 관리…")
        btn_rates.clicked.connect(self._open_rates)
        can_edit = config.is_rates_admin(self.account)
        btn_rates.setEnabled(can_edit)
        if not can_edit:
            btn_rates.setToolTip("수당율은 관리자 계정에서만 고칠 수 있습니다.")
        sl.addRow("수당계산기", btn_rates)
        if not can_edit:
            sl.addRow(QLabel(
                "수당율은 관리자 계정에서만 수정할 수 있습니다.\n"
                "이 PC 는 관리자가 저장한 값을 받아서 계산에 씁니다."))

        # '자주 쓴 계약조건' 은 없앴다. 계약조건을 손으로만 적기로 하면서
        # 그 값을 쓰던 '골라서 넣기' 드롭다운이 사라져, 남겨 두면 아무 일도
        # 하지 않는 입력칸이 된다. (적어 두신 내용은 파일에 그대로 있다)
        sl.addRow(QLabel(
            "함수 칸(순번·합계·고객센터번호·사고접수연락처·고객안내멘트)은\n"
            "프로그램이 건드리지 않고 시트 수식 그대로 둡니다.\n"
            "⚠ 처음 사용할 때 [Google 로그아웃] 후 다시 로그인해야 합니다(권한 추가)."))
        P("고객관리").addWidget(gb_s)

        # ---- 고객정보(서류) ----
        gb_files = QGroupBox("고객정보 — 고객별 서류 보기")
        ffl = QFormLayout(gb_files)
        frow = QHBoxLayout()
        self.ed_files_dir = QLineEdit()
        self.ed_files_dir.setPlaceholderText(
            "비워 두면 이 PC 의 구글 드라이브에서 자동으로 찾습니다")
        frow.addWidget(self.ed_files_dir, 1)
        btn_files_dir = QPushButton("찾기")
        btn_files_dir.clicked.connect(self._pick_files_dir)
        frow.addWidget(btn_files_dir)
        ffl.addRow("서류 폴더", frow)
        ffl.addRow(QLabel(
            "비워 두면 이 PC 의 구글 드라이브에서 '내 드라이브 \\ 고객정보' 를\n"
            "스스로 찾아 씁니다. PC 마다 다시 고를 필요가 없습니다.\n"
            "(드라이브 문자가 G: 가 아니어도 찾습니다. 다른 곳에 두셨을 때만 직접 고르세요)"))
        # 지금 이 PC 에서 무엇이 잡히는지 바로 보여 준다 — 되는지 안 되는지를
        # 설정 창을 닫고 탭을 열어 봐야 아는 것이 제일 답답하다.
        self.lbl_files_auto = QLabel("")
        self.lbl_files_auto.setWordWrap(True)
        ffl.addRow("", self.lbl_files_auto)

        # 드라이브 데스크톱이 없거나 꺼져 있을 때 — 인터넷으로 같은 폴더를 읽는다.
        self.chk_files_drive = QCheckBox(
            "구글 드라이브가 없거나 꺼져 있으면 인터넷으로 같은 폴더를 읽기")
        # ⚠️ 이 칸을 만든 **뒤에** 상태를 적는다. 적는 쪽이 이 칸을 보기 때문이다.
        self.chk_files_drive.toggled.connect(lambda _on: self._refresh_files_auto())
        ffl.addRow("인터넷으로 읽기", self.chk_files_drive)
        self._refresh_files_auto()
        lbl_warn = QLabel(
            "이걸 켜 두면 드라이브 데스크톱이 깔려 있지 않은 PC 에서도 같은 서류가\n"
            "보입니다(PC 에 받아 둔 것이 없어 조금 느립니다).\n"
            "⚠ 로그인할 때 '드라이브 읽기' 권한을 함께 요청하므로, 처음 한 번은\n"
            "[Google 로그아웃] 후 다시 로그인해야 합니다.")
        lbl_warn.setStyleSheet(f"color:{theme.c('subtext')};")
        ffl.addRow(lbl_warn)
        # 드라이브가 안 깔려 있으면 여기서 바로 받게 해 준다
        self.lbl_install = QLabel("")
        self.lbl_install.setOpenExternalLinks(True)      # 눌러서 바로 받기
        self.lbl_install.setWordWrap(True)
        ffl.addRow("", self.lbl_install)
        self._refresh_install_hint()
        P("고객관리").addWidget(gb_files)

        # ---- 휴대폰 인증번호 받기(v1.31, otp.py) ----
        gb_o = QGroupBox("휴대폰 인증번호 받기 — 폰으로 온 인증번호를 PC 에 바로 띄우기")
        ofl = QFormLayout(gb_o)
        self.chk_otp = QCheckBox("사용 (몇 초마다 아래 시트를 보고, 새 인증번호가 오면 화면 오른쪽 아래에 띄웁니다)")
        ofl.addRow(self.chk_otp)
        self.ed_otp_sheet = QLineEdit()
        self.ed_otp_sheet.setPlaceholderText("비워 두면 지점 기본 인증문자 시트")
        ofl.addRow("인증문자 시트", self.ed_otp_sheet)
        self.ed_otp_tab = QLineEdit()
        self.ed_otp_tab.setPlaceholderText("비워 두면 첫 번째 탭")
        ofl.addRow("탭 이름", self.ed_otp_tab)
        self.chk_otp_copy = QCheckBox("오면 바로 클립보드에 복사 (로그인 칸에서 Ctrl+V)")
        ofl.addRow("", self.chk_otp_copy)
        self.chk_otp_clean = QCheckBox("2일 지난 문자는 인증문자 시트에서 저절로 지우기 (관리자 PC 가 지웁니다)")
        self.chk_otp_clean.setEnabled(config.is_rates_admin(self.account))
        ofl.addRow("", self.chk_otp_clean)
        lbl_o = QLabel("기본은 지점 공용 인증문자 시트입니다 — 다른 시트를 쓸 때만 주소를 바꾸세요(비우면 기본으로).\n"
                       "MacroDroid 가 받은 문자를 시트 맨 위 줄에 넣어 주면 됩니다(맨 위가 최신 · 첫 칸 날짜 · 본문).\n"
                       "켤 때 이미 있던 문자는 띄우지 않고, 뜬 번호는 10초 뒤 닫힙니다(마우스를 올리면 그대로).")
        lbl_o.setStyleSheet(f"color:{theme.c('subtext')};")
        ofl.addRow(lbl_o)
        P("인증번호").addWidget(gb_o)

        # ---- 오늘의 뉴스 ----
        gb_n = QGroupBox("오늘의 뉴스 (대시보드 [오늘의 뉴스] 단추)")
        nfl = QFormLayout(gb_n)
        self.ed_news = QLineEdit()
        self.ed_news.setPlaceholderText("구글 문서 주소 — https://docs.google.com/document/d/…")
        nfl.addRow("뉴스 문서", self.ed_news)
        lbl_n = QLabel("제미나이 등이 매일 새로 써 주는 구글 문서를 대시보드에서 바로 봅니다.\n"
                       "켤 때 미리 받아 두고, 누르면 새로 받아 바꿔 끼웁니다.")
        lbl_n.setStyleSheet(f"color:{theme.c('subtext')};")
        nfl.addRow(lbl_n)
        P("화면·기타").addWidget(gb_n)

        # ---- 수입차 프로모션(v1.34, promo.py) ----
        gb_p = QGroupBox("수입차 프로모션 (왼쪽 메뉴 '수입차 프로모션' 이 읽는 조건표)")
        pfl = QFormLayout(gb_p)
        self.ed_promo_sheet = QLineEdit()
        self.ed_promo_sheet.setPlaceholderText("비워 두면 회사 프로모션 시트")
        pfl.addRow("프로모션 시트", self.ed_promo_sheet)
        self.ed_promo_tab = QLineEdit()
        self.ed_promo_tab.setPlaceholderText("비워 두면 '수입차 프로모션' 탭")
        pfl.addRow("탭 이름", self.ed_promo_tab)
        lbl_p = QLabel("4행을 열 제목으로, B:G · I:N · P:U 처럼 빈 열로 나뉜 블록을 브랜드별 표로 읽습니다(읽기만).\n"
                       "이 시트를 '뷰어' 로 공유받은 계정이면 볼 수 있습니다.")
        lbl_p.setStyleSheet(f"color:{theme.c('subtext')};")
        pfl.addRow(lbl_p)
        P("화면·기타").addWidget(gb_p)

        # ---- 화면 ----
        gb_v = QGroupBox("화면")
        vl = QHBoxLayout(gb_v)
        trow = QHBoxLayout()
        trow.addWidget(QLabel("화면 테마"))
        self.cmb_theme = QComboBox()
        searchcombo.install(self.cmb_theme)
        for key in theme.THEME_ORDER:
            self.cmb_theme.addItem(theme.THEMES[key][0], key)
        trow.addWidget(self.cmb_theme, 1)
        vl.addLayout(trow)
        vl.addWidget(QLabel("고르면 [확인] 을 눌렀을 때 바로 바뀝니다."))
        vl.addStretch()
        P("화면·기타").addWidget(gb_v)

        # ---- 창 닫기 동작 ----
        gb_c = QGroupBox("창 닫기(X) 버튼")
        cl = QVBoxLayout(gb_c)
        self.cmb_close = QComboBox()
        searchcombo.install(self.cmb_close)
        self.cmb_close.addItem("트레이로 내리기 (알람 계속 동작)", True)
        self.cmb_close.addItem("완전 종료", False)
        cl.addWidget(self.cmb_close)
        cl.addWidget(QLabel("완전히 끄려면 트레이 아이콘 우클릭 → [종료] 를 쓰세요."))
        P("화면·기타").addWidget(gb_c)

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
        searchcombo.install(self.cmb_key)
        self.cmb_key.addItems([chr(c) for c in range(ord("A"), ord("Z") + 1)]
                              + [f"F{i}" for i in range(1, 13)])
        krow.addWidget(self.chk_ctrl)
        krow.addWidget(self.chk_alt)
        krow.addWidget(self.chk_shift)
        krow.addWidget(QLabel("+"))
        krow.addWidget(self.cmb_key)
        krow.addStretch()
        hl.addLayout(krow)

        # 업무자료 빠른검색 — 다른 프로그램을 쓰는 중에도 검색창을 띄운다
        hl.addWidget(_hline())
        self.chk_kbhot = QCheckBox("업무자료 빠른검색 단축키 사용")
        hl.addWidget(self.chk_kbhot)
        krow2 = QHBoxLayout()
        self.chk_kb_ctrl = QCheckBox("Ctrl")
        self.chk_kb_alt = QCheckBox("Alt")
        self.chk_kb_shift = QCheckBox("Shift")
        self.cmb_kb_key = QComboBox()
        searchcombo.install(self.cmb_kb_key)
        self.cmb_kb_key.addItems([chr(c) for c in range(ord("A"), ord("Z") + 1)]
                                 + [f"F{i}" for i in range(1, 13)])
        krow2.addWidget(self.chk_kb_ctrl)
        krow2.addWidget(self.chk_kb_alt)
        krow2.addWidget(self.chk_kb_shift)
        krow2.addWidget(QLabel("+"))
        krow2.addWidget(self.cmb_kb_key)
        krow2.addStretch()
        hl.addLayout(krow2)
        hl.addWidget(QLabel(
            "상담 통화 중에도 이 키를 누르면 전자약정·심사서류 검색창이 바로 뜹니다.\n"
            "다른 프로그램이 같은 조합을 이미 쓰고 있으면 등록되지 않습니다 — 그때는 키를 바꿔 보세요."))
        P("화면·기타").addWidget(gb_h)

        # ---- 백업 / 복원 ----
        gb_b = QGroupBox("백업 / 복원 · 다른 PC 동기화")
        bl = QVBoxLayout(gb_b)
        brow2 = QHBoxLayout()
        btn_backup = QPushButton("백업 / 복원 창 열기…")
        btn_backup.clicked.connect(self._open_backup)
        brow2.addWidget(btn_backup)
        btn_sync = QPushButton("지금 동기화")
        btn_sync.setToolTip("다른 PC 의 변경을 지금 받아오고, 이 PC 의 내용도 올립니다.")
        btn_sync.clicked.connect(self._sync_now)
        brow2.addWidget(btn_sync)
        brow2.addStretch()
        bl.addLayout(brow2)
        bl.addWidget(QLabel(
            "할일·알람·설정·고객메모·멘트문구를 하루 한 번 자동으로 백업합니다.\n"
            "잘못 지웠거나 덮어썼을 때 시점을 골라 되돌릴 수 있습니다.\n"
            "동기화는 켤 때와 10분마다 자동으로 돕니다. 급하면 [지금 동기화] 를 누르세요."))
        P("계정·동기화").addWidget(gb_b)

        # ---- 연결 상태 점검(v1.32) ----
        gb_st = QGroupBox("연결 상태 점검 · 오류 기록 보내기")
        stl = QVBoxLayout(gb_st)
        strow = QHBoxLayout()
        btn_status = QPushButton("연결 상태 점검 열기…")
        btn_status.clicked.connect(self._open_status)
        strow.addWidget(btn_status)
        strow.addStretch()
        stl.addLayout(strow)
        lbl_st = QLabel("로그인·권한·시트·동기화·인증번호·업데이트가 되는지 한 화면에서 봅니다.\n"
                        "안 되는 것이 있으면 [점검 결과·오류 기록 복사] 로 글을 복사해 보내 주세요.")
        lbl_st.setStyleSheet(f"color:{theme.c('subtext')};")
        stl.addWidget(lbl_st)
        P("계정·동기화").addWidget(gb_st)

        # ---- 고객관리 시트 자동 백업(v1.32) ----
        gb_bk = QGroupBox("고객관리 시트 자동 백업")
        bkl = QVBoxLayout(gb_bk)
        self.chk_sheet_backup = QCheckBox("주 1회 고객관리 시트의 사본을 내 구글 드라이브에 저절로 만들기 (최근 4개만 보관)")
        bkl.addWidget(self.chk_sheet_backup)
        lbl_bk = QLabel("사본 이름은 '[백업] 고객관리 날짜' 입니다. 시트를 잘못 지우거나 덮어썼을 때 꺼내 쓰세요.\n"
                        "이 계정이 고칠 수 있는 시트만 백업합니다('보기' 만 공유받은 시트는 하지 않습니다).")
        lbl_bk.setStyleSheet(f"color:{theme.c('subtext')};")
        bkl.addWidget(lbl_bk)
        P("고객관리").addWidget(gb_bk)

        # ---- 지점 공유 캘린더(v1.32) ----
        gb_bc = QGroupBox("지점 공유 캘린더 (출고·교육 등 지점 일정을 내 일정과 함께 보기)")
        bcl = QFormLayout(gb_bc)
        self.ed_branch_cal = QLineEdit()
        self.ed_branch_cal.setPlaceholderText("지점 공용 구글 캘린더의 ID(…@group.calendar.google.com) 또는 공유 주소")
        bcl.addRow("캘린더", self.ed_branch_cal)
        lbl_bc = QLabel("구글 캘린더 → 그 캘린더의 [설정 및 공유] → '캘린더 통합' 의 캘린더 ID 를 붙여넣으세요.\n"
                        "그 캘린더가 내 계정에 공유돼 있어야 보입니다. 일정 앞에 [지점] 이 붙습니다.")
        lbl_bc.setStyleSheet(f"color:{theme.c('subtext')};")
        bcl.addRow(lbl_bc)
        P("알림·일정").addWidget(gb_bc)

        for _lay in self._pages.values():
            _lay.addStretch()

        # ---- 버튼 (탭 밖에 고정) ----
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
        self.ed_files_dir.setText(s.files_dir)
        self._refresh_files_auto()       # 설정을 불러온 뒤의 상태로 다시 적는다
        self.chk_files_drive.setChecked(s.drive_api_on)
        self.sp_expiry.setValue(s.expiry_months)
        self.chk_weekly.setChecked(s.weekly_on)
        self.ed_news.setText(s.news_doc)
        self.chk_otp.setChecked(bool(getattr(s, "otp_on", False)))
        self.ed_otp_sheet.setText(getattr(s, "otp_sheet", "") or "")
        self.ed_otp_tab.setText(getattr(s, "otp_tab", "") or "")
        self.chk_otp_copy.setChecked(bool(getattr(s, "otp_copy", True)))
        self.chk_otp_clean.setChecked(bool(getattr(s, "otp_clean", True)))
        self.chk_sheet_backup.setChecked(bool(getattr(s, "sheet_backup", True)))
        self.ed_branch_cal.setText(getattr(s, "branch_cal", "") or "")
        self.ed_promo_sheet.setText(getattr(s, "promo_sheet", "") or "")
        self.ed_promo_tab.setText(getattr(s, "promo_tab", "") or "")
        cur = (s.theme or ("dark" if s.dark_mode else "light")).lower()
        i = self.cmb_theme.findData(cur)
        self.cmb_theme.setCurrentIndex(i if i >= 0 else 0)
        self.cmb_close.setCurrentIndex(0 if s.close_to_tray else 1)
        self.chk_hot.setChecked(s.hot_on)
        self.chk_ctrl.setChecked(s.hot_ctrl)
        self.chk_alt.setChecked(s.hot_alt)
        self.chk_shift.setChecked(s.hot_shift)
        idx = self.cmb_key.findText((s.hot_key or "A").upper())
        self.cmb_key.setCurrentIndex(idx if idx >= 0 else 0)
        self.chk_kbhot.setChecked(getattr(s, "kb_hot_on", True))
        self.chk_kb_ctrl.setChecked(getattr(s, "kb_hot_ctrl", True))
        self.chk_kb_alt.setChecked(getattr(s, "kb_hot_alt", True))
        self.chk_kb_shift.setChecked(getattr(s, "kb_hot_shift", False))
        idx = self.cmb_kb_key.findText((getattr(s, "kb_hot_key", "F") or "F").upper())
        self.cmb_kb_key.setCurrentIndex(idx if idx >= 0 else 0)

    def _sync_now(self):
        if callable(self._on_sync):
            self._on_sync()
        else:
            QMessageBox.information(self, config.APP_NAME,
                                    "메인 창에서만 동기화할 수 있습니다.")

    def _open_backup(self):
        if callable(self._on_backup):
            self._on_backup()
            return
        # 메인 창 없이 띄운 경우(테스트 등) — 되돌린 뒤 화면 갱신은 없다
        from .backup_dialog import BackupDialog
        BackupDialog(self).exec()

    def _open_status(self):
        if callable(self._on_status):
            self.reject()                    # 설정 창을 닫고 연다(점검 창에서 다시 설정을 열 수 있다)
            self._on_status()
        else:
            QMessageBox.information(self, config.APP_NAME, "메인 창에서만 열 수 있습니다.")

    def _open_rates(self):
        from .rate_dialog import RateDialog
        if not config.is_rates_admin(self.account):
            QMessageBox.information(
                self, config.APP_NAME,
                "수당율은 관리자 계정에서만 수정할 수 있습니다.\n"
                f"(현재 로그인: {self.account or '로그인 안 됨'})")
            return
        # 수당율은 고객관리 시트와 무관하게 **전용 스프레드시트 한 곳**만 쓴다.
        auth = self.gauth if self.gauth.is_connected() else None
        RateDialog(self, auth=auth, sheet_id=config.RATES_SHEET_ID).exec()

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
        s.files_dir = self.ed_files_dir.text().strip()
        s.drive_api_on = self.chk_files_drive.isChecked()
        s.expiry_months = self.sp_expiry.value()
        s.weekly_on = self.chk_weekly.isChecked()
        s.news_doc = self.ed_news.text().strip()
        s.otp_on = self.chk_otp.isChecked()
        # 주소를 붙여넣어도 ID 만 · 비우면 지점 기본 시트(탭이 비면 '시트1')
        s.otp_sheet, s.otp_tab = otp_where(sheets.parse_sheet_id(self.ed_otp_sheet.text()),
                                           self.ed_otp_tab.text())
        s.otp_copy = self.chk_otp_copy.isChecked()
        if self.chk_otp_clean.isEnabled():
            s.otp_clean = self.chk_otp_clean.isChecked()
        s.sheet_backup = self.chk_sheet_backup.isChecked()
        s.branch_cal = parse_calendar_id(self.ed_branch_cal.text())
        s.promo_sheet, s.promo_tab = promo_where(sheets.parse_sheet_id(self.ed_promo_sheet.text()),
                                                 self.ed_promo_tab.text())
        s.theme = self.cmb_theme.currentData() or "light"
        # 예전 항목도 함께 맞춰 둔다(다른 곳에서 dark_mode 를 보는 코드 대비)
        s.dark_mode = theme.THEMES.get(s.theme, (None, None, False))[2]
        s.close_to_tray = bool(self.cmb_close.currentData())
        s.hot_on = self.chk_hot.isChecked()
        s.hot_ctrl = self.chk_ctrl.isChecked()
        s.hot_alt = self.chk_alt.isChecked()
        s.hot_shift = self.chk_shift.isChecked()
        s.hot_key = self.cmb_key.currentText()
        s.kb_hot_on = self.chk_kbhot.isChecked()
        s.kb_hot_ctrl = self.chk_kb_ctrl.isChecked()
        s.kb_hot_alt = self.chk_kb_alt.isChecked()
        s.kb_hot_shift = self.chk_kb_shift.isChecked()
        s.kb_hot_key = self.cmb_kb_key.currentText()
        self.accept()

    def _pick_files_dir(self):
        start = (self.ed_files_dir.text().strip()
                 or drive_path.find() or os.path.expanduser("~"))
        d = QFileDialog.getExistingDirectory(self, "고객정보 폴더 선택", start)
        if d:
            self.ed_files_dir.setText(d)
            self._refresh_files_auto()

    def _refresh_install_hint(self):
        """드라이브 데스크톱이 없으면 받을 곳을 알려 준다(눌러서 바로 받기)."""
        st = drive_path.status()
        if st["installed"] and st["running"]:
            self.lbl_install.hide()
            return
        self.lbl_install.show()
        if st["installed"]:
            # 깔려 있는데 안 돌고 있다 — 받으라고 하면 엉뚱한 말이 된다
            self.lbl_install.setText(
                "구글 드라이브가 지금 실행되고 있지 않습니다. "
                "켜 두면 서류가 PC 에 있어 훨씬 빠릅니다.")
            self.lbl_install.setStyleSheet(f"color:{theme.strong('orange')};")
            return
        self.lbl_install.setText(
            f"{drive_path.INSTALL_HINT} "
            f"<a href='{drive_path.INSTALL_URL}'>구글 드라이브 내려받기</a>")
        self.lbl_install.setStyleSheet(f"color:{theme.strong('orange')};")

    def _refresh_files_auto(self):
        """이 PC 에서 서류 폴더가 잡히는지 지금 확인해 적는다."""
        drive_path.invalidate()          # 방금 폴더 이름을 고쳤을 수 있다
        manual = self.ed_files_dir.text().strip()
        if manual:
            ok = os.path.isdir(manual)
            self.lbl_files_auto.setText(
                ("직접 지정한 폴더를 씁니다." if ok else
                 "⚠ 지정한 폴더가 이 PC 에는 없습니다. 비워 두면 자동으로 찾습니다."))
            self.lbl_files_auto.setStyleSheet(
                f"color:{theme.c('subtext') if ok else theme.strong('red')};")
            return
        found, why = drive_path.detect()
        if found:
            self.lbl_files_auto.setText("✔ 자동으로 찾았습니다 — " + found)
            self.lbl_files_auto.setStyleSheet(f"color:{theme.c('status_ok')};")
            return
        # 설치 안내는 바로 아래 줄(눌러서 받는 곳)이 맡는다 → 여기선 뺀다
        why = why.replace(drive_path.INSTALL_HINT + "\n", "")
        text = "⚠ " + why.replace("\n", "  ")
        if self.chk_files_drive.isChecked():
            # 폴더가 PC 에 없어도 인터넷으로 읽으면 화면은 똑같이 나온다.
            # 그 사실을 안 적으면 '안 되는 줄' 알고 헛손질하게 된다.
            text += "\n(지금은 인터넷으로 읽습니다 — 폴더를 만들어 두면 더 빠릅니다)"
        self.lbl_files_auto.setText(text)
        self.lbl_files_auto.setStyleSheet(f"color:{theme.strong('red')};")

    # ---- 구글 로그인 ----
    def _update_gstatus(self):
        if self.gauth.is_connected():
            self.lbl_gstatus.setText("구글: 연결됨")
            self.lbl_gstatus.setStyleSheet(f"color:{theme.c('status_ok')};")
            self.btn_login.setText("Google 로그아웃")
        else:
            self.lbl_gstatus.setText("구글: 로그인 필요")
            self.lbl_gstatus.setStyleSheet(f"color:{theme.c('status_bad')};")
            self.btn_login.setText("Google 로그인")

    def _on_login_click(self):
        if self.gauth.is_connected():
            if QMessageBox.question(self, config.APP_NAME, "구글 연결을 해제할까요?") == QMessageBox.Yes:
                self.gauth.disconnect()
                self.tasks_changed = True
                self.logged_out = True
                if callable(self._on_auth):
                    self._on_auth()          # 지금 계정 폴더로는 더 동기화하지 않게(바로)
                self._update_gstatus()
            return
        self.btn_login.setEnabled(False)
        self.btn_login.setText("로그인 중...")

        # '드라이브에서 직접 조회' 를 켜 두었으면 그 권한도 같이 요청한다.
        # 기본 권한에 넣지 않는 이유는 config.SCOPE_DRIVE_READ 설명 참고.
        extra = ([config.SCOPE_DRIVE_READ]
                 if self.chk_files_drive.isChecked() else [])

        def worker():
            try:
                self.gauth.authorize(extra_scopes=extra)
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
        self.logged_in = True
        if callable(self._on_auth):
            self._on_auth()                  # 다른 계정일 수 있다 — 확인하기 전엔 동기화하지 않게(바로)
        # 동의 화면에서 뺀 항목이 있으면 바로 알린다(v1.31.3) — 구글은 항목마다 체크를 받는다.
        # 예전엔 스프레드시트만 봤고, 안내도 개발자용(클라우드 콘솔)이라 직원은 무엇을 할지 몰랐다.
        miss = self.gauth.missing_scopes()
        if miss:
            QMessageBox.warning(
                self, config.APP_NAME,
                "구글 로그인은 됐지만, 동의 화면에서 빠진 항목이 있어 아래 기능이 동작하지 않습니다.\n\n· "
                + "\n· ".join(config.SCOPE_LABELS[m] for m in miss)
                + "\n\n[Google 로그아웃] 후 다시 로그인하면서,\n"
                  "동의 화면의 '모두 선택' 에 체크하고 [계속] 을 눌러 주세요.")


def parse_calendar_id(text: str) -> str:
    """캘린더 ID — 공유 주소(…?cid=… · …/calendar/embed?src=…)를 붙여넣어도 ID 만 뽑는다(v1.32)."""
    import base64
    import re
    import urllib.parse
    t = (text or "").strip()
    if not t:
        return ""
    m = re.search(r"[?&]src=([^&#]+)", t)
    if m:
        return urllib.parse.unquote(m.group(1)).strip()
    m = re.search(r"[?&]cid=([^&#]+)", t)
    if m:
        raw = urllib.parse.unquote(m.group(1)).strip()
        if "@" in raw:
            return raw
        try:
            dec = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
            if "@" in dec:
                return dec.strip()
        except Exception:
            pass
        return raw
    return t
