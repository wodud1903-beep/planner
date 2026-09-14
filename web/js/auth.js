// 구글 로그인 — GIS 토큰 방식.
//
// 브라우저에는 리프레시 토큰이 없다. **1시간짜리 액세스 토큰**만 받고, 만료되면
// 구글 세션으로 조용히 다시 받는다. 그래서 '테스트 모드 7일 제한'(리프레시 토큰을
// 회수하는 규칙)에 걸리지 않는다.
//
// 토큰은 메모리 + sessionStorage 에 둔다. localStorage 는 안 쓴다 — 폰을 잃었을 때
// 디스크에 남은 유효 토큰을 넘겨주지 않기 위해서다.

import { CLIENT_ID, SCOPES } from "./config.js";

const KEY = "planner.tok";
let _tok = null;          // {token, expiresAt, email}
let _client = null;
let _listeners = [];

export const STATE = {
  UNKNOWN: "unknown", AUTHED: "authed", NEED: "needsSignIn", OFFLINE: "offline",
};
let _state = STATE.UNKNOWN;

export function state() { return _state; }
export function email() { return _tok && _tok.email || ""; }
export function onChange(fn) { _listeners.push(fn); }
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

function gis() {
  return (window.google && window.google.accounts && window.google.accounts.oauth2) || null;
}

function client() {
  if (_client) return _client;
  const g = gis();
  if (!g) return null;
  _client = g.initTokenClient({
    client_id: CLIENT_ID,
    scope: SCOPES,
    callback: () => {},               // 부를 때마다 갈아 끼운다
  });
  return _client;
}

// 조용히 토큰 받기. prompt:'' 는 이미 동의했고 구글 세션이 살아 있으면 화면 없이 끝난다.
export function acquire({ interactive = false, timeoutMs = 4000 } = {}) {
  return new Promise((resolve) => {
    const c = client();
    if (!c) { setState(STATE.NEED); resolve(null); return; }
    let done = false;
    const finish = (tok) => {
      if (done) return;
      done = true;
      if (tok) { setState(STATE.AUTHED); resolve(tok); }
      else { setState(STATE.NEED); resolve(null); }
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
      fetchEmail(t);                  // 계정 이름은 뒤에서 채운다
    };
    // 조용한 시도는 답이 없을 수 있다 → 기다리다 포기한다
    if (!interactive) setTimeout(() => finish(null), timeoutMs);
    try {
      c.requestAccessToken({ prompt: interactive ? "consent" : "" });
    } catch (e) { finish(null); }
  });
}

async function fetchEmail(t) {
  try {
    const r = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
      headers: { Authorization: "Bearer " + t.token },
    });
    if (!r.ok) return;
    const j = await r.json();
    if (j.email) { t.email = j.email; save(t); setState(STATE.AUTHED); }
  } catch (e) { /* 계정 이름은 없어도 그만 */ }
}

export async function token({ interactive = false } = {}) {
  if (_tok && _tok.expiresAt > Date.now()) return _tok.token;
  const cached = load();
  if (cached) { _tok = cached; setState(STATE.AUTHED); return cached.token; }
  const t = await acquire({ interactive });
  return t ? t.token : null;
}

export function signIn() { return acquire({ interactive: true, timeoutMs: 0 }); }

export function signOut() {
  _tok = null;
  try { sessionStorage.removeItem(KEY); } catch (e) {}
  setState(STATE.NEED);
}

export function init() {
  const cached = load();
  if (cached) { _tok = cached; setState(STATE.AUTHED); }
  // 만료 5분 전에 미리 갈아 끼운다. 폰은 대부분 뒤에 가 있어서 타이머가 굼뜨므로
  // 화면이 앞으로 올 때도 한 번 본다.
  setInterval(() => { if (_tok && _tok.expiresAt - Date.now() < 5 * 60 * 1000) token(); },
              60 * 1000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && _tok
        && _tok.expiresAt - Date.now() < 5 * 60 * 1000) token();
  });
}

export function setOffline(on) { setState(on ? STATE.OFFLINE : STATE.AUTHED); }
