"""내 계정에서만 고친 회사 공통 자료 — 구글 계정으로 주고받기(v1.29).

지점장 요청: "자료검색에서 회사 공통자료로 들어가 있는 것도 로그인한 계정에 한해서, 내 계정에만
자료수정을 할 수 있게 — 예를 들어 팩스번호를 본인 걸로 지정해서 저장. 업무자료검색에도 동일하게."

주고받는 곳: 내 구글 드라이브 앱 전용 공간(appDataFolder)의 `kb_edits.json` 하나 — 업무자료검색
프로그램(kbsearch/sync.py)·업무자료검색 웹(public/sync.js)과 **같은 파일 · 같은 모양 · 같은 규칙**이다.
  {"v": 1, "edits": {제목: {"item": 고친 것 | null(회사 자료로 되돌림), "base": 고칠 때 본 원본, "at": UTC}}}
  · 제목마다 **나중에 고친 쪽(at)** 이 이긴다. 시각이 같으면 드라이브 쪽(내용까지 같으면 그대로).
  · 같은 제목이 여럿인 공통 자료는 첫 번째만 주고받는다(나머지는 이 PC 에만).
  · 일정관리기 동기화 묶음(planner_sync.json)과는 따로 둔다 — 서로 건드리지 않는다.
  · 못 읽거나 깨졌으면 쓰지 않는다(남의 것을 덮지 않게).
"""

from __future__ import annotations

import json

from . import google_client, kb

FILE = "kb_edits.json"


class EditsError(Exception):
    pass


def _good_rec(r) -> bool:
    return isinstance(r, dict) and isinstance(r.get("at"), str) and (
        r.get("item") is None or isinstance(r.get("item"), dict))


def _upload_item(item: dict) -> dict:
    out = dict(kb._clean(item) or {})
    out.pop("at", None)
    return out


def _apply_item(remote_item: dict, shared_item) -> dict:
    """받은 것을 이 PC 모양으로 — 원본 위에 덮는다(웹은 체크리스트 등을 싣지 않는다)."""
    base = dict(shared_item or {})
    base.update({k: v for k, v in (remote_item or {}).items() if v is not None})
    return kb._clean(base) or kb._clean(remote_item) or {}


def merge(recs: list, dead: dict, remote: dict, now: str, shared: list) -> dict:
    """이 PC 것과 드라이브 것을 합친다(계산만). 업무자료검색 sync.merge_edits 와 같은 규칙.

    돌려줌 {recs, dead, edits, changed(받아서 바뀐 제목), push(올려야 하나)}
    """
    by_key = dict(zip(kb.shared_keys(shared), shared))
    out_recs = [r for r in recs if tuple(r["key"])[1] != 0]       # 둘째 이후 같은 제목은 이 PC 에만
    out_dead, edits, changed, push = {}, dict(remote or {}), [], False
    titles = []
    for t in [tuple(r["key"])[0] for r in recs if tuple(r["key"])[1] == 0] + list(dead or {}) + list(remote or {}):
        if t and t not in titles:
            titles.append(t)
    for t in titles:
        key = (t, 0)
        lr = next((r for r in recs if tuple(r["key"]) == key), None)
        R = remote.get(t) if _good_rec((remote or {}).get(t)) else None
        if lr is not None:
            L = {"item": _upload_item(lr["item"]), "base": lr.get("base"), "at": lr.get("at") or ""}
        elif (dead or {}).get(t):
            L = {"item": None, "base": None, "at": str(dead[t])}
        else:
            L = None
        # 동기화 전에 고친 것(시각 없음) — 드라이브가 비었을 때만 지금 고친 것으로 올린다
        if L is not None and not L["at"]:
            L["at"] = "" if R else now
        if L is None and R is None:
            continue
        if R is None or L is None:
            W = L if R is None else R
        elif R["at"] > L["at"] or (R["at"] == L["at"] and R.get("item") != L["item"]):
            W = R
        else:
            W = L
        if W is L:
            if W["item"] is not None:
                out_recs.append(lr if lr.get("at") else dict(lr, at=W["at"]))
            else:
                out_dead[t] = W["at"]
        else:
            if W["item"] is not None:
                cur = by_key.get(key)
                item = _apply_item(W["item"], cur)
                rb = kb._clean(W.get("base")) if isinstance(W.get("base"), dict) else None
                # 웹은 원본을 {제목, 본문} 만 적는다 — 본문이 지금 원본과 같으면 지금 원본을 쓴다
                if cur is not None and (rb is None or rb.get("body") == kb._clean(cur).get("body")):
                    rb = kb._clean(cur)
                out_recs.append({"key": key, "base": rb, "item": item, "at": W["at"]})
            else:
                out_dead[t] = W["at"]
            before = lr["item"].get("body") if lr else None
            after = (W["item"] or {}).get("body") if W["item"] is not None else None
            if before != after:
                changed.append(t)
        rec = {"item": W["item"], "base": W.get("base"), "at": W["at"]}
        if R is None or rec != {"item": R.get("item"), "base": R.get("base"), "at": R["at"]}:
            edits[t] = rec
            push = True
    return {"recs": out_recs, "dead": out_dead, "edits": edits, "changed": changed, "push": push}


def sync(auth) -> list:
    """드라이브와 맞춘다. 받아서 바뀐 제목 목록. 못 읽으면 EditsError(쓰지 않는다)."""
    try:
        fid = google_client.drive_find(auth, FILE)
        text = google_client.drive_read(auth, fid) if fid else ""
    except Exception as e:
        raise EditsError(f"고친 자료를 받지 못했습니다: {e}")
    try:
        o = json.loads(text) if text.strip() else {}
    except Exception:
        raise EditsError("드라이브의 고친 자료 파일이 깨져 있어 주고받지 않았습니다.")
    remote = o.get("edits") if isinstance(o, dict) and isinstance(o.get("edits"), dict) else {}
    stamp = kb.utc_stamp()
    recs0, dead0 = kb.load_local(), kb.load_local_dead()
    m = merge(recs0, dead0, remote, stamp, kb.load_shared())
    if m["push"]:
        try:
            google_client.drive_write(auth, FILE, json.dumps(
                {"v": 1, "updatedAt": stamp, "edits": m["edits"]}, ensure_ascii=False, indent=1))
        except Exception as e:
            raise EditsError(f"고친 자료를 올리지 못했습니다: {e}")
    # 바뀐 것이 있을 때만 쓴다 — 쓸 때마다 파일 시각이 바뀌어 동기화가 또 도는 일이 없게
    shape = lambda recs: sorted((list(r["key"]), r["item"], r.get("base"), r.get("at") or "") for r in recs)  # noqa: E731
    if shape(m["recs"]) != shape(recs0) or m["dead"] != dead0:
        kb.replace_local(m["recs"], m["dead"])
    return m["changed"]
