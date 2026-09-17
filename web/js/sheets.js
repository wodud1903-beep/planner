// 구글 시트 읽기 — planner/sheets.py 의 읽기 부분만 옮긴 것.
import { SHEETS_API } from "./config.js";
import { token, setOffline, STATE } from "./auth.js";
import { digitsOnly } from "./fmt.js";

export class NeedSignIn extends Error {}
export class WrongAccount extends Error {}
export class Offline extends Error {}
/** 시트/탭 이름이 틀렸을 때. 화면이 '탭 고르기' 를 띄울 수 있게 따로 둔다. */
export class BadRange extends Error {}
/** 토큰에 그 권한이 안 붙어 있을 때. **다시 로그인하면 풀린다** —
 *  '계정이 다르다'(WrongAccount) 와 처방이 정반대라 반드시 갈라야 한다.
 *  권한 목록을 늘리면 기존 토큰에는 새 권한이 없어서 꼭 한 번은 여기로 온다. */
export class NeedScope extends Error {}

/** 구글이 돌려준 진짜 메시지를 뽑는다.
 *
 * ⚠️ 이걸 버리면 안 된다. 'HTTP 400' 만 보여 주면 시트 주소가 틀린 건지,
 *    탭 이름이 틀린 건지, 범위가 격자 밖인지 알 길이 없다 —
 *    실제로 그것 때문에 한 번 막혔다. */
async function detail(r) {
  try {
    const j = await r.clone().json();
    const e = j && j.error;
    if (!e) return "";
    if (typeof e === "string") return e;
    return e.message || "";
  } catch (x) { return ""; }
}

const rng = (tab, a1) => encodeURIComponent(`'${tab}'!${a1}`);

