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

// ------------------------------------------------------------------ 바뀐 곳(v1.35 — P1)
// 같은 달 판끼리만 견준다. 회사가 달 중간에 조건을 고치면(11/03 판 → 11/20 판) 바뀐 칸을 노랗게,
// 새로 생긴 모델은 '신규', 빠진 모델은 이름으로 알린다. 달이 바뀌면(11월 → 12월) 표시하지 않는다.
// 브랜드마다 '지금 판' 과 '전 판' 을 들고 있는다 — 새 표가 지금 판과 같으면 그대로(표시가 남는다).
// ⚠️ python/planner/promo.py 와 똑같이 — vectors.json 'promo_track' 으로 대조한다.
const KST_MS = 9 * 3600e3;
const RE_MONTH = /([0-9]{1,2})\s*월/;
const RE_MD = /([0-9]{1,2})\s*\/\s*([0-9]{1,2})/;
const p2 = (n) => String(n).padStart(2, "0");

export function titleMonth(title) {
  const t = String(title || "");
  let m = RE_MONTH.exec(t);
  if (m && +m[1] >= 1 && +m[1] <= 12) return +m[1];
  m = RE_MD.exec(t);
  if (m && +m[1] >= 1 && +m[1] <= 12) return +m[1];
  return 0;
}

export function titleDate(title) {
  const m = RE_MD.exec(String(title || ""));
  if (m && +m[1] >= 1 && +m[1] <= 12 && +m[2] >= 1 && +m[2] <= 31) return `${p2(+m[1])}/${p2(+m[2])}`;
  return "";
}

const kst = (ms) => new Date((Math.trunc(Number(ms) || 0)) + KST_MS);
const md = (ms) => { const d = kst(ms); return `${p2(d.getUTCMonth() + 1)}/${p2(d.getUTCDate())}`; };

/** block.rows 와 같은 자리의 열쇠 — 모델 줄은 '구역␟모델␟몇 번째', 나머지는 ''. */
export function rowKeys(block) {
  const seen = {}, out = [];
  for (const r of (block && block.rows) || []) {
    const cells = r.cells || [""];
    if (r.kind !== "model" || !cells[0]) { out.push(""); continue; }
    const base = (r.section || "") + "\x1f" + cells[0];
    const n = seen[base] || 0;
    seen[base] = n + 1;
    out.push(`${base}\x1f${n}`);
  }
  return out;
}

export function snap(block) {
  const rows = {}, order = [];
  const keys = rowKeys(block);
  ((block && block.rows) || []).forEach((r, i) => {
    const k = keys[i];
    if (k) { rows[k] = (r.cells || []).map(String); order.push(k); }
  });
  const t = String((block && block.title) || "");
  return { title: t, month: titleMonth(t), date: titleDate(t),
           headers: ((block && block.headers) || []).map(String), rows, order };
}

const canon = (s) => JSON.stringify([s.title, s.headers, s.order, (s.order || []).map((k) => (s.rows || {})[k])]);

export function sameMonth(prev, prevAt, cur, curAt) {
  const a = +prev.month || 0, b = +cur.month || 0;
  if (a && b) return a === b;
  const pa = kst(prevAt), ca = kst(curAt);
  return pa.getUTCFullYear() === ca.getUTCFullYear() && pa.getUTCMonth() === ca.getUTCMonth();
}

function colIds(headers) {
  const seen = {}, out = [];
  (headers || []).forEach((h0, i) => {
    const h = String(h0 || "").trim();
    if (!h) { out.push(`\x1f#${i}`); return; }
    const n = seen[h] || 0;
    seen[h] = n + 1;
    out.push(`${h}\x1f${n}`);
  });
  return out;
}

/** 전 판 → 지금 판: {changed: {줄 열쇠: [바뀐 칸 번호]}, new: [새 줄 열쇠], gone: [빠진 모델 이름], count}. */
export function diff(prev, cur) {
  const pid = {};
  colIds(prev.headers).forEach((c, j) => { pid[c] = j; });
  const cid = colIds(cur.headers);
  const prows = prev.rows || {}, crows = cur.rows || {};
  const changed = {}, added = [];
  for (const k of cur.order || []) {
    const cells = crows[k] || [];
    if (!(k in prows)) { added.push(k); continue; }
    const old = prows[k];
    const cols = [];
    for (let i = 1; i < cells.length; i++) {
      const id = i < cid.length ? cid[i] : `\x1f#${i}`;
      const j = id in pid ? pid[id] : -1;
      const was = j >= 0 && j < old.length ? old[j] : "";
      if (String(was).trim() !== String(cells[i]).trim()) cols.push(i);
    }
    if (cols.length) changed[k] = cols;
  }
  const gone = (prev.order || []).filter((k) => !(k in crows)).map((k) => (prows[k] || [""])[0]);
  return { changed, new: added, gone, count: Object.keys(changed).length + added.length };
}

/** 한 브랜드의 기록 → 보여 줄 바뀐 곳(없으면 null). 다른 달 판끼리는 null. */
export function markOf(h) {
  if (!h || typeof h !== "object") return null;
  const prev = h.prev, cur = h.cur;
  if (!prev || typeof prev !== "object" || !cur || typeof cur !== "object") return null;
  const pa = h.prev_at || 0, ca = h.cur_at || 0;
  if (!sameMonth(prev, pa, cur, ca)) return null;
  const d = diff(prev, cur);
  if (!d.count && !d.gone.length) return null;
  let a = prev.date || md(pa), z = cur.date || md(ca);
  if (a === z) { a = md(pa); z = md(ca); }        // 제목 기준일은 그대로인데 값이 바뀌었다 — 받은 날로
  d.from = a;
  d.to = z;
  return d;
}

/** 새로 읽은 표 → [새 기록, {브랜드 열쇠: 바뀐 곳 또는 null}]. 표에서 빠진 브랜드는 버린다. */
export function track(history, blocks, nowMs) {
  const old = history && typeof history === "object" ? history : {};
  const hist = {}, marks = {};
  for (const b of blocks || []) {
    const s = snap(b);
    let h = old[b.key];
    if (!h || typeof h !== "object" || !h.cur || typeof h.cur !== "object") {
      h = { cur: s, cur_at: Math.trunc(nowMs), prev: null, prev_at: 0 };
    } else if (canon(h.cur) !== canon(s)) {
      h = { cur: s, cur_at: Math.trunc(nowMs), prev: h.cur, prev_at: Math.trunc(h.cur_at || 0) };
    }
    hist[b.key] = h;
    marks[b.key] = markOf(h);
  }
  return [hist, marks];
}

/** 저장해 둔 기록만으로(새로 읽기 전) 보여 줄 바뀐 곳. */
export function marksFrom(history) {
  const out = {};
  if (history && typeof history === "object") for (const [k, h] of Object.entries(history)) out[k] = markOf(h);
  return out;
}

/** '11/03 → 11/20 바뀐 모델 3개 · 빠진 모델: A, B'(없으면 ''). */
export function changeText(m) {
  if (!m) return "";
  const bits = [`${m.from} → ${m.to} ` + (m.count ? `바뀐 모델 ${m.count}개` : "바뀜")];
  const gone = m.gone || [];
  if (gone.length) bits.push("빠진 모델: " + gone.slice(0, 5).join(", ") + (gone.length > 5 ? ` 외 ${gone.length - 5}개` : ""));
  return bits.join(" · ");
}
