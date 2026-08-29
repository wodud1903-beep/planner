"""백업 / 복원 창.

앱은 하루 한 번 계정 폴더의 데이터 파일을 `backup/` 에 복사해 둔다.
지금까지는 그걸 되돌릴 화면이 없어서, 실수로 지운 할일이나 잘못 덮어쓴 설정을
탐색기에서 손으로 옮겨야 했다. 이 창이 그 일을 대신한다.

백업 파일 이름은 `20260820_134501_todos.json` 처럼 **시각 + 원래 이름** 이다.
그래서 시각별로 묶으면 그대로 '복원 시점' 이 된다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout,
)

from . import config, sync, theme

# 복원 직전에 남기는 자동 백업의 표시. 시각 뒤에 붙여 목록에서 구분한다.
BEFORE_MARK = "-복원전"


def backup_dir() -> Path:
    d = config.data_dir() / "backup"
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_backup(mark: str = "") -> str:
    """지금 상태를 백업하고 그 시각(stamp)을 돌려준다.

    담는 파일은 `sync._FILES` 하나만 본다 — 동기화 대상과 백업 대상이 어긋나면
    새 기능을 넣을 때마다 한쪽을 빠뜨리게 된다.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S") + (mark or "")
    d = backup_dir()
    src_dir = config.data_dir()
    for name in sync._FILES:
        src = src_dir / name
        if not src.exists():
            continue
        try:
            shutil.copyfile(src, d / f"{stamp}_{name}")
        except Exception:
            pass            # 한 파일이 실패해도 나머지는 남긴다
    return stamp


def _split(fname: str) -> tuple:
    """'20260820_134501_todos.json' → ('20260820_134501', 'todos.json').

    파일명을 앞에서 자르지 않고 **아는 이름으로 뒤에서** 맞춘다.
    시각 뒤에 표시(-복원전)가 붙어도 그대로 갈린다.
    """
    for name in sync._FILES:
        tail = "_" + name
        if fname.endswith(tail) and len(fname) > len(tail):
            return fname[: -len(tail)], name
    return "", ""


def list_points() -> list:
    """[(stamp, 표시문구, [(파일이름, 경로)])] — 최근 순."""
    groups: dict = {}
    for p in backup_dir().glob("*.json"):
        stamp, name = _split(p.name)
        if not stamp:
            continue
        groups.setdefault(stamp, []).append((name, p))
    out = []
    for stamp in sorted(groups, reverse=True):
        files = sorted(groups[stamp])
        out.append((stamp, _label(stamp, len(files)), files))
    return out


def _label(stamp: str, count: int) -> str:
    mark = ""
    base = stamp
    if base.endswith(BEFORE_MARK):
        base, mark = base[: -len(BEFORE_MARK)], "  · 복원 직전 자동 백업"
    try:
        t = datetime.strptime(base, "%Y%m%d_%H%M%S")
        when = t.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        when = base
    return f"{when}   (파일 {count}개){mark}"


def restore(files: list) -> tuple:
    """백업 파일들을 계정 폴더로 되돌린다. (성공 수, 실패한 이름들)"""
    dst_dir = config.data_dir()
    okc, bad = 0, []
    for name, path in files:
        try:
            data = Path(path).read_bytes()
            tmp = dst_dir / (name + ".tmp")
            with open(tmp, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dst_dir / name)
            okc += 1
        except Exception:
            bad.append(name)
    return okc, bad


class BackupDialog(QDialog):
    """복원 시점을 고르는 창."""

    def __init__(self, parent=None, on_restored=None):
        super().__init__(parent)
        self.setWindowTitle("백업 / 복원")
        self.resize(560, 480)
        self._on_restored = on_restored

        root = QVBoxLayout(self)

        self.lbl_head = QLabel(
            "데이터가 매일 자동으로 백업됩니다. 되돌릴 시점을 고르세요.")
        root.addWidget(self.lbl_head)

        self.lst = QListWidget()
        root.addWidget(self.lst, 1)

        self.lbl_warn = QLabel(
            "· 백업에 들어 있는 파일만 되돌립니다(그 뒤에 생긴 파일은 그대로 둡니다).\n"
            "· 복원 직전 상태도 자동으로 백업하므로 되돌리기를 다시 되돌릴 수 있습니다.\n"
            "⚠ 복원한 내용은 잠시 뒤 구글 드라이브로 올라가 다른 PC 에도 반영됩니다.")
        self.lbl_warn.setWordWrap(True)
        root.addWidget(self.lbl_warn)

        row = QHBoxLayout()
        self.btn_now = QPushButton("지금 백업")
        self.btn_now.clicked.connect(self._backup_now)
        self.btn_open = QPushButton("백업 폴더 열기")
        self.btn_open.clicked.connect(self._open_folder)
        self.btn_restore = QPushButton("이 시점으로 복원")
        self.btn_restore.clicked.connect(self._restore)
        self.btn_close = QPushButton("닫기")
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_now)
        row.addWidget(self.btn_open)
        row.addStretch()
        row.addWidget(self.btn_restore)
        row.addWidget(self.btn_close)
        root.addLayout(row)

        self._reload()
        self.apply_theme()

    # ------------------------------------------------------------ 목록
    def _reload(self):
        self._points = list_points()
        self.lst.clear()
        for _stamp, label, _files in self._points:
            self.lst.addItem(QListWidgetItem(label))
        has = bool(self._points)
        self.btn_restore.setEnabled(has)
        if has:
            self.lst.setCurrentRow(0)
        else:
            self.lst.addItem("아직 백업이 없습니다. [지금 백업] 을 눌러 하나 만들어 두세요.")

    def _sel(self):
        i = self.lst.currentRow()
        if not self._points or not (0 <= i < len(self._points)):
            return None
        return self._points[i]

    # ------------------------------------------------------------ 동작
    def _backup_now(self):
        try:
            make_backup()
        except Exception as e:
            QMessageBox.warning(self, config.APP_NAME, "백업 실패:\n" + str(e))
            return
        self._reload()
        self.lbl_head.setText("백업했습니다. 되돌릴 시점을 고르세요.")

    def _open_folder(self):
        d = str(backup_dir())
        try:
            if sys.platform == "win32":
                os.startfile(d)                      # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception:
            QMessageBox.information(self, config.APP_NAME, "백업 폴더:\n" + d)

    def _restore(self):
        got = self._sel()
        if not got:
            return
        _stamp, label, files = got
        names = "\n".join("  · " + n for n, _p in files)
        if QMessageBox.question(
                self, config.APP_NAME,
                f"{label}\n\n이 시점으로 되돌릴까요?\n\n되돌릴 파일:\n{names}\n\n"
                "지금 상태는 '복원 직전 자동 백업' 으로 남습니다."
        ) != QMessageBox.Yes:
            return

        try:
            make_backup(BEFORE_MARK)     # 되돌리기의 되돌리기
        except Exception:
            pass                          # 자동 백업 실패로 복원을 막지는 않는다

        okc, bad = restore(files)
        self._reload()
        if callable(self._on_restored):
            try:
                self._on_restored()
            except Exception:
                pass
        if bad:
            QMessageBox.warning(
                self, config.APP_NAME,
                f"{okc}개를 되돌렸습니다.\n되돌리지 못한 파일:\n"
                + "\n".join("  · " + b for b in bad))
        else:
            QMessageBox.information(
                self, config.APP_NAME,
                f"{okc}개 파일을 되돌렸습니다.\n화면에 바로 반영됩니다.")

    # ------------------------------------------------------------ 테마
    def apply_theme(self):
        self.lbl_warn.setStyleSheet(f"color:{theme.c('subtext')};")
