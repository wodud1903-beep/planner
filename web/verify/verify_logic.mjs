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
import * as BD from "../js/board.js";
import * as SH from "../js/sheets.js";
import * as PR from "../js/promo.js";
import * as MT from "../js/ment.js";

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
const wrows = V.weekly_rows.map((r) => ({ row: r.row, total: r.total, values: r.values }));
for (const [day, title, want] of V.weekly_sections) {
  const today = new Date(day + "T00:00:00");
  eq(`titleLine(${day})`, WK.titleLine(today), title);
  eq(`sections(${day})`, WK.sections(wrows, today), want);
}
console.log(`  ${V.weekly_sections.length}일치 대조`);
// 대시보드 '다음 주 요약' — 다음 주 월요일 기준, 출고 예정·계약만
for (const [day, want] of V.weekly_next) {
  const nmon = WK.weekRange(new Date(day + "T00:00:00"), 1)[0];
  eq(`sections(${day} 다음 주)`, WK.sections(wrows, nmon, undefined,
                                          { word: "다음 주", weekOnly: true }), want);
}
// 복사용 평문(카톡에 붙여 넣는 글)
for (const [day, want] of V.weekly_text) {
  const today = new Date(day + "T00:00:00");
  eq(`renderText(${day})`, WK.renderText(WK.titleLine(today), WK.sections(wrows, today)), want);
}
console.log(`  다음 주 ${V.weekly_next.length}일 · 복사 글 ${V.weekly_text.length}일 대조`);

console.log("\n[13-2] 고객 진행 보드 (board.columns)");
for (const [st, want] of V.board_stage) eq(`stage(${st})`, BD.stage(st), want);
for (const [day, show, want] of V.board_columns) {
  eq(`columns(${day}, 취소 ${show ? "보임" : "숨김"})`,
     BD.columns(wrows, new Date(day + "T00:00:00"), show), want);
}
console.log(`  단계 ${V.board_stage.length}개 · 보드 ${V.board_columns.length}가지 대조`);

console.log("\n[14] 시트에 적을 날짜 서식 (sheets.fmt_date)");
// ⚠️ 0 을 안 채운다. "2026. 8. 14" 이지 "2026. 08. 14" 가 아니다.
for (const [iso, want] of V.fmt_sheet_date) {
  const d = iso ? new Date(iso + "T00:00:00") : null;
  eq(`fmtSheetDate(${iso})`, F.fmtSheetDate(d), want);
}
console.log(`  ${V.fmt_sheet_date.length}개 대조`);

console.log("\n[15] 고르는 칸 후보 (sheets.choices)");
eq("choices(고객줄)", C.choices(wrows), V.choices);
console.log(`  ${Object.keys(V.choices).length}칸 대조`);

console.log("\n[16] 열 번호 → 글자 (sheets.col_letter)");
for (const [i, want] of [[0, "A"], [1, "B"], [7, "H"], [15, "P"], [16, "Q"],
                         [17, "R"], [18, "S"], [19, "T"], [20, "U"], [25, "Z"],
                         [26, "AA"], [27, "AB"]]) {
  eq(`colLetter(${i})`, SH.colLetter(i), want);
}
console.log("  12개 대조");

