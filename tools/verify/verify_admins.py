"""업무자료 관리자 · 수당율 관리자 — 따로 둔다(v1.28.3).

지점장: "qkrwlsgh7303@gmail.com 이 아이디를 관리자 아이디로 지정해서 업무자료 편집이 가능하게".
  · 업무자료(자료검색 '회사 공통') 관리자 = KB_ADMINS — 새 계정을 더했다.
  · 수당율 관리자 = RATES_ADMINS — 그대로(지점장만). 업무자료만 맡긴다.
  · 업무자료검색 프로그램(kbsearch/config.py KB_ADMINS)과 같은 목록이어야 한다 — 그쪽 검사가 대조한다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import os
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from planner import config, kb  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


NEW = "qkrwlsgh7303@gmail.com"
BOSS = "wodud1903@gmail.com"

print("[1] 누가 무엇을 고치나")
ok("새 계정은 업무자료 관리자", config.is_kb_admin(NEW))
ok("대소문자·앞뒤 빈칸이 달라도 같은 계정", config.is_kb_admin("  QKRWLSGH7303@Gmail.com "))
ok("새 계정은 수당율 관리자가 아니다(업무자료만 맡긴다)", not config.is_rates_admin(NEW))
ok("지점장은 둘 다", config.is_kb_admin(BOSS) and config.is_rates_admin(BOSS))
ok("수당율 관리자는 모두 업무자료 관리자이기도 하다", set(config.RATES_ADMINS) <= set(config.KB_ADMINS))
ok("다른 계정·빈 값은 아니다", not config.is_kb_admin("someone@gmail.com") and not config.is_kb_admin("")
   and not config.is_kb_admin(None))
ok("목록은 소문자·빈칸 없이 적는다(그래야 맞춰 볼 수 있다)",
   all(e == e.strip().lower() for e in config.KB_ADMINS + config.RATES_ADMINS))

print("[2] 어디에 쓰나 — 자료검색은 업무자료 관리자, 설정의 수당율은 수당율 관리자")
src = lambda f: (_ROOT / "python" / "planner" / f).read_text(encoding="utf-8")  # noqa: E731
ok("자료검색 편집(kb_tab)은 is_kb_admin", src("kb_tab.py").count("config.is_kb_admin(") == 2
   and "is_rates_admin" not in src("kb_tab.py"))
ok("수당율 편집(설정)은 그대로 is_rates_admin", src("settings_dialog.py").count("config.is_rates_admin(") == 2
   and "is_kb_admin" not in src("settings_dialog.py"))

print("[3] 편집 창 — 새 계정은 '회사 공통' 을 고칠 수 있다")
app = QApplication.instance() or QApplication([])
from planner.kb_tab import KbEditDialog  # noqa: E402

kb.save_shared([{"category": "심사서류", "title": "개인 심사서류", "body": "가"}])
d = KbEditDialog(NEW, None)
srcs = [d.cmb_src.itemData(i) for i in range(d.cmb_src.count())]
ok("새 계정 — '회사 공통' 묶음이 있다", kb.SRC_SHARED in srcs, srcs)
d.reject()
d = KbEditDialog("staff@gmail.com", None)
srcs = [d.cmb_src.itemData(i) for i in range(d.cmb_src.count())]
ok("일반 직원 — '회사 공통' 은 없다(내 메모만)", kb.SRC_SHARED not in srcs, srcs)
d.reject()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
