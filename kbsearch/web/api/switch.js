// POST /api/switch — 관리자만 서버를 켜고 끈다(구글 로그인 없이, 비밀번호로).
//   { password }               → 비밀번호만 확인 { ok, on, message, at }
//   { password, on, message }  → 켜기/끄기
// 비밀번호는 Vercel 환경 변수 KB_ADMIN_PASSWORD 에만 있다(코드·저장소에는 없다).
import crypto from "node:crypto";
import { readState, writeState, storeReady } from "../lib/state.js";
import { send } from "../lib/http.js";

const digest = (s) => crypto.createHash("sha256").update(String(s), "utf8").digest();
const same = (a, b) => crypto.timingSafeEqual(digest(a), digest(b));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function body(req) {
  if (req.body && typeof req.body === "object") return req.body;
  if (typeof req.body === "string") { try { return JSON.parse(req.body); } catch (e) { return {}; } }
  return {};
}

export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, 405, { error: "POST 로만 됩니다" });
  const want = process.env.KB_ADMIN_PASSWORD || "";
  if (!want) return send(res, 500, { error: "관리자 비밀번호가 아직 설정되지 않았습니다" });
  const b = await body(req);
  if (!same(b.password || "", want)) {
    await sleep(1200);              // 마구 넣어 보기를 늦춘다
    return send(res, 401, { error: "비밀번호가 맞지 않습니다" });
  }
  if (typeof b.on !== "boolean") {
    const s = await readState();
    return send(res, 200, { ok: true, ...s });
  }
  if (!storeReady()) {
    return send(res, 503, { error: "스위치 저장소(Vercel Blob)가 아직 연결되지 않았습니다" });
  }
  try {
    const s = await writeState(b.on, b.message);
    return send(res, 200, { ok: true, ...s, store: true });
  } catch (e) {
    return send(res, 500, { error: "저장하지 못했습니다: " + String((e && e.message) || e) });
  }
}
