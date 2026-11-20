// 수입차 프로모션(v1.34.2) — planner/promo.py 의 해석·검색을 그대로 옮긴 것. 일정관리기 웹과 업무자료검색 웹이
// **같은 파일**을 쓴다(kbsearch/web/public/promo.js 는 이 파일의 사본이다 — 고치면 둘 다).
//
// ⚠️ PC 와 결과가 한 줄이라도 달라지면 안 된다. 파이썬이 낸 정답표(web/verify/vectors.json 의 promo)를
//    검사가 대조한다(tools/gen_vectors.py 로 다시 뽑는다).
//
// 시트 모양: B:G 벤츠 · I:N BMW · P:U 아우디 — 4행이 열 제목, 2~3행이 제목·묶음 제목, 5행부터 모델.
//   첫 칸만 있는 짧은 줄 = 구역(전기차 라인업 …), 여러 줄 글 = 안내(재구매 · 이번달 특별 이슈).
//
// ⚠️ **읽기만 한다.** 지점장: "절대 할인내역이 수정되면 안 된다." 이 모듈은 시트에 쓰는 함수가 없고,
//    readOnlyGuard 로 이 시트 주소에 가는 GET 이 아닌 요청을 막는다(sheets.js · 업무자료검색 app.js 가 부른다).
import { prepare, matchesPrepared } from "./hangul.js";

export const DEF_SHEET_ID = "1W8maHjHzkyEf2QgAPi5agvHp08OLYRvMa-A9TPRl6-M";
export const DEF_TAB = "수입차 프로모션";
export const READ_COLS = "A1:AZ";
export const STALE_MS = 10 * 60e3;          // 화면을 다시 열 때 이만큼 지났으면 새로 읽는다

// ------------------------------------------------------------------ 읽기 전용
const PROTECTED = new Set([DEF_SHEET_ID]);
export class ReadOnlySheet extends Error {}

/** 이 스프레드시트를 읽기 전용으로(설정에서 다른 프로모션 시트를 골랐을 때도). */
export function protect(sheetId) {
  const s = String(sheetId || "").trim();
  if (s.length >= 20) PROTECTED.add(s);
}
export const isProtected = (sheetId) => PROTECTED.has(String(sheetId || "").trim());

/** 쓰기 요청(GET 이 아닌 것)이 읽기 전용 시트로 가면 ReadOnlySheet — 보내기 **전에** 부른다. */
export function readOnlyGuard(method, url) {
  if (["GET", "HEAD", "OPTIONS"].includes(String(method || "GET").toUpperCase())) return;
  const u = String(url || "");
  for (const sid of PROTECTED) {
    if (u.includes(sid)) throw new ReadOnlySheet("수입차 프로모션 시트는 읽기 전용입니다 — 이 앱은 그 시트를 고치지 않습니다.");
  }
}

/** 읽을 주소들(값 · 병합/탭 번호). 둘 다 GET 이다. */
export function readUrls(sheetsApi, sheetId, tab) {
  const t = String(tab || "").trim();
  const rng = encodeURIComponent(t ? `'${t}'!${READ_COLS}` : READ_COLS);
  return {
    values: `${sheetsApi}/${sheetId}/values/${rng}?valueRenderOption=FORMATTED_VALUE&dateTimeRenderOption=FORMATTED_STRING`,
    meta: `${sheetsApi}/${sheetId}?fields=${encodeURIComponent("sheets(properties(title,sheetId),merges)")}`,
  };
}

/** 메타 응답 → {merges:[[r0,r1,c0,c1]], gid} — 그 탭 것만(탭이 비면 첫 탭). */
export function metaOf(j, tab) {
  const t = String(tab || "").trim();
  for (const sh of (j && j.sheets) || []) {
    const p = sh.properties || {};
    if (t && p.title !== t) continue;
    return {
      merges: (sh.merges || []).map((g) => [g.startRowIndex || 0, g.endRowIndex || 0,
                                            g.startColumnIndex || 0, g.endColumnIndex || 0]),
      gid: Number.isInteger(p.sheetId) ? p.sheetId : null,
    };
  }
  return { merges: [], gid: null };
}

export const sheetUrl = (sheetId, gid) =>
  `https://docs.google.com/spreadsheets/d/${sheetId}/edit` + (Number.isInteger(gid) ? `#gid=${gid}` : "");

