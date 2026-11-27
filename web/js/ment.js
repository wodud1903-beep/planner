// 멘트 · 명함 보내기(v1.37, H2) — 계산만(화면은 ui/ment.js). PC [멘트복사] 와 **같은 글 · 같은 명함**.
//
//   · 글: PC 동기화 묶음(planner_sync.json)의 greetings.json. PC 에서 한 번도 고친 적 없으면 그 파일이
//         없으므로 PC 의 기본 문구 그대로(python/planner/greetings.py DEFAULTS — verify_logic 이 대조한다).
//   · 명함: 내 구글 계정 앱 전용 공간의 bizcard_<열쇠>.png. 열쇠 = 채널 이름(앞뒤 공백 뺀)의 SHA-1 앞 16자 —
//           PC bizcard.key_of 와 같은 계산(verify_logic 이 대조한다). 명함이 없는 채널은 [명함] 이 꺼진다.
//   · 폰에서는 고치지 않는다(보기 · 보내기만) — 고치는 곳은 PC 한 곳.

const AFTER_TAIL = "\n\n좋은견적 준비해서 발송드리겠습니다 :)";
const MISS_TAIL = "\n부재중이셔서 통화 가능하신 시간 회신 남겨주시면, 다시한번 연락드리겠습니다.\n\n"
  + "혹시라도 통화 어려우시다면 , 카톡으로 문의 남겨주셔도 상담 가능합니다.^^";
const A1 = "안녕하세요 차량문의 주셔서 연락드린 에이원오토 이재영 부지점장입니다.😊";
const direct = (company) => `안녕하세요 ${company}로 차량문의 주셔서 연락드린 다이렉트팀 이재영 부지점장 입니다.😊`;

/** PC 의 기본 문구(greetings.DEFAULTS) 그대로. */
export const DEFAULTS = [
  { name: "에이원오토", after: A1 + AFTER_TAIL, miss: A1 + MISS_TAIL },
  { name: "우리금융", after: direct("우리금융캐피탈") + AFTER_TAIL, miss: direct("우리금융캐피탈") + MISS_TAIL },
  { name: "하나캐피탈", after: direct("하나캐피탈") + AFTER_TAIL, miss: direct("하나캐피탈") + MISS_TAIL },
  { name: "BNK캐피탈", after: direct("BNK캐피탈") + AFTER_TAIL, miss: direct("BNK캐피탈") + MISS_TAIL },
  { name: "롯데렌터카", after: direct("롯데렌탈") + AFTER_TAIL, miss: direct("롯데렌탈") + MISS_TAIL },
  { name: "KB캐피탈", after: direct("KB캐피탈") + AFTER_TAIL, miss: direct("KB캐피탈") + MISS_TAIL },
];

/** 묶음의 greetings.json(·deleted.json) → 보일 채널 [{name, after, miss}]. PC greetings.load 와 같은 규칙.
 *  지운 표식(deleted.json 의 greetings.json 칸)보다 나중에 고치지 않은 채널은 뺀다. 통신 없는 계산. */
export function liveGreetings(saved, deleted = null) {
  const dead = (deleted && typeof deleted === "object" && deleted["greetings.json"]
    && typeof deleted["greetings.json"] === "object") ? deleted["greetings.json"] : {};
  const out = [];
  for (const o of Array.isArray(saved) ? saved : []) {
    if (!o || typeof o !== "object") continue;
    const name = String(o.name == null ? "" : o.name).trim();
    if (!name) continue;
    const at = o.at ? String(o.at) : "";
    if (dead[name] && !(at && at > String(dead[name]))) continue;
    out.push({ name, after: String(o.after == null ? "" : o.after), miss: String(o.miss == null ? "" : o.miss) });
  }
  return out.length ? out : DEFAULTS.map((d) => ({ ...d }));
}

/** 채널 이름 → 명함 열쇠(SHA-1 앞 16자, PC bizcard.key_of 와 같다). */
export async function bizKey(name) {
  const data = new TextEncoder().encode(String(name == null ? "" : name).trim());
  const h = await crypto.subtle.digest("SHA-1", data);
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}

export const cardFile = (key) => `bizcard_${key}.png`;

/** 공유할 명함 파일 이름 — '명함_에이원오토.png' (파일 이름에 못 쓰는 글자는 뺀다). */
export function cardName(channel) {
  const s = String(channel || "").replace(/[\\/:*?"<>|\r\n\t]+/g, " ").trim();
  return `명함_${s || "채널"}.png`;
}
