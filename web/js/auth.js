// 구글 로그인.
//
// ■ 기본: 서버 쿠키 방식(jyplanner.vercel.app 의 /api/auth/*)
//   한 번 로그인하면 구글 '갱신 토큰' 이 쿠키(화면 코드가 못 읽는 HttpOnly)에 남는다.
//   켤 때·만료 전에 /api/auth/token 을 부르면 1시간짜리 토큰을 **팝업 없이** 새로 준다.
//   로그인 단추는 팝업이 아니라 **화면을 넘긴다** — 폰 브라우저가 막을 일이 없어
//   한 번 누르면 끝난다(예전엔 두세 번 눌러야 했다).
//
// ■ 예비: 서버가 없거나(옛 주소) 설정 전(503)이면 예전 GIS 토큰 방식
//   1시간짜리 토큰만 있고, 조용한 다시 받기는 팝업이라 폰에서는 자주 막힌다.
//
// 액세스 토큰은 메모리 + sessionStorage 에만 둔다. localStorage 는 안 쓴다 — 폰을
// 잃었을 때 디스크에 남은 토큰을 넘겨주지 않기 위해서다(오래가는 것은 쿠키 쪽).

import { CLIENT_ID, SCOPES } from "./config.js";

const KEY = "planner.tok";
const API = "./api/auth/";
let _tok = null;          // {token, expiresAt, email}
let _client = null;
let _listeners = [];
let _emailFns = [];
let _mode = "";           // "server" | "legacy" | "" (아직 모름)
let _missing = [];        // 받은 권한에서 빠진 것(동의 화면에서 체크를 덜 했다)

export const STATE = {
  UNKNOWN: "unknown", AUTHED: "authed", NEED: "needsSignIn", OFFLINE: "offline",
};
let _state = STATE.UNKNOWN;

export function state() { return _state; }
export function email() { return _tok && _tok.email || ""; }
export function mode() { return _mode; }
/** 동의 화면에서 빠진 권한(있으면 화면이 '모두 체크' 안내를 띄운다). */
export function missing() { return _missing.slice(); }
export function onChange(fn) { _listeners.push(fn); }
/** 로그인 계정(이메일)을 알게 됐을 때 부른다. 계정이 바뀌었는지 판단하는 쪽에서 쓴다. */
export function onEmail(fn) { _emailFns.push(fn); }
function tellEmail(e) {
  for (const fn of _emailFns) { try { fn(e); } catch (x) { /* 하나가 탈나도 계속 */ } }
}
function setState(s) {
  if (s === _state) return;
  _state = s;
  for (const fn of _listeners) { try { fn(s); } catch (e) { /* 화면 하나가 탈나도 계속 */ } }
}

function load() {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const t = JSON.parse(raw);
    return (t && t.expiresAt > Date.now() + 5000) ? t : null;
  } catch (e) { return null; }
}
function save(t) {
  _tok = t;
  try { sessionStorage.setItem(KEY, JSON.stringify(t)); } catch (e) { /* 사생활 보호 모드 */ }
}
function drop() {
  _tok = null;
  try { sessionStorage.removeItem(KEY); } catch (e) {}
}

