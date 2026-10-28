// 로그인 서버 함수(api/auth/*) — 가짜 요청·가짜 구글로 돌려 본다.
//   node web/verify/verify_api.mjs
//
// 지키는 것: 한 번 로그인하면 쿠키의 갱신 토큰으로 팝업 없이 계속 토큰을 받는다 ·
// 쿠키는 화면 코드가 못 읽고(HttpOnly) 잠겨 있다 · 이 주소에서 온 요청만 받는다 ·
// 위조된 로그인 귀환은 거절한다 · 설정 전이면 503(앱은 예전 방식).
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { readFileSync } from "node:fs";
import { randomBytes } from "node:crypto";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const require = createRequire(import.meta.url);
let fails = 0;
const ok = (name, cond, extra = "") => {
  console.log((cond ? "  OK  " : "  ** FAIL **  ") + name + (extra ? "  " + extra : ""));
  if (!cond) fails++;
};

const load = (p) => {
  const full = join(ROOT, "api", p);
  delete require.cache[require.resolve(full)];
  return require(full);
};

function req({ method = "GET", url = "/", origin = "https://jyplanner.vercel.app", cookie = "" } = {}) {
  return { method, url, headers: { origin, cookie, host: "jyplanner.vercel.app" } };
}
function res() {
  const r = { statusCode: 200, headers: {}, body: "" };
  r.setHeader = (k, v) => { r.headers[k.toLowerCase()] = v; };
  r.end = (b) => { r.body = b || ""; r.done = true; };
  r.json = () => JSON.parse(r.body || "{}");
  r.cookies = () => [].concat(r.headers["set-cookie"] || []);
  r.cookieHeader = () => r.cookies().map((c) => c.split(";")[0]).join("; ");
  return r;
}
// 구글 토큰 창구를 가짜로 — 무엇을 보냈는지 적고, 정해 둔 답을 준다
let googleReply = null;
const sent = [];
globalThis.fetch = async (url, init) => {
  sent.push({ url, body: Object.fromEntries(new URLSearchParams(init.body)) });
  const { status = 200, json = {} } = googleReply || {};
  return { ok: status < 400, status, json: async () => json };
};
const idToken = (email) => "x." + Buffer.from(JSON.stringify({ email })).toString("base64url") + ".y";

// web/js/config.js 의 SCOPES(웹앱이 쓰는 권한)
const cfg = readFileSync(join(ROOT, "web", "js", "config.js"), "utf-8");
const WEB_SCOPES = [...cfg.slice(cfg.indexOf("SCOPES = [")).split("].join")[0]
  .matchAll(/"([^"]+)"/g)].map((m) => m[1]);

console.log("\n[1] 설정 전 — 503 · 앱은 예전 방식으로");
delete process.env.GOOGLE_CLIENT_SECRET;
delete process.env.SESSION_KEY;
let S = load("_session.js");
ok("설정 안 됨", !S.configured());
let r = res();
await load("auth/token.js")(req({ method: "POST" }), r);
ok("토큰 요청은 503", r.statusCode === 503 && r.json().error === "not_configured", r.statusCode);
r = res();
load("auth/start.js")(req({ url: "/api/auth/start?r=%23%2Fkb" }), r);
ok("[로그인] 은 앱으로 돌려보낸다(unconfigured)",
   r.statusCode === 302 && r.headers.location === "https://jyplanner.vercel.app/?auth=unconfigured#/kb",
   r.headers.location);

console.log("\n[2] 권한 목록이 웹앱과 같다");
ok("서버 SCOPES = web/js/config.js SCOPES", JSON.stringify(S.SCOPES) === JSON.stringify(WEB_SCOPES),
   WEB_SCOPES.join(" "));

console.log("\n[2-2] 클라이언트 비밀 하나만 넣어도 된다(열쇠는 비밀에서 뽑는다)");
process.env.GOOGLE_CLIENT_SECRET = "secret-for-test";
S = load("_session.js");
ok("비밀만 있어도 설정 끝", S.configured());
const viaSecret = S.seal({ rt: "rt-x" });
ok("그 열쇠로 잠그고 연다", S.unseal(viaSecret).rt === "rt-x");
process.env.GOOGLE_CLIENT_SECRET = "other-secret";
ok("비밀이 바뀌면 옛 쿠키는 못 연다(모두 다시 로그인)", S.unseal(viaSecret) === null);
process.env.GOOGLE_CLIENT_SECRET = "secret-for-test";

