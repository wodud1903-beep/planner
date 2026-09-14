// 파이썬이 낸 정답표(vectors.json)를 JS 포팅이 맞히는지 대조한다.
// 옮긴 것이 원본과 조용히 어긋나는 것을 막는 유일한 장치다.
//
//   node web/verify/verify_logic.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as H from "../js/hangul.js";
import * as F from "../js/fmt.js";

const here = dirname(fileURLToPath(import.meta.url));
const V = JSON.parse(readFileSync(join(here, "vectors.json"), "utf-8"));

let fails = 0, total = 0;
function eq(name, got, want, extra = "") {
  total++;
  const same = JSON.stringify(got) === JSON.stringify(want);
  if (!same) {
    fails++;
    console.log(`  ** FAIL **  ${name}  → ${JSON.stringify(got)} (정답 ${JSON.stringify(want)}) ${extra}`);
  }
  return same;
}

console.log("\n[1] 초성 검색 (hangul.py)");
for (const [item, want] of V.hangul_chosung) eq(`chosung(${item})`, H.chosung(item), want);
for (const [item, q, want] of V.hangul_matches) eq(`matches(${item}, ${q})`, H.matches(item, q), want);
for (const [item, q, want] of V.hangul_rank) eq(`rank(${item}, ${q})`, H.rank(item, q), want);
console.log(`  ${V.hangul_chosung.length + V.hangul_matches.length + V.hangul_rank.length}개 대조`);

console.log("\n[2] 미리 다듬어 둔 것으로 찾아도 결과가 같다");
for (const [item, q, want] of V.hangul_matches) {
  eq(`matchesPrepared(${item}, ${q})`, H.matchesPrepared(H.prepare(item), q), want);
}
console.log(`  ${V.hangul_matches.length}개 대조`);

console.log("\n[3] 돈 (sheets.digits_only / fmt_money)");
for (const [s, want] of V.digits_only) eq(`digitsOnly(${JSON.stringify(s)})`, F.digitsOnly(s), want);
for (const [s, want] of V.fmt_money) eq(`fmtMoney(${JSON.stringify(s)})`, F.fmtMoney(s), want);
console.log(`  ${V.digits_only.length + V.fmt_money.length}개 대조`);

console.log("\n[4] 날짜 (sheets.parse_date)");
for (const [s, want] of V.parse_date) {
  const d = F.parseDate(s);
  eq(`parseDate(${JSON.stringify(s)})`, d ? F.fmtDate(d) : null, want);
}
console.log(`  ${V.parse_date.length}개 대조`);

console.log("\n[5] 계약조건에서 개월 (sheets.contract_months)");
for (const [s, want] of V.contract_months) eq(`contractMonths(${JSON.stringify(s)})`, F.contractMonths(s), want);
console.log(`  ${V.contract_months.length}개 대조`);

console.log("\n" + (fails ? `${fails}건 실패 / ${total}건` : `전부 통과 (${total}건)`));
process.exit(fails ? 1 : 0);
