// [구글 동기화] 의 로그인 — 시작 값(n)을 쿠키에 적고 jyplanner 의 로그인 길로 보낸다(lib/auth.js).
//   GET /api/auth/login?hint=메일&prompt=select_account
import { randomBytes } from "node:crypto";
import { BROKER, stateCookie, redirect } from "../../lib/auth.js";

export default function handler(req, res) {
  const q = new URL(req.url, "http://x").searchParams;
  const n = randomBytes(18).toString("base64url");
  const p = new URLSearchParams({ app: "kb", n });
  const hint = q.get("hint") || "";
  if (hint && /^[^\s@]+@[^\s@]+$/.test(hint)) p.set("hint", hint);
  if (q.get("prompt") === "select_account") p.set("prompt", "select_account");
  redirect(res, 302, `${BROKER}/api/auth/start?${p}`, [stateCookie(n)]);
}
