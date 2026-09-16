// 주간 요약 — planner/weekly.py 의 sections() 를 그대로 옮긴 것.
//
// 새 통신이 없다. 폰이 이미 갖고 있는 고객 줄만 가지고 계산한다.
//
// ⚠️ 파이썬과 한 건도 달라지면 안 된다. 주 경계(월요일 시작)·만기 계산·
//    취소/보류 제외 같은 규칙이 어긋나면 '이번 주 출고' 건수가 달라지는데,
//    그건 눈에 잘 안 띈다. web/verify/vectors.json 에 파이썬이 낸 정답표가 있고
//    verify_logic.mjs 가 대조한다.
import { parseDate, digitsOnly, contractMonths } from "./fmt.js";

export const WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"];

// 진행현황이 이 말로 시작하면 '끝난 계약'
const DONE_WORDS = ["출고", "완료"];
// 이 말로 시작하면 '내가 재촉할 건이 아니다'
const HOLD_WORDS = ["진행보류", "보류", "홀딩"];
const CANCEL_WORD = "취소";
export const EXPIRY_MONTHS = 6;

const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
                 + `-${String(d.getDate()).padStart(2, "0")}`;
const md = (d) => `${String(d.getMonth() + 1).padStart(2, "0")}-`
                + `${String(d.getDate()).padStart(2, "0")}`;

/** 그 주의 [월요일, 일요일].
 *  ⚠️ 한 주는 **월요일 시작**이다. 일요일 시작으로 두면 금요일에 보는 요약에
 *     다음 주 이틀이 섞여 들어온다. */
export function weekRange(today, offset = 0) {
  // JS 의 getDay() 는 일=0 이라 파이썬 weekday()(월=0)와 다르다. 맞춰 준다.
  const wd = (today.getDay() + 6) % 7;
  const mon = new Date(today.getFullYear(), today.getMonth(),
                       today.getDate() - wd + 7 * offset);
  const sun = new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + 6);
  return [mon, sun];
}

/** d 에 months 개월을 더한다 (말일 보정). followup.add_months 와 같은 규칙. */
export function addMonths(d, months) {
  let month = d.getMonth() + months;
  const year = d.getFullYear() + Math.floor(month / 12);
  month = ((month % 12) + 12) % 12;
  const last = new Date(year, month + 1, 0).getDate();   // 그 달의 마지막 날
  return new Date(year, month, Math.min(d.getDate(), last));
}

const label = (d) => `${md(d)}(${WEEKDAY_KO[(d.getDay() + 6) % 7]})`;
const money = (n) => `${Number(n || 0).toLocaleString("ko-KR")}원`;
const get = (cr, k) => String((cr.values || {})[k] || "");

function fee(cr) {
  const n = parseInt(digitsOnly(cr.total || ""), 10);
  return isFinite(n) ? n : 0;
}

const live = (cr) => get(cr, "status").trim() !== CANCEL_WORD;

// 날짜만 견준다 — 시각이 섞이면 같은 날이 경계에서 갈린다
const between = (d, lo, hi) => d !== null && d >= lo
  && d <= new Date(hi.getFullYear(), hi.getMonth(), hi.getDate(), 23, 59, 59);

/** 계약 만기일. 계산할 수 없으면 null. (sheets.expiry_date) */
export function expiryDate(cr) {
  const n = contractMonths(get(cr, "terms"));
  if (!n) return null;
  const base = parseDate(get(cr, "deliver_date")) || parseDate(get(cr, "contract_date"));
  if (!base) return null;
  return addMonths(base, n);
}

const days = (a, b) => Math.round((a - b) / 86400000);

