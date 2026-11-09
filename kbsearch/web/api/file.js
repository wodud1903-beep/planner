// GET /api/file?id=첨부ID — 회사 공통 자료의 첨부(그림·PDF)를 이 주소로 받아 준다([카톡으로 보내기]).
//
// 왜: 폰의 '보내기' 화면에 그림을 파일로 넘기려면 브라우저가 그 파일을 받아야 하는데, 구글 드라이브는
// 다른 주소(우리 웹)에서 받는 것을 막는다(CORS). 그래서 서버가 대신 받아 같은 주소로 준다.
//   · **회사 공통 자료에 붙은 첨부만** 받는다(시트 목록에 있는 id) — 아무 파일이나 받아 주지 않게.
//   · 공개로 올린 회사 첨부라 로그인 없이 받는다. 그림은 드라이브 미리보기(최대 1600px), PDF 는 원본.
//   · 4MB 가 넘으면 413(함수가 줄 수 있는 크기 — 화면은 링크로 보낸다).
//   · 같은 id 는 내용이 안 바뀌므로(새로 올리면 새 id) 끝(edge)에 하루 묶어 둔다.
import { readKb } from "../lib/sheet.js";
import { send } from "../lib/http.js";

const MAX = 4 * 1024 * 1024;
const LIST_TTL = 5 * 60e3;
let known = null, knownAt = 0;               // id → 첨부 정보(함수가 살아 있는 동안 5분 묶어 둔다)

async function attachments(force = false) {
  if (!force && known && Date.now() - knownAt < LIST_TTL) return known;
  const items = await readKb();
  const m = new Map();
  for (const it of items) for (const f of it.files || []) m.set(f.id, f);
  known = m; knownAt = Date.now();
  return m;
}

/** 테스트용 — 묶어 둔 목록을 비운다. */
export function _reset() { known = null; knownAt = 0; }

const isPdf = (f) => /\.pdf$/i.test(f.name || "") || /pdf/i.test(f.mime || "");

export default async function handler(req, res) {
  if (req.method !== "GET") return send(res, 405, { error: "method" });
  const id = new URL(req.url, "http://x").searchParams.get("id") || "";
  if (!/^[\w-]{10,200}$/.test(id)) return send(res, 400, { error: "id" });
  let f;
  try {
    f = (await attachments()).get(id);
    if (!f && Date.now() - knownAt > 30e3) f = (await attachments(true)).get(id);   // 방금 붙인 첨부
  } catch (e) {
    return send(res, 502, { error: "자료 목록을 받지 못했습니다" });
  }
  if (!f) return send(res, 404, { error: "회사 자료의 첨부가 아닙니다" });
  const pdf = isPdf(f);
  if (pdf && f.size > MAX) return send(res, 413, { error: "too_big" });
  const url = pdf
    ? `https://drive.google.com/uc?export=download&id=${encodeURIComponent(id)}`
    : `https://drive.google.com/thumbnail?id=${encodeURIComponent(id)}&sz=w1600`;
  let r;
  try {
    r = await fetch(url, { redirect: "follow" });
  } catch (e) {
    return send(res, 502, { error: "드라이브에 닿지 못했습니다" });
  }
  if (!r.ok) return send(res, 502, { error: `드라이브 HTTP ${r.status}` });
  const buf = Buffer.from(await r.arrayBuffer());
  if (buf.length > MAX) return send(res, 413, { error: "too_big" });
  let type = String(r.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  if (pdf) {
    // 드라이브는 PDF 를 application/octet-stream 으로 주기도 한다 — 내용 머리(%PDF)로 확인
    if (buf.subarray(0, 4).toString("latin1") !== "%PDF") return send(res, 502, { error: "PDF 가 아닌 것이 왔습니다" });
    type = "application/pdf";
  } else if (!type.startsWith("image/")) {
    // 공개가 아니면 구글이 로그인 화면(HTML)을 준다
    return send(res, 502, { error: "그림이 아닌 것이 왔습니다(공개가 아닌 파일일 수 있습니다)" });
  }
  res.statusCode = 200;
  res.setHeader("Content-Type", type);
  res.setHeader("Content-Length", String(buf.length));
  res.setHeader("Cache-Control", "public, max-age=86400");
  res.setHeader("Vercel-CDN-Cache-Control", "max-age=86400");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.end(buf);
}
