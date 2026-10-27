// 회사 공통 업무자료 — 일정관리기와 같은 시트의 '업무자료' 탭을 **로그인 없이** 읽는다.
// PC 프로그램 sheets_kb.read_kb_public 을 옮긴 것(같은 막이를 둔다).
//
// ⚠️ 이 주소는 탭 이름이 틀리면 오류 대신 첫 탭(수당율)을 준다 → 머리글이 업무자료 것일 때만 받는다.
// ⚠️ 시트가 잠기면 구글이 로그인 화면(HTML)을 200 으로 준다 → 종류(CSV)를 본다.
export const SHEET_ID = "1PSjqA7wvIBHusjYHFfD9cLKP-EbtdFrCkNqlZHz2jm0";
export const TAB = "업무자료";
const HEAD = ["카테고리", "금융사", "제목"];

export class NotPublic extends Error {}

// RFC 4180 — 따옴표 안의 줄바꿈·쉼표·"" 를 받는다(본문이 여러 줄이다).
export function parseCsv(text) {
  const rows = [];
  let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; } else q = false;
      } else cell += ch;
    } else if (ch === '"') q = true;
    else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += ch;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

function cleanFiles(files) {
  const out = [];
  for (const f of Array.isArray(files) ? files : []) {
    if (!f || typeof f !== "object") continue;
    const id = String(f.id || "").trim(), name = String(f.name || "").trim();
    if (!id || !name || id.startsWith("local-")) continue;   // 아직 안 올린 것은 남이 못 받는다
    out.push({ id, name, mime: String(f.mime || "").trim(), size: Math.max(0, parseInt(f.size, 10) || 0) });
  }
  return out;
}

function filesFrom(cell, title) {
  try {
    const o = String(cell || "").trim() ? JSON.parse(cell) : null;
    if (!o || typeof o !== "object" || String(o.title || "").trim() !== title) return [];
    return cleanFiles(o.files);
  } catch (e) {
    return [];
  }
}

export function itemsFromRows(rows) {
  const out = [];
  for (const r of rows) {
    const v = [...r.map((x) => String(x ?? "").trim()), "", "", "", "", "", "", ""];
    const [category, finance, title, tags, body, checks] = v;
    if (!title || title === "제목") continue;
    const it = {
      category, finance, title, tags,
      body: String(r[4] ?? "").split("\n").map((l) => l.trimEnd()).join("\n").trim(),
    };
    void checks;                // 체크리스트는 검색 화면에 쓰지 않는다(PC 와 같다)
    const files = filesFrom(r[6], title);
    if (files.length) it.files = files;
    out.push(it);
  }
  return out;
}

export async function readKb(fetchImpl = fetch) {
  const url = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq`
    + `?tqx=out:csv&headers=1&sheet=${encodeURIComponent(TAB)}`;
  let r;
  try {
    r = await fetchImpl(url, { redirect: "follow" });
  } catch (e) {
    throw new NotPublic("시트에 연결하지 못했습니다");
  }
  const ctype = (r.headers.get("content-type") || "").toLowerCase();
  if (r.status !== 200 || !ctype.includes("csv")) {
    throw new NotPublic(`시트를 공개로 읽지 못했습니다 (HTTP ${r.status})`);
  }
  const rows = parseCsv((await r.text()).replace(/^﻿/, ""));
  if (!rows.length) return [];
  const head = rows[0].map((x) => String(x).trim());
  if (HEAD.some((h, i) => head[i] !== h)) {
    throw new NotPublic("업무자료 탭이 아닌 것이 왔습니다(탭 이름이 바뀌었을 수 있습니다)");
  }
  return itemsFromRows(rows.slice(1));
}
