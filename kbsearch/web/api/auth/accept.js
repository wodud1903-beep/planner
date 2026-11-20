// jyplanner 가 로그인 뒤에 잠근 쪽지를 폼(POST)으로 건네는 곳 — 시작 값이 맞으면 쿠키에 둔다.
//   POST h=쪽지 & n=시작 값 & f=ok|partial  →  303 /?auth=ok|partial|expired
import { cookie, STATE, sessionCookie, clearState, goodSeal, goodNonce, formBody, redirect } from "../../lib/auth.js";

export default async function handler(req, res) {
  if (req.method !== "POST") return redirect(res, 303, "/?auth=error");
  const b = await formBody(req);
  const want = cookie(req, STATE);
  if (!goodNonce(want) || String(b.n || "") !== want || !goodSeal(b.h)) {
    return redirect(res, 303, "/?auth=expired", [clearState()]);
  }
  const f = b.f === "partial" ? "partial" : "ok";
  redirect(res, 303, `/?auth=${f}`, [sessionCookie(b.h), clearState()]);
}
