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

console.log("\n[8] 아침 브리핑 알림 — 열쇠 · 구독 · 하루 한 번 · 내용");
const PU = load("_push.js");
const keyA = PU.vapid(), keyB = PU.vapid();
ok("알림 서명 열쇠는 클라이언트 비밀에서 늘 같게(설정할 값 없음)",
   keyA && keyA.publicKey === keyB.publicKey && Buffer.from(keyA.publicKey, "base64url").length === 65);
const webpush = require(join(ROOT, "node_modules", "web-push"));
const ecdh = (await import("node:crypto")).createECDH("prime256v1");
ecdh.generateKeys();
const SUB = { endpoint: "https://fcm.googleapis.com/fcm/send/abc123",
              keys: { p256dh: ecdh.getPublicKey().toString("base64url"),
                      auth: randomBytes(16).toString("base64url") } };
const det = webpush.generateRequestDetails(SUB, "{}", { vapidDetails: {
  subject: "https://jyplanner.vercel.app", publicKey: keyA.publicKey, privateKey: keyA.privateKey } });
ok("web-push 가 이 열쇠로 서명한다(VAPID)", String(det.headers.Authorization).includes("k=" + keyA.publicKey));
r = res();
load("push/key.js")(req({ method: "GET" }), r);
ok("저장소(Blob)를 연결하기 전이면 '준비 전'(503)", r.statusCode === 503 && r.json().error === "no_store");
process.env.BLOB_STORE_ID = "store_test";
r = res();
load("push/key.js")(req({ method: "GET" }), r);
ok("공개키를 준다", r.statusCode === 200 && r.json().publicKey === keyA.publicKey);

// 가짜 저장소(비공개 Blob 대신)
const mem = new Map();
let tag = 0;
PU._setStore({
  async put(id, rec, etag) {
    if (etag && (mem.get(id) || {}).etag !== etag) throw new Error("precondition");
    mem.set(id, { rec: JSON.parse(JSON.stringify(rec)), etag: "e" + (++tag), sealed: S.seal(rec) });
  },
  async get(id) { const x = mem.get(id); return x ? { rec: JSON.parse(JSON.stringify(x.rec)), etag: x.etag } : null; },
  async list() { return [...mem.keys()]; },
  async del(id) { mem.delete(id); },
});
const pushed = [];
let pushFail = null;
PU._setSend(async (sub, payload) => {
  if (pushFail) { const e = new Error("push"); e.statusCode = pushFail; throw e; }
  pushed.push({ sub, payload });
});
const subscribe = load("push/subscribe.js");
r = res();
await subscribe({ ...req({ method: "POST" }), body: { subscription: SUB } }, r);
ok("로그인 전이면 구독 못 함(401)", r.statusCode === 401);
r = res();
await subscribe({ ...req({ method: "POST", origin: "https://evil.com", cookie: sessCookie }),
                  body: { subscription: SUB } }, r);
ok("다른 사이트에서는 못 함(403)", r.statusCode === 403);
r = res();
await subscribe({ ...req({ method: "POST", cookie: sessCookie }), body: { subscription: { endpoint: "x" } } }, r);
ok("이상한 알림 주소는 거절(400)", r.statusCode === 400);
r = res();
await subscribe({ ...req({ method: "POST", cookie: sessCookie }), body: { subscription: SUB } }, r);
const id = PU.subId(SUB.endpoint);
ok("구독 — 알림 주소와 로그인(갱신 토큰)을 묶어 둔다", r.statusCode === 200 && mem.get(id)
   && mem.get(id).rec.rt === "rt-1" && mem.get(id).rec.sub.endpoint === SUB.endpoint);
ok("저장소에는 잠근 글로(갱신 토큰이 그대로 안 보인다)", !mem.get(id).sealed.includes("rt-1"));

// 가짜 구글 — 오늘 일정 · 할일 · 시트 · 뉴스
const CLOCK = new Date("2026-11-02T00:10:00Z");            // 한국 09:10 (월)
PU._setClock(() => CLOCK);
const HDR = ["순번", "고객명/사업자", "금융사", "차종", "차량가격", "금융수수료", "대리점 수당", "합계",
             "특판/대리점", "계약일(발주)", "출고일", "진행현황", "계약조건", "내용", "출고유형",
             "고객센터 번호", "사고접수연락처"];
