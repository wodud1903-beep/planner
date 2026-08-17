"""할일 / PC알람 / 구글 Tasks 편집 대화상자 (델파이 uPlanEdit 이식).

- 할일: 날짜 + 시각 + 알람 + 메모
- PC알람: 요일 + 시각 + 메모
- 구글 Tasks: 기한(없음 가능) + 알람시각 + 메모
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTextEdit, QTimeEdit, QVBoxLayout,
)

from . import config
from .models import PcAlarm, TaskAlarm, TodoItem


def _to_qtime(t: time) -> QTime:
    return QTime(t.hour, t.minute)


def _from_qtime(qt: QTime) -> time:
    return time(qt.hour(), qt.minute())


def _to_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _from_qdate(qd: QDate) -> date:
    return date(qd.year(), qd.month(), qd.day())


class EditDialog(QDialog):
    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(caption)
        self.setMinimumWidth(440)
        self._days: list[QCheckBox] = []

        root = QVBoxLayout(self)

        root.addWidget(QLabel("제목"))
        self.ed_title = QLineEdit()
        root.addWidget(self.ed_title)

        # 날짜 + 기한없음
        drow = QHBoxLayout()
        self.lbl_date = QLabel("날짜")
        drow.addWidget(self.lbl_date)
        self.dt_date = QDateEdit()
        self.dt_date.setCalendarPopup(True)
        self.dt_date.setDisplayFormat("yyyy-MM-dd")
        self.dt_date.setDate(QDate.currentDate())
        drow.addWidget(self.dt_date)
        self.chk_nodue = QCheckBox("기한 없음")
        self.chk_nodue.toggled.connect(lambda on: self.dt_date.setEnabled(not on))
        drow.addWidget(self.chk_nodue)
        drow.addStretch()
        root.addLayout(drow)

        # 시각 + 알람
        trow = QHBoxLayout()
        trow.addWidget(QLabel("시각"))
        self.dt_time = QTimeEdit()
        self.dt_time.setDisplayFormat("HH:mm")
        self.dt_time.setTime(QTime(9, 0))
        trow.addWidget(self.dt_time)
        self.chk_alarm = QCheckBox("이 시각에 알람")
        trow.addWidget(self.chk_alarm)
        trow.addStretch()
        root.addLayout(trow)

        # 요일 (PC알람)
        self.gb_days = QGroupBox("요일")
        g = QGridLayout(self.gb_days)
        for i in range(1, 8):
            cb = QCheckBox(config.DAY_NAMES[i])
            self._days.append(cb)
            g.addWidget(cb, 0, i - 1)
        drow2 = QHBoxLayout()
        btn_wd = QPushButton("평일")
        btn_wd.clicked.connect(lambda: self._set_days("23456"))
        btn_all = QPushButton("매일")
        btn_all.clicked.connect(lambda: self._set_days("1234567"))
        drow2.addWidget(btn_wd)
        drow2.addWidget(btn_all)
        drow2.addStretch()
        g.addLayout(drow2, 1, 0, 1, 7)
        root.addWidget(self.gb_days)

        self.lbl_ment = QLabel("메모")
        root.addWidget(self.lbl_ment)
        self.txt_ment = QTextEdit()
        self.txt_ment.setMinimumHeight(140)
        root.addWidget(self.txt_ment)

        brow = QHBoxLayout()
        brow.addStretch()
        btn_ok = QPushButton("확인")
        btn_ok.clicked.connect(self._on_ok)
        btn_ok.setDefault(True)
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        brow.addWidget(btn_ok)
        brow.addWidget(btn_cancel)
        root.addLayout(brow)

        self._days_required = False

    def _set_days(self, s: str):
        for i in range(1, 8):
            self._days[i - 1].setChecked(str(i) in s)

    def _get_days(self) -> str:
        return "".join(str(i) for i in range(1, 8) if self._days[i - 1].isChecked())

    def _on_ok(self):
        if not self.ed_title.text().strip():
            QMessageBox.information(self, config.APP_NAME, "제목을 입력하세요.")
            self.ed_title.setFocus()
            return
        if self._days_required and not self._get_days():
            QMessageBox.information(self, config.APP_NAME, "요일을 하나 이상 선택하세요.")
            return
        self.accept()

    # ---- 공개 진입점 ----
    @classmethod
    def edit_todo(cls, item: TodoItem, parent=None) -> bool:
        d = cls("할일 편집", parent)
        # 반복 할일이면 요일칸을 보여주고 설정을 유지한다.
        # (예전엔 요일칸을 숨긴 채 repeats/weekdays 를 무조건 지워서, 제목 오타만
        #  고쳐도 매주 울리던 알람이 조용히 멈췄다)
        d._days_required = bool(item.repeats)
        if item.repeats:
            d._set_days(item.weekdays)
        else:
            d.gb_days.hide()
        d.chk_nodue.hide()
        d.ed_title.setText(item.title)
        d.dt_date.setDate(_to_qdate(item.run_date or date.today()))
        d.dt_time.setTime(_to_qtime(item.run_time))
        d.chk_alarm.setChecked(item.alarm)
        d.txt_ment.setPlainText(item.ment)
        if d.exec() != QDialog.Accepted:
            return False
        item.title = d.ed_title.text().strip()
        item.run_date = _from_qdate(d.dt_date.date())
        item.run_time = _from_qtime(d.dt_time.time())
        item.has_time = True
        item.alarm = d.chk_alarm.isChecked()
        if item.repeats:
            item.weekdays = d._get_days()
        item.ment = d.txt_ment.toPlainText()
        return True

    @classmethod
    def edit_alarm(cls, item: PcAlarm, parent=None) -> bool:
        d = cls("PC 알람 편집", parent)
        d._days_required = True
        d.lbl_date.hide()
        d.dt_date.hide()
        d.chk_nodue.hide()
        d.chk_alarm.hide()
        d.lbl_ment.setText("팝업 메모")
        d.ed_title.setText(item.title)
        d.dt_time.setTime(_to_qtime(item.run_time))
        d._set_days(item.weekdays)
        d.txt_ment.setPlainText(item.ment)
        if d.exec() != QDialog.Accepted:
            return False
        item.title = d.ed_title.text().strip()
        item.run_time = _from_qtime(d.dt_time.time())
        item.weekdays = d._get_days()
        item.ment = d.txt_ment.toPlainText()
        return True

    @classmethod
    def edit_google_task(cls, caption: str, title: str, notes: str,
                         due: Optional[date], has_due: bool,
                         al: TaskAlarm, parent=None):
        """반환: (accepted, title, notes, due, has_due) — al 은 제자리 갱신."""
        d = cls(caption, parent)
        d._days_required = False
        d.gb_days.hide()
        d.chk_nodue.show()
        d.lbl_ment.setText("메모")
        d.ed_title.setText(title)
        d.chk_nodue.setChecked(not has_due)
        d.dt_date.setDate(_to_qdate(due if (has_due and due) else date.today()))
        d.dt_date.setEnabled(has_due)
        d.dt_time.setTime(_to_qtime(al.run_time))
        d.chk_alarm.setChecked(al.alarm)
        d.txt_ment.setPlainText(al.ment if al.ment.strip() else notes)
        if d.exec() != QDialog.Accepted:
            return False, title, notes, due, has_due
        new_title = d.ed_title.text().strip()
        new_notes = d.txt_ment.toPlainText()
        new_has_due = not d.chk_nodue.isChecked()
        new_due = _from_qdate(d.dt_date.date()) if new_has_due else None
        al.alarm = d.chk_alarm.isChecked()
        al.run_time = _from_qtime(d.dt_time.time())
        al.ment = new_notes
        return True, new_title, new_notes, new_due, new_has_due
