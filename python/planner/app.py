"""애플리케이션 진입점."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QLineEdit,
)

from . import config, crashlog, theme, updater
from .main_window import MainWindow

# 중복 실행 방지용 로컬 소켓 이름 (한 사용자당 하나만 실행)
_SINGLE_KEY = "Planner_SingleInstance_v1"


def _activate_existing():
    """이미 실행 중인 인스턴스가 있으면 그 창을 띄우도록 신호를 보낸다.

    반환: None(없음) / ""(있지만 대답이 없음 — v1.23.0 이전 판이거나 멈춘 것) /
    판 번호(v1.23.1 부터는 'ok 판번호' 로 대답한다).
    """
    sock = QLocalSocket()
    sock.connectToServer(_SINGLE_KEY)
    if not sock.waitForConnected(400):
        return None
    reply = ""
    try:
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(500)
        if sock.waitForReadyRead(1200):
            got = bytes(sock.readAll()).decode("ascii", "ignore").split()
            if len(got) >= 2 and got[0] == "ok":
                reply = got[1]
        sock.disconnectFromServer()
    except Exception:
        pass
    return reply


def _take_over_after_update(reply) -> bool:
    """방금 업데이트로 깔린 새 판인데 옛 판이 아직 남아 있으면 그것을 끝내고 이어서 뜬다.

    ⚠️ v1.22.1 → v1.23.0 에서 겪은 일: 옛 판이 끝나지 않고 남아 있어, 새 판이 떠도
       '이미 실행 중' 으로 보고 옛 창만 불러온 뒤 스스로 꺼졌다 → 업데이트를 눌러도
       계속 옛 판. 방금 깔린 것(업데이트 기록이 막 'replaced ok')이고, 남은 쪽이
       대답이 없거나(옛 판) 더 낮은 판이면 새 판이 이긴다. 그 밖(보통 두 번 실행)은
       예전처럼 있는 창만 띄우고 끝낸다.
    """
    if not updater.is_frozen() or not updater.just_installed():
        return False
    if reply and updater._parse_ver(reply) >= updater._parse_ver(config.APP_VERSION):
        return False
    return updater.kill_other_instances() > 0

# 화면 색은 theme.py 한 곳에서만 만든다(theme.apply_to_app).
# 예전에는 여기에도 스타일시트가 한 벌 있었는데, 쓰이지 않으면서 옛 색만
# 남아 있어 고칠 때 헷갈렸다. 지웠다.


class _NoWheelOnCombo(QObject):
    """드롭다운·숫자·날짜·시각 칸 위에서 휠을 굴려도 값이 바뀌지 않게 막는다.

    화면을 스크롤하려고 휠을 굴리다가 그 아래 있던 금융사·진행현황이나
    '알림 30분 전' 같은 숫자가 엉뚱하게 바뀌는 사고가 잦다.
    드롭다운은 목록이 펼쳐진 상태에서 휠로 고르는 게 정상이므로 그때만 통과시킨다.
    """

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Wheel:
            if isinstance(obj, QComboBox):
                if not obj.view().isVisible():
                    ev.ignore()
                    return True    # 값 변경을 막고, 스크롤은 부모가 처리하게 둔다
            elif isinstance(obj, QLineEdit) and isinstance(obj.parent(), QComboBox):
                # 검색형 드롭다운은 안쪽이 입력칸이라 휠이 여기로 먼저 온다
                ev.ignore()
                return True
            elif isinstance(obj, QAbstractSpinBox):
                # 숫자칸(QSpinBox) · 날짜칸(QDateEdit) · 시각칸(QTimeEdit)
                ev.ignore()
                return True
        return super().eventFilter(obj, ev)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)

    # ── 중복 실행 방지 ──
    # 이미 실행 중이면 기존 창만 띄우고 이 프로세스는 즉시 종료한다.
    # (단, 방금 업데이트로 깔렸는데 옛 판이 남아 있으면 그것을 끝내고 이어서 뜬다)
    reply = _activate_existing()
    if reply is not None:
        if not _take_over_after_update(reply):
            return 0
        import time as _time
        _time.sleep(1.5)                # 끝낸 옛 판이 소켓·파일을 놓을 때까지
    # 갑자기 꺼짐·멈춤을 기록한다(crashlog.py). 두 번째 실행은 위에서 이미 빠졌으므로
    # 여기는 '실제로 도는 하나' 만 지난다.
    prev_crash = crashlog.start()
    crashlog.install_qt_handler()       # Qt 의 오류 문구도 같은 기록에(창 프로그램이라 안 보인다)
    app.aboutToQuit.connect(crashlog.clean_exit)
    app.aboutToQuit.connect(crashlog.remove_qt_handler)   # 정리 중 문구가 파이썬을 안 부르게
    # 윈도를 끌 때(앱을 켜 둔 채)도 정상 종료다 — 다음에 '비정상' 이라고 묻지 않게
    app.commitDataRequest.connect(crashlog.clean_exit)

    # 이전 비정상 종료로 남은 소켓 잔재 정리 후 서버로 대기
    QLocalServer.removeServer(_SINGLE_KEY)
    _server = QLocalServer()
    _server.listen(_SINGLE_KEY)

    # 트레이로 최소화해도 프로세스가 살아있게
    app.setQuitOnLastWindowClosed(False)

    # 한글 친화 폰트 (없으면 시스템 기본).
    # 굵게 — 스타일시트가 닿지 않는 곳(기본 대화상자·툴팁·표 안 글자 등)도
    # 같은 두께로 나오게 여기서도 함께 지정한다.
    _font = QFont("Malgun Gothic", 10)
    _font.setWeight(QFont.DemiBold)
    app.setFont(_font)
    # 드롭다운은 휠로 바뀌지 않게 (앱 전체에 적용)
    _nowheel = _NoWheelOnCombo(app)
    app.installEventFilter(_nowheel)
    # 저장된 테마(라이트/다크) 선호를 미리 반영 (계정별 설정은 로그인 후 재적용)
    try:
        from .models import AppSettings
        _s = AppSettings.load(config.data_file("plan_cfg.json"))
        theme.set_theme(getattr(_s, 'theme', '') or ('dark' if _s.dark_mode else 'light'))
    except Exception:
        theme.set_theme(False)
    # 스타일시트 + 팔레트를 함께 적용 (팔레트를 안 주면 윈도우 시스템 다크 테마가
    # 스크롤 영역 등 스타일시트가 닿지 않는 표면으로 새어 나온다)
    theme.apply_to_app(app)

    win = MainWindow()
    crashlog.start_watchdog(app)        # 화면이 15초 넘게 멈추면 그때 상황을 적는다
    if prev_crash:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2500, lambda: crashlog.show_notice(win, prev_crash))

    # 두 번째 실행이 신호를 보내오면 기존 창을 앞으로 띄운다.
    # 'ok 판번호' 로 대답한다 — 업데이트로 막 깔린 새 판이 '남은 옛 판인가' 를 가린다.
    def _on_second_instance():
        conn = _server.nextPendingConnection()
        if conn is not None:
            try:
                conn.write(f"ok {config.APP_VERSION}\n".encode("ascii"))
                conn.flush()
                conn.waitForBytesWritten(300)
            except Exception:
                pass
            conn.disconnectFromServer()
        win.show_window()

    _server.newConnection.connect(_on_second_instance)

    # /tray 스위치로 실행되면 트레이로 시작
    if any(a.lstrip("/-").lower() == "tray" for a in sys.argv[1:]):
        win.hide()
    else:
        win.show()

    rc = app.exec()
    # ⚠️ 파이썬의 마무리 정리(위젯·Qt 객체를 하나씩 지우기)를 건너뛰고 바로 끝낸다.
    #    그 정리 중에 멈추거나 꺼지면 프로그램이 남아 업데이트·다음 실행을 막았다.
    #    저장할 것은 이미 다 저장했다(_shutdown · 바뀔 때마다 저장).
    crashlog.shutdown()
    try:
        sys.stdout and sys.stdout.flush()
        sys.stderr and sys.stderr.flush()
    except Exception:
        pass
    os._exit(rc)


if __name__ == "__main__":
    sys.exit(main())