console.log("\n[17] 수입차 프로모션 (promo.py) — 해석 · 검색 · 복사 글");
{
  const P = V.promo;
  const fx = JSON.parse(readFileSync(join(here, "fixtures", "promo.json"), "utf-8"));
  const blocks = PR.parse(fx.values, fx.merges);
  // 파이썬 정답표와 같은 열쇠 차례로(내용 비교 — 차례만 다른 것은 같은 것)
  const plain = PR.stripPrep(blocks).map(({ key, brand, title, groups, headers, col, rows }) =>
    ({ key, brand, title, groups, headers, col, rows }));
  eq("parse(블록)", plain, P.blocks);
  eq("parse(병합 모름 — 묶음 너비)", PR.parse(fx.values, []).map((b) => b.groups), P.blocks_nomerge);
  eq("headerRow", PR.headerRow(fx.values), P.header_row);
  eq("modelCount", PR.modelCount(blocks), P.model_count);
  for (const [q, brand, want, counts] of P.search) {
    const got = PR.search(blocks, q, brand).map(([b, rows]) => [b.key, rows.map((r) => [r.kind, r.cells[0]])]);
    eq(`search(${q}, ${brand})`, got, want);
    eq(`hitCount(${q})`, PR.hitCount(PR.search(blocks, q, "")), counts);
  }
  for (const [key, row, want] of P.row_text) {
    const b = blocks.find((x) => x.key === key);
    eq(`rowText(${key} ${row})`, PR.rowText(b, b.rows.find((r) => r.row === row)), want);
  }
  for (const [s, want] of P.is_number) eq(`isNumber(${s})`, PR.isNumber(s), want);
  for (const [s, want] of P.tone) eq(`toneOf(${s})`, PR.toneOf(s), want);
  for (const [s, want] of P.brand_token) eq(`brandToken(${s})`, PR.brandToken(s), want);
  for (const [s, want] of P.clean_title) eq(`cleanTitle(${s})`, PR.cleanTitle(s), want);
  console.log(`  ${P.search.length * 2 + P.row_text.length + P.is_number.length + P.tone.length + P.brand_token.length + P.clean_title.length + 4}개 대조`);
  // 읽기 전용 — 이 시트로 가는 쓰기는 보내기 전에 막힌다
  const u = `https://sheets.googleapis.com/v4/spreadsheets/${PR.DEF_SHEET_ID}/values:batchUpdate`;
  let blocked = 0;
  for (const m of ["POST", "PUT", "PATCH", "DELETE"]) {
    try { PR.readOnlyGuard(m, u); } catch (e) { if (e instanceof PR.ReadOnlySheet) blocked++; }
  }
  eq("읽기 전용 — 쓰기 4가지 모두 막힘", blocked, 4);
  let okGet = true;
  try { PR.readOnlyGuard("GET", u); PR.readOnlyGuard("POST", u.replace(PR.DEF_SHEET_ID, "MYSHEET")); } catch (e) { okGet = false; }
  eq("읽기 · 다른 시트 쓰기는 그대로", okGet, true);
}

console.log("\n[18] 프로모션 바뀐 곳 (promo.py track) — 같은 달 판끼리만");
{
  const T = V.promo_track;
  // 열쇠 차례는 보지 않는다(파이썬 dict · JS 객체 — 내용만 같으면 같은 것)
  const canon = (x) => Array.isArray(x) ? x.map(canon)
    : (x && typeof x === "object" ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, canon(x[k])])) : x);
  let hist = {};
  T.steps.forEach((st, i) => {
    const [h, marks] = PR.track(hist, PR.parse(st.values, T.merges), st.now);
    hist = h;
    eq(`track ${i + 1}단계 — 기록`, canon(h), canon(st.hist));
    eq(`track ${i + 1}단계 — 바뀐 곳`, canon(marks), canon(st.marks));
    const txt = Object.fromEntries(Object.entries(marks).map(([k, m]) => [k, PR.changeText(m)]));
    eq(`changeText ${i + 1}단계`, canon(txt), canon(st.text));
    eq(`marksFrom ${i + 1}단계(저장본만으로)`, canon(PR.marksFrom(h)), canon(st.marks));
  });
  for (const [t, m, d] of T.title_month) {
    eq(`titleMonth(${t})`, PR.titleMonth(t), m);
    eq(`titleDate(${t})`, PR.titleDate(t), d);
  }
  eq("rowKeys", PR.rowKeys({ rows: [
    { kind: "section", cells: ["전기차"], section: "" },
    { kind: "model", cells: ["EQA", "1"], section: "전기차" },
    { kind: "model", cells: ["EQA", "2"], section: "전기차" },
    { kind: "note", cells: ["안내"], section: "전기차" },
    { kind: "model", cells: ["", "x"], section: "" },
    { kind: "model", cells: ["EQA", "3"], section: "" }] }), T.row_keys);
  // 사람이 볼 것 — 2단계(11/20 판): 벤츠만 바뀜 · 3단계 그대로 · 4단계(12월) 없음 · 5단계(12월 안) 다시
  const S = T.steps;
  eq("11/20 판 — 벤츠만 표시", Object.entries(S[1].marks).filter(([, m]) => m).map(([k]) => k), ["benz"]);
  eq("11/20 판 — 바뀐 2 · 신규 1 · 빠짐 1", [Object.keys(S[1].marks.benz.changed).length, S[1].marks.benz.new.length,
    S[1].marks.benz.gone], [2, 1, ["GLC300 4M+ AV [26MY]"]]);
  eq("11/20 판 — 글", S[1].text.benz, "11/03 → 11/20 바뀐 모델 3개 · 빠진 모델: GLC300 4M+ AV [26MY]");
  eq("한 번 더 읽어도 표시가 남는다", canon(S[2].marks), canon(S[1].marks));
  eq("12월 판 — 달이 바뀌면 표시 없음", Object.values(S[3].marks).filter(Boolean).length, 0);
  eq("12/15 판 — 12월 안에서 바뀐 것은 다시 표시(벤츠 · 아우디)",
    Object.entries(S[4].marks).filter(([, m]) => m).map(([k]) => k).sort(), ["audi", "benz"]);
  eq("아우디(제목에 달이 없음)는 받은 날로", [S[4].marks.audi.from, S[4].marks.audi.to], ["12/01", "12/15"]);
  console.log(`  ${T.steps.length * 4 + T.title_month.length * 2 + 8}개 대조`);
}