const SHEETV = [HDR,
  ["1", "김상현", "KB캐피탈", "쏘나타", "", "", "", "", "", "2026. 9. 1", "2026. 11. 2", "출고", "", "", "", "", ""],
  ["2", "박영희", "KB캐피탈", "아이오닉5", "", "", "", "", "", "2026. 11. 2", "", "발주", "", "", "", "", ""],
  ["3", "한지민", "IM캐피탈", "G70", "", "", "", "", "", "", "2026. 11. 2", "취소", "", "", "", "", ""]];
let revoked = false;
const calUrls = [];
const NEWS = "# **주요 뉴스**\n|  **호재** | **SK하이닉스, 3분기 영업익 83조 돌파**[원문](https://x)*08:30* 본문 |\n"
  + "|  **악재** | **기업 경기 전망 2개월 연속 부정적**[원문](https://y) |";
const J = (o) => ({ ok: true, status: 200, headers: new Map([["content-type", "application/json"]]),
                    json: async () => o, text: async () => JSON.stringify(o) });
const T = (t) => ({ ok: true, status: 200, headers: new Map([["content-type", "text/plain"]]),
                    json: async () => ({}), text: async () => t });
globalThis.fetch = async (url, init = {}) => {
  const u = decodeURIComponent(String(url));
  if (u.startsWith("https://oauth2.googleapis.com/token")) {
    return revoked ? { ok: false, status: 400, json: async () => ({ error: "invalid_grant" }) }
                   : { ok: true, status: 200, json: async () => ({ access_token: "at-push" }) };
  }
  if (u.includes("calendarList")) return J({ items: [{ id: "primary", primary: true }] });
  if (u.includes("/calendar/v3/calendars/")) {
    calUrls.push(u);
    return J({ items: [{ summary: "김상현 고객 출고 안내 전화", start: { dateTime: "2026-11-02T01:30:00Z" } },
                       { summary: "지점 회의", start: { date: "2026-11-02" } }] });
  }
  if (u.includes("users/@me/lists")) return J({ items: [{ id: "L1" }] });
  if (u.includes("/lists/L1/tasks")) return J({ items: [
    { title: "박영희 심사서류 받기", due: "2026-11-02T00:00:00.000Z" },
    { title: "지난 할일", due: "2026-10-30T00:00:00.000Z" },
    { title: "다음 주 할일", due: "2026-11-09T00:00:00.000Z" }] });
  if (u.includes("spaces=appDataFolder") && u.includes("planner_web.json")) return J({ files: [{ id: "W1" }] });
  if (u.includes("spaces=appDataFolder")) return J({ files: [] });
  if (u.includes("/files/W1?alt=media")) return T(JSON.stringify({ sheetId: "SHEETX", sheetTab: "미출고차량" }));
  if (u.includes("values:batchGet")) return J({ valueRanges: [{ values: SHEETV }, { values: SHEETV.map(() => []) }] });
  if (u.includes("fields=modifiedTime")) return J({ modifiedTime: "2026-11-01T23:40:00Z" });   // 한국 08:40
  if (u.includes("/export?mimeType=text/plain")) return T(NEWS);
  return { ok: false, status: 404, headers: new Map(), json: async () => ({}), text: async () => "" };
};

const cron = load("push/cron.js");
const cronReq = () => ({ ...req({ method: "GET" }), headers: { "user-agent": "vercel-cron/1.0" } });
r = res();
await cron({ ...cronReq(), url: "/api/push/cron?check=1" }, r);
ok("?check=1 — 저장소에 닿는지만 본다(보내지 않음)", r.statusCode === 200 && r.json().store === "ok"
   && r.json().subscriptions === 1 && pushed.length === 0, JSON.stringify(r.json()));
r = res();
await cron({ ...req({ method: "GET" }), headers: { "user-agent": "curl" } }, r);
ok("예약 작업이 아니면 거절(403)", r.statusCode === 403);
PU._setClock(() => new Date("2026-11-01T23:30:00Z"));      // 한국 08:30 — 아직
r = res();
await cron(cronReq(), r);
ok("8:50 전이면 안 보낸다", r.json().skipped === "time" && pushed.length === 0);
PU._setClock(() => CLOCK);
r = res();
await cron(cronReq(), r);
ok("8:50 이 지난 첫 예약 작업에 보낸다", r.json().sent === 1 && pushed.length === 1, JSON.stringify(r.json()));
ok("일정은 한국 시각 오늘 하루만", calUrls[0].includes("timeMin=2026-11-02T00:00:00+09:00")
   && calUrls[0].includes("timeMax=2026-11-03T00:00:00+09:00"), calUrls[0]);
