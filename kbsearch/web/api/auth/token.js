// 쓸 토큰 — 쿠키의 쪽지를 jyplanner 에 내밀고 1시간짜리 토큰을 받아 준다. 팝업 없음.
//   POST /api/auth/token → 200 {access_token, expires_in, email, missing, sheets}
//        sheets = 시트 **보기**(읽기 전용) 권한이 있나 — 수입차 프로모션 화면(v1.34.2). 예전 로그인은 false.
//                          401 {error:"signin"}  로그인 전 · 권한을 뺐음
//                          502 {error}           jyplanner·구글이 잠깐 탈남(로그인은 그대로 둔다)
//                          403 {error:"blocked", email}  지점장이 사용을 제한한 계정(kb-v1.13)
import { BROKER, SESSION, cookie, sessionCookie, clearSession, goodSeal, sameOrigin } from "../../lib/auth.js";
import { send } from "../../lib/http.js";

export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, 405, { error: "method" });
  if (!sameOrigin(req)) return send(res, 403, { error: "origin" });
  const h = cookie(req, SESSION);
  if (!goodSeal(h)) return send(res, 401, { error: "signin" });
  let r, j = {};
  try {
    r = await fetch(`${BROKER}/api/auth/kb-token`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ h }),
    });
    j = await r.json().catch(() => ({}));
  } catch (e) {
    return send(res, 502, { error: "broker" });
  }
  if (r.status === 401) {
    res.setHeader("Set-Cookie", [clearSession()]);
    return send(res, 401, { error: "signin", reason: j.reason || "" });
  }
  // 지점장이 이 계정의 사용을 제한했다(kb-v1.13 — jyplanner 가 403 blocked 로 답한다). 로그인은 그대로 두고 알린다.
  if (r.status === 403 && j.error === "blocked") return send(res, 403, { error: "blocked", email: j.email || "" });
  if (r.status !== 200 || !j.access_token) return send(res, 502, { error: j.error || "broker" });
  res.setHeader("Set-Cookie", [sessionCookie(h)]);      // 쓰는 동안은 수명을 다시 늘린다
  send(res, 200, { access_token: j.access_token, expires_in: j.expires_in || 3600,
                   email: j.email || "", missing: j.missing || [], sheets: j.sheets === true });
}
