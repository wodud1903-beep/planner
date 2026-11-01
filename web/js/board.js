// 고객 진행 보드 — planner/board.py 를 그대로 옮긴 것(플로우의 '업무 상태').
//
// 칸 = 시트에 실제로 있는 진행현황 값. 카드를 옮기면 그 칸의 글자를 L열에 쓴다.
// ⚠️ 파이썬과 한 건도 달라지면 안 된다 — verify_logic.mjs 가 정답표로 대조한다.
import { parseDate } from "./fmt.js";

const RULES = [
  [8, ["진행보류", "보류", "홀딩"]],
  [9, ["취소", "부결", "철회"]],
  [0, ["상담", "문의", "견적"]],
  [1, ["서류", "접수", "신청"]],
  [2, ["심사"]],
  [3, ["가결", "승인"]],
  [5, ["배정", "생산", "선적", "입고", "탁송"]],
  [6, ["출고대기", "출고예정", "출고 대기", "출고 예정"]],
  [4, ["계약", "발주", "약정"]],
  [7, ["출고", "완료", "인도"]],
  [6, ["대기", "예정"]],
];
export const NO_STATUS = "(진행현황 없음)";
export const DONE = 7;
export const HOLD = 8;
export const CANCEL = 9;
const STALE_WARN = 14;
const STALE_BAD = 30;
export const DONE_DAYS = 30;

const get = (cr, k) => String((cr.values || {})[k] || "");
const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const md = (d) => `${d.getMonth() + 1}/${d.getDate()}`;
const day0 = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const days = (a, b) => Math.round((day0(a) - day0(b)) / 86400000);

export function stage(status) {
  const s = String(status || "").trim();
  if (!s) return -1;
  for (const [rank, words] of RULES) if (words.some((w) => s.includes(w))) return rank;
  return 4;
}

export function card(cr, today) {
  const st = get(cr, "status").trim();
  const rk = stage(st);
  const cd = parseDate(get(cr, "contract_date"));
  const dd = parseDate(get(cr, "deliver_date"));
  let chip = "", tone = "", key = "";
  if (rk === DONE) {
    if (dd) { chip = `출고 ${md(dd)}`; key = iso(dd); }
  } else if (rk === CANCEL) {
    chip = st;
  } else if (dd && rk >= 3) {
    const left = days(dd, today);
    chip = `출고 ${md(dd)}` + (left > 0 ? ` · D-${left}` : left === 0 ? " · 오늘" : ` · ${-left}일 지남`);
    tone = left >= 0 ? "green" : "red";
    key = iso(dd);
  } else if (cd) {
    const n = days(today, cd);
    if (n >= 0) {
      chip = `계약 ${n}일째`;
      tone = n >= STALE_BAD ? "red" : n >= STALE_WARN ? "orange" : "";
      if (rk === HOLD) tone = "";
    } else chip = `계약 ${md(cd)}`;
    key = iso(cd);
  }
  if (rk !== DONE) key = cd ? iso(cd) : dd ? iso(dd) : "";   // 진행 중은 늘 계약일 순
  return {
    row: cr.row, name: get(cr, "customer").trim(),
    sub: [get(cr, "finance"), get(cr, "model")].filter(Boolean).join(" · "),
    chip, tone, key,
  };
}

// 파이썬의 정렬과 같게 — 글자는 코드값 순서로 견준다(localeCompare 를 쓰면 어긋난다)
const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

export function columns(rows, today, showCancel = false, doneDays = DONE_DAYS) {
  const groups = new Map();
  for (const cr of rows || []) {
    if (!get(cr, "customer").trim()) continue;
    const st = get(cr, "status").trim() || NO_STATUS;
    if (!groups.has(st)) groups.set(st, []);
    groups.get(st).push(cr);
  }
  const cols = [];
  for (const [st, crs] of groups) {
    const rk = stage(st === NO_STATUS ? "" : st);
    if (rk === CANCEL && !showCancel) continue;
    let cards = crs.map((cr) => card(cr, today));
    let more = 0;
    if (rk === DONE) {
      const lo = new Date(today.getFullYear(), today.getMonth(), today.getDate() - doneDays);
      // 출고일이 아직 없는 건(방금 이 칸으로 옮긴 것)은 늘 보이게 맨 위에
      const recent = cards.filter((c) => !c.key || c.key >= iso(lo));
      more = cards.length - recent.length;
      cards = recent.sort((a, b) => cmp(b.key === "" ? 1 : 0, a.key === "" ? 1 : 0)
        || cmp(b.key, a.key));
    } else {
      cards.sort((a, b) => cmp(a.key === "" ? 1 : 0, b.key === "" ? 1 : 0)
        || cmp(a.key, b.key) || cmp(a.name, b.name));
    }
    cols.push({ status: st, rank: rk, count: crs.length, cards, more });
  }
  cols.sort((a, b) => cmp(a.rank, b.rank) || cmp(b.count, a.count) || cmp(a.status, b.status));
  return cols;
}
