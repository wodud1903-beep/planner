// 내 계정에서만 고친 회사 공통 자료(팩스번호 등) — 구글 드라이브 앱 전용 공간의 kb_edits.json (v1.30).
//
// 일정관리기 PC(planner/kb_edits.py) · 업무자료검색 PC(kbsearch/sync.py) · 업무자료검색 웹(public/sync.js)과
// **같은 파일 · 같은 모양 · 같은 규칙**이다. 자료는 이 기기가 아니라 **내 구글 계정**에 저장된다.
//   {"v": 1, "updatedAt", "edits": {제목: {"item": 고친 것 | null(회사 자료로 되돌림), "base": 고칠 때 본 원본, "at": UTC}}}
//   · 제목마다 나중에 고친 쪽(at)이 이긴다 — 여기서 고치면 지금 시각으로 적는다.
//   · 같은 제목이 여럿인 회사 자료는 첫 번째에만 겹친다(PC 와 같다).
//   · 회사 자료와 다른 사람 화면은 그대로다 — 내 계정으로 로그인한 곳에서만 보인다.
import * as appdata from "./appdata.js";

export const FILE = "kb_edits.json";
const FIELDS = ["title", "category", "finance", "tags", "body", "checklist", "files"];

const stamp = () => new Date().toISOString().slice(0, 19) + "Z";

/** 파일 → {제목: 기록}. 모양이 틀린 기록은 뺀다. */
export function editsOf(data) {
  const e = data && typeof data === "object" && data.edits && typeof data.edits === "object" ? data.edits : {};
  const out = {};
  for (const [t, r] of Object.entries(e)) {
    if (r && typeof r === "object" && typeof r.at === "string"
        && (r.item === null || (r.item && typeof r.item === "object"))) out[t] = r;
  }
  return out;
}

/** 회사 자료에 내가 고친 것을 겹친다. 고친 것엔 _local(내 계정에서 고침) · _orig(회사 원본) · _stale(회사가 또 고침). */
export function overlay(items, edits) {
  const seen = new Set();
  return (items || []).map((it) => {
    const t = String((it && it.title) || "").trim();
    if (!t || seen.has(t)) return it;
    seen.add(t);
    const rec = edits && edits[t];
    if (!rec || !rec.item || typeof rec.item !== "object") return it;
    const out = { ...it };
    for (const k of FIELDS) {
      const v = rec.item[k];
      if (v !== null && v !== undefined) out[k] = v;
    }
    out.title = it.title;                        // 제목은 열쇠 — 바꾸지 않는다
    out._local = true;
    out._orig = it;
    const b = rec.base && typeof rec.base === "object" ? rec.base : null;
    if (b && typeof b.body === "string" && b.body !== String(it.body || "")) out._stale = true;
    return out;
  });
}

const pick = (it) => {
  const o = {};
  for (const k of FIELDS) if (it && it[k] !== undefined && it[k] !== null) o[k] = it[k];
  return o;
};

/** 계정의 고친 자료를 읽는다(바뀌었을 때만 받는다). {edits, changed}. */
export async function read() {
  const { data, changed } = await appdata.readIfChanged(FILE);
  return { edits: editsOf(data), changed };
}

/** 고쳐서 내 계정에 저장한다. shown = 지금 보이는 것(겹친 것), body = 새 본문. 원본과 같아지면 되돌림.
 *  ⚠️ 바꾼 칸만 싣는다(제목 · 본문 + 전에 PC 에서 고쳐 둔 칸). 화면에 있던 칸을 통째로 실으면 PC 가 받을 때
 *     회사 원본의 체크리스트·첨부를 웹이 가진 빈 값으로 덮는다.
 *  ⚠️ 못 읽으면 쓰지 않는다(남의 기록을 덮지 않게 — 예외가 그대로 올라간다). 새 {제목: 기록} 을 돌려준다. */
export async function save(shown, body) {
  const orig = (shown && shown._orig) || shown;
  const t = String(orig.title || "").trim();
  if (!t) throw new Error("제목이 없는 자료는 고칠 수 없습니다.");
  const { data } = await appdata.readIfChanged(FILE);
  const o = data && typeof data === "object" ? { ...data } : {};
  const edits = { ...editsOf(data) };
  const prev = edits[t] && edits[t].item && typeof edits[t].item === "object" ? edits[t].item : {};
  const item = { ...prev, title: orig.title, body: String(body) };
  const now = stamp();
  const merged = { ...orig };
  for (const k of FIELDS) if (item[k] !== null && item[k] !== undefined) merged[k] = item[k];
  if (JSON.stringify(pick(merged)) === JSON.stringify(pick(orig))) {
    edits[t] = { item: null, base: null, at: now };       // 원본과 같아졌다 = 회사 자료로 되돌림
  } else {
    edits[t] = { item, base: { title: orig.title, body: String(orig.body || "") }, at: now };
  }
  o.v = 1;
  o.updatedAt = now;
  o.edits = edits;
  await appdata.writeAppJson(FILE, o);
  return edits;
}

/** 회사 자료로 되돌린다(내 계정의 고친 것을 지운다 — 다른 곳에도 전해진다). */
export async function revert(shown) {
  const orig = (shown && shown._orig) || shown;
  const t = String(orig.title || "").trim();
  const { data } = await appdata.readIfChanged(FILE);
  const o = data && typeof data === "object" ? { ...data } : {};
  const edits = { ...editsOf(data) };
  const now = stamp();
  edits[t] = { item: null, base: null, at: now };
  o.v = 1;
  o.updatedAt = now;
  o.edits = edits;
  await appdata.writeAppJson(FILE, o);
  return edits;
}
