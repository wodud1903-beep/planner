// 구글에서 돌아오는 곳 — 받은 코드를 토큰으로 바꾸고, 갱신 토큰을 쿠키에 잠가 둔 뒤
// 앱으로 되돌아간다. 결과는 ?auth=… 로 알린다(앱이 읽고 지운다).
//
//   ok          끝
//   partial     로그인은 됐지만 동의 화면에서 빠진 항목이 있다(→ 앱이 다시 체크하라고 안내)
//   denied      [취소] 를 눌렀다
//   expired     로그인 도중 너무 오래 걸렸거나 다른 창에서 시작한 것
//   norefresh   구글이 갱신 토큰을 안 줬다(드문 일 — 다시 하면 된다)
//   error / unconfigured
const s = require("../_session.js");

module.exports = async (req, res) => {
  const q = new URL(req.url, s.ORIGIN).searchParams;
  const saved = s.unseal(s.cookie(req, s.STATE)) || {};
  const ret = s.safeReturn(saved.ret);
  const back = (flag, extra = []) => {
    s.setCookies(res, [s.clearState(), ...extra]);
    s.redirect(res, `${s.ORIGIN}/?auth=${flag}${ret}`);
  };
  if (!s.configured()) { back("unconfigured"); return; }
  if (q.get("error")) { back(q.get("error") === "access_denied" ? "denied" : "error"); return; }
  // 위조 방지 — 우리가 방금 보낸 그 로그인인지(10분 안)
  if (!saved.st || saved.st !== q.get("state") || Date.now() - (saved.at || 0) > 10 * 60e3) {
    back("expired");
    return;
  }
  const code = q.get("code");
  if (!code) { back("error"); return; }
  let g;
  try {
    g = await s.google({ code, grant_type: "authorization_code", redirect_uri: s.REDIRECT });
  } catch (e) { back("error"); return; }
  if (!g.ok || !g.j.access_token) { back("error"); return; }
  const email = s.emailOf(g.j.id_token);
  let rt = g.j.refresh_token;
  if (!rt) {
    // 같은 계정으로 다시 로그인했는데 구글이 새 갱신 토큰을 안 줬다 → 갖고 있던 것을 쓴다
    const old = s.unseal(s.cookie(req, s.SESSION));
    if (old && old.rt && old.email && old.email === email) rt = old.rt;
  }
  if (!rt) { back("norefresh"); return; }
  const miss = s.missingScopes(g.j.scope);
  back(miss.length ? "partial" : "ok", [s.sessionCookie({ rt, email, at: Date.now() })]);
};
