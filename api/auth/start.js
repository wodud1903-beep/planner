// [로그인] — 구글 로그인 화면으로 보낸다(팝업이 아니라 화면을 넘긴다).
//
// 팝업은 폰 브라우저가 막거나 늦게 떠서 단추를 두세 번 눌러야 했다. 화면을 넘기면
// 막힐 일이 없다. 끝나면 /api/auth/callback 으로 돌아와 앱으로 되돌아간다.
//
//   GET /api/auth/start?r=#/보던화면&prompt=select_account&hint=메일
//
// prompt=consent 를 꼭 넣는다 — 그래야 구글이 '갱신 토큰' 을 준다(두 번째 로그인부터는
// 넣지 않으면 안 준다). 로그인은 몇 달에 한 번이라 동의 화면이 한 번 더 나와도 괜찮다.
const crypto = require("node:crypto");
const s = require("../_session.js");

module.exports = (req, res) => {
  const q = new URL(req.url, s.ORIGIN).searchParams;
  const ret = s.safeReturn(q.get("r"));
  if (!s.configured()) { s.redirect(res, `${s.ORIGIN}/?auth=unconfigured${ret}`); return; }
  const st = crypto.randomBytes(18).toString("base64url");
  const choose = q.get("prompt") === "select_account";
  const p = new URLSearchParams({
    client_id: s.CLIENT_ID,
    redirect_uri: s.REDIRECT,
    response_type: "code",
    scope: s.SCOPES.join(" "),
    access_type: "offline",
    include_granted_scopes: "true",
    prompt: choose ? "select_account consent" : "consent",
    state: st,
  });
  // 지난번 계정을 알려 주면 계정 고르는 화면을 건너뛴다(계정 바꾸기일 때는 안 준다)
  const hint = q.get("hint") || "";
  if (hint && !choose && /^[^\s@]+@[^\s@]+$/.test(hint)) p.set("login_hint", hint);
  s.setCookies(res, [s.stateCookie({ st, ret, at: Date.now() })]);
  s.redirect(res, `${s.AUTH_URL}?${p}`);
};