/** 주간 요약의 내용. weekly.sections 와 같은 모양을 돌려준다. */
export function sections(rows, today, expiryMonths = EXPIRY_MONTHS) {
  const [mon, sun] = weekRange(today);
  rows = (rows || []).filter(live);
  const secs = [];
  const who = (cr) => [get(cr, "finance"), get(cr, "model")].filter(Boolean).join(" · ");

  // ---- 이번 주 출고 ----
  const out = [];
  for (const cr of rows) {
    const d = parseDate(get(cr, "deliver_date"));
    if (between(d, mon, sun)) out.push([d, cr]);
  }
  out.sort((a, b) => a[0] - b[0]);
  const feeSum = out.reduce((s, [, cr]) => s + fee(cr), 0);
  secs.push({
    icon: "🚗", title: "이번 주 출고", color: "green",
    items: out.map(([d, cr]) => ({ lead: label(d), text: get(cr, "customer"), sub: who(cr) })),
    note: out.length ? `수수료 합계 ${money(feeSum)}` : "",
    empty: "이번 주 출고가 없습니다",
  });

  // ---- 이번 주 계약 ----
  const made = [];
  for (const cr of rows) {
    const d = parseDate(get(cr, "contract_date"));
    if (between(d, mon, sun)) made.push([d, cr]);
  }
  made.sort((a, b) => a[0] - b[0]);
  secs.push({
    icon: "📝", title: "이번 주 계약", color: "blue",
    items: made.map(([d, cr]) => ({ lead: label(d), text: get(cr, "customer"), sub: who(cr) })),
    empty: "이번 주 신규 계약이 없습니다",
  });

  // ---- 진행 중 (발주했는데 아직 출고 안 됨) ----
  const open = [];
  for (const cr of rows) {
    const st = get(cr, "status").trim();
    if (DONE_WORDS.some((w) => st.startsWith(w))) continue;
    if (HOLD_WORDS.some((w) => st.startsWith(w))) continue;   // 보류는 기다리는 건
    const cd = parseDate(get(cr, "contract_date"));
    if (cd === null || cd > today) continue;
    if (parseDate(get(cr, "deliver_date")) !== null) continue;
    open.push([days(today, cd), cd, cr]);
  }
  open.sort((a, b) => b[0] - a[0]);          // 오래 묵은 것이 위로
  if (open.length) {
    secs.push({
      icon: "⏳", title: "진행 중 (출고 대기)", color: "red",
      items: open.slice(0, 15).map(([n, cd, cr]) => ({
        lead: `${n}일째`, text: get(cr, "customer"),
        sub: `${md(cd)} 계약 · ${get(cr, "status") || "진행현황 없음"}`,
      })),
      count: open.length,
      more: Math.max(0, open.length - 15),
      hint: "오래 묵은 건부터 캐피탈에 진행 상황을 확인해 보세요.",
    });
  }

  // ---- 만기 예정 ----
  const months = Math.max(1, parseInt(expiryMonths, 10) || EXPIRY_MONTHS);
  const limit = addMonths(today, months);
  const exp = [];
  for (const cr of rows) {
    const d = expiryDate(cr);
    if (between(d, today, limit)) exp.push([d, cr]);
  }
  exp.sort((a, b) => a[0] - b[0]);
  secs.push({
    icon: "🔔", title: `${months}개월 이내 만기 예정`, color: "violet",
    items: exp.slice(0, 20).map(([d, cr]) => ({
      lead: `D-${days(d, today)}`, text: get(cr, "customer"),
      sub: [ymd(d), get(cr, "model")].filter(Boolean).join(" · "),
    })),
    count: exp.length,
    more: Math.max(0, exp.length - 20),
    empty: `${months}개월 안에 만기가 오는 고객이 없습니다`,
    // ⚠️ 파이썬과 **글자까지 같게** 둔다. 폰에 안 맞는 말(PC 의 탭 이름 등)은
    //    화면 쪽에서 바꿔 넣는다. 여기서 바꾸면 정답표 대조가 통째로 어긋나
    //    진짜 차이를 못 보게 된다 — 실제로 그렇게 5건이 한꺼번에 빨개졌다.
    hint: "[고객관리] 탭에서 [이력] 로 상담 내역을 보고 재계약을 준비하세요.",
  });

  return secs;
}

/** "2026년 09월 14일 ~ 09월 20일 주간 요약" — weekly.title_line 과 글자까지 같다. */
export function titleLine(today) {
  const [mon, sun] = weekRange(today);
  const p2 = (n) => String(n).padStart(2, "0");
  return `${mon.getFullYear()}년 ${p2(mon.getMonth() + 1)}월 ${p2(mon.getDate())}일`
       + ` ~ ${p2(sun.getMonth() + 1)}월 ${p2(sun.getDate())}일 주간 요약`;
}
