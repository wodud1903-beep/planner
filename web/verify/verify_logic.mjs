// 파이썬이 낸 정답표(vectors.json)를 JS 포팅이 맞히는지 대조한다.
// 옮긴 것이 원본과 조용히 어긋나는 것을 막는 유일한 장치다.
//
//   node web/verify/verify_logic.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as H from "../js/hangul.js";
import * as F from "../js/fmt.js";
import * as C from "../js/customers.js";
import * as D from "../js/drive.js";
import * as CM from "../js/commission.js";
import * as WK from "../js/weekly.js";

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

console.log("\n[6] 시트 풀기 (sheets.parse_rows)");
for (const [name, left, right, want] of V.parse_rows) {
  let got;
  try {
    const r = C.parseRows(left, right, "미출고차량");
    got = { headerRow: r.headerRow, rows: r.rows, summary: r.summary };
  } catch (e) {
    // 파이썬은 GoogleError 를 던지는데 여기선 이름이 다르다. '못 찾았다' 로 맞춘다.
    got = { error: e instanceof C.HeaderNotFound ? "Exception" : e.constructor.name };
  }
  eq(`parseRows: ${name}`, got, want);
}
console.log(`  ${V.parse_rows.length}개 대조`);

console.log("\n[7] 드라이브 폴더 지정 (파이썬에 짝이 없는 순수 계산이라 직접 적는다)");
// 폰에서 44자 id 를 손으로 치는 건 무리라 '링크 복사' 를 붙여넣게 했다.
// 붙여넣기 모양이 여러 가지라 여기서 못 박아 둔다.
for (const [input, kind, value] of [
  ["https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz01234", "id", "1AbCdEfGhIjKlMnOpQrStUvWxYz01234"],
  ["https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz01234?usp=sharing", "id", "1AbCdEfGhIjKlMnOpQrStUvWxYz01234"],
  ["https://drive.google.com/drive/u/0/folders/1AbCdEf_-Xyz", "id", "1AbCdEf_-Xyz"],
  ["https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUvWxYz01234", "id", "1AbCdEfGhIjKlMnOpQrStUvWxYz01234"],
  ["1AbCdEfGhIjKlMnOpQrStUvWxYz01234", "id", "1AbCdEfGhIjKlMnOpQrStUvWxYz01234"],
  ["고객정보", "name", "고객정보"],
  ["고객 서류 2026", "name", "고객 서류 2026"],
  ["  고객정보  ", "name", "고객정보"],
  // 파일 링크를 붙여넣으면 폴더가 아니다. 이름으로 오해하면 엉뚱한 걸 찾는다.
  ["https://drive.google.com/file/d/1AbCdEf/view", "bad", "https://drive.google.com/file/d/1AbCdEf/view"],
  ["https://example.com", "bad", "https://example.com"],
  ["", "none", ""],
  ["   ", "none", ""],
]) {
  eq(`parseFolderRef(${JSON.stringify(input)})`, D.parseFolderRef(input), { kind, value });
}
console.log("  12개 대조");

console.log("\n[8] 수당 계산 (commission.calc) — 1원도 어긋나면 안 된다");
for (const [price, rate, truck, pay, free, want] of V.commission_calc) {
  eq(`calc(${price}, ${rate}%, ${truck ? "화물" : "승용"}, 지급 ${pay}%, ${free ? "면세" : "과세"})`,
     CM.calc(price, rate, truck, pay, free), want);
}
console.log(`  ${V.commission_calc.length}개 대조`);

console.log("\n[9] 공유 수당율 표 풀기 (sheets.read_rates)");
for (const [rows, want] of V.parse_rates) {
  eq(`parseRates(${rows.length}줄)`, CM.parseRates(rows), want);
}
console.log(`  ${V.parse_rates.length}개 대조`);

console.log("\n[10] 견적서 수식에서 주소 뽑기 (sheets.doc_url)");
for (const [cell, want] of V.doc_url) eq(`docUrl(${JSON.stringify(cell)})`, C.docUrl(cell), want);
console.log(`  ${V.doc_url.length}개 대조`);

console.log("\n[11] 드라이브 주소에서 파일 id (파이썬에 짝이 없어 직접 적는다)");
for (const [u, want] of [
  ["https://drive.google.com/uc?export=view&id=1AbCdEf_-Xyz", "1AbCdEf_-Xyz"],
  ["https://drive.google.com/file/d/1AbCdEf/view?usp=sharing", "1AbCdEf"],
  ["https://drive.google.com/open?id=1AbCdEf", "1AbCdEf"],
  ["https://lh3.googleusercontent.com/d/1AbCdEf", "1AbCdEf"],
  ["https://example.com/a.png", ""],
  ["", ""],
]) eq(`driveIdOf(${JSON.stringify(u)})`, C.driveIdOf(u), want);
console.log("  6개 대조");

console.log("\n[12] 기본 수당율 표가 파이썬과 같은지 (시트를 못 읽을 때 쓰는 표)");
eq("DEFAULT_RATES 전체", CM.DEFAULT_RATES, V.default_rates);
console.log(`  현대 ${V.default_rates.hyundai.length}종 · 기아 ${V.default_rates.kia.length}종 대조`);

console.log("\n[13] 주간 요약 (weekly.sections)");
// 고객 줄을 파이썬이 만든 그대로 되살린다 (CustomerRow 흉내)
const wrows = V.weekly_rows.map((r) => ({ total: r.total, values: r.values }));
for (const [day, title, want] of V.weekly_sections) {
  const today = new Date(day + "T00:00:00");
  eq(`titleLine(${day})`, WK.titleLine(today), title);
  eq(`sections(${day})`, WK.sections(wrows, today), want);
}
console.log(`  ${V.weekly_sections.length}일치 대조`);

console.log("\n" + (fails ? `${fails}건 실패 / ${total}건` : `전부 통과 (${total}건)`));
process.exit(fails ? 1 : 0);
