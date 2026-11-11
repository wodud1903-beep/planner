// 내 계정에서만 고친 회사 공통 자료(팩스번호 등) — 구글 드라이브 앱 전용 공간의 kb_edits.json (v1.30).
//
// 일정관리기 PC(planner/kb_edits.py) · 업무자료검색 PC(kbsearch/sync.py) · 업무자료검색 웹(public/sync.js)과
// **같은 파일 · 같은 모양 · 같은 규칙**이다. 자료는 이 기기가 아니라 **내 구글 계정**에 저장된다.
//   {"v": 1, "updatedAt", "edits": {제목: {"item": 고친 것 | null(회사 자료로 되돌림), "base": 고칠 때 본 원본, "at": UTC}}}
//   · 제목마다 나중에 고친 쪽(at)이 이긴다 — 여기서 고치면 지금 시각으로 적는다.
//   · 같은 제목이 여럿인 회사 자료는 첫 번째에만 겹친다(PC 와 같다).
//   · 회사 자료와 다른 사람 화면은 그대로다 — 내 계정으로 로그인한 곳에서만 보인다.
//
// v1.32: 같은 파일에 **내 정보**("me": {fax, name, phone, email, at})도 둔다. 회사 자료 본문의
//   {내 팩스} · {내 이름} · {내 연락처} · {내 이메일} 자리(기본값은 {내 팩스|0504-…})를 내 것으로 바꿔 보여 준다.
import * as appdata from "./appdata.js";

export const FILE = "kb_edits.json";
const FIELDS = ["title", "category", "finance", "tags", "body", "checklist", "files"];

const stamp = () => new Date().toISOString().slice(0, 19) + "Z";
export const norm = (t) => String(t == null ? "" : t).replace(/\r\n?/g, "\n")
  .split("\n").map((l) => l.replace(/\s+$/, "")).join("\n").trim();

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
    // 다듬은 것끼리 견준다 — PC 는 줄 끝 공백을 턴 본문을 원본으로 적는다(공백 차이는 '또 고침' 이 아니다)
    if (b && typeof b.body === "string" && norm(b.body) !== norm(it.body)) out._stale = true;
    return out;
  });
}

const pick = (it) => {
  const o = {};
  for (const k of FIELDS) if (it && it[k] !== undefined && it[k] !== null) o[k] = it[k];
  return o;
};

// ---------------------------------------------------------------- 내 정보(v1.32)
export const ME_FIELDS = [["fax", "팩스"], ["name", "이름"], ["phone", "연락처"], ["email", "이메일"]];
const ME_KEY = Object.fromEntries(ME_FIELDS.map(([k, l]) => [l, k]));
const ME_RE = /\{내 (팩스|이름|연락처|이메일)(?:\|([^{}\n]*))?\}/g;

export function cleanMe(o) {
  const src = o && typeof o === "object" ? o : {};
  const out = {};
  for (const [k] of ME_FIELDS) out[k] = String(src[k] == null ? "" : src[k]).trim().slice(0, 80);
  out.at = String(src.at || "");
  return out;
}
export const hasMe = (me) => ME_FIELDS.some(([k]) => !!(me && me[k]));
const meVals = (me) => ME_FIELDS.map(([k]) => (me && me[k]) || "").join("\x1f");

/** {내 팩스|기본값} 자리를 내 정보로. 안 적었으면 기본값, 그것도 없으면 '〔내 팩스 미입력〕' (PC kb.fill_me 와 같다). */
export function fillMe(text, me) {
  const s = String(text == null ? "" : text);
  if (!s.includes("{내 ")) return s;
  return s.replace(ME_RE, (_m, label, def) => {
    const v = String((me && me[ME_KEY[label]]) || "").trim();
    if (v) return v;
    const d = String(def || "").trim();
    return d || `〔내 ${label} 미입력〕`;
  });
}

/** 이 기기의 내 정보(local)와 계정 것(remote)을 맞춘다 → {me, push}. 나중에 고친 쪽(PC kb_edits.merge_me 와 같다).
 *  예전 판(v1.31 까지)은 파일을 쓸 때 "me" 를 빼먹는다 — 계정에 없고 이 기기에 있으면 다시 올린다(push). */
export function mergeMe(local, remote) {
  const L = cleanMe(local);
  const R = remote && typeof remote === "object" ? cleanMe(remote) : null;
  if (!R || !(hasMe(R) || R.at)) return { me: L, push: hasMe(L) };
  if (meVals(L) === meVals(R)) return { me: L.at ? L : R, push: false };
  if (L.at && L.at > (R.at || "")) return { me: L, push: true };
  return { me: R, push: false };
}

/** 계정의 고친 자료 · 내 정보를 읽는다(바뀌었을 때만 받는다). {edits, me(없으면 null), changed}. */
export async function read() {
  const { data, changed } = await appdata.readIfChanged(FILE);
  const me = data && typeof data === "object" && data.me && typeof data.me === "object" ? cleanMe(data.me) : null;
  return { edits: editsOf(data), me, changed };
}

/** 내 정보를 내 계정에 저장한다(다른 기기·PC 가 따라온다). at 을 안 주면 지금 고친 것으로.
 *  ⚠️ 못 읽으면 쓰지 않는다(고친 자료를 덮지 않게 — 예외가 그대로 올라간다). */
export async function saveMe(values, at = null) {
  const { data } = await appdata.readIfChanged(FILE);
  const o = data && typeof data === "object" ? { ...data } : {};
  const now = stamp();
  const me = cleanMe({ ...values, at: at || now });
  o.v = 1;
  o.updatedAt = now;
  if (!o.edits || typeof o.edits !== "object") o.edits = {};
  o.me = me;
  await appdata.writeAppJson(FILE, o);
  return me;
}

const listOf = (v) => (Array.isArray(v) ? v : String(v == null ? "" : v).split("\n"))
  .map((x) => String(x).trim()).filter(Boolean);

/** 고쳐서 내 계정에 저장한다. shown = 지금 보이는 것(겹친 것), body = 새 본문. 원본과 같아지면 되돌림.
 *  checklist(v1.32 — 줄 목록 또는 줄바꿈 글)를 주면 체크리스트도 고친다. 회사 것과 같으면 그 칸은 싣지 않는다.
 *  ⚠️ 바꾼 칸만 싣는다(제목 · 본문 + 전에 PC 에서 고쳐 둔 칸). 화면에 있던 칸을 통째로 실으면 PC 가 받을 때
 *     회사 원본의 체크리스트·첨부를 웹이 가진 빈 값으로 덮는다.
 *  ⚠️ 못 읽으면 쓰지 않는다(남의 기록을 덮지 않게 — 예외가 그대로 올라간다). 새 {제목: 기록} 을 돌려준다. */
export async function save(shown, body, checklist = undefined) {
  const orig = (shown && shown._orig) || shown;
  const t = String(orig.title || "").trim();
  if (!t) throw new Error("제목이 없는 자료는 고칠 수 없습니다.");
  const { data } = await appdata.readIfChanged(FILE);
  const o = data && typeof data === "object" ? { ...data } : {};
  const edits = { ...editsOf(data) };
  const prev = edits[t] && edits[t].item && typeof edits[t].item === "object" ? edits[t].item : {};
  const item = { ...prev, title: orig.title, body: norm(body) };
  if (checklist !== undefined) {
    const cl = listOf(checklist);
    if (JSON.stringify(cl) === JSON.stringify(listOf(orig.checklist))) delete item.checklist;
    else item.checklist = cl;
  }
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