// ------------------------------------------------------------------ 브랜드
export const BRANDS = [
  ["benz", "벤츠", ["benz", "벤츠", "mercedes", "메르세데스"]],
  ["bmw", "BMW", ["bmw", "비엠", "비엠더블유"]],
  ["audi", "아우디", ["audi", "아우디"]],
  ["volvo", "볼보", ["volvo", "볼보"]],
  ["porsche", "포르쉐", ["porsche", "포르쉐"]],
  ["lexus", "렉서스", ["lexus", "렉서스"]],
  ["lr", "랜드로버", ["landrover", "land rover", "랜드로버"]],
];
const BRAND_WORDS = {};
for (const [k, , ws] of BRANDS) for (const w of ws) if (!w.includes(" ")) BRAND_WORDS[w] = k;
const isKo = (s) => /^[가-힣]/.test(s);
const squash = (s) => String(s || "").split(/\s+/).join("").toLowerCase();

export function brandOf(text) {
  const low = String(text || "").toLowerCase().replace(/\s+/g, "");
  for (const [key, name, words] of BRANDS) {
    if (words.some((w) => low.includes(w.replace(/ /g, "")))) return [key, name];
  }
  return null;
}

export function brandToken(tok) {
  const t = squash(tok);
  if (!t) return "";
  if (Object.prototype.hasOwnProperty.call(BRAND_WORDS, t)) return BRAND_WORDS[t];
  if (isKo(t)) {
    for (const [w, k] of Object.entries(BRAND_WORDS)) if (isKo(w) && w.startsWith(t)) return k;
  }
  return "";
}