process.env.SESSION_KEY = randomBytes(32).toString("base64");
S = load("_session.js");
const start = load("auth/start.js");
const callback = load("auth/callback.js");
const token = load("auth/token.js");
const logout = load("auth/logout.js");

console.log("\n[3] 쿠키 잠금");
const sealed = S.seal({ rt: "rt-1", email: "me@x.com" });
ok("열면 그대로", S.unseal(sealed).rt === "rt-1");
ok("갱신 토큰이 쿠키 글자에 그대로 보이지 않는다", !sealed.includes("rt-1"));
ok("한 글자라도 고치면 못 연다", S.unseal(sealed.slice(0, -2) + (sealed.endsWith("A") ? "BB" : "AA")) === null);
const k0 = process.env.SESSION_KEY;
process.env.SESSION_KEY = randomBytes(32).toString("base64");
ok("열쇠가 다르면 못 연다", S.unseal(sealed) === null);
process.env.SESSION_KEY = k0;

console.log("\n[4] [로그인] — 구글 화면으로(팝업 아님)");
r = res();
start(req({ url: "/api/auth/start?r=%23%2Fcustomers&hint=me%40x.com" }), r);
const loc = new URL(r.headers.location || "http://x/");
ok("구글 로그인 화면으로 보낸다", r.statusCode === 302 && loc.host === "accounts.google.com", loc.host);
const P = loc.searchParams;
ok("갱신 토큰을 받게(access_type=offline · prompt=consent)",
   P.get("access_type") === "offline" && P.get("prompt") === "consent", P.get("prompt"));
ok("돌아올 곳", P.get("redirect_uri") === "https://jyplanner.vercel.app/api/auth/callback");
ok("권한 전부", P.get("scope") === WEB_SCOPES.join(" "));
ok("지난 계정을 알려 줘 계정 고르기를 건너뛴다", P.get("login_hint") === "me@x.com");
const stC = r.cookies().find((c) => c.startsWith("__Host-jyp_st="));
ok("위조 방지 값을 쿠키로(HttpOnly·Secure)", stC && /HttpOnly/.test(stC) && /Secure/.test(stC), stC);
const state = P.get("state");
const stCookie = r.cookieHeader();
r = res();
start(req({ url: "/api/auth/start?prompt=select_account&hint=me%40x.com" }), r);
const P2 = new URL(r.headers.location).searchParams;
ok("계정 바꾸기는 계정 고르는 화면부터", P2.get("prompt") === "select_account consent"
   && !P2.get("login_hint"), P2.get("prompt"));
ok("엉뚱한 돌아갈 곳은 받지 않는다", S.safeReturn("https://evil.com") === "#/agenda"
   && S.safeReturn("#/kb/3") === "#/kb/3" && S.safeReturn("#/a?x=<s>") === "#/agenda");

console.log("\n[5] 구글에서 돌아옴 — 코드 → 토큰 → 쿠키");
const FULL = WEB_SCOPES.filter((x) => x.startsWith("https://")).join(" ") + " openid";
googleReply = { json: { access_token: "at-1", expires_in: 3599, refresh_token: "rt-1",
                        id_token: idToken("me@x.com"), scope: FULL } };
r = res();
await callback(req({ url: `/api/auth/callback?code=c1&state=${state}`, cookie: stCookie }), r);
ok("앱으로 돌아간다(ok, 보던 화면)",
   r.headers.location === "https://jyplanner.vercel.app/?auth=ok#/customers", r.headers.location);
const exch = sent.at(-1).body;
ok("코드를 비밀과 함께 바꾼다", exch.code === "c1" && exch.client_secret === "secret-for-test"
   && exch.grant_type === "authorization_code");
const sess = r.cookies().find((c) => c.startsWith("__Host-jyp="));
ok("갱신 토큰 쿠키 — HttpOnly·Secure·오래(400일)", sess && /HttpOnly/.test(sess) && /Secure/.test(sess)
   && /Max-Age=34560000/.test(sess), sess);
