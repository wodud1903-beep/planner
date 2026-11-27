"""카톡 매크로 — A1Auto(kmacro 1.1.2, 델파이)를 그대로 옮긴 엔진(v1.37).

지점장: "kmacro 의 카카오톡 매크로 기능을 일정관리기 파이썬 코드에 맞게 변환해서 추가 — 일정관리기·업무자료검색 앱에만.
기능은 절대 수정하지 말고 기존 기능을 전부." 서버 기능은 지점장 결정으로 바꿨다:
  ① 킬스위치(켤 때 서버 확인 · 안 맞으면 exe 지우기 · 연결 안 되면 종료) — 삭제
  ② 켤 때 비밀번호 인증 — 삭제(화면을 열면 바로 쓴다)
  ③ 자주 쓰는 문구(예전엔 서버에) → 내 구글 계정 앱 전용 공간의 kakao_macro.json(자동으로 불러온다)
  ④ jy.ini(발송 간격 — 처음 한 번 서버에서 받던 것) → 같은 kakao_macro.json. C:\\jy.ini 가 있으면 처음 한 번 그 값으로.
  A1Auto 자체 업데이트는 옮기지 않는다 — 이 프로그램의 자동 업데이트로 같이 바뀐다. 서버 주소는 하나도 없다.

이 파일은 Qt 를 모른다(화면은 kakao_macro_view). 바깥과 닿는 곳은 둘 — `ui`(화면)와 `env`(시계·지연·클립보드·
1ms 타이머·윈도 API). 검사는 둘 다 가짜를 끼워 A1Auto 동작을 한 줄씩 대조한다.
업무자료검색(kbsearch/kbsearch/kakao_macro.py)은 이 파일의 **그대로 사본**이다.

델파이 대응표(Unit1.pas)
  Button1Click           → MacroEngine.button1_click      (시작 — '실행할 모드를 선택해 주세요.' 등 그대로)
  Button2Click           → MacroEngine.button2_click      (중단 — 로그 · 클립보드 복원 · 색인 저장 · 풍선 알림)
  textTimer/PictureTimer/textpicTimer → MacroEngine._tick (1ms 타이머 — 한 사람씩)
  ExecuteSendStep        → MacroEngine.execute_send_step
  AttachImage            → MacroEngine.attach_image       (Ctrl+T → 파일 열기 창 확인 → Ctrl+V → Enter)
  FatalStop / SkipStep   → fatal_stop / skip_step         (연속 3회면 안전 중단)
  GotoNextRoom           → goto_next_room                 (ESC → 다음 지연 → ↓)
  AdvanceAndCheckEnd     → advance_and_check_end          (발송인원수에 닿으면 '정상 종료')
  IsKakaoForeground      → is_kakao_foreground            (KakaoPid 로 카톡이 띄운 대화상자도 인정)
  WaitForFileDialog      → wait_for_file_dialog           (60ms 마다)
  TryGetKakaoChatNameOnce / WaitForChatRoom → try_get_kakao_chat_name_once / wait_for_chat_room (80ms 마다)
  SafeSendKey / SafeSendKeyCombo / SendKey / SendKeyCombo → 같은 이름(소문자)
  SetClipboardSafe       → set_clipboard_safe             (5번까지 · 실패하면 100ms 뒤 다시)
  UpdateProgressUI / FormatRemain → update_progress_ui / format_remain
  Timer2Timer            → timer2_timer                   (1초마다 카드·속도)
  HotkeyTimer            → hotkey_timer                   (Insert = 시작 · Delete = 중지 — 1초마다)
  RestoreClipboard       → restore_clipboard
  FormClose              → form_close                     (클립보드 복원 · 색인 저장 · 로그 파일)
  BtnLoadLogClick        → load_log_text                  (화면이 파일을 고르고 이 함수가 글을 만든다)
  CustomerDB.pas         → CustomerStore                  (customers.tsv — 같은 모양)
  Unit2(환경설정)        → Prefs.set_intervals · DEFAULT_BUTTON
  Unit3(자주 쓰는 문구)  → Prefs.titles/get/put/delete     (서버 대신 구글 계정)

A1Auto 와 다른 것(앱 안에 들어오며 · 오발송을 막으려고)
  · 실행 중에 Insert 를 다시 누르면 무시한다 — A1Auto 는 꺼진 단추라도 Click 이 불려 숫자가 0 으로 돌아가고
    같은 단계가 겹쳐 돌 수 있었다(같은 사람에게 두 번 갈 수 있는 자리). 중단 뒤 그 사람 차례가 아직 끝나는
    중일 때 누른 Insert 도 같은 까닭으로 무시한다.
  · Delete(중단)는 A1Auto 처럼 '지금 사람까지 마치고' 멈춘다. 다만 클립보드 되돌리기는 그 사람 차례가 끝난
    뒤로 미룬다 — A1Auto 는 바로 되돌려, 남은 Ctrl+V 가 메시지 대신 원래 클립보드 글을 보낼 수 있었다.
  · 시작할 때 customers.tsv 를 다시 읽는다 — 일정관리기와 업무자료검색이 같은 파일을 쓰므로. 중단 · 닫기 때의
    저장은 못 쓴 것이 있을 때만(다른 프로그램이 그사이 쓴 기록을 옛 사본으로 덮지 않게).
  · 중복 발송 일수(dupdays)는 jy.ini 대신 환경설정 칸으로 고친다(기본 1, 0 = 검사 안 함).
  · 구글 로그인을 해야만 시작한다(지점장 — 예전 비밀번호 인증 대신). 화면(ui.start_block)이 까닭 글을 준다.
  · 발송 기록(customers.tsv) · 발송 로그는 내 구글 계정에도 올려 PC 사이에서 맞춘다(kakao_history — v1.38).
    로그 줄 · customers.tsv 모양은 그대로이고, customers.tsv 는 다 쓴 뒤 바꿔 끼운다.
  · 수정로그는 '도움말 내용 생략' 대신 실제 이력(CHANGE_LOG — 고칠 때마다 맨 위에 더한다).
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import kakao_win as kw

APP_TITLE = "A1Auto"
MAX_CONSECUTIVE_FAIL = 3
MSG_FOCUS_LOST = "카카오톡 창 이탈 — 오발송 방지"
MODES = ("텍스트", "이미지", "이미지+텍스트")
MODE_TEXT, MODE_IMAGE, MODE_IMAGE_TEXT = 0, 1, 2

# 지연(ms) — FormCreate 가 jy.ini 를 못 읽었을 때 쓰던 값 · 환경설정 [기본값] 단추가 넣는 값(서로 다르다 — 그대로)
DEFAULTS = {"textsleep": 700, "nextsleep": 700, "imagesleep": 1200, "dupdays": 1}
DEFAULT_BUTTON = {"textsleep": 800, "nextsleep": 800, "imagesleep": 1200}

TSV_HEADER = "이름\t최초발견\t최종발송\t발송횟수\t수신거부\t메모"
DT_FMT = "%Y-%m-%d %H:%M:%S"
REMOTE_NAME = "kakao_macro.json"
OLD_INI = r"C:\jy.ini"
SEED_AT = "1970-01-01T00:00:00.000000Z"   # jy.ini 에서 가져온 값의 시각 — 계정에 정해 둔 값이 있으면 그것이 이긴다
TITLE_MAX = 100                     # 문구 제목 길이(예전 문구 서버가 막던 것 그대로)

# ---------------------------------------------------------------------------
# 수정로그(도구 → 수정로그) — A1Auto 는 '도움말 내용 생략' 이었다. 지점장(v1.38): "수정로그는 앞으로 너가 직접
# 업데이트해서 올려줘." ⚠️ 매크로(kakao_*.py)를 고칠 때마다 맨 위에 한 절을 더한다(CLAUDE.md 규칙 · 검사가 모양을 본다).
# (날짜, 판, 직원이 읽을 말 — 다섯 줄 안쪽)
# ---------------------------------------------------------------------------
CHANGE_LOG = (
    ("2026-11-27", "일정관리기 v1.38.0 · 업무자료검색 v1.11.0", (
        "발송 기록(고객 목록)과 발송 로그를 내 구글 계정에 올려, 다른 PC 에서도 자동으로 불러옵니다",
        "도구 → 발송 기록: 발송 로그(기간 · 결과 · 검색)와 고객 목록(마지막 발송 · 횟수), 엑셀로 저장",
        "다른 PC 에서 보낸 사람도 '최근 N일 내 발송함' 으로 건너뜁니다",
        "예전 A1Auto 로그 파일(logs 폴더)도 처음 한 번 읽어 올립니다",
        "수정로그를 채웠습니다 — 앞으로 고칠 때마다 여기에 적습니다",
    )),
    ("2026-11-27", "일정관리기 v1.37.0 · 업무자료검색 v1.10.0", (
        "A1Auto 를 일정관리기 · 업무자료검색 안으로 옮겼습니다 — 화면 · 순서 · 기다리는 시간 · 로그 그대로",
        "서버 점검(킬스위치) · 비밀번호 인증을 없앴습니다 — 대신 구글 로그인을 해야 시작합니다",
        "자주 쓰는 문구 · 발송 간격을 내 구글 계정에 저장합니다(다른 PC · 두 프로그램이 같이 봅니다)",
        "환경설정에 '중복 발송 막기(일)' 칸과 [A1Auto 기록 가져오기] 단추",
        "오발송 막기: 도는 중 Insert 는 무시 · Delete 로 멈추면 클립보드는 그 사람 차례 뒤에 되돌림",
    )),
    ("2026-09-27", "A1Auto 1.1.2", (
        "이미지를 보낼 때 카톡 창 확인이 매크로를 멈추던 문제를 고쳤습니다",
    )),
    ("2026-09-21", "A1Auto 1.1", (
        "발송 안정성: 방 이름 확인 · 연속 3회 실패하면 안전 중단 · 최근 발송한 사람 건너뛰기",
        "진행률 · 남은 시간 · 트레이 알림 · 자동 업데이트",
    )),
    ("2026-08-03", "A1Auto 1.0", (
        "처음 — 카카오톡 친구 목록을 차례로 돌며 같은 메시지 · 이미지를 보냅니다",
    )),
)


def change_log_text() -> str:
    """수정로그를 글로(새것이 위)."""
    out = []
    for day, ver, lines in CHANGE_LOG:
        out.append(f"■ {day}  {ver}")
        out.extend(f"  · {t}" for t in lines)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# 둘 곳 — 일정관리기·업무자료검색이 함께 쓴다(중복 발송 막기가 두 프로그램 사이에서도 맞게)
# ---------------------------------------------------------------------------
def base_dir() -> Path:
    root = os.environ.get("APPDATA") or str(Path.home())
    d = Path(root) / "A1Auto"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def data_file() -> Path:
    return base_dir() / "data" / "customers.tsv"


def logs_dir() -> Path:
    d = base_dir() / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def prefs_file() -> Path:
    return base_dir() / REMOTE_NAME


# ---------------------------------------------------------------------------
# 델파이 흉내 — 숫자·반올림·시각
# ---------------------------------------------------------------------------
def str_to_int_def(s, default: int) -> int:
    """StrToIntDef — 앞 공백은 넘기고, 뒤에 다른 글자가 있으면 기본값."""
    m = re.fullmatch(r"\s*([+-]?\d+)", str(s if s is not None else ""))
    if not m:
        return default
    try:
        return int(m.group(1))
    except ValueError:
        return default


def _round_half_up(x: float, nd: int = 0) -> float:
    q = 10 ** nd
    return int(x * q + (0.5 if x >= 0 else -0.5)) / q


def format_remain(seconds: float) -> str:
    """FormatRemain — 60초 안쪽은 '42초', 넘으면 '4분 20초'."""
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{int(_round_half_up(seconds))}초"
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}분 {s}초"


def speed_text(success: int, elapsed_min: float) -> str:
    speed = success / elapsed_min if elapsed_min > 0 else 0.0
    return f"{_round_half_up(speed, 1):.1f}건/분"


def stamp(dt: datetime) -> str:
    return dt.strftime(DT_FMT)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# CustomerDB.pas — customers.tsv
# ---------------------------------------------------------------------------
class Customer:
    __slots__ = ("name", "first_seen", "last_sent", "send_count", "opt_out", "memo")

    def __init__(self, name: str = ""):
        self.name = name
        self.first_seen: datetime | None = None
        self.last_sent: datetime | None = None
        self.send_count = 0
        self.opt_out = False
        self.memo = ""


def _sanitize(s: str) -> str:
    return str(s or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _date_to_str(d) -> str:
    return stamp(d) if d else ""


_DT_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T]+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?")


def _str_to_date(s: str):
    """StrToDateTimeDef(…, 0, 'yyyy-MM-dd HH:mm:ss') — 시간이 없거나 한 자리여도 읽는다. 못 읽으면 None."""
    m = _DT_RE.fullmatch(str(s or "").strip())
    if not m:
        return None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h, mi, se = (int(m.group(i) or 0) for i in (4, 5, 6))
        return datetime(y, mo, d, h, mi, se)
    except ValueError:
        return None


def _lines(text: str) -> list:
    """TStringList 처럼 CR · LF · CRLF 로만 줄을 나눈다(마지막 빈 줄은 없다)."""
    parts = re.split(r"\r\n|\r|\n", text)
    if parts and parts[-1] == "":
        parts.pop()
    return parts


class CustomerStore:
    """A1Auto 고객 색인 — 카톡 채팅방 이름을 순회하며 저절로 모은다(TCustomerStore 그대로).

    파일: <A1Auto 폴더>\\data\\customers.tsv (탭 구분 · UTF-8 BOM · 엑셀에서 바로 열림).
    수신거부 · 메모는 A1Auto 처럼 읽고 쓰기만 하고 동작에는 쓰지 않는다."""

    def __init__(self, path=None, now=None):
        self.path = Path(path) if path else data_file()
        self._now = now or datetime.now
        self.items: dict = {}
        self.dirty = False                # 바꿨는데 아직 파일에 못 쓴 것이 있다(엑셀에 열려 있었다 등)

    @staticmethod
    def normalize_key(name: str) -> str:
        return str(name or "").strip()

    def count(self) -> int:
        return len(self.items)

    def load(self) -> None:
        self.items = {}
        self.dirty = False
        try:
            if not self.path.is_file():
                return
            text = self.path.read_bytes().decode("utf-8-sig", errors="replace")
        except OSError:
            return                        # 파일이 깨졌으면 빈 상태로 시작
        for i, line in enumerate(_lines(text)):
            if not line.strip():
                continue
            if i == 0 and line.startswith("이름\t"):
                continue                  # 머리줄
            parts = line.split("\t")
            cu = Customer(parts[0].strip())
            if not cu.name:
                continue
            if len(parts) > 1:
                cu.first_seen = _str_to_date(parts[1])
            if len(parts) > 2:
                cu.last_sent = _str_to_date(parts[2])
            if len(parts) > 3:
                cu.send_count = str_to_int_def(parts[3].strip(), 0)
            if len(parts) > 4:
                cu.opt_out = parts[4].strip() == "1"
            if len(parts) > 5:
                cu.memo = parts[5]
            self.items[self.normalize_key(cu.name)] = cu

    def save(self) -> None:
        lines = [TSV_HEADER]
        for cu in self.items.values():
            lines.append("\t".join([_sanitize(cu.name), _date_to_str(cu.first_seen), _date_to_str(cu.last_sent),
                                    str(cu.send_count), "1" if cu.opt_out else "0", _sanitize(cu.memo)]))
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # TStringList.SaveToFile(TEncoding.UTF8) — BOM + CRLF. 임시 파일에 다 쓴 뒤 바꿔 끼운다(v1.38) —
            # 쓰는 도중 꺼지거나 다른 프로그램(업무자료검색 ↔ 일정관리기)이 읽어도 반쯤 쓴 파일을 보지 않게.
            tmp.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8-sig"))
            os.replace(tmp, self.path)
            self.dirty = False
        except OSError:
            self.dirty = True             # 엑셀에 열려 있으면 못 쓴다 — 발송은 계속되어야 하므로 넘어간다
            try:
                tmp.unlink()
            except OSError:
                pass

    def flush(self) -> None:
        """중단 · 닫을 때의 CustomerStore.Save — 못 쓴 것이 있을 때만(다른 프로그램이 쓴 기록을 덮지 않게)."""
        if self.dirty:
            self.save()

    def sent_within_days(self, name: str, days: int) -> bool:
        if days <= 0:
            return False                  # 0 이하면 중복 검사 안 함
        cu = self.items.get(self.normalize_key(name))
        if cu is None or cu.last_sent is None:
            return False
        return (self._now() - cu.last_sent) < timedelta(days=days)

    def register_seen(self, name: str) -> None:
        key = self.normalize_key(name)
        if not key:
            return
        if key not in self.items:
            cu = Customer(key)
            cu.first_seen = self._now()
            self.items[key] = cu
            self.save()

    def register_sent(self, name: str) -> None:
        key = self.normalize_key(name)
        if not key:
            return
        cu = self.items.get(key)
        if cu is None:
            cu = Customer(key)
            cu.first_seen = self._now()
        cu.last_sent = self._now()
        cu.send_count += 1
        self.items[key] = cu
        self.save()                       # 도중에 꺼져도 이력이 남게 매번 저장

    def import_from(self, other_path) -> int:
        """[A1Auto 기록 가져오기] — 다른 customers.tsv 를 합친다(최근 발송 · 처음 본 날 · 횟수는 큰 쪽). 합친 수."""
        src = CustomerStore(other_path, now=self._now)
        src.load()
        n = 0
        for key, cu in src.items.items():
            mine = self.items.get(key)
            if mine is None:
                self.items[key] = cu
                n += 1
                continue
            if cu.first_seen and (mine.first_seen is None or cu.first_seen < mine.first_seen):
                mine.first_seen = cu.first_seen
            if cu.last_sent and (mine.last_sent is None or cu.last_sent > mine.last_sent):
                mine.last_sent = cu.last_sent
            mine.send_count = max(mine.send_count, cu.send_count)
            mine.opt_out = mine.opt_out or cu.opt_out
            if not mine.memo and cu.memo:
                mine.memo = cu.memo
            n += 1
        if n:
            self.save()
        return n


def import_a1auto(store: CustomerStore, folder) -> tuple:
    """[A1Auto 기록 가져오기] — A1Auto.exe 가 있던 폴더의 data\\customers.tsv 를 합치고 logs\\*.txt 를 옮겨 온다.

    → (합친 고객 수, 옮긴 로그 수). 폴더에 둘 다 없으면 (-1, 0)."""
    root = Path(folder)
    tsv = root / "data" / "customers.tsv"
    logs = root / "logs"
    if not tsv.is_file() and not logs.is_dir():
        return -1, 0
    n_cu = store.import_from(tsv) if tsv.is_file() else 0
    n_log = 0
    if logs.is_dir():
        dst = logs_dir()
        try:
            files = sorted(logs.glob("*.txt"))
        except OSError:
            files = []
        for p in files:
            q = dst / p.name
            if q.exists():
                continue                  # 같은 이름은 이미 옮겼다
            try:
                q.write_bytes(p.read_bytes())
                n_log += 1
            except OSError:
                continue
    return n_cu, n_log


# ---------------------------------------------------------------------------
# ③④ 발송 간격 · 자주 쓰는 문구 — 내 구글 계정(앱 전용 공간 kakao_macro.json) + 이 PC 사본
# ---------------------------------------------------------------------------
def clean_title(t: str) -> str:
    """문구 제목 — 앞뒤 공백 · 줄바꿈을 뺀다(예전 서버가 하던 그대로)."""
    return str(t or "").strip().replace("\r", "").replace("\n", "")


def read_old_ini(path: str = OLD_INI):
    """A1Auto 가 쓰던 C:\\jy.ini 의 [jy] 값(없으면 None). 처음 한 번 시작값으로만 쓴다."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16", errors="ignore")     # 윈도 ini 는 UTF-16 일 수도 있다
    else:
        text = raw.decode("utf-8-sig", errors="ignore")  # 값은 숫자뿐 — ANSI 여도 그대로 읽힌다
    sec, vals = "", {}
    for line in _lines(text):
        t = line.strip()
        if t.startswith("[") and t.endswith("]"):
            sec = t[1:-1].strip().lower()
            continue
        if sec == "jy" and "=" in t:
            k, v = t.split("=", 1)
            vals[k.strip().lower()] = v.strip()
    if not vals:
        return None
    return {k: str_to_int_def(vals.get(k, ""), DEFAULTS[k]) for k in DEFAULTS}