// 한 번 조용히 다시 받아 한 번만 재시도한다. 두 번은 안 한다.
async function call(url, body = null) {
  let tok = await token();
  if (!tok) throw new NeedSignIn();
  const go = () => fetch(url, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: "Bearer " + tok,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  let r;
  try { r = await go(); } catch (e) { setOffline(true); throw new Offline(); }
  if (r.status === 401) {
    tok = await token({ interactive: false });
    if (!tok) throw new NeedSignIn();
    try { r = await go(); } catch (e) { setOffline(true); throw new Offline(); }
  }
  // 403 은 토큰 문제가 아니라 '이 계정으로는 못 연다' 는 뜻이다. 다시 로그인해도 소용없다.
  if (r.status === 403) {
    const m = await detail(r);
    if (/insufficient|scope/i.test(m)) throw new NeedScope(m);
    throw new WrongAccount();
  }
  if (!r.ok) {
    const msg = await detail(r);
    // 400 + 'Unable to parse range' 는 거의 언제나 **탭 이름이 다른 것**이다.
    if (r.status === 400 && /unable to parse range|파싱|parse range/i.test(msg)) {
      throw new BadRange(msg);
    }
    if (r.status === 404) throw new BadRange(msg || "그 스프레드시트를 찾지 못했습니다.");
    throw new Error(msg
      ? `시트를 읽지 못했습니다 (HTTP ${r.status})\n${msg}`
      : `시트를 읽지 못했습니다 (HTTP ${r.status})`);
  }
  return r.json();
}

export async function values(sheetId, tab, a1) {
  const url = `${SHEETS_API}/${sheetId}/values/${rng(tab, a1)}`
            + `?valueRenderOption=FORMATTED_VALUE&dateTimeRenderOption=FORMATTED_STRING`;
  const j = await call(url);
  return j.values || [];
}

export async function batch(sheetId, tab, ranges) {
  const qs = ranges.map((a) => "ranges=" + rng(tab, a)).join("&");
  const url = `${SHEETS_API}/${sheetId}/values:batchGet?${qs}`
            + `&valueRenderOption=FORMATTED_VALUE&dateTimeRenderOption=FORMATTED_STRING`;
  const j = await call(url);
  return (j.valueRanges || []).map((v) => v.values || []);
}

// ---------------------------------------------------------------- 업무자료(KB)
// A:F = 카테고리 | 금융사 | 제목 | 태그 | 본문 | 체크리스트(줄바꿈)
export async function readKb(sheetId, tab) {
  const rows = await values(sheetId, tab, "A1:F");
  const out = [];
  for (const row of rows) {
    const title = (row[2] || "").trim();
    if (!title || title === "제목") continue;   // 머리글 줄은 값으로 걸러낸다
    out.push({
      category: (row[0] || "").trim(),
      finance: (row[1] || "").trim(),
      title,
      tags: (row[3] || "").trim(),
      body: (row[4] || "").replace(/\r\n/g, "\n"),
      checklist: (row[5] || "").split("\n").map((x) => x.trim()).filter(Boolean),
    });
  }
  return out;
}

// ---------------------------------------------------------------- 고객관리
// A1:Q + S1:T 두 범위를 한 번에 받는다.
//
// ⚠️ U열(고객ID)을 여기 넣으면 안 된다. 시트가 T 에서 끝나면 U 범위는 문법은
//    맞아도 격자 밖이라 400 이 나고, **묶인 고객 목록까지 통째로 실패한다**
//    (파이썬 쪽에 그 사고 기록이 있다 — sheets.py 의 read_uids 주석).
// ⚠️ R열(고객안내멘트)도 뺀다. 한 건에 20줄 가까워서 폰에서 제일 큰 낭비다.
//    고객을 열 때 그 한 칸만 readMent 로 받는다.
export async function readCustomers(sheetId, tab) {
  const [left, right] = await batch(sheetId, tab, ["A1:Q", "S1:T"]);
  return { left, right };
}

/** S열 한 칸을 **수식 그대로** 읽는다 — 견적서 이미지 주소를 되찾으려면 이것뿐이다.
 *
 * ⚠️ 셀 안 그림은 =IMAGE() 수식이라 표시값으로 읽으면 빈 문자열이 온다.
 *    그래서 목록의 doc 칸만 보고는 '견적서가 없다' 와 구분되지 않는다.
 *    (파이썬 쪽 read_docs 에 같은 사고 기록이 있다) */
export async function readDocFormula(sheetId, tab, row) {
  try {
    const url = `${SHEETS_API}/${sheetId}/values/${rng(tab, `S${row}:S${row}`)}`
              + `?valueRenderOption=FORMULA`;
    const j = await call(url);
    return String(((j.values || [])[0] || [])[0] || "").trim();
  } catch (e) {
    if (e instanceof NeedSignIn || e instanceof WrongAccount || e instanceof NeedScope) throw e;
    return "";
  }
}

/** R열 한 칸만 — 고객을 열 때 부른다. 실패하면 빈 문자열(멘트만 못 볼 뿐이다). */
export async function readMent(sheetId, tab, row) {
  try {
    const v = await values(sheetId, tab, `R${row}:R${row}`);
    return ((v[0] || [])[0] || "").replace(/\s+$/, "");
  } catch (e) {
    if (e instanceof NeedSignIn || e instanceof WrongAccount) throw e;
    return "";
  }
}

/** 이 스프레드시트에 실제로 있는 탭 이름들. 탭 이름이 틀렸을 때 골라 쓰게 한다. */
export async function tabNames(sheetId) {
  const j = await call(`${SHEETS_API}/${sheetId}`
    + `?fields=${encodeURIComponent("properties.title,sheets.properties.title")}`);
  return {
    title: (j.properties && j.properties.title) || "",
    tabs: (j.sheets || []).map((x) => x.properties && x.properties.title).filter(Boolean),
  };
}


// ---------------------------------------------------------------- 고객 고치기
//
// ⚠️ 여기가 이 앱에서 **처음으로 시트에 쓰는 자리**다. 잘못 쓰면 남의 시트의
//    수식이 값으로 덮이고 되돌리기 어렵다. 규칙을 새로 만들지 않고
//    planner/sheets.py 의 _write_cells 를 글자 그대로 옮긴다.
//
//  · 직접기재 열만, **칸 단위로** 쓴다. 줄을 통째로 쓰면 수식 칸이 덮인다.
//    수식 칸 = A(순번) H(합계) P(고객센터) Q(사고접수) R(안내멘트) T(등록완료).
//  · S열(견적서)은 **절대 안 쓴다.** =IMAGE() 수식이라 표시값이 빈 문자열이고,
//    그걸 되돌려 쓰면 그림이 지워진다(PC 쪽에도 같은 사고 기록이 있다).
//  · 금액은 콤마를 떼고 숫자로 — 안 그러면 시트 통화 서식이 깨진다.
//  · valueInputOption 은 USER_ENTERED.

/** 0=A, 1=B … 열 번호를 글자로. */
export function colLetter(i) {
  let n = Number(i), out = "";
  do { out = String.fromCharCode(65 + (n % 26)) + out; n = Math.floor(n / 26) - 1; }
  while (n >= 0);
  return out;
}

/** 고객 한 줄의 직접기재 칸을 고친다. values 에 **든 키만** 쓴다. */
export async function writeCells(sheetId, tab, row, values, fields, moneyKeys) {
  const data = [];
  for (const [ci, key] of fields) {
    if (!(key in values)) continue;             // 안 고친 칸은 안 보낸다
    let v = values[key];
    if (moneyKeys.includes(key)) v = digitsOnly(v);   // 콤마를 떼고 숫자로
    data.push({ range: `'${tab}'!${colLetter(ci)}${row}`, values: [[v]] });
  }
  if (!data.length) return 0;
  await call(`${SHEETS_API}/${sheetId}/values:batchUpdate`,
             { valueInputOption: "USER_ENTERED", data });
  return data.length;
}

/** 그 줄의 A~Q + S~T 를 다시 읽는다 — 저장 직전 '그 사이 바뀌었나' 확인용. */
export async function readRow(sheetId, tab, row) {
  const [left, right] = await batch(sheetId, tab, [`A${row}:Q${row}`, `S${row}:T${row}`]);
  return { left: left || [], right: right || [] };
}
