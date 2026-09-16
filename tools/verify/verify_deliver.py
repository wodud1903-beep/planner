"""출고일 자동 등록 — 무엇을 할지 정하는 규칙을 못 박는다.

통신 없이 돈다(plan 은 순수 계산). 화면도 필요 없다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import os
import tempfile
from datetime import date

os.environ.setdefault("APPDATA", tempfile.mkdtemp())

from planner import deliver_cal, followup  # noqa: E402

fails = []


def ok(name, cond, detail=""):
    print(("  OK  " if cond else "  ** FAIL **  ") + name
          + ("  " + str(detail) if detail else ""))
    if not cond:
        fails.append(name)


REC = {"cal_id": "primary", "event_id": "EV1",
       "date": "2026-08-20", "title": "홍길동 출고"}

print("\n[A] 제목 — 팔로업이 되읽을 수 있는 모양인가")
ok("사람 이름", followup.deliver_title("홍길동") == "홍길동 출고")
ok("고객 칸을 통째로 앞에 둔다",
   followup.deliver_title("박성일 / 박가네 백년약초") == "박성일 / 박가네 백년약초 출고")
ok("설정의 키워드를 쓴다", followup.deliver_title("홍길동", "인도") == "홍길동 인도")
# ⚠️ 이게 핵심이다. 제목을 만들어 두고 팔로업이 못 읽으면 [출고 1개월] 이 안 생긴다.
for c in ("홍길동", "박성일 / 박가네 백년약초", "(주) 마린패브론 / 이성우",
          "주식회사 드림데브 / 홍성현", "토탈광고기획 / 이중복"):
    ok(f"되읽힌다: {c}", followup.deliver_ok(c), followup.deliver_title(c))
ok("영문 상호는 만들지 않는다", not followup.deliver_ok("ACME Corp"))
ok("빈 고객은 만들지 않는다", not followup.deliver_ok(""))
ok("공백뿐인 고객도 만들지 않는다", not followup.deliver_ok("   "))

print("\n[B] 미정 → 날짜")
a = deliver_cal.plan("u1", "홍길동", "", "2026. 8. 20", None)
ok("새로 만든다", a[0] == "create" and a[1] == "홍길동 출고"
   and a[2] == date(2026, 8, 20), a)
ok("시트 서식이 아닌 날짜도 읽는다",
   deliver_cal.plan("u1", "홍길동", "", "2026-08-20", None)[0] == "create")

print("\n[C] 날짜 → 다른 날짜")
a = deliver_cal.plan("u1", "홍길동", "2026. 8. 20", "2026. 9. 1", REC)
# ⚠️ 지웠다 새로 만들면 일정 UID 가 바뀌어 팔로업 할일이 두 번 생긴다 → 옮긴다
ok("지우고 다시 만들지 않고 **옮긴다**", a[0] == "move", a[0])
ok("옮길 일정을 제대로 가리킨다", a[1] == "primary" and a[2] == "EV1", a[1:3])
ok("옮긴 날짜가 맞다", a[4] == date(2026, 9, 1), a[4])

print("\n[D] 날짜 → 미정")
a = deliver_cal.plan("u1", "홍길동", "2026. 8. 20", "", REC)
ok("지운다", a == ("delete", "primary", "EV1"), a)
ok("미정인데 기록도 없으면 할 것 없다",
   deliver_cal.plan("u1", "홍길동", "", "", None) == ("none",))
ok("'미정' 이라고 적혀 있어도 날짜가 아니다",
   deliver_cal.plan("u1", "홍길동", "2026. 8. 20", "미정", REC)[0] == "delete")

print("\n[E] 아무것도 안 해야 하는 때")
ok("날짜가 그대로면 안 건드린다",
   deliver_cal.plan("u1", "홍길동", "2026. 8. 20", "2026. 8. 20", REC) == ("none",))
# ⚠️ 여기가 '기존 고객은 건드리지 않는다' 를 지키는 자리다.
#    다른 칸만 고쳐 저장해도 출고일이 그대로면 일정을 만들면 안 된다.
ok("기록이 없어도 출고일이 안 바뀌었으면 안 만든다",
   deliver_cal.plan("u1", "홍길동", "2026. 8. 20", "2026. 8. 20", None) == ("none",))
ok("빈 값끼리도 안 만든다",
   deliver_cal.plan("u1", "홍길동", "", "", None) == ("none",))

print("\n[F] 이름이 바뀐 때")
a = deliver_cal.plan("u1", "홍길순", "2026. 8. 20", "2026. 8. 20", REC)
ok("날짜는 그대로, 제목만 고친다", a[0] == "rename" and a[3] == "홍길순 출고", a)
a = deliver_cal.plan("u1", "홍길순", "2026. 8. 20", "2026. 9. 1", REC)
ok("날짜와 이름이 같이 바뀌면 옮기면서 제목도 고친다",
   a[0] == "move" and a[3] == "홍길순 출고" and a[4] == date(2026, 9, 1), a)
a = deliver_cal.plan("u1", "ACME Corp", "2026. 8. 20", "2026. 8. 20", REC)
ok("되읽히지 않는 이름으로 바뀌면 남은 일정을 치운다",
   a == ("delete", "primary", "EV1"), a)

print("\n[G] 기록 파일")
d = deliver_cal.remember({}, "u1", "primary", "EV9", date(2026, 9, 1), "홍길동 출고")
ok("적어 둔다", d["u1"]["event_id"] == "EV9" and d["u1"]["date"] == "2026-09-01")
ok("지우면 사라진다", deliver_cal.forget(d, "u1") == {})
ok("없는 것을 지워도 탈나지 않는다", deliver_cal.forget({}, "없음") == {})
deliver_cal.save(d)
ok("저장한 것을 그대로 읽는다", deliver_cal.load() == d)
ok("파일이 깨져 있어도 빈 것으로 버틴다",
   (_pl.Path(os.environ["APPDATA"]).joinpath("Planner", deliver_cal.FILE)
    .write_text("{깨짐", encoding="utf-8"), deliver_cal.load())[1] == {})

print("\n[H] 기록이 반쯤 빈 경우 (옛 판이 남긴 것)")
for bad in ({}, {"cal_id": "primary"}, {"event_id": "EV1"},
            {"cal_id": "", "event_id": ""}):
    a = deliver_cal.plan("u1", "홍길동", "2026. 8. 20", "2026. 9. 1", bad)
    ok(f"못 쓰는 기록이면 새로 만든다: {bad}", a[0] == "create", a[0])

print("\n" + (f"{len(fails)}건 실패" if fails else "전부 통과"))
raise SystemExit(1 if fails else 0)