def _clean_settings(o) -> dict:
    o = o if isinstance(o, dict) else {}
    out = {k: str_to_int_def(o.get(k, ""), v) if not isinstance(o.get(k), int) else int(o[k])
           for k, v in DEFAULTS.items()}
    out["at"] = str(o.get("at") or "")
    return out


def _clean_data(o) -> dict:
    o = o if isinstance(o, dict) else {}
    phrases = {}
    for t, r in (o.get("phrases") or {}).items() if isinstance(o.get("phrases"), dict) else []:
        if isinstance(r, dict) and isinstance(r.get("text"), str) and str(t).strip():
            phrases[str(t)] = {"text": r["text"], "at": str(r.get("at") or "")}
    dead = {str(t): str(a) for t, a in (o.get("dead") or {}).items()} if isinstance(o.get("dead"), dict) else {}
    return {"v": 1, "account": str(o.get("account") or ""), "settings": _clean_settings(o.get("settings")),
            "phrases": phrases, "dead": dead}


def merge(local: dict, remote) -> tuple:
    """이 PC 것과 계정 것을 합친다(계산만) → (합친 것, 계정에 올려야 하나).

    발송 간격: 나중에 고친 쪽(at) — 같으면 계정 것(두 PC 가 모두 jy.ini 로 시작했으면 먼저 올린 PC 의 값).
    문구: 제목마다 나중에 고친 쪽 — 지운 것(dead)도 시각으로 겨룬다."""
    L = _clean_data(local)
    R = _clean_data(remote) if isinstance(remote, dict) else None
    if R is None:
        return L, bool(L["settings"]["at"] or L["phrases"] or L["dead"])
    out = {"v": 1, "account": L["account"], "settings": dict(L["settings"]), "phrases": {}, "dead": {}}
    if R["settings"]["at"] and R["settings"]["at"] >= L["settings"]["at"]:
        out["settings"] = dict(R["settings"])
    titles = []
    for src in (L["phrases"], R["phrases"], L["dead"], R["dead"]):
        for t in src:
            if t not in titles:
                titles.append(t)
    for t in titles:
        cands = []
        for side in (L, R):
            if t in side["phrases"]:
                cands.append((side["phrases"][t]["at"], "live", side["phrases"][t]))
            if t in side["dead"]:
                cands.append((side["dead"][t], "dead", None))
        # 나중 시각이 이긴다 · 같은 시각이면 살아 있는 쪽(내용이 지워지지 않게)
        cands.sort(key=lambda c: (c[0], c[1] == "live"))
        at, kind, rec = cands[-1]
        if kind == "live":
            out["phrases"][t] = dict(rec)
        else:
            out["dead"][t] = at
    push = (out["settings"] != R["settings"] or out["phrases"] != R["phrases"] or out["dead"] != R["dead"])
    return out, push