// ---------------------------------------------------------------- 서버 쿠키 방식
/** /api/auth/token — 쿠키로 새 토큰. 결과: 토큰 | null(로그인 필요) | undefined(서버 없음·못 닿음). */
async function fromServer(timeoutMs = 8000) {
  const ctl = typeof AbortController === "function" ? new AbortController() : null;
  const timer = ctl ? setTimeout(() => ctl.abort(), timeoutMs) : 0;
  let r;
  try {
    r = await fetch(API + "token", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json" }, body: "{}",
      ...(ctl ? { signal: ctl.signal } : {}),
    });
  } catch (e) {
    clearTimeout(timer);
    // 통신이 안 되거나 너무 늦다 — 서버가 없는 게 아니라 지금 못 닿는 것
    if (typeof navigator !== "undefined" && navigator.onLine === false) setState(STATE.OFFLINE);
    return undefined;
  }
  clearTimeout(timer);
  if (r.status === 200) {
    let j = {};
    try { j = await r.json(); } catch (e) { return undefined; }
    if (!j.access_token) return undefined;
    _mode = "server";
    _missing = Array.isArray(j.missing) ? j.missing : [];
    const had = _tok && _tok.email;
    const t = {
      token: j.access_token,
      expiresAt: Date.now() + (Number(j.expires_in || 3600) - 60) * 1000,
      email: j.email || had || "",
    };
    save(t);
    setState(STATE.AUTHED);
    if (t.email && t.email !== had) tellEmail(t.email);
    return t;
  }
  if (r.status === 401) { _mode = "server"; return null; }
  // 404(서버 없음 — 옛 주소) · 503(비밀 설정 전) · 403(미리보기 주소) · 405 → 예전 방식
  if ([403, 404, 405, 503].includes(r.status)) _mode = "legacy";
  return undefined;
}

// ---------------------------------------------------------------- 예전 GIS 방식
function gis() {
  return (window.google && window.google.accounts && window.google.accounts.oauth2) || null;
}

let _gisLoading = null;
/** 구글 로그인 스크립트 — 예전 방식일 때만 받는다(서버 방식은 필요 없어 첫 화면이 가볍다). */
export function loadGis() {
  if (gis()) return Promise.resolve(true);
  if (_gisLoading) return _gisLoading;
  _gisLoading = new Promise((ok) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => ok(!!gis());
    s.onerror = () => { _gisLoading = null; ok(false); };
    document.head.appendChild(s);
  });
  return _gisLoading;
}

function client() {
  if (_client) return _client;
  const g = gis();
  if (!g) return null;
  _client = g.initTokenClient({
    client_id: CLIENT_ID,
    scope: SCOPES,
    callback: () => {},               // 부를 때마다 갈아 끼운다
    error_callback: () => {},
  });
  return _client;
}

// prompt — "" : 필요할 때만 묻는다 · "select_account" : 계정 고르기 · "consent" : 동의 화면
// keep   — 실패해도 '다시 로그인' 상태로 바꾸지 않는다(아직 쓸 수 있는 토큰이 있을 때)
export function acquire({ interactive = false, timeoutMs = 4000, prompt = "", keep = false } = {}) {
  return new Promise((resolve) => {
    const c = client();
    if (!c) { if (!keep) setState(STATE.NEED); resolve(null); return; }
    let done = false;
    const finish = (tok) => {
      if (done) return;
      done = true;
      if (tok) { setState(STATE.AUTHED); resolve(tok); }
      else { if (!keep) setState(STATE.NEED); resolve(null); }
    };
    c.callback = (resp) => {
      if (!resp || resp.error || !resp.access_token) { finish(null); return; }
      const t = {
        token: resp.access_token,
        expiresAt: Date.now() + (Number(resp.expires_in || 3600) - 60) * 1000,
        email: (_tok && _tok.email) || "",
      };
      save(t);
      finish(t);
      // ⚠️ 계정 이름은 '있으면 좋은 것' 이 아니다. 누구로 로그인했는지 모르면
      //    앞사람 자료가 남아 있어도 걸러낼 수 없다(실제로 그렇게 새어 나갔다).
      fetchEmail(t);
    };
    // 창을 닫았거나 막혔다 — 예전엔 알 길이 없어 단추를 다시 눌러야 했다
    c.error_callback = () => finish(null);
    if (!interactive) setTimeout(() => finish(null), timeoutMs);
    try {
      c.requestAccessToken({ prompt });
    } catch (e) { finish(null); }
  });
}

