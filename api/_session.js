// 로그인 세션 — 구글 '갱신 토큰' 을 암호화해 쿠키에 담아 둔다(웹앱 jyplanner 전용).
//
// 왜 서버가 필요한가
//   브라우저만으로는 1시간짜리 액세스 토큰밖에 못 받는다. 그것도 '조용히 다시 받기' 를
//   팝업으로 하는데, 폰 브라우저는 누르지 않은 팝업을 막는다 → 켤 때마다 [로그인].
//   갱신 토큰은 클라이언트 비밀(client secret)이 있어야 받고 쓸 수 있다. 비밀은
//   브라우저에 둘 수 없으므로 여기(Vercel 함수)에 둔다.
//
// 지키는 것
//   · 갱신 토큰은 **화면 코드가 못 읽는** 쿠키(HttpOnly)에, AES-256-GCM 으로 잠가서 둔다.
//   · 쿠키는 이 주소(__Host-)에만, https 로만(Secure) 간다.
//   · 토큰을 내주는 요청은 이 주소에서 온 것(Origin)만 받는다.
//   · 비밀이 아직 없으면(설정 전) 503 — 웹앱은 예전 방식으로 돈다.
//
// 환경 변수(Vercel → Settings → Environment Variables)
//   GOOGLE_CLIENT_SECRET  구글 콘솔의 웹 클라이언트 '클라이언트 보안 비밀'(이것 하나면 된다)
//   SESSION_KEY           (있으면) 쿠키를 잠그는 열쇠(32바이트를 base64 로).
//                         없으면 클라이언트 비밀에서 뽑는다 — 비밀을 바꾸면 모두 다시 로그인.
//   PUBLIC_ORIGIN         (있으면) 이 앱의 주소. 없으면 https://jyplanner.vercel.app
//
// ⚠️ 이 파일은 밑줄(_)로 시작해 Vercel 이 주소로 내보내지 않는다(공용 도우미).

const crypto = require("node:crypto");

const CLIENT_ID = process.env.GOOGLE_CLIENT_ID
  || "593737105209-o24o5moa3k2lo3hqivkgl6stpogpqgnf.apps.googleusercontent.com";
const ORIGIN = (process.env.PUBLIC_ORIGIN || "https://jyplanner.vercel.app").replace(/\/$/, "");
const REDIRECT = ORIGIN + "/api/auth/callback";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";

// web/js/config.js 의 SCOPES 와 **같아야 한다**(검사가 대조한다)
const SCOPES = [
  "openid",
  "email",
  "https://www.googleapis.com/auth/spreadsheets",
  "https://www.googleapis.com/auth/drive.readonly",
  "https://www.googleapis.com/auth/calendar.readonly",
  "https://www.googleapis.com/auth/tasks",
  "https://www.googleapis.com/auth/drive.appdata",
];

const SESSION = "__Host-jyp";        // 갱신 토큰
const STATE = "__Host-jyp_st";       // 로그인 도중 잠깐(위조 방지 값 + 돌아갈 화면)
const SESSION_AGE = 400 * 24 * 3600; // 크롬이 쿠키 수명을 400일로 자른다 — 쓸 때마다 다시 늘린다
const STATE_AGE = 10 * 60;

function key() {
  const b = Buffer.from(process.env.SESSION_KEY || "", "base64");
  if (b.length === 32) return b;
  const sec = process.env.GOOGLE_CLIENT_SECRET || "";
  if (!sec) return null;
  // 따로 정한 열쇠가 없으면 클라이언트 비밀에서 뽑는다(설정할 것이 하나로 준다)
  return Buffer.from(crypto.hkdfSync("sha256", sec, "jyplanner", "session-cookie-v1", 32));
}

function configured() {
  return !!(process.env.GOOGLE_CLIENT_SECRET && key());
}

function seal(obj) {
  const iv = crypto.randomBytes(12);
  const c = crypto.createCipheriv("aes-256-gcm", key(), iv);
  const ct = Buffer.concat([c.update(JSON.stringify(obj), "utf8"), c.final()]);
  return Buffer.concat([iv, c.getAuthTag(), ct]).toString("base64url");
}