ok("로그인 도중 쿠키는 지운다", r.cookies().some((c) => c.startsWith("__Host-jyp_st=;")));
const sessCookie = sess.split(";")[0];
r = res();
await callback(req({ url: `/api/auth/callback?code=c1&state=WRONG`, cookie: stCookie }), r);
ok("위조 값이 다르면 거절(expired)", /auth=expired/.test(r.headers.location), r.headers.location);
r = res();
await callback(req({ url: `/api/auth/callback?error=access_denied&state=${state}`, cookie: stCookie }), r);
ok("[취소] 는 denied", /auth=denied/.test(r.headers.location));
googleReply = { json: { access_token: "at-2", refresh_token: "rt-2", id_token: idToken("me@x.com"),
                        scope: "openid https://www.googleapis.com/auth/spreadsheets" } };
r = res();
await callback(req({ url: `/api/auth/callback?code=c2&state=${state}`, cookie: stCookie }), r);
ok("동의 화면에서 항목을 덜 체크했으면 partial(앱이 다시 안내)", /auth=partial/.test(r.headers.location));
googleReply = { json: { access_token: "at-3", id_token: idToken("me@x.com"), scope: FULL } };
r = res();
await callback(req({ url: `/api/auth/callback?code=c3&state=${state}`, cookie: stCookie }), r);
ok("갱신 토큰을 안 주면 norefresh", /auth=norefresh/.test(r.headers.location));
r = res();
await callback(req({ url: `/api/auth/callback?code=c3&state=${state}`,
                     cookie: stCookie + "; " + sessCookie }), r);
ok("같은 계정이 다시 로그인했으면 갖고 있던 갱신 토큰으로", /auth=ok/.test(r.headers.location));

console.log("\n[6] 쓸 토큰 — 팝업 없이 쿠키로");
googleReply = { json: { access_token: "fresh-1", expires_in: 3599, scope: FULL } };
r = res();
await token(req({ method: "POST", cookie: sessCookie }), r);
const tj = r.json();
ok("200 + 새 토큰 + 이메일", r.statusCode === 200 && tj.access_token === "fresh-1"
   && tj.email === "me@x.com" && tj.missing.length === 0, JSON.stringify(tj));
ok("구글에 갱신 토큰으로 묻는다", sent.at(-1).body.refresh_token === "rt-1"
   && sent.at(-1).body.grant_type === "refresh_token");
ok("쓸 때마다 쿠키 수명을 다시 늘린다", r.cookies().some((c) => c.startsWith("__Host-jyp=") && /Max-Age=34560000/.test(c)));
r = res();
await token(req({ method: "POST" }), r);
ok("쿠키 없으면 401(로그인)", r.statusCode === 401 && r.json().error === "signin");
r = res();
await token(req({ method: "POST", cookie: "__Host-jyp=garbage" }), r);
ok("고친 쿠키는 401", r.statusCode === 401);
r = res();
await token(req({ method: "POST", cookie: sessCookie, origin: "https://evil.com" }), r);
ok("다른 사이트에서 온 요청은 403", r.statusCode === 403);
r = res();
await token(req({ method: "GET", cookie: sessCookie }), r);
ok("GET 은 405", r.statusCode === 405);
googleReply = { status: 400, json: { error: "invalid_grant" } };
r = res();
await token(req({ method: "POST", cookie: sessCookie }), r);
ok("구글에서 권한을 뺐으면 401 + 쿠키 지움", r.statusCode === 401
   && r.cookies().some((c) => c.startsWith("__Host-jyp=;")));
googleReply = { status: 500, json: { error: "backend" } };
r = res();
await token(req({ method: "POST", cookie: sessCookie }), r);
ok("구글이 잠깐 탈났으면 502(로그인을 지우지 않는다)", r.statusCode === 502 && r.cookies().length === 0);

console.log("\n[7] 로그아웃");
r = res();
logout(req({ method: "POST", cookie: sessCookie }), r);
ok("쿠키를 지운다", r.statusCode === 200 && r.cookies().some((c) => c.startsWith("__Host-jyp=;")));

console.log(fails ? `\n${fails}건 실패` : "\n전부 통과");
process.exit(fails ? 1 : 0);