class Prefs:
    """발송 간격 · 자주 쓰는 문구. 바뀌면 이 PC 사본에 바로 쓰고, 계정과는 sync_once 로 맞춘다."""

    def __init__(self, path=None):
        self.path = Path(path) if path else prefs_file()
        self.lock = threading.RLock()
        self.data = _clean_data({})
        self.load_local()

    # ---- 이 PC 사본 ----
    def load_local(self) -> None:
        try:
            o = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            o = {}
        with self.lock:
            self.data = _clean_data(o)

    def save_local(self) -> None:
        # 쓰는 동안 잠가 둔다 — 뒤에서 계정과 맞추는 쪽과 화면에서 저장하는 쪽이 같은 임시 파일을 동시에 쓰지 않게.
        # 임시 파일 이름엔 프로세스 번호 — 일정관리기 · 업무자료검색이 같은 사본을 쓴다.
        with self.lock:
            text = json.dumps(self.data, ensure_ascii=False, indent=1)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
                tmp.write_text(text, encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError:
                pass

    # ---- 발송 간격(interval1·2·3 · DupDays) ----
    def value(self, key: str) -> int:
        with self.lock:
            return int(self.data["settings"].get(key, DEFAULTS[key]))

    @property
    def interval1(self) -> int:
        return self.value("textsleep")

    @property
    def interval2(self) -> int:
        return self.value("nextsleep")

    @property
    def interval3(self) -> int:
        return self.value("imagesleep")

    @property
    def dupdays(self) -> int:
        return self.value("dupdays")

    def set_intervals(self, textsleep: int, nextsleep: int, imagesleep: int, dupdays=None) -> None:
        with self.lock:
            st = self.data["settings"]
            st.update({"textsleep": int(textsleep), "nextsleep": int(nextsleep), "imagesleep": int(imagesleep)})
            if dupdays is not None:
                st["dupdays"] = int(dupdays)
            st["at"] = _utc_now()
        self.save_local()

    def seed_from_ini(self, path: str = OLD_INI) -> bool:
        """한 번도 정한 적 없으면 C:\\jy.ini 값으로 시작한다(있을 때만). 바꿨으면 True.

        시각은 맨 처음(SEED_AT) — 계정에 이미 값이 있으면(다른 PC 에서 정했으면) 계정 것이 이긴다."""
        with self.lock:
            if self.data["settings"]["at"]:
                return False
        got = read_old_ini(path)
        if not got:
            return False
        with self.lock:
            self.data["settings"] = dict(got, at=SEED_AT)
        self.save_local()
        return True

    # ---- 자주 쓰는 문구 ----
    def titles(self) -> list:
        with self.lock:
            return list(self.data["phrases"])

    def get(self, title: str) -> str:
        with self.lock:
            r = self.data["phrases"].get(title)
            return r["text"] if r else ""

    def put(self, title: str, text: str) -> None:
        with self.lock:
            self.data["phrases"][title] = {"text": str(text), "at": _utc_now()}
            self.data["dead"].pop(title, None)
        self.save_local()

    def delete(self, title: str) -> None:
        with self.lock:
            if title in self.data["phrases"]:
                self.data["phrases"].pop(title, None)
                self.data["dead"][title] = _utc_now()
        self.save_local()

    # ---- 계정과 맞추기 ----
    def sync_once(self, io, account: str) -> bool:
        """계정(앱 전용 공간)과 한 번 맞춘다 — 뒤에서 부른다. 이 PC 것이 바뀌었으면 True.

        io = {find(name) → id|None, read(id) → str, write(name, text)} (일정관리기 google_client ·
        업무자료검색 google_auth 를 감싼 것). 계정 것을 못 읽거나 깨졌으면 쓰지 않는다(남의 것을 덮지 않게)."""
        fid = io.find(REMOTE_NAME)
        remote = None
        if fid:
            txt = io.read(fid)
            try:
                remote = json.loads(txt) if (txt or "").strip() else {}
            except ValueError:
                return False
            if not isinstance(remote, dict):
                return False
        with self.lock:
            snap = copy.deepcopy(self.data)
        base = self._mine(snap, account)
        out, push = merge(base, remote)
        out["account"] = account or base["account"]
        if push:
            body = {k: v for k, v in out.items() if k != "account"}
            io.write(REMOTE_NAME, json.dumps(body, ensure_ascii=False, indent=1))
        with self.lock:
            before = self._shape(self.data)
            if self.data != snap:
                # 맞추는 사이에 이 PC 에서 고친 것 — 살린다(시각이 나중이라 이긴다 · 다음 맞추기에 올라간다)
                new, _p = merge(self._mine(self.data, account), out)
                new["account"] = out["account"]
                out = new
            self.data = out
            changed = self._shape(self.data) != before
        self.save_local()
        return changed

    @staticmethod
    def _shape(d: dict) -> str:
        """화면에 보이는 것(간격 · 문구)만 — 계정 표시가 붙은 것만으로는 '바뀜'이 아니다."""
        return json.dumps({"s": d["settings"], "p": d["phrases"]}, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _mine(d: dict, account: str) -> dict:
        """이 PC 사본 — 다른 계정 것이면 빈 것(새 계정에 올리지 않고 그 계정 것으로 바꾼다)."""
        if d["account"] and account and d["account"] != account:
            return _clean_data({})
        return copy.deepcopy(d)


# ---------------------------------------------------------------------------
# 엔진 — Unit1.pas TForm1 의 발송 흐름
# ---------------------------------------------------------------------------
class MacroEngine:
    """한 사람씩 — Enter 로 방 열기 → 방 확인 → 중복 검사 → 보내기 → ESC → ↓."""

    def __init__(self, ui, env, store: CustomerStore, prefs: Prefs):
        self.ui = ui
        self.env = env
        self.win = env.win
        self.store = store
        self.prefs = prefs
        # Unit1 의 전역 변수들
        self.c = 0
        self.ni = 0
        self.stop_reason = ""
        self.success_count = 0
        self.stop_count = 0
        self.skip_count = 0
        self.consecutive_fail = 0
        self.start_tick = 0
        self.kakao_pid = 0
        self.current_name = ""
        self.clip_backup = ""
        self.running = False              # = not button1.Enabled
        self._timer_mode = None           # 켜져 있는 발송 타이머(text / Picture / textpic)
        self._timer_gen = 0
        self._in_step = False             # 한 사람 차례(ExecuteSendStep)가 도는 중
        self._restore_after_step = False  # 차례 도중에 중단됨 — 차례가 끝나면 클립보드를 되돌린다
        self.store.load()                 # CustomerStore 함수 — 처음 부를 때 만들고 읽는다(FormCreate)

    # ---- 지연(interval1·2·3 · DupDays) ----
    @property
    def interval1(self) -> int:
        return self.prefs.interval1

    @property
    def interval2(self) -> int:
        return self.prefs.interval2

    @property
    def interval3(self) -> int:
        return self.prefs.interval3

    @property
    def dupdays(self) -> int:
        return self.prefs.dupdays

    # ---- 키·클립보드 ----
    def delay(self, ms: int) -> None:
        self.env.delay(ms)

    def set_clipboard_safe(self, s: str) -> None:
        for _ in range(5):
            try:
                self.env.clip_set(s)
                break
            except Exception:
                self.delay(100)

    def send_key(self, vk: int) -> None:
        sc = self.win.map_vk(vk)
        self.win.key_event(vk, sc, 0)
        self.delay(10)
        self.win.key_event(vk, sc, kw.KEYEVENTF_KEYUP)

    def send_key_combo(self, mod: int, key: int) -> None:
        ms, ks = self.win.map_vk(mod), self.win.map_vk(key)
        self.win.key_event(mod, ms, 0)
        self.win.key_event(key, ks, 0)
        self.delay(10)
        self.win.key_event(key, ks, kw.KEYEVENTF_KEYUP)
        self.win.key_event(mod, ms, kw.KEYEVENTF_KEYUP)

    def is_kakao_foreground(self) -> bool:
        """지금 키를 보내도 안전한가 — 카톡 본체 창 · 카톡이 띄운 팝업 · 카톡 프로세스의 대화상자(파일 열기)."""
        w = self.win
        h = w.foreground()
        if not h:
            return False
        if kw.is_kakao_window_class(w, h):
            self.kakao_pid = w.window_pid(h)
            return True
        if (kw.is_kakao_window_class(w, kw.get_top_level_window(w, h))
                or kw.is_kakao_window_class(w, w.ancestor(h, kw.GA_ROOTOWNER))
                or kw.is_kakao_window_class(w, w.ancestor(h, kw.GA_ROOT))):
            self.kakao_pid = w.window_pid(w.ancestor(h, kw.GA_ROOTOWNER))
            return True
        if self.kakao_pid and w.window_pid(h) == self.kakao_pid:
            return True
        return False

    def safe_send_key(self, vk: int) -> bool:
        ok = self.is_kakao_foreground()
        if ok:
            self.send_key(vk)
        return ok

    def safe_send_key_combo(self, mod: int, key: int) -> bool:
        ok = self.is_kakao_foreground()
        if ok:
            self.send_key_combo(mod, key)
        return ok

    def wait_for_file_dialog(self, timeout_ms: int) -> bool:
        deadline = self.env.tick() + timeout_ms
        while self.env.tick() < deadline:
            h = self.win.foreground()
            if kw.is_dialog_class(self.win, h) and (self.kakao_pid == 0 or self.win.window_pid(h) == self.kakao_pid):
                return True
            self.delay(60)
        return False

    def try_get_kakao_chat_name_once(self):
        """채팅방 제목을 한 번 읽어 본다 → 이름 또는 None."""
        w = self.win
        h = w.foreground()
        if not h:
            return None
        top = kw.get_top_level_window(w, h)
        if not top:
            return None
        cls = w.class_name(top)
        if not cls or not any(p in cls for p in kw.KAKAO_CLASS_PARTS):
            return None
        name = kw.clean_kakao_title(w.window_text(top))
        if name and name not in ("카카오톡", "KakaoTalk"):
            return name
        return None

    def wait_for_chat_room(self, timeout_ms: int):
        """→ ('ok', 이름) · ('timeout', '') · ('focus', '')"""
        deadline = self.env.tick() + timeout_ms
        while self.env.tick() < deadline:
            if not self.is_kakao_foreground():
                return "focus", ""
            name = self.try_get_kakao_chat_name_once()
            if name:
                return "ok", name
            self.delay(80)
        return "timeout", ""

    # ---- 시작 · 중단 ----
    def button1_click(self) -> None:
        if self.running or self._in_step:
            return                        # 실행 중 · 중단한 사람 차례가 아직 끝나는 중 — 겹쳐 돌지 않게
        # 구글 로그인을 해야만 시작한다(v1.37 지점장: "매크로를 작동하려면 로그인이 필수") — 화면이 까닭을 준다
        block = getattr(self.ui, "start_block", None)
        why = block() if block else ""
        if why:
            self.ui.show_message(why)
            return
        mode = self.ui.mode()
        if mode == -1:
            self.ui.show_message("실행할 모드를 선택해 주세요.")
            return
        if mode in (MODE_IMAGE, MODE_IMAGE_TEXT):
            path = self.ui.image_path()
            if path.strip() == "":
                self.ui.show_message("이미지를 불러와주세요. (이미지 경로가 비어있습니다.)")
                return
            if not os.path.isfile(path):
                self.ui.show_message("선택한 이미지 파일이 존재하지 않습니다. 경로를 다시 확인해주세요.")
                return
        # 사용자의 클립보드를 덮어쓰므로 백업해 두었다가 중단 때 되돌린다
        try:
            t = self.env.clip_get()
            self.clip_backup = t if t is not None else ""
        except Exception:
            self.clip_backup = ""
        self.store.load()                 # 다른 프로그램(업무자료검색 ↔ 일정관리기)이 그사이 보냈을 수 있다
        self.running = True
        self.ui.set_running(True)
        self.success_count = self.stop_count = self.skip_count = self.consecutive_fail = 0
        self.current_name = ""
        self.start_tick = self.env.tick()
        self.ui.set_stats("성공: 0", "중단: 0", "건너뜀: 0", "0.0건/분")
        self.c = str_to_int_def(self.ui.count_text(), 0)
        self.ni = 0
        self.update_progress_ui()
        if mode == MODE_TEXT:
            self.set_clipboard_safe(self.ui.message_text())
        self._arm(mode)

    def button2_click(self) -> None:
        reason = self.stop_reason or "사용자 중단"
        self.ui.add_log(f"❌ {stamp(self.env.now())} → 중단: {reason}", "stop")
        self.stop_count += 1
        self.ui.set_stats(None, f"중단: {self.stop_count}", None, None)
        self._timer_mode = None
        self._timer_gen += 1
        self.running = False
        self.ui.set_running(False)
        if self._in_step:
            self._restore_after_step = True   # 남은 Ctrl+V 가 원래 클립보드 글을 보내지 않게 — 차례가 끝나면
        else:
            self.restore_clipboard()
        self.store.flush()
        self.current_name = ""
        self.update_progress_ui()
        try:
            self.ui.tray_balloon(f"{APP_TITLE} — {reason}",
                                 f"성공 {self.success_count} · 건너뜀 {self.skip_count} · 처리 {self.ni}건")
        except Exception:
            pass
        self.stop_reason = ""

    def fatal_stop(self, reason: str) -> None:
        self.stop_reason = reason
        self.button2_click()

    def restore_clipboard(self) -> None:
        if self.clip_backup != "":
            self.set_clipboard_safe(self.clip_backup)
        self.clip_backup = ""

    # ---- 1ms 타이머(text / Picture / textpic) ----
    def _arm(self, mode: int) -> None:
        self._timer_mode = mode
        self._timer_gen += 1
        gen = self._timer_gen
        self.env.later(lambda: self._tick(gen))

    def _tick(self, gen: int) -> None:
        if gen != self._timer_gen or self._timer_mode is None:
            return
        mode = self._timer_mode
        self._timer_mode = None           # Timer.Enabled := False
        if not self.running:
            return
        self.execute_send_step(mode)
        if self.running:
            self._arm(mode)

    # ---- 한 사람 ----
    def execute_send_step(self, mode: int) -> None:
        self._in_step = True
        try:
            self._send_step(mode)
        finally:
            self._in_step = False
            if self._restore_after_step:
                self._restore_after_step = False
                if not self.running:
                    self.restore_clipboard()

    def _send_step(self, mode: int) -> None:
        # 1) 채팅방 열기
        if not self.safe_send_key(kw.VK_RETURN):
            self.fatal_stop(MSG_FOCUS_LOST)
            return
        self.delay(min(self.interval1, 300))
        # 2) 방이 실제로 열릴 때까지
        wr, name = self.wait_for_chat_room(max(2000, self.interval1 * 3))
        if wr == "focus":
            self.fatal_stop(MSG_FOCUS_LOST)
            return
        if wr == "timeout":
            self.skip_step("채팅방 이름 확인 실패")
            return
        self.current_name = name
        self.store.register_seen(name)
        self.update_progress_ui()
        # 3) 중복 검사(이름 정확히 같을 때)
        if self.store.sent_within_days(name, self.dupdays):
            self.skip_step(f"최근 {self.dupdays}일 내 발송함: {name}")
            return
        # 4) 보내기
        ok = True
        if mode == MODE_TEXT:
            self.set_clipboard_safe(self.ui.message_text())
            self.delay(50)
            ok = self.safe_send_key_combo(kw.VK_CONTROL, kw.VK_V) and self.safe_send_key(kw.VK_RETURN)
            if ok:
                self.delay(200)
        elif mode == MODE_IMAGE:
            r = self.attach_image()
            if r == "fatal":
                self.fatal_stop(MSG_FOCUS_LOST)
                return
            if r == "skip":
                self.skip_step("파일 열기 창이 열리지 않음")
                return
            self.delay(self.interval3)
        else:
            r = self.attach_image()
            if r == "fatal":
                self.fatal_stop(MSG_FOCUS_LOST)
                return
            if r == "skip":
                self.skip_step("파일 열기 창이 열리지 않음")
                return
            self.delay(self.interval3)
            self.set_clipboard_safe(self.ui.message_text())
            self.delay(150)
            ok = self.safe_send_key_combo(kw.VK_CONTROL, kw.VK_V)
            if ok:
                self.delay(200)
                ok = self.safe_send_key(kw.VK_RETURN)
            if ok:
                self.delay(500)
        if not ok:
            self.fatal_stop(MSG_FOCUS_LOST)
            return
        self.store.register_sent(name)
        self.ui.add_log(f"✅ {stamp(self.env.now())} → {name.strip()} 발송완료", "ok")
        self.success_count += 1
        self.consecutive_fail = 0
        # 5) 다음 방으로
        if not self.goto_next_room():
            return
        self.advance_and_check_end()

    def attach_image(self) -> str:
        """Ctrl+T → 파일 열기 창이 뜨는지 확인 → Ctrl+V(경로) → Enter. → 'ok' · 'skip' · 'fatal'"""
        self.set_clipboard_safe(self.ui.image_path())
        self.delay(100)
        if not self.safe_send_key_combo(kw.VK_CONTROL, kw.VK_T):
            return "fatal"
        if not self.wait_for_file_dialog(max(3000, self.interval3)):
            return "skip"
        self.delay(150)
        if not self.safe_send_key_combo(kw.VK_CONTROL, kw.VK_V):
            return "fatal"
        self.delay(200)
        if not self.safe_send_key(kw.VK_RETURN):
            return "fatal"
        return "ok"

    def skip_step(self, reason: str) -> None:
        self.ui.add_log(f"⏭ {stamp(self.env.now())} → 건너뜀: {reason}", "skip")
        self.skip_count += 1
        self.consecutive_fail += 1
        if self.consecutive_fail >= MAX_CONSECUTIVE_FAIL:
            self.fatal_stop(f"연속 {self.consecutive_fail}회 실패 — 안전 중단")
            return
        if not self.goto_next_room():
            return
        self.advance_and_check_end()

    def goto_next_room(self) -> bool:
        if not self.safe_send_key(kw.VK_ESCAPE):
            self.fatal_stop(MSG_FOCUS_LOST)
            return False
        self.delay(self.interval2)
        if not self.safe_send_key(kw.VK_DOWN):
            self.fatal_stop(MSG_FOCUS_LOST)
            return False
        return True

    def advance_and_check_end(self) -> None:
        self.ni += 1
        self.update_progress_ui()
        if self.c != 0 and self.ni >= self.c:
            self.fatal_stop("정상 종료")

    # ---- 진행 · 카드 · 단축키 ----
    def progress_text(self) -> str:
        if self.c > 0:
            s = f"{self.ni} / {self.c}"
        else:
            s = f"{self.ni}건 진행"
        if self.start_tick > 0 and self.ni > 0 and self.c > 0 and self.ni < self.c:
            elapsed = (self.env.tick() - self.start_tick) / 1000.0
            remain = elapsed / self.ni * (self.c - self.ni)
            s += " · 남은 약 " + format_remain(remain)
        if self.current_name:
            s += " · 현재: " + self.current_name
        return s

    def update_progress_ui(self) -> None:
        if self.c > 0:
            pct = min(1.0, self.ni / self.c)
        else:
            pct = 0.0
        s = self.progress_text()
        self.ui.set_progress(pct, s)
        self.ui.tray_hint(f"{APP_TITLE} · {s}")

    def timer2_timer(self) -> None:
        speed = None
        if self.start_tick > 0:
            speed = speed_text(self.success_count, (self.env.tick() - self.start_tick) / 60000.0)
        self.ui.set_stats(f"성공: {self.success_count}", f"중단: {self.stop_count}",
                          f"건너뜀: {self.skip_count}", speed)
        self.update_progress_ui()

    def hotkey_timer(self) -> None:
        if self.win.async_key(kw.VK_INSERT) != 0:
            self.button1_click()
        if self.win.async_key(kw.VK_DELETE) != 0:
            self.button2_click()

    # ---- 닫을 때 ----
    def form_close(self, log_text: str) -> str:
        """클립보드 복원 · 색인 저장 · 로그가 있으면 logs\\log_YYYY-MM-DD_HHNN.txt 로. 저장한 파일 경로(없으면 "")."""
        self.restore_clipboard()
        self.store.flush()
        if not (log_text or "").strip():
            return ""
        p = logs_dir() / f"log_{self.env.now().strftime('%Y-%m-%d_%H%M')}.txt"
        try:
            p.write_bytes(log_text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8-sig"))
        except OSError:
            return ""
        return str(p)


def load_log_text(path) -> str:
    """[로그 불러오기] — 저장한 로그 파일의 글(UTF-8 이 아니면 예전 A1Auto 의 ANSI(CP949)로 읽는다)."""
    raw = Path(path).read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")