console.log("\n[멘트] 폰 멘트 · 명함(v1.37) — PC 멘트복사와 같은 글 · 같은 명함 열쇠");
{
  eq("기본 문구 = PC greetings.DEFAULTS", MT.DEFAULTS, V.greetings_defaults);
  for (const [name, key] of V.bizcard_keys) eq(`명함 열쇠(${JSON.stringify(name)}) = PC bizcard.key_of`, await MT.bizKey(name), key);
  eq("명함 파일 이름", MT.cardFile("0123456789abcdef"), "bizcard_0123456789abcdef.png");
  eq("PC 에서 고친 적 없으면(파일 없음) 기본 문구", MT.liveGreetings(null).map((g) => g.name), V.greetings_defaults.map((g) => g.name));
  eq("깨졌거나 비었으면 기본 문구", MT.liveGreetings([{ name: "  " }, 3, null]).length, V.greetings_defaults.length);
  const saved = [{ name: " 우리금융 ", after: "A", miss: "M", at: "2026-11-01T00:00:00Z" },
                 { name: "지운채널", after: "x", miss: "y", at: "2026-10-01T00:00:00Z" },
                 { name: "되살린채널", after: "x", miss: "y", at: "2026-11-05T00:00:00Z" },
                 { name: "옛채널", after: 5, miss: null }];
  const dead = { "greetings.json": { "지운채널": "2026-10-02T00:00:00Z", "되살린채널": "2026-11-01T00:00:00Z",
                                     "옛채널": "2026-01-01T00:00:00Z" } };
  eq("저장한 것 — 이름 앞뒤 공백 빼고 · 지운 표식보다 나중에 고친 것만(PC tombs 와 같은 규칙)",
     MT.liveGreetings(saved, dead), [{ name: "우리금융", after: "A", miss: "M" }, { name: "되살린채널", after: "x", miss: "y" }]);
  eq("지운 표식이 없으면 다 보인다", MT.liveGreetings(saved).map((g) => g.name), ["우리금융", "지운채널", "되살린채널", "옛채널"]);
  eq("글이 아닌 값은 글로", MT.liveGreetings(saved).at(-1), { name: "옛채널", after: "5", miss: "" });
  eq("공유할 명함 파일 이름", [MT.cardName("에이원오토"), MT.cardName("A/B:C"), MT.cardName("")],
     ["명함_에이원오토.png", "명함_A B C.png", "명함_채널.png"]);
  console.log(`  ${V.bizcard_keys.length + 9}개 대조`);
}

console.log("\n" + (fails ? `${fails}건 실패 / ${total}건` : `전부 통과 (${total}건)`));
process.exit(fails ? 1 : 0);
