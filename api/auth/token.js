// 쓸 토큰 — 쿠키의 갱신 토큰으로 1시간짜리 액세스 토큰을 새로 받아 준다.
// 켤 때와 만료 몇 분 전에 앱이 부른다. 팝업도 화면 이동도 없다.
//
//   POST /api/auth/token  →  200 {access_token, expires_in, scope, email, missing}
//                            401 {error:"signin"}   로그인 전이거나 구글에서 권한을 뺐다
//                            503 {error:"not_configured"}  비밀 설정 전(앱은 예전 방식)
const s = require("../_session.js");

module.exports = async (req, res) => {
  if (!s.guard(req, res)) return;
  const sess = s.unseal(s.cookie(req, s.SESSION));
  if (!sess || !sess.rt) { s.send(res, 401, { error: "signin" }); return; }
  let g;
  try {
    g = await s.google({ refresh_token: sess.rt, grant_type: "refresh_token" });
  } catch (e) { s.send(res, 502, { error: "google" }); return; }
  if (!g.ok || !g.j.access_token) {
    if (g.j.error === "invalid_grant") {
      // 구글 계정에서 앱 권한을 뺐거나 오래 안 써서 끊겼다 → 다시 로그인
      s.setCookies(res, [s.clearSession()]);
      s.send(res, 401, { error: "signin", reason: "revoked" });
      return;
    }
    s.send(res, 502, { error: g.j.error || "google" });
    return;
  }
  // 쓰는 동안은 쿠키 수명을 다시 늘린다 — 매일 쓰면 끊기지 않는다
  s.setCookies(res, [s.sessionCookie({ ...sess, at: Date.now() })]);
  s.send(res, 200, {
    access_token: g.j.access_token,
    expires_in: g.j.expires_in || 3600,
    scope: g.j.scope || "",
    email: sess.email || "",
    missing: s.missingScopes(g.j.scope),
  });
};