async function fetchEmail(t) {
  try {
    const r = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
      headers: { Authorization: "Bearer " + t.token },
    });
    if (!r.ok) return "";
    const j = await r.json();
    if (j.email) {
      t.email = j.email; save(t); setState(STATE.AUTHED); tellEmail(j.email);
      return j.email;
    }
  } catch (e) { /* 못 물어보면 빈 값 */ }
  return "";
}

// ---------------------------------------------------------------- 밖에서 쓰는 것
/** 지금 로그인한 계정을 **확실히** 알아낸다.
 *
 * ⚠️ 이건 '있으면 좋은 것' 이 아니다. 누구로 로그인했는지 모르는 채로 화면을
 *    그리면 **앞사람 자료를 그대로 보여 준다.** 그래서 켤 때 이걸 먼저 기다린다.
 *    서버 방식은 쿠키 한 번(보통 0.3~0.6초)이라 빠르다. 예전 방식은 팝업이 막혀
 *    4초씩 기다리던 것을 여기서는 하지 않는다(뒤에서 조용히 해 본다).
 */
export async function ensureEmail({ timeoutMs = 2500 } = {}) {
  if (_tok && _tok.email) return _tok.email;
  if (_mode !== "legacy") {
    const t = await fromServer(timeoutMs);
    if (t) return t.email || "";
    if (t === null) { setState(STATE.NEED); return ""; }
  }
  if (_mode === "legacy" && _tok && !_tok.email) {
    return Promise.race([fetchEmail(_tok), new Promise((r) => setTimeout(() => r(""), timeoutMs))]);
  }
  return "";
}

// 만료 몇 분 전부터 미리 갈아 끼울지
export const REFRESH_AHEAD_MS = 5 * 60 * 1000;
let _refreshing = null;

/** 쓸 토큰.
 *  refresh:true — 곧 만료될 토큰을 **미리** 갈아 끼운다(실패해도 지금 토큰은 쓴다)
 *  fresh:true   — 방금 401 을 받았다 → 들고 있던 토큰은 버리고 새로 받는다
 *
 * ⚠️ 예전엔 401 뒤에도 같은 토큰을 다시 돌려줘 재시도가 늘 같은 401 로 끝났다.
 */
export async function token({ interactive = false, refresh = false, fresh = false } = {}) {
  const now = Date.now();
  if (fresh) drop();
  if (_tok && _tok.expiresAt > now) {
    if (!refresh || _tok.expiresAt - now > REFRESH_AHEAD_MS) return _tok.token;
    if (!_refreshing) {
      _refreshing = (async () => {
        if (_mode !== "legacy") {
          const t = await fromServer();
          if (t !== undefined) return t;
        }
        return acquire({ interactive: false, keep: true });
      })().finally(() => { _refreshing = null; });
    }
    const t = await _refreshing;
    return t ? t.token : (_tok && _tok.expiresAt > Date.now() ? _tok.token : null);
  }
  const cached = load();
  if (cached) { _tok = cached; setState(STATE.AUTHED); return cached.token; }
  if (_mode !== "legacy") {
    if (!_refreshing) _refreshing = fromServer().finally(() => { _refreshing = null; });
    const t = await _refreshing;
    if (t) return t.token;
    if (t === null) { setState(STATE.NEED); return null; }
    if (_mode !== "legacy") return null;     // 지금 서버에 못 닿는다 — 다음에 다시
  }
  // 예전 방식 — 조용한 시도는 폰에서 막히기 쉽다(그래도 PC 브라우저에서는 된다)
  await loadGis();
  const t = await acquire({ interactive });
  return t ? t.token : null;
}

/** 카카오톡 안 브라우저 — 구글이 여기서는 로그인을 막는다(보안 정책). 바깥 브라우저로 연다. */
export function inKakao() {
  return /KAKAOTALK/i.test(navigator.userAgent || "");
}

