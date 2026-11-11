// 로그아웃 — 이 브라우저의 쪽지를 지운다(이 기기에서 고친 것은 그대로 남는다).
import { clearSession, sameOrigin } from "../../lib/auth.js";
import { send } from "../../lib/http.js";

export default function handler(req, res) {
  if (req.method !== "POST") return send(res, 405, { error: "method" });
  if (!sameOrigin(req)) return send(res, 403, { error: "origin" });
  res.setHeader("Set-Cookie", [clearSession()]);
  send(res, 200, { ok: true });
}
