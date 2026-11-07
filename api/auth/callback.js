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

const escAttr = (v) => String(v).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// 업무자료검색 웹의 로그인(start.js 의 app=kb) — 잠근 쪽지를 그쪽 서버로 **POST** 로 건넨다.
// 주소창(?…)에 실으면 방문 기록에 남으므로 폼으로 보낸다. 받는 쪽은 위조 방지 값(n)을 맞춰 본다.
async function finishKb(q, saved, res) {
  const back = (flag) => {
    s.setCookies(res, [s.clearState()]);
    s.redirect(res, `${s.KB_ORIGIN}/?auth=${flag}`);
  };
  if (!s.configured()) { back("unconfigured"); return; }
  if (q.get("error")) { back(q.get("error") === "access_denied" ? "denied" : "error"); return; }
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
  if (!g.j.refresh_token) { back("norefresh"); return; }
  const email = s.emailOf(g.j.id_token);
  const h = s.sealKb({ rt: g.j.refresh_token, email, at: Date.now() });
  const f = s.missingScopes(g.j.scope, s.KB_SCOPES).length ? "partial" : "ok";
  s.setCookies(res, [s.clearState()]);
  res.statusCode = 200;
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Referrer-Policy", "no-referrer");
  res.end(`<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>업무자료검색으로 돌아가는 중</title></head>
<body style="font-family:sans-serif;text-align:center;padding-top:60px">
<form id="f" method="post" action="${escAttr(s.KB_ORIGIN)}/api/auth/accept">
<input type="hidden" name="h" value="${escAttr(h)}"><input type="hidden" name="n" value="${escAttr(saved.n || "")}">
<input type="hidden" name="f" value="${f}">
<p>로그인했습니다. 업무자료검색으로 돌아갑니다…</p><button type="submit">돌아가기</button></form>
<script>document.getElementById("f").submit();</script></body></html>`);
}

module.exports = async (req, res) => {
  const q = new URL(req.url, s.ORIGIN).searchParams;
  const saved = s.unseal(s.cookie(req, s.STATE)) || {};
  if (saved.app === "kb") { await finishKb(q, saved, res); return; }
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