function unseal(s) {
  try {
    const b = Buffer.from(String(s || ""), "base64url");
    if (b.length < 29) return null;
    const d = crypto.createDecipheriv("aes-256-gcm", key(), b.subarray(0, 12));
    d.setAuthTag(b.subarray(12, 28));
    return JSON.parse(Buffer.concat([d.update(b.subarray(28)), d.final()]).toString("utf8"));
  } catch (e) {
    return null;                     // 열쇠가 바뀌었거나 누가 고친 쿠키
  }
}

function cookie(req, name) {
  for (const part of String(req.headers.cookie || "").split(/;\s*/)) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i) === name) return decodeURIComponent(part.slice(i + 1));
  }
  return "";
}

function setCookies(res, list) {
  res.setHeader("Set-Cookie", list);
}

// SameSite=Lax — 구글에서 돌아올 때(다른 사이트에서 넘어오는 이동)도 로그인 도중 쿠키가 와야 한다
const make = (name, val, age) =>
  `${name}=${val}; Path=/; Max-Age=${age}; HttpOnly; Secure; SameSite=Lax`;
const sessionCookie = (obj) => make(SESSION, seal(obj), SESSION_AGE);
const clearSession = () => make(SESSION, "", 0);
const stateCookie = (obj) => make(STATE, seal(obj), STATE_AGE);
const clearState = () => make(STATE, "", 0);

function send(res, code, obj) {
  res.statusCode = code;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(obj));
}

function redirect(res, url) {
  res.statusCode = 302;
  res.setHeader("Location", url);
  res.setHeader("Cache-Control", "no-store");
  res.end();
}

/** 토큰을 내주는 요청인지 확인 — POST, 이 주소에서 온 것, 설정이 끝난 상태. */
function guard(req, res, { needConfig = true } = {}) {
  if (req.method !== "POST") { send(res, 405, { error: "method" }); return false; }
  if ((req.headers.origin || "") !== ORIGIN) { send(res, 403, { error: "origin" }); return false; }
  if (needConfig && !configured()) { send(res, 503, { error: "not_configured" }); return false; }
  return true;
}

async function google(params, fetchImpl = fetch) {
  const r = await fetchImpl(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: CLIENT_ID, client_secret: process.env.GOOGLE_CLIENT_SECRET || "", ...params,
    }).toString(),
  });
  let j = {};
  try { j = await r.json(); } catch (e) { /* 빈 응답 */ }
  return { ok: r.ok, status: r.status, j };
}

/** id_token 에서 이메일만 꺼낸다 — 구글에서 https 로 직접 받은 것이라 서명 검사는 생략한다. */
function emailOf(idToken) {
  try {
    const p = JSON.parse(Buffer.from(String(idToken).split(".")[1], "base64url").toString("utf8"));
    return p.email || "";
  } catch (e) { return ""; }
}

/** 받은 권한에서 빠진 것 (구글은 동의 화면에서 항목마다 체크를 받는다). */
function missingScopes(granted) {
  const have = new Set(String(granted || "").split(/\s+/).filter(Boolean));
  // openid·email 은 다른 이름(…/userinfo.email)으로 돌아오기도 해서 따지지 않는다
  return SCOPES.filter((s) => s.startsWith("https://") && !have.has(s));
}

/** 돌아갈 화면 — '#/화면' 모양만 받는다(엉뚱한 주소로 보내지 않게). */
function safeReturn(r) {
  const s = String(r || "");
  return /^#\/[\w/-]{0,80}$/.test(s) ? s : "#/agenda";
}

module.exports = {
  CLIENT_ID, ORIGIN, REDIRECT, TOKEN_URL, AUTH_URL, SCOPES, SESSION, STATE,
  configured, seal, unseal, cookie, setCookies, sessionCookie, clearSession,
  stateCookie, clearState, send, redirect, guard, google, emailOf, missingScopes, safeReturn,
};
