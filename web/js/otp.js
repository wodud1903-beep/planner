// 휴대폰 인증번호(v1.32) — planner/otp.py 의 읽기·번호 뽑기를 옮긴 것(통신 없는 계산 + 시트 읽기 한 줄).
//
// 폰의 매크로드로이드가 받은 문자를 구글 시트 맨 위에 한 줄씩 끼워 넣는다(맨 위가 최신).
//   1행 머리글: 일시 | (빈칸) | 인증번호 | 맨위가 최신입니다
//   그 아래:    2026. 11. 9 | 수신문자 | [Web발신] … 인증번호 (123456) …
// PC 는 새 줄이 생기면 팝업으로 띄운다. 웹(폰)은 밖에서 PC 없이 볼 때 쓴다 — 오늘 온 것을 크게 보여 준다.
import * as sheets from "./sheets.js";
import { OTP_DEF_SHEET_ID, OTP_DEF_TAB } from "./config.js";

export const TOP_ROWS = 12;
export const POLL_MS = 4000;      // PC 와 같은 박자

const KEY = "(?:인증|승인|확인|보안|OTP|otp|Otp|코드|code|Code|CODE|비밀번호)";
const RE_KEY = new RegExp(KEY + "[^0-9\\n]{0,20}?(?<!\\d)(\\d{4,8})(?!\\d)");
const RE_BRACKET = /[\[\(【<]\s*(\d{4,8})\s*[\]\)】>]/;
const RE_SIX = /(?<![\d\-])(\d{6})(?![\d\-])/;
const RE_TAG = /\[([^\[\]\n]{1,24})\]/g;
const NOT_SENDER = new Set(["web발신", "국외발신", "국제발신", "광고"]);
const RE_DATE = /(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})/;

export function extractCode(body) {
  const s = String(body || "");
  for (const rx of [RE_KEY, RE_BRACKET, RE_SIX]) {
    const m = s.match(rx);
    if (m) return m[1];
  }
  return "";
}

export function senderOf(body) {
  for (const m of String(body || "").matchAll(RE_TAG)) {
    const t = m[1].trim();
    if (t && !NOT_SENDER.has(t.replace(/ /g, "").toLowerCase())) return t;
  }
  return "";
}

/** '2026. 11. 9' → 'YYYY-MM-DD' (못 읽으면 ""). */
export function parseDay(s) {
  const m = String(s || "").match(RE_DATE);
  if (!m) return "";
  const y = +m[1], mo = +m[2], d = +m[3];
  const dt = new Date(y, mo - 1, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return "";
  return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export const dayKey = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function isHeader(cells) {
  const c = cells.map((x) => String(x || "").trim());
  if (!c.some(Boolean)) return false;
  if (c.some((x) => /\d{4,}/.test(x))) return false;          // 숫자가 든 줄은 문자다
  return c.some((x) => ["일시", "날짜", "인증", "내용", "문자", "보낸"].some((k) => x.includes(k)));
}

/** 시트 값 → [{date, body, key}] (위에서부터). 머리글·빈 줄은 뺀다. */
export function rowsOf(values) {
  const out = [];
  (values || []).forEach((row, i) => {
    const cells = (row || []).map((c) => String(c == null ? "" : c));
    if (!cells.some((c) => c.trim())) return;
    if (i === 0 && isHeader(cells)) return;
    // 본문 = 날짜 칸(A) 뒤에서 가장 긴 칸. ⚠️ 날짜 칸까지 넣고 고르면 "인증 1234" 처럼 짧은 문자는
    //    날짜("2026. 11. 9")가 더 길어 본문으로 뽑혀 번호를 놓친다(v1.32 에서 고침 — PC otp.rows_of 와 같다).
    let body = "";
    for (const c of cells.slice(1)) if (c.trim() && c.trim().length >= body.length) body = c.trim();   // 같으면 뒤 칸
    if (!body) body = (cells[0] || "").trim();
    const d = (cells[0] || "").trim();
    out.push({ date: d, body, key: d + "\x1f" + body });
  });
  return out;
}

/** 보여 줄 인증번호 [{code, sender, body, date, key}] — 오늘 것만(날짜를 못 읽는 줄은 둔다) · 위에서부터. */
export function itemsOf(rows, today = dayKey()) {
  const out = [];
  for (const r of rows || []) {
    const code = extractCode(r.body);
    if (!code) continue;
    const d = parseDay(r.date);
    if (d && d !== today) continue;                           // 옛 문자
    out.push({ code, sender: senderOf(r.body), body: r.body, date: r.date, key: r.key });
  }
  return out;
}

/** PC 설정(plan_cfg.json 의 otpSheet · otpTab)에서 어느 시트인지 — 비어 있으면 지점 기본 시트. */
export function whereOf(cfg) {
  const c = cfg && typeof cfg === "object" ? cfg : {};
  const id = String(c.otpSheet || "").trim() || OTP_DEF_SHEET_ID;
  let tab = String(c.otpTab || "").trim();
  if (!tab && id === OTP_DEF_SHEET_ID) tab = OTP_DEF_TAB;
  return { id, tab };
}

/** 시트 맨 위 몇 줄을 읽어 오늘의 인증번호를 돌려준다. 권한이 없으면 sheets.WrongAccount / BadRange. */
export async function read(where, today = dayKey()) {
  const vals = await sheets.values(where.id, where.tab, `A1:F${TOP_ROWS}`);
  return itemsOf(rowsOf(vals), today);
}
