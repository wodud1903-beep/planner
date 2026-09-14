// 구글 시트 읽기 — planner/sheets.py 의 읽기 부분만 옮긴 것.
import { SHEETS_API } from "./config.js";
import { token, setOffline, STATE } from "./auth.js";

export class NeedSignIn extends Error {}
export class WrongAccount extends Error {}
export class Offline extends Error {}

const rng = (tab, a1) => encodeURIComponent(`'${tab}'!${a1}`);

// 한 번 조용히 다시 받아 한 번만 재시도한다. 두 번은 안 한다.
async function call(url) {
  let tok = await token();
  if (!tok) throw new NeedSignIn();
  let r;
  try {
    r = await fetch(url, { headers: { Authorization: "Bearer " + tok } });
  } catch (e) {
    setOffline(true);
    throw new Offline();
  }
  if (r.status === 401) {
    tok = await token({ interactive: false });
    if (!tok) throw new NeedSignIn();
    try {
      r = await fetch(url, { headers: { Authorization: "Bearer " + tok } });
    } catch (e) { setOffline(true); throw new Offline(); }
  }
  // 403 은 토큰 문제가 아니라 '이 계정으로는 못 연다' 는 뜻이다. 다시 로그인해도 소용없다.
  if (r.status === 403) throw new WrongAccount();
  if (!r.ok) throw new Error(`시트를 읽지 못했습니다 (HTTP ${r.status})`);
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
