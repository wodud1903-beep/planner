"""고객 피드(이력 · 메모) — 폰과 PC 가 같은 메모를 쓰고, 지운 메모가 되살아나지 않는다.

지점장 요청(v1.25): "플로우 피드처럼 폰에서도 고객 메모."
같이 잡은 버그: 메모 파일은 동기화 때 양쪽 목록을 **합친다**. 그래서 PC 에서 메모를
지워도 다른 쪽(다른 PC·폰)에 남은 같은 메모가 합쳐지며 되살아났다.
→ 지울 때 {"date","text","del":1} 표식을 남기고, 표식과 같은 메모는 안 보인다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import json
import os
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from planner import config, sync, theme  # noqa: E402
from planner import customer_history as ch  # noqa: E402
from planner.sheets import CustomerRow  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


A = {"date": "2026-10-20", "text": "통화함 — 보증금 문의"}
B = {"date": "2026-10-21", "text": "서류 받음"}
W = {"date": "2026-10-22", "time": "14:20", "text": "폰에서 남김", "via": "web"}

print("[1] 지운 표식")
notes = [A, B]
after = ch.delete_note(notes, 0)
ok("지우면 표식이 남는다", {"date": A["date"], "text": A["text"], "del": 1} in after and A not in after)
ok("보일 메모에서 빠진다", [n for _, n in ch.visible_notes(after)] == [B])
ok("원래 자리를 그대로 준다(지우기 단추가 맞는 것을 지우게)",
   ch.visible_notes([A, B, {"date": A["date"], "text": A["text"], "del": 1}]) == [(1, B)])

print("[2] 동기화가 합쳐도 되살아나지 않는다")
uid = "uid0000000000001"
here = json.dumps({uid: after}, ensure_ascii=False)            # 이 PC: A 를 지웠다
there = json.dumps({uid: [A, B, W]}, ensure_ascii=False)       # 저쪽: 아직 A 가 있다 + 폰 메모
merged = json.loads(sync.merge_text("customer_notes.json", here, there))[uid]
vis = [n["text"] for _, n in ch.visible_notes(merged)]
ok("A 는 합쳐져도 안 보인다", A["text"] not in vis, vis)
ok("폰에서 남긴 메모는 들어온다", W["text"] in vis, vis)
merged2 = json.loads(sync.merge_text("customer_notes.json", there, here))[uid]
ok("거꾸로 합쳐도 같다(어느 쪽이 최신이든)", sorted(n["text"] for _, n in ch.visible_notes(merged2))
   == sorted(vis))

print("[3] 고객 이력 창")
app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)
cr = CustomerRow(row=2, total="", center="", accident="")
cr.values.update({"customer": "김상현", "finance": "KB캐피탈", "model": "쏘나타",
                  "contract_date": "2026. 8. 1", "deliver_date": "2026. 8. 20",
                  "status": "출고완료", "terms": "60개월"})
dlg = ch.CustomerHistoryDialog(cr, after + [W], ment_sent=False)
rows = [dlg.lst.item(i).text() for i in range(dlg.lst.count())]
ok("지운 메모는 목록에 없다", not any(A["text"] in r for r in rows), rows)
ok("폰에서 남긴 메모는 📱", any("폰에서 남김" in r and "📱" in r for r in rows), rows)
dlg.ed.setText("새 메모")
dlg._add()
nw = [n for n in dlg.notes() if n.get("text") == "새 메모"][0]
ok("새 메모에 시각도 남긴다(피드에서 순서가 맞게)", len(nw.get("time", "")) == 5, nw)
# 이력 창에서 지우기 → 표식
for i in range(dlg.lst.count()):
    if "새 메모" in dlg.lst.item(i).text():
        dlg.lst.setCurrentRow(i)
from PySide6.QtWidgets import QMessageBox  # noqa: E402
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
dlg._del()
ok("창에서 지워도 표식", any(n.get("del") and n.get("text") == "새 메모" for n in dlg.notes()))
ok("목록에서 사라진다", not any("새 메모" in dlg.lst.item(i).text() for i in range(dlg.lst.count())))

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