/** [로그인] — 서버 방식이면 화면을 넘긴다(한 번에 끝). 예전 방식이면 팝업.
 *  prompt:"select_account" 는 계정 바꾸기.
 *
 * ⚠️ 예전 방식의 팝업은 **누른 그 순간** 열어야 막히지 않는다 — 이 함수는 기다리지
 *    않고 바로 부른다(스크립트는 켤 때 미리 받아 둔다: preload()).
 */
export function signIn({ prompt = "", hint = "" } = {}) {
  if (inKakao()) {
    location.href = "kakaotalk://web/openExternal?url=" + encodeURIComponent(location.href);
    return Promise.resolve(null);
  }
  if (_mode !== "legacy") {
    const q = new URLSearchParams({ r: location.hash || "#/agenda" });
    if (prompt === "select_account") q.set("prompt", "select_account");
    else if (hint || email()) q.set("hint", hint || email());
    location.assign(API + "start?" + q);
    return new Promise(() => {});          // 화면이 넘어간다 — 돌아오면 새로 켜진다
  }
  return acquire({ interactive: true, timeoutMs: 0, prompt });
}

/** 어느 방식인지 알아 두고, 예전 방식이면 로그인 스크립트를 미리 받아 둔다
 *  (단추를 눌렀을 때 바로 팝업이 뜨게). 이 기기에 남은 토큰으로 켜면 서버에 아직
 *  안 물어봤으므로 여기서 한 번 묻는다. */
export async function preload() {
  if (!_mode) await fromServer();
  if (_mode === "legacy") await loadGis();
}
/** 이 기기의 로그인을 지운다(서버 쿠키 포함). */
export async function signOut() {
  drop();
  if (_mode === "server") {
    try {
      await fetch(API + "logout", { method: "POST", credentials: "same-origin",
                                    headers: { "Content-Type": "application/json" }, body: "{}" });
    } catch (e) { /* 다음에 켤 때 401 이면 그만 */ }
  }
  setState(STATE.NEED);
}

/** 계정 바꾸기 — 계정 고르는 화면으로. 지금 로그인은 지우지 않는다: 구글에서
 *  [취소] 하면 쓰던 계정 그대로 돌아오고, 다른 계정을 고르면 돌아올 때 쿠키가
 *  그 계정 것으로 바뀐다(앞사람 자료는 boot 의 onEmail 이 지운다). */
export function switchAccount() {
  return signIn({ prompt: "select_account" });
}

/** 로그인에서 돌아왔을 때 주소에 붙은 결과(?auth=…)를 읽고 지운다. init() 보다 먼저 부른다.
 *
 * ⚠️ 새로 로그인했으면 이 탭에 남은 토큰을 버린다. 계정 바꾸기로 다른 계정을 골랐는데
 *    앞 계정 토큰(아직 1시간 유효)을 그대로 쓰면 앞사람 자료를 보여 준다.
 */
export function takeReturn() {
  let flag = "";
  try {
    const u = new URL(location.href);
    flag = u.searchParams.get("auth") || "";
    if (flag) {
      u.searchParams.delete("auth");
      history.replaceState(null, "", u.pathname + u.search + u.hash);
    }
  } catch (e) { /* 옛 브라우저 */ }
  if (flag === "ok" || flag === "partial") drop();
  if (flag === "unconfigured") _mode = "legacy";
  return flag;
}

export function init() {
  const cached = load();
  if (cached) {
    _tok = cached;
    setState(STATE.AUTHED);
    if (cached.email) tellEmail(cached.email);
  }
  // 만료 5분 전에 미리 갈아 끼운다. 폰은 대부분 뒤에 가 있어서 타이머가 굼뜨므로
  // 화면이 앞으로 올 때도 한 번 본다.
  const soon = () => _tok && _tok.expiresAt - Date.now() < REFRESH_AHEAD_MS;
  setInterval(() => { if (soon()) token({ refresh: true }); }, 60 * 1000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && soon()) token({ refresh: true });
  });
}

export function setOffline(on) { setState(on ? STATE.OFFLINE : STATE.AUTHED); }
