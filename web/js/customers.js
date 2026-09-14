// 고객관리 — 시트를 푸는 규칙. planner/sheets.py 의 parse_rows 를 그대로 옮겼다.
//
// ⚠️ 여기 규칙이 파이썬과 어긋나면 PC 와 폰이 서로 다른 목록을 보여 준다.
//    그래서 파이썬이 낸 정답표(web/verify/vectors.json 의 parse_rows)를
//    JS 가 맞히도록 검사에 걸어 두었다. 고칠 때는 양쪽을 같이 고쳐야 한다.

// 열 인덱스(0=A) → 필드키. 파이썬 sheets.FIELDS 와 같은 순서·같은 뜻.
export const FIELDS = [
  [1, "customer", "고객명 / 사업자 / (실차주)"],
  [2, "finance", "금융사"],
  [3, "model", "차종"],
  [4, "price", "차량가격"],
  [5, "fee", "금융수수료"],
  [6, "incentive", "대리점 수당"],
  [8, "channel", "특판 / 대리점"],
  [9, "contract_date", "계약일(발주)"],
  [10, "deliver_date", "출고일"],
  [11, "status", "진행현황"],
  [12, "terms", "계약조건"],
  [13, "note", "내용"],
  [14, "kind", "출고유형"],
  [18, "doc", "견적서/계약서"],
];

export const COL_CENTER = 15;    // P 고객센터 번호
export const COL_ACCIDENT = 16;  // Q 사고접수 연락처
export const COL_MENT = 17;      // R 고객안내멘트 — 목록에서는 늘 빈 값이다

export class HeaderNotFound extends Error {}

/** A~Q 와 S~T 두 범위를 합쳐 { headerRow, rows, summary } 로 푼다. */
export function parseRows(left, right, tab = "") {
  left = left || [];
  right = right || [];

  // R 자리는 빈칸으로 채워 열 번호를 맞춘다 (멘트는 고객을 열 때 한 칸만 받는다)
  const values = [];
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    const a = (i < left.length ? [...left[i]] : []);
    const b = (i < right.length ? [...right[i]] : []);
    while (a.length < 17) a.push("");    // A..Q = 17칸
    a.push("");                          // R 자리
    while (b.length < 2) b.push("");     // S, T
    values.push(a.concat(b));
  }

  // 헤더 행 자동 탐지 — 위쪽 요약행 개수가 바뀌어도 안전하다.
  let headerIdx = -1;
  for (let i = 0; i < Math.min(30, values.length); i++) {
    const a = String(values[i][0] || "").trim();
    const b = String(values[i][1] || "").trim();
    if (a.startsWith("순번") && b.includes("고객명")) { headerIdx = i; break; }
  }
  if (headerIdx < 0) {
    throw new HeaderNotFound(
      `'${tab}' 시트에서 머리글(순번/고객명…)을 찾지 못했습니다.`);
  }

  const rows = [];
  for (let i = headerIdx + 1; i < values.length; i++) {
    const row = values[i];
    if (!row.some((c) => String(c || "").trim())) continue;
    const cell = (idx) => String((idx < row.length ? row[idx] : "") || "");
    const cr = {
      row: i + 1,
      seq: cell(0).trim(),
      total: cell(7).trim(),
      ment: cell(COL_MENT).replace(/\s+$/, ""),
      center: cell(COL_CENTER).trim(),
      accident: cell(COL_ACCIDENT).trim(),
      values: {},
    };
    for (const [ci, key] of FIELDS) cr.values[key] = cell(ci).trim();
    // 고객명이 없으면 빈 줄로 본다. 지운 행은 A열 순번이 수식이라 값이 남는다 —
    // '순번도 비어야' 건너뛰게 하면 지울 때마다 빈 줄이 쌓인다(파이썬에서 겪은 일).
    if (!cr.values.customer) continue;
    rows.push(cr);
  }

  // 상단 요약(N·O열) — 이미 받은 값에서 뽑는다. 요청을 더 보내지 않는다.
  const summary = [];
  for (let i = 0; i < Math.min(4, headerIdx); i++) {
    const row = values[i] || [];
    const label = String(row[13] || "").trim();
    const value = String(row[14] || "").trim();
    if (label) summary.push([label, value]);
  }
  return { headerRow: headerIdx + 1, rows, summary };
}

/** 진행현황 칩 후보 — 하드코딩하지 않고 **시트에 실제로 있는 값**에서 뽑는다. */
export function statuses(rows) {
  const seen = new Map();
  for (const r of rows) {
    const v = (r.values.status || "").trim();
    if (v) seen.set(v, (seen.get(v) || 0) + 1);
  }
  return [...seen.keys()].sort((a, b) => seen.get(b) - seen.get(a) || a.localeCompare(b, "ko"));
}


// ---------------------------------------------------------------- 견적서 이미지
/** '=IMAGE("https://…", 1)' 에서 주소만 뽑는다. sheets.py 의 doc_url 과 같은 규칙.
 *
 * ⚠️ S열은 **수식**이라 표시값(FORMATTED_VALUE)으로 읽으면 빈 문자열이다.
 *    그래서 목록에서는 '견적서 없음' 과 구분되지 않는다 — 따로 수식으로 읽어야 한다.
 *    (폰에서 견적서가 안 보이던 이유가 이것이었다) */
export function docUrl(cell) {
  const t = String(cell || "").trim();
  if (!t) return "";
  const m = t.match(/=\s*IMAGE\s*\(\s*"([^"]+)"/i);
  if (m) return m[1].trim();
  if (t.toLowerCase().startsWith("http")) return t.split(/\s+/)[0];
  return "";
}

/** 드라이브 주소에서 파일 id. 못 찾으면 "".
 *
 * 견적서는 드라이브에 올라가 있다. 주소를 <img src> 에 그냥 넣는 대신 id 를 뽑아
 * **API 로 받아 온다** — 그러면 파일 공개 설정과 상관없이, 내 권한으로 열린다. */
export function driveIdOf(url) {
  const t = String(url || "");
  let m = t.match(/[?&]id=([A-Za-z0-9_-]+)/);        // uc?export=view&id=…
  if (m) return m[1];
  m = t.match(/\/file\/d\/([A-Za-z0-9_-]+)/);        // /file/d/…/view
  if (m) return m[1];
  m = t.match(/\/d\/([A-Za-z0-9_-]+)/);
  if (m) return m[1];
  return "";
}
