"""업데이트 — 묻지 않고 새 판을 받아 바꾸고 다시 켠다(kb-v1.4.0) · 진행 창(kb-v1.5.0).

지점장 요청: "업데이트 할건지 물어보고있는데, 묻지않고 업데이트가 있으면 자동으로"(kb-v1.4.0),
"업데이트 할 때에는 프로그레스바를 만들어서 업데이트 하고 있다는 내용을 시각적으로"(kb-v1.5.0).
  · 새 판이 있으면 **단추 없는** 진행 창(막대·%·MB)에 받는 정도를 보여 주고, 다 받으면 '바꾸는 중 —
    잠시 뒤 새 버전이 저절로 켜집니다' 를 보여 준 뒤 바꿔 저절로 다시 켠다.
    kb-v1.5.0 부터는 트레이로 켤 때(PC 시작)와 켜 둔 채로 바꿀 때도 보인다(예전엔 아무것도 안 보였다).
    켤 때(창이 뜨기 전)는 화면 가운데, 켜 둔 동안은 오른쪽 아래(corner).
  · 받지 못하면(인터넷 등) 세 번까지 다시 해 보고, 그래도 안 되면 까닭을 잠깐 보여 주고 **지금 판으로 켠다** —
    켜 둔 동안 3시간마다 다시 확인해 받는다(main_window).
  · 방금 바꾸려다 그대로 이 판으로 켜졌으면(교체 실패) 되풀이하지 않는다 — 몇 시간 뒤 다시.
  · 트레이에 있었으면 다시 켜질 때도 트레이로, 새 판은 '업데이트 완료' 를 잠깐(updater.mark_resume).
"""

from __future__ import annotations

import threading
import time

from PySide6.QtWidgets import QApplication

from . import crashlog, updater
from .update_progress import UpdateProgress

RESTART = "restart"      # 바꾸는 배치를 띄웠다 — 앱을 곧바로 끝내야 한다
CONTINUE = "continue"    # 지금 판으로 계속(받지 못했거나 소스로 도는 중)

TRIES = 3                # 받기를 이만큼까지
RETRY_WAIT_SEC = 3
DOWNLOAD_LIMIT_SEC = 300
APPLY_SHOW_SEC = 0.8     # '바꾸는 중' 을 읽을 틈
FAIL_SHOW_SEC = 2.5      # 못 받은 까닭을 읽을 틈


class UpdateSplash(UpdateProgress):
    """업데이트 진행 창(단추 없음). 예전 이름을 그대로 둔다(검사·옛 코드)."""

    def __init__(self, info: dict, corner: bool = False):
        super().__init__(str((info or {}).get("version", "")), corner=corner)

    def say(self, text: str) -> None:
        self.lbl_sub.setText(text)


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
    if splash is not None and "p" in box:
        splash.progress(*box["p"])           # 마지막 정도(100%)까지 그린다
    if th.is_alive():
        return "", "시간이 너무 오래 걸립니다."
    return box.get("path", ""), box.get("err", "")


def run(info: dict, show: bool = True, tray: bool = False, corner: bool = False) -> str:
    """새 판을 묻지 않고 받아 바꾼다 → RESTART(곧바로 끝내야 한다) | CONTINUE(지금 판으로 계속).

    show   : 진행 창을 보여 줄지(kb-v1.5.0 부터 부르는 곳은 늘 True — 검사만 False)
    tray   : 다시 켜질 때 트레이로 켤지
    corner : 진행 창을 오른쪽 아래에(켜 둔 동안) — 아니면 가운데(켤 때)
    """
    if not updater.is_frozen():
        return CONTINUE                       # 소스로 도는 중(개발) — 바꿀 exe 가 없다
    ver = str(info.get("version", ""))
    if updater.just_failed(ver):
        crashlog.note(f"업데이트 v{ver} — 방금 바꾸지 못해 이번에는 건너뜀(몇 시간 뒤 다시)")
        return CONTINUE
    splash = UpdateSplash(info, corner=corner) if show else None
    if splash is not None:
        splash.pop()
        _pump(0.05)
    try:
        path, err = "", ""
        for i in range(TRIES):
            if splash is not None and i:
                splash.downloading()
            path, err = _download(info, splash)
            if path:
                break
            if splash is not None:
                splash.say(f"받지 못했습니다 — 다시 해 봅니다({i + 1}/{TRIES})")
            _pump(RETRY_WAIT_SEC)
        if not path:
            crashlog.note(f"업데이트 v{ver} 받기 실패 — 지금 판으로 계속: {err}")
            if splash is not None:
                splash.failed(err)
                _pump(FAIL_SHOW_SEC)
            return CONTINUE
        if splash is not None:
            splash.applying()
            _pump(APPLY_SHOW_SEC)
        updater.note_attempt(ver)
        updater.mark_resume(tray, to=ver, notes=str(info.get("notes") or ""))
        try:
            updater.apply_and_restart(path, ver)
        except Exception as e:
            crashlog.note(f"업데이트 v{ver} 바꾸기 실패 — 지금 판으로 계속: {e}")
            if splash is not None:
                splash.failed(str(e))
                _pump(FAIL_SHOW_SEC)
            return CONTINUE
        return RESTART
    finally:
        if splash is not None:
            splash.close()
