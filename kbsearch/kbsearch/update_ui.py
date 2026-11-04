"""업데이트 — 묻지 않고 새 판을 받아 바꾸고 다시 켠다(kb-v1.4.0, 지점장 요청).

지점장 요청: "업데이트 할건지 물어보고있는데, 묻지않고 업데이트가 있으면 자동으로".
예전엔 켤 때 업데이트 창([다시 시도]·[종료])이 떠서 묻는 것처럼 보였고, 받지 못하면 종료밖에
길이 없었다. 이제
  · 새 판이 있으면 **단추 없는** 작은 창에 받는 정도만 보이고, 다 받으면 바꿔 저절로 다시 켠다.
    트레이로 켤 때(PC 시작)와 켜 둔 채로 바꿀 때는 그 창도 없이 조용히.
  · 받지 못하면(인터넷 등) 세 번까지 다시 해 보고, 그래도 안 되면 **지금 판으로 켠다** —
    켜 둔 동안 3시간마다 다시 확인해 받는다(main_window).
  · 방금 바꾸려다 그대로 이 판으로 켜졌으면(교체 실패) 되풀이하지 않는다 — 몇 시간 뒤 다시.
  · 트레이에 있었으면 다시 켜질 때도 트레이로(updater.mark_resume).
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from . import config, crashlog, updater

RESTART = "restart"      # 바꾸는 배치를 띄웠다 — 앱을 곧바로 끝내야 한다
CONTINUE = "continue"    # 지금 판으로 계속(받지 못했거나 소스로 도는 중)

TRIES = 3                # 받기를 이만큼까지
RETRY_WAIT_SEC = 3
DOWNLOAD_LIMIT_SEC = 300


class UpdateSplash(QWidget):
    """단추 없는 작은 창 — '새 버전 받는 중 37%'."""

    def __init__(self, info: dict):
        super().__init__(None, Qt.SplashScreen | Qt.WindowStaysOnTopHint)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 20, 28, 20)
        self.lbl = QLabel(f"{config.APP_NAME} — 새 버전 v{info.get('version', '')} 으로 바꾸는 중…")
        v.addWidget(self.lbl)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setMinimumWidth(320)
        v.addWidget(self.bar)
        self.state = QLabel("다 받으면 저절로 다시 켜집니다.")
        v.addWidget(self.state)

    def progress(self, got: int, total: int) -> None:
        if total > 0:
            self.bar.setRange(0, 100)
            self.bar.setValue(min(100, int(got * 100 / total)))
        else:
            self.bar.setRange(0, 0)

    def say(self, text: str) -> None:
        self.state.setText(text)


def _pump(sec: float) -> None:
    app = QApplication.instance()
    end = time.monotonic() + sec
    while time.monotonic() < end:
        if app is not None:
            app.processEvents()
        time.sleep(0.05)


def _download(info: dict, splash) -> tuple[str, str]:
    """받기를 뒤에서 돌리고 화면은 계속 그린다 → (받은 파일, 오류)."""
    box: dict = {}

    def work():
        try:
            box["path"] = updater.download(info, lambda g, t: box.__setitem__("p", (g, t)))
        except Exception as e:
            box["err"] = str(e) or "받지 못했습니다."
    th = threading.Thread(target=work, daemon=True)
    th.start()
    app = QApplication.instance()
    started = time.monotonic()
    while th.is_alive() and time.monotonic() - started < DOWNLOAD_LIMIT_SEC:
        if splash is not None and "p" in box:
            splash.progress(*box["p"])
        if app is not None:
            app.processEvents()
        th.join(0.05)
    if th.is_alive():
        return "", "시간이 너무 오래 걸립니다."
    return box.get("path", ""), box.get("err", "")


def run(info: dict, show: bool = True, tray: bool = False) -> str:
    """새 판을 묻지 않고 받아 바꾼다 → RESTART(곧바로 끝내야 한다) | CONTINUE(지금 판으로 계속).

    show : 받는 정도를 작은 창으로 보여 줄지(트레이로 켤 때·켜 둔 채로 바꿀 때는 False)
    tray : 다시 켜질 때 트레이로 켤지
    """
    if not updater.is_frozen():
        return CONTINUE                       # 소스로 도는 중(개발) — 바꿀 exe 가 없다
    ver = str(info.get("version", ""))
    if updater.just_failed(ver):
        crashlog.note(f"업데이트 v{ver} — 방금 바꾸지 못해 이번에는 건너뜀(몇 시간 뒤 다시)")
        return CONTINUE
    splash = UpdateSplash(info) if show else None
    if splash is not None:
        splash.show()
        _pump(0.05)
    try:
        path, err = "", ""
        for i in range(TRIES):
            path, err = _download(info, splash)
            if path:
                break
            if splash is not None:
                splash.say(f"받지 못했습니다 — 다시 해 봅니다({i + 1}/{TRIES})")
            _pump(RETRY_WAIT_SEC)
        if not path:
            crashlog.note(f"업데이트 v{ver} 받기 실패 — 지금 판으로 계속: {err}")
            return CONTINUE
        if splash is not None:
            splash.progress(1, 1)
            splash.say("바꾸는 중입니다 — 잠시 뒤 새 버전이 저절로 켜집니다.")
            _pump(0.05)
        updater.note_attempt(ver)
        updater.mark_resume(tray)
        try:
            updater.apply_and_restart(path, ver)
        except Exception as e:
            crashlog.note(f"업데이트 v{ver} 바꾸기 실패 — 지금 판으로 계속: {e}")
            return CONTINUE
        return RESTART
    finally:
        if splash is not None:
            splash.close()
