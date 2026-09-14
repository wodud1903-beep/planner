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

console.log("\n" + (fails ? `${fails}건 실패 / ${total}건` : `전부 통과 (${total}건)`));
process.exit(fails ? 1 : 0);
