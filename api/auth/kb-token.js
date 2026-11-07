// 업무자료검색 웹의 쓸 토큰 — 그쪽 서버(kbsearch.vercel.app/api/auth/token)가 잠근 쪽지를 들고 온다.
//
//   POST /api/auth/kb-token  {h}  →  200 {access_token, expires_in, scope, email, missing}
//                                    401 {error:"signin"}   쪽지가 틀렸거나 구글에서 권한을 뺐다
//                                    503 {error:"not_configured"}
// 쪽지(callback.js 의 sealKb)는 이 서버만 연다. 쪽지 자체가 열쇠라 보낸 곳(Origin)은 따지지 않는다
// (서버끼리 묻는 길이다). 쪽지에서 나온 토큰은 드라이브 앱 전용 공간 권한만 갖는다.
const s = require("../_session.js");

function body(req) {
  if (req.body && typeof req.body === "object") return req.body;
  try { return JSON.parse(String(req.body || "{}")); } catch (e) { return {}; }
}

module.exports = async (req, res) => {
  if (req.method !== "POST") { s.send(res, 405, { error: "method" }); return; }
  if (!s.configured()) { s.send(res, 503, { error: "not_configured" }); return; }
  const h = String(body(req).h || "");
  const sess = h.length < 4096 ? s.unsealKb(h) : null;
  if (!sess || !sess.rt) { s.send(res, 401, { error: "signin" }); return; }
  let g;
  try {
    g = await s.google({ refresh_token: sess.rt, grant_type: "refresh_token" });
  } catch (e) { s.send(res, 502, { error: "google" }); return; }
  if (!g.ok || !g.j.access_token) {
    s.send(res, g.j.error === "invalid_grant" ? 401 : 502,
           g.j.error === "invalid_grant" ? { error: "signin", reason: "revoked" } : { error: g.j.error || "google" });
    return;
  }
  s.send(res, 200, {
    access_token: g.j.access_token,
    expires_in: g.j.expires_in || 3600,
    scope: g.j.scope || "",
    email: sess.email || "",
    missing: s.missingScopes(g.j.scope, s.KB_SCOPES),
  });
};
