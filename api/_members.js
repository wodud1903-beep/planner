// 회원 목록(v1.37) — 일정관리기 · 업무자료검색 PC 앱에 구글 로그인한 계정을 관리자만 본다.
//
// ⚠️ 밑줄(_) 파일이라 따로 서버 함수가 되지 않는다 — Vercel 무료(Hobby)는 한 배포에 함수 12개까지라
//    (13개째에서 배포가 통째로 실패했다), /api/members 는 vercel.json 주소 연결로 api/update.js 가 받아 여기로 넘긴다.
//
// 지점장: "일정관리기 및 자료검색 앱에서 로그인한 목록은 내 관리자 계정으로 회원 리스트를 이메일로 알고 싶어."
//
//   POST /api/members  {app: "planner"|"kb", ver}   Authorization: Bearer <그 앱의 구글 접근 토큰>
//        → 200 {ok}        서버가 그 토큰으로 구글에 '누구냐' 를 직접 물어 이메일을 정한다(앱이 보낸 이메일은 믿지 않는다)
//   GET  /api/members                                Authorization: Bearer <지점장 계정 토큰>
//        → 200 {owner, members: [{email, apps: {planner|kb: {first, last, ver, n}}, blocked, admin}]}  아니면 403
//   GET  /api/members?me=1                           Authorization: Bearer <아무 로그인 토큰>
//        → 200 {email, owner, admin, blocked}       PC 앱이 켤 때 · 30분마다 묻는다(v1.40)
//   POST /api/members  {action: block|unblock|admin|unadmin, email}   지점장만(v1.40)
//        → 200 {ok, status}   지점장 계정은 제한 · 관리자 해제할 수 없다(400 owner)
//   503 {error: "not_configured" | "no_store"}       서버 설정 · 저장소(Blob)가 아직이면
//
// 사용 제한 · 관리자 지정(v1.40 지점장: "로그인했던 사용자 중에 계정 리스트를 보고 그 이메일에 사용 제한" ·
// "내가 관리자로 지정할 이메일도 — 관리자는 지금 내가 자료 수정할 수 있는 권한을 모두"):
//   members/_roles.json(잠금) = {admins: {이메일: 시각}, blocked: {이메일: 시각}}. 제한하면 관리자도 풀린다.
//   제한된 계정은 웹 로그인 토큰도 받지 못한다(auth/token · auth/kb-token → 403 blocked — check()).
//
// 저장: 비공개 Blob members/<이메일 해시>.<앱>.json — 앱마다 따로(v1.38). 한 파일에 두 앱을 담으면 PC 를 켤 때
//       두 프로그램이 같은 순간 알려 나중 것이 앞 것을 덮어 한 앱이 목록에서 빠졌다. v1.37 의 members/<해시>.json
//       (앱 묶음)도 그대로 읽는다. 내용은 로그인 쿠키와 같은 열쇠로 한 번 더 잠근다(_session.seal).
// 토큰은 저장하지 않는다. 지점장(OWNER) = python/planner/config.py OWNER_EMAIL 과 같다(검사가 대조한다).
const crypto = require("node:crypto");
const s = require("./_session.js");

const OWNER = "wodud1903@gmail.com";
const ACTIONS = new Set(["block", "unblock", "admin", "unadmin"]);
const ROLES = "_roles";                                    // members/_roles.json — 회원 기록과 섞이지 않게 밑줄
const APPS = new Set(["planner", "kb"]);
const USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo";   // PC config.USERINFO_URL 과 같다

let _who = null;
let _store = null;
let _clock = null;
const now = () => (_clock ? _clock() : new Date());

/** 토큰의 주인(구글이 확인한 이메일, 소문자). 모르면 "". */
async function who(token) {
  if (_who) return _who(token);
  if (!token) return "";
  try {
    const r = await fetch(USERINFO, { headers: { Authorization: "Bearer " + token } });
    if (!r.ok) return "";
    const j = await r.json();
    if (j.email_verified === false) return "";
    return String(j.email || "").trim().toLowerCase();
  } catch (e) {
    return "";
  }
}

const storeReady = () => !!(_store || process.env.BLOB_READ_WRITE_TOKEN || process.env.BLOB_STORE_ID);
const idOf = (email) => crypto.createHash("sha256").update(email).digest("hex").slice(0, 32);
const path = (id) => `members/${id}.json`;

