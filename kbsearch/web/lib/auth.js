// 구글 로그인(구글 동기화용) — 이 서버에는 클라이언트 비밀이 없다.
//
// 로그인은 일정관리기 웹(jyplanner) 서버가 대신 받아 준다(그 주소는 구글 콘솔에 이미 등록돼 있다):
//   [구글 동기화] → /api/auth/login → jyplanner /api/auth/start?app=kb → 구글 동의 →
//   jyplanner 가 갱신 토큰을 **잠근 쪽지**로 만들어 /api/auth/accept 로 POST → 이 주소 쿠키에 둔다.
// 쓸 토큰이 필요하면 /api/auth/token 이 쪽지를 jyplanner /api/auth/kb-token 에 내밀어 받아 온다.
//   · 쪽지는 이 서버도 못 연다(잠근 열쇠는 jyplanner 에만). 화면 코드도 못 읽는다(HttpOnly).
//   · 받는 권한은 드라이브 '앱 전용 공간' 하나 — 고친 심사서류를 PC 와 주고받는 파일(kb_edits.json).
//   · 남이 자기 쪽지를 내 브라우저에 밀어 넣지 못하게(로그인 위조) 시작할 때 정한 값(n)을 맞춰 본다.
export const ORIGIN = (process.env.PUBLIC_ORIGIN || "https://kbsearch.vercel.app").replace(/\/$/, "");
export const BROKER = (process.env.AUTH_BROKER || "https://jyplanner.vercel.app").replace(/\/$/, "");
export const SESSION = "__Host-kbs";
export const STATE = "__Host-kbs_st";
const SESSION_AGE = 400 * 24 * 3600;    // 크롬이 400일로 자른다 — 쓸 때마다 다시 늘린다
const STATE_AGE = 10 * 60;

export function cookie(req, name) {
  for (const part of String(req.headers.cookie || "").split(/;\s*/)) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i) === name) return decodeURIComponent(part.slice(i + 1));
  }
  return "";
}
// 쪽지 쿠키 — SameSite=Lax. 시작 값 쿠키는 jyplanner 에서 **POST 로 돌아올 때**도 와야 해서 None.
export const sessionCookie = (h) => `${SESSION}=${h}; Path=/; Max-Age=${SESSION_AGE}; HttpOnly; Secure; SameSite=Lax`;
export const clearSession = () => `${SESSION}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax`;
export const stateCookie = (n) => `${STATE}=${n}; Path=/; Max-Age=${STATE_AGE}; HttpOnly; Secure; SameSite=None`;
export const clearState = () => `${STATE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=None`;

export const goodSeal = (h) => /^[\w-]{40,4000}$/.test(String(h || ""));
export const goodNonce = (n) => /^[\w-]{16,64}$/.test(String(n || ""));

export function redirect(res, status, url, cookies) {
  res.statusCode = status;
  if (cookies) res.setHeader("Set-Cookie", cookies);
  res.setHeader("Location", url);
  res.setHeader("Cache-Control", "no-store");
  res.end();
}

/** 이 주소에서 온 요청인가(다른 사이트가 토큰을 받아 가지 못하게). 시험용 127.0.0.1 은 그 주소 그대로. */
export function sameOrigin(req) {
  const o = String(req.headers.origin || "");
  const host = String(req.headers.host || "");
  if (o === ORIGIN) return true;
  if (/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(host) && o === `http://${host}`) return true;
  return false;
}

/** 폼(POST) 몸통 — Vercel 이 풀어 준 것이 있으면 그것, 아니면 직접 읽는다. */
export async function formBody(req) {
  if (req.body && typeof req.body === "object") return req.body;
  let raw = typeof req.body === "string" ? req.body : "";
  if (!raw && req.readable !== false && typeof req[Symbol.asyncIterator] === "function") {
    try { for await (const c of req) raw += c; } catch (e) { /* 끊김 */ }
  }
  return Object.fromEntries(new URLSearchParams(raw));
}