// ------------------------------------------------------------------ 글 다듬기
const cell = (row, i) => String((row || [])[i] ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
// 파이썬 str.strip() 과 같게 — 앞뒤 공백(줄바꿈 포함)
const strip = (s) => String(s).replace(/^\s+|\s+$/g, "");
const stripNl = (s) => String(s).replace(/^[\n ]+|[\n ]+$/g, "");

export function cleanTitle(s) {
  return String(s || "").replace(/\*{2,}/g, " ").replace(/\s+/g, " ").trim();
}
export const cleanHead = (s) => String(s || "").replace(/\n/g, " ").replace(/[ \t]+/g, " ").trim();

export function isNumber(s) {
  const t = strip(String(s || ""));
  return !!t && /\d/.test(t) && /^[\d,.\s%+\-원만]+$/.test(t);
}

const BAD = ["재고없음", "재고 없음", "종료", "단종", "재고 0"];
const NEW = ["신형", "연식변경", "신규"];
export function toneOf(s) {
  const t = strip(String(s || ""));
  if (!t || isNumber(t)) return "";
  if (BAD.some((w) => t.includes(w))) return "red";
  if (NEW.some((w) => t.includes(w))) return "blue";
  return "";
}

// ------------------------------------------------------------------ 해석
function runs(cells) {
  const out = [];
  let start = null;
  const all = [...cells, ""];
  for (let i = 0; i < all.length; i++) {
    if (strip(String(all[i] ?? ""))) { if (start === null) start = i; }
    else if (start !== null) { if (i - start >= 2) out.push([start, i - start]); start = null; }
  }
  return out;
}

const RE_HEAD = /모델|차\s*종|차량\s*가/;
export function headerRow(values) {
  let best = -1;
  const v = values || [];
  for (let i = 0; i < Math.min(10, v.length); i++) {
    const hits = (v[i] || []).filter((c) => RE_HEAD.test(String(c ?? ""))).length;
    if (hits >= 2) return i;
    if (hits === 1 && best < 0) best = i;
  }
  return best >= 0 ? best : 3;
}

function mergeSpans(merges, row, c0, width) {
  const out = {};
  for (const m of merges || []) {
    const [r0, r1, k0, k1] = (m || []).map((x) => parseInt(x, 10));
    if ([r0, r1, k0, k1].some((x) => !Number.isFinite(x))) continue;
    if (r0 <= row && row < r1 && c0 <= k0 && k0 < c0 + width) out[k0 - c0] = Math.max(1, Math.min(k1, c0 + width) - k0);
  }
  return out;
}

function kindOf(cells) {
  const first = strip(cells[0]);
  const rest = cells.slice(1).filter((c) => strip(c));
  if (rest.length || !first) return "model";
  if (first.includes("\n") || [...first].length > 40) return "note";
  if (!/[A-Za-z0-9]/.test(first)) return "section";
  return "model";
}

/** 시트 값 → 블록 [{key, brand, title, groups[[시작,너비,글]], headers, rows[{kind, cells, section, row}], col}]. */
export function parse(values, merges = []) {
  values = values || [];
  if (!values.length) return [];
  const hi = headerRow(values);
  const heads = (values[hi] || []).map((c) => String(c ?? ""));
  const blocks = [];
  const used = new Set();
  runs(heads).forEach(([c0, width], bi) => {
    const headers = [];
    for (let k = 0; k < width; k++) headers.push(cleanHead(cell(heads, c0 + k)));
    const titles = [], groups = [];
    for (let r = 0; r < hi; r++) {
      const cells = [];
      for (let k = 0; k < width; k++) cells.push(strip(cell(values[r], c0 + k)));
      const filled = cells.map((t, k) => [k, t]).filter(([, t]) => t);
      if (!filled.length) continue;
      if (filled.length === 1 && filled[0][0] === 0) {
        const t = cleanTitle(filled[0][1]);
        if (t && t !== ".") titles.push(t);
        continue;
      }
      const spans = mergeSpans(merges, r, c0, width);
      filled.forEach(([k, t], j) => {
        const nxt = j + 1 < filled.length ? filled[j + 1][0] : width;
        groups.push([k, k in spans ? spans[k] : nxt - k, cleanTitle(t)]);
      });
    }
    let b = brandOf(titles.join(" ")) || brandOf(groups.map((g) => g[2]).join(" "));
    if (!b || used.has(b[0])) {
      const first = titles.length ? (titles[0].split(/\s+/).filter(Boolean)[0] || "") : "";
      b = [`b${bi}`, first || `브랜드 ${bi + 1}`];
    }
    used.add(b[0]);
    const rows = [];
    let section = "";
    for (let r = hi + 1; r < values.length; r++) {
      let cells = [];
      for (let k = 0; k < width; k++) cells.push(cell(values[r], c0 + k));
      if (!cells.some((c) => strip(c))) continue;
      const kind = kindOf(cells);
      if (kind === "section") section = strip(cells[0]);
      cells = cells.map((c) => (kind !== "note" ? strip(c) : stripNl(c)));
      if (kind === "model") cells = cells.map((c) => c.replace(/\s*\n\s*/g, " "));
      const hay = cells[0] + (section && kind !== "section" ? "\x1f" + section : "");
      rows.push({ kind, cells, section: kind !== "section" ? section : "", row: r + 1, prep: prepare(hay) });
    }
    blocks.push({ key: b[0], brand: b[1], title: titles.join(" · "), groups, headers, rows, col: c0 });
  });
  return blocks;
}

export const modelCount = (blocks) =>
  (blocks || []).reduce((n, b) => n + b.rows.filter((r) => r.kind === "model" && r.cells[0]).length, 0);

// ------------------------------------------------------------------ 찾기
export function splitQuery(query) {
  const brands = new Set(), rest = [];
  for (const tok of String(query || "").split(/\s+/).filter(Boolean)) {
    const k = brandToken(tok);
    if (k) brands.add(k); else rest.push(tok);
  }
  return [brands, rest.join(" ")];
}

/** 보일 것 [[블록, 줄 목록]] — 맞는 줄 + 그 줄이 든 구역 이름. 브랜드는 고른 것(또는 친 것)만. */
export function search(blocks, query = "", brand = "") {
  const [typed, text] = splitQuery(query);
  const allow = typed.size ? typed : (brand ? new Set([brand]) : null);
  const out = [];
  for (const b of blocks || []) {
    if (allow && !allow.has(b.key)) continue;
    let rows;
    if (!text.trim()) rows = [...b.rows];
    else {
      rows = [];
      const shown = new Set();
      const secRows = {};
      for (const r of b.rows) if (r.kind === "section") secRows[r.cells[0]] = r;
      for (const r of b.rows) {
        if (r.kind === "section") continue;
        if (!matchesPrepared(r.prep, text)) continue;
        const sec = r.section || "";
        if (sec && !shown.has(sec) && secRows[sec]) { shown.add(sec); rows.push(secRows[sec]); }
        rows.push(r);
      }
    }
    if (rows.length) out.push([b, rows]);
  }
  return out;
}

export function hitCount(found) {
  const o = {};
  for (const [b, rows] of found) o[b.key] = rows.filter((r) => r.kind === "model").length;
  return o;
}

/** 한 줄을 카톡에 붙이기 좋게 — 'E300 … · 차량가격 99,000,000 · MBF 13,900,000 …'. */
export function rowText(block, row) {
  const cells = (row && row.cells) || [];
  if (!row || row.kind !== "model") return strip(cells[0] || "");
  const parts = cells[0] ? [cells[0]] : [];
  for (let k = 1; k < cells.length; k++) {
    const v = strip(cells[k]);
    if (!v) continue;
    const h = k < block.headers.length ? block.headers[k] : "";
    parts.push(h ? `${h} ${v}` : v);
  }
  return parts.join(" · ");
}

/** 저장해 둘 모양 — prep(검색용 다듬은 글)은 빼고 둔다(다시 parse 하면 생긴다). */
export function stripPrep(blocks) {
  return (blocks || []).map((b) => ({ ...b, rows: b.rows.map(({ prep, ...r }) => r) }));
}
