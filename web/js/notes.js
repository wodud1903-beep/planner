// 고객 메모 — PC 앱의 '고객 이력' 메모와 **같은 것**(customer_notes.json).
//
//   {고객ID: [{date: "2026-11-01", time: "14:20", text: "통화함 — 보증금 문의", via: "web"}, …]}
//
// PC 의 동기화 묶음 안에 있으므로 폰에서 남긴 메모가 PC 이력에도 뜨고(📱 표시),
// PC 에서 남긴 메모도 폰에서 보인다.
//
// 지울 때는 빼지 않고 {date, text, del: 1} 표식을 더한다. 동기화가 양쪽 목록을
// 합치므로 그냥 빼면 다른 쪽에 남은 같은 메모가 되살아난다(PC 도 같은 규칙).
import * as appdata from "./appdata.js";
import * as store from "./store.js";

export const FILE = "customer_notes.json";
const CACHE = "notes";              // 이 기기에 받아 둔 전체 메모(오프라인에서도 보이게)

const same = (a, b) => String(a.date || "") === String(b.date || "")
  && String(a.text || "") === String(b.text || "");

/** 보일 메모 — 지운 표식과 그 짝은 뺀다. 최신이 위로. */
export function visible(list) {
  const all = (list || []).filter((n) => n && typeof n === "object");
  const dead = all.filter((n) => n.del);
  return all.filter((n) => !n.del && !dead.some((d) => same(n, d)))
    .sort((a, b) => (String(b.date) + (b.time || "")).localeCompare(String(a.date) + (a.time || "")));
}

const pad = (n) => String(n).padStart(2, "0");
function today() {
  const d = new Date();
  return { date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
           time: `${pad(d.getHours())}:${pad(d.getMinutes())}` };
}

/** 받아 둔 메모(바로 그리기용). */
export async function cached(uid) {
  const m = (await store.get("meta", CACHE)) || {};
  return uid ? (m[uid] || []) : [];
}

/** 계정에서 새로 받는다. 실패하면 받아 둔 것. */
export async function load(uid) {
  try {
    const m = (await appdata.readPcFile(FILE)) || {};
    await store.put("meta", CACHE, m);
    return uid ? (m[uid] || []) : [];
  } catch (e) {
    return cached(uid);
  }
}

async function change(uid, fn) {
  const next = await appdata.updatePcFile(FILE, (m) => {
    const out = m && typeof m === "object" && !Array.isArray(m) ? m : {};
    out[uid] = fn(Array.isArray(out[uid]) ? out[uid] : []);
    return out;
  });
  await store.put("meta", CACHE, next);
  return next[uid] || [];
}

export function add(uid, text) {
  const t = String(text || "").trim();
  return change(uid, (list) => [...list, { ...today(), text: t, via: "web" }]);
}

export function remove(uid, note) {
  return change(uid, (list) => [...list, { date: note.date || "", text: note.text || "", del: 1 }]);
}
