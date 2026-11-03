// 아침 브리핑·금요일 주간 보고에 들어갈 '고객 이야기' — 통신 없는 계산(v1.26).
//
// 알림 서버(api/_push.js)가 시트 줄을 읽어 이 함수로 고른다. 화면 없이 시험한다
// (web/verify/verify_api.mjs). 고르는 규칙은 PC 와 같다.
//   · 안내멘트 미발송 — 출고일 ~ 출고일+2일 사이인데 아직 [복사] 안 한 고객
//     (PC main_window._ment_due_customers · 보낸 기록은 PC 묶음의 ment_copied.json)
//   · 30일 넘게 멈춘 건 — 진행 보드에서 빨간 카드('계약 N일째', 보류 제외 — board.card)
//   · 이번 달 만기 — 이번 달 안에 계약이 끝나는 고객(재계약·안 함으로 정리한 건 뺀다 —
//     PC 의 만기 재계약 목록 renewals.json)
import { parseDate } from "./fmt.js";
import * as board from "./board.js";
import { expiryDate } from "./weekly.js";

const get = (cr, k) => String(((cr || {}).values || {})[k] || "").trim();
const p2 = (n) => String(n).padStart(2, "0");
export const ymd = (d) => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
const md = (d) => `${d.getMonth() + 1}/${d.getDate()}`;
const dayDiff = (a, b) => Math.round((a - b) / 86400000);

/** 안내멘트 '보냄' 기록의 열쇠 — PC 의 _ment_key 와 같다. */
export function mentKey(cr) {
  const uid = String(cr.uid || "").trim();
  if (uid) return "uid:" + uid;
  return `${cr.seq || ""}|${get(cr, "customer")}`.trim();
}

/** 만기 재계약 기록의 열쇠 — 고객(ID) + 그 만기일. 같은 고객이 재계약하면 새 만기일이라 새 건. */
export function renewKey(cr, d) {
  return `${mentKey(cr)}|${ymd(d)}`;
}

/** 재계약·안 함으로 정리한 건인가. renew = {열쇠: {s: "재계약"|"안 함"|…}} */
export function renewClosed(renew, cr, d) {
  const r = (renew || {})[renewKey(cr, d)];
  const s = r && typeof r === "object" ? r.s : "";
  return s === "재계약" || s === "안 함";
}

const live = (cr) => get(cr, "customer") && get(cr, "status") !== "취소";
const sameDay = (a, b) => a && b && a.getFullYear() === b.getFullYear()
  && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const label = (cr) => get(cr, "customer") + (get(cr, "model") ? `(${get(cr, "model")})` : "");

/** today: 그 날 자정(Date). sent: Set(보낸 안내멘트 열쇠). renew: 재계약 기록. */
export function items(rows, today, { sent = new Set(), renew = {} } = {}) {
  const t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const tomorrow = new Date(t0.getFullYear(), t0.getMonth(), t0.getDate() + 1);
  const rs = (rows || []).filter(live);
  const out = { deliver: [], contract: [], tomorrow: [], unsent: [], stale: [], expiry: [] };
  for (const cr of rs) {
    const dd = parseDate(get(cr, "deliver_date"));
    const cd = parseDate(get(cr, "contract_date"));
    if (sameDay(dd, t0)) out.deliver.push(label(cr));
    if (sameDay(cd, t0)) out.contract.push(get(cr, "customer"));
    if (sameDay(dd, tomorrow)) out.tomorrow.push(label(cr));
    if (dd) {
      const n = dayDiff(t0, dd);
      if (n >= 0 && n <= 2 && !sent.has(mentKey(cr))) out.unsent.push([dd, get(cr, "customer")]);
    }
    // 진행 중(보드의 칸)인데 계약 30일이 넘었다 — 보드와 같은 빨간 카드
    const rk = board.stage(get(cr, "status"));
    if (rk >= 0 && rk !== board.DONE && rk !== board.HOLD && rk !== board.CANCEL) {
      const k = board.card(cr, t0);
      if (k.tone === "red" && k.chip.startsWith("계약")) {
        out.stale.push([cd ? dayDiff(t0, cd) : 0, get(cr, "customer")]);
      }
    }
    const ed = expiryDate(cr);
    if (ed && ed.getFullYear() === t0.getFullYear() && ed.getMonth() === t0.getMonth()
        && !renewClosed(renew, cr, ed)) {
      out.expiry.push([ed, get(cr, "customer")]);
    }
  }
  out.unsent = out.unsent.sort((a, b) => a[0] - b[0]).map((x) => x[1]);
  out.stale = out.stale.sort((a, b) => b[0] - a[0]).map(([n, name]) => `${name} ${n}일`);
  out.expiry = out.expiry.sort((a, b) => a[0] - b[0]).map(([d, name]) => `${name} ${md(d)}`);
  return out;
}

/** 금요일 주간 보고 알림 글 — weekly.sections(이번 주) 를 한 화면 알림으로 줄인다. */
export function weeklyLines(secs) {
  const by = (pre) => (secs || []).find((s) => String(s.title || "").includes(pre)) || { items: [] };
  const out = by("출고"), made = by("계약"), open = by("진행 중"), exp = by("만기");
  const n = (s) => (s.count !== undefined ? s.count : (s.items || []).length);
  const lines = [`출고 ${n(out)} · 계약 ${n(made)}` + (out.note ? ` · ${out.note.replace("수수료 합계 ", "수수료 ")}` : "")];
  if (n(out)) lines.push("🚗 " + out.items.slice(0, 4).map((x) => x.text).join(", ") + (n(out) > 4 ? ` 외 ${n(out) - 4}` : ""));
  if (n(made)) lines.push("📝 " + made.items.slice(0, 4).map((x) => x.text).join(", ") + (n(made) > 4 ? ` 외 ${n(made) - 4}` : ""));
  if (n(open)) lines.push(`⏳ 출고 대기 ${n(open)}건`);
  if (n(exp)) lines.push(`🔔 만기 예정 ${n(exp)}건`);
  lines.push("눌러서 [복사] → 본사 보고방에 붙여 넣기");
  return lines;
}