const msg = pushed[0].payload;
ok("제목 — 날짜와 요일", msg.title === "☀️ 11/2(월) 오늘 브리핑", msg.title);
const lines = msg.body.split("\n");
ok("첫 줄 — 일정·할일·출고 건수", lines[0] === "일정 2 · 할일 2 · 출고 1", lines[0]);
ok("일정 — 시각 순(종일은 앞)", lines.some((l) => l.startsWith("📅 지점 회의 / 10:30 김상현")));
ok("할일 — 오늘·지난 기한만(다음 주 것은 빼고)", lines.some((l) => l.startsWith("✅ 박영희 심사서류 받기 외 1 (지난 기한 1)")));
ok("오늘 출고 — 취소는 빼고", lines.includes("🚗 오늘 출고: 김상현(쏘나타)"));
ok("오늘 계약", lines.includes("📝 오늘 계약: 박영희"));
ok("오늘 뉴스 — 첫 기사 제목", lines.includes("📰 [호재] SK하이닉스, 3분기 영업익 83조 돌파 외 1"));
ok("누르면 홈으로 · 같은 날은 같은 꼬리표(알림이 겹치면 하나만)", msg.url === "./#/agenda" && msg.tag === "brief-2026-11-02");
r = res();
await cron(cronReq(), r);
ok("같은 날 두 번째 예약 작업은 건너뛴다", r.json().sent === 0 && pushed.length === 1);
PU._setClock(() => new Date("2026-11-03T03:30:00Z"));      // 한국 12:30 — 늦었다
r = res();
await cron(cronReq(), r);
ok("한낮이 지나면 그날은 안 보낸다", r.json().skipped === "time");
PU._setClock(() => new Date("2026-11-03T00:20:00Z"));
pushFail = 500;
r = res();
await cron(cronReq(), r);
ok("잠깐 탈났으면 다음 예약 작업이 다시 해 보게 둔다", r.json().failed === 1 && mem.get(id).rec.last !== "2026-11-03");
pushFail = 410;
r = res();
await cron(cronReq(), r);
ok("폰이 알림 주소를 버렸으면(410) 기록을 지운다", r.json().removed === 1 && !mem.has(id));
pushFail = null;
r = res();
await subscribe({ ...req({ method: "POST", cookie: sessCookie }), body: { subscription: SUB } }, r);
revoked = true;
PU._setClock(() => new Date("2026-11-04T00:20:00Z"));
r = res();
await cron(cronReq(), r);
ok("구글에서 권한을 뺐으면 기록을 지운다(토큰도 함께)", r.json().removed === 1 && !mem.has(id));
revoked = false;

// 지금 한 번 받아 보기 · 끄기
r = res();
await subscribe({ ...req({ method: "POST", cookie: sessCookie }), body: { subscription: SUB } }, r);
const tst = load("push/test.js");
r = res();
await tst({ ...req({ method: "POST", cookie: sessCookie }), body: { endpoint: SUB.endpoint } }, r);
ok("[지금 받아 보기] — 바로 보내고 내용도 돌려준다", r.statusCode === 200 && r.json().title.includes("오늘 브리핑")
   && pushed.at(-1).payload.tag === "brief-test");
r = res();
await load("push/unsubscribe.js")({ ...req({ method: "POST" }), body: { endpoint: SUB.endpoint } }, r);
ok("[알림 끄기] — 기록을 지운다", r.statusCode === 200 && !mem.has(id));
const empty = PU.compose(PU.kst(CLOCK), { events: [], tasks: [], sheet: null, news: null });
ok("아무것도 없는 날은 인사 한 줄", empty.body.endsWith("좋은 하루 보내세요!"), empty.body);

console.log(fails ? `\n${fails}건 실패` : "\n전부 통과");
process.exit(fails ? 1 : 0);