function store() {
  if (_store) return _store;
  const b = require("@vercel/blob");
  const opts = { access: "private", addRandomSuffix: false, contentType: "text/plain", allowOverwrite: true };
  _store = {
    async get(id) {
      const r = await b.get(path(id), { access: "private", useCache: false });
      if (!r || r.statusCode !== 200) return null;
      return s.unseal(await new Response(r.stream).text());
    },
    async put(id, rec) { await b.put(path(id), s.seal(rec), opts); },
    async list() {
      const out = [];
      let cursor;
      do {
        const r = await b.list({ prefix: "members/", cursor });
        for (const x of r.blobs) out.push(x.pathname.replace(/^members\//, "").replace(/\.json$/, ""));
        cursor = r.hasMore ? r.cursor : undefined;
      } while (cursor);
      return out;
    },
  };
  return _store;
}

function bearer(req) {
  const h = String((req.headers || {}).authorization || "");
  return h.startsWith("Bearer ") ? h.slice(7).trim() : "";
}

function body(req) {
  const b = req.body;
  if (b && typeof b === "object") return b;
  try { return JSON.parse(String(b || "{}")); } catch (e) { return {}; }
}

const looksEmail = (e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e) && e.length <= 200;

async function readRoles(st) {
  const r = (await st.get(ROLES).catch(() => null)) || {};
  return { admins: { ...(r.admins || {}) }, blocked: { ...(r.blocked || {}) } };
}

/** 이 계정의 지금 상태 — 지점장은 늘 관리자 · 제한 없음. */
function statusOf(rl, email) {
  const owner = email === OWNER;
  const blocked = !owner && !!rl.blocked[email];
  return { email, owner, blocked, admin: owner || (!blocked && !!rl.admins[email]) };
}

/** 웹 로그인 서버(auth/token · auth/kb-token)가 토큰을 주기 전에 묻는다. 저장소가 없거나 못 읽으면 막지 않는다. */
async function check(email) {
  const who = String(email || "").trim().toLowerCase();
  if (!who || !storeReady()) return statusOf({ admins: {}, blocked: {} }, who);
  try { return statusOf(await readRoles(store()), who); } catch (e) { return statusOf({ admins: {}, blocked: {} }, who); }
}

function query(req) {
  try { return new URL(req.url || "/", "http://x").searchParams; } catch (e) { return new URLSearchParams(); }
}

module.exports = async (req, res) => {
  if (req.method !== "POST" && req.method !== "GET") { s.send(res, 405, { error: "method" }); return; }
  if (!s.configured()) { s.send(res, 503, { error: "not_configured" }); return; }
  if (!storeReady()) { s.send(res, 503, { error: "no_store" }); return; }
  const email = await who(bearer(req));
  if (!email) { s.send(res, 401, { error: "auth" }); return; }
  const st = store();
  if (req.method === "GET" && query(req).get("me")) {          // 내 상태(제한 · 관리자) — 누구나 자기 것만
    s.send(res, 200, statusOf(await readRoles(st), email));
    return;
  }
  if (req.method === "POST" && body(req).action !== undefined) {
    if (email !== OWNER) { s.send(res, 403, { error: "owner" }); return; }
    const b = body(req);
    const action = String(b.action || "");
    const target = String(b.email || "").trim().toLowerCase();
    if (!ACTIONS.has(action) || !looksEmail(target)) { s.send(res, 400, { error: "bad" }); return; }
    if (target === OWNER) { s.send(res, 400, { error: "owner" }); return; }
    const rl = await readRoles(st);
    const at = now().toISOString();
    if (action === "block") { rl.blocked[target] = at; delete rl.admins[target]; }
    if (action === "unblock") delete rl.blocked[target];
    if (action === "admin") { rl.admins[target] = at; delete rl.blocked[target]; }
    if (action === "unadmin") delete rl.admins[target];
    await st.put(ROLES, rl);
    s.send(res, 200, { ok: true, status: statusOf(rl, target) });
    return;
  }
  if (req.method === "POST") {
    const b = body(req);
    const app = String(b.app || "");
    if (!APPS.has(app)) { s.send(res, 400, { error: "app" }); return; }
    const ver = String(b.ver || "").slice(0, 20);
    const id = idOf(email);
    const at = now().toISOString();
    let a = await st.get(`${id}.${app}`);
    if (!a) {                                      // 이 앱은 처음 — v1.37 묶음 파일에 있던 처음 날 · 횟수를 이어 받는다
      const old = await st.get(id).catch(() => null);
      a = (old && old.apps && old.apps[app]) || { first: at, n: 0 };
    }
    await st.put(`${id}.${app}`, { email, app, first: a.first || at, last: at, ver, n: (a.n || 0) + 1 });
    s.send(res, 200, { ok: true, ...statusOf(await readRoles(st), email) });
    return;
  }
  if (email !== OWNER) { s.send(res, 403, { error: "admin" }); return; }
  const ids = (await st.list()).filter((id) => !id.startsWith("_"));
  const recs = (await Promise.all(ids.map((id) => st.get(id).catch(() => null)))).filter((r) => r && r.email);
  const rl = await readRoles(st);
  // 이메일마다 하나로 — 앱마다 파일(v1.38)과 예전 묶음 파일(v1.37)을 합친다(같은 앱이면 나중에 알린 것)
  const by = new Map();
  const add = (email, app, x) => {
    if (!APPS.has(app) || !x) return;
    const m = by.get(email) || { email, apps: {} };
    const had = m.apps[app];
    if (!had || String(x.last || "") > String(had.last || "")) {
      m.apps[app] = { first: x.first || "", last: x.last || "", ver: x.ver || "", n: x.n || 0 };
    }
    by.set(email, m);
  };
  for (const r of recs) {
    if (r.app) add(r.email, r.app, r);
    else for (const [app, x] of Object.entries(r.apps || {})) add(r.email, app, x);
  }
  // 로그인 기록이 없어도 제한 · 관리자로 정해 둔 계정은 목록에 보인다
  for (const e of [...Object.keys(rl.blocked), ...Object.keys(rl.admins)]) {
    if (!by.has(e)) by.set(e, { email: e, apps: {} });
  }
  const out = [...by.values()].map((m) => ({ ...m, ...statusOf(rl, m.email), email: m.email }));
  const last = (r) => Object.values(r.apps || {}).map((x) => x.last || "").sort().pop() || "";
  out.sort((x, y) => (last(y) > last(x) ? 1 : last(y) < last(x) ? -1 : 0));
  s.send(res, 200, { owner: OWNER, members: out });
};

module.exports.check = check;

module.exports._test = {
  OWNER,
  setWho: (fn) => { _who = fn; },
  setStore: (st) => { _store = st; },
  setClock: (fn) => { _clock = fn; },
};
