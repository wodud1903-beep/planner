// 회원 목록(v1.37) — 일정관리기 · 업무자료검색 PC 앱에 구글 로그인한 계정을 관리자만 본다.
//
// ⚠️ 밑줄(_) 파일이라 따로 서버 함수가 되지 않는다 — Vercel 무료(Hobby)는 한 배포에 함수 12개까지라
//    (13개째에서 배포가 통째로 실패했다), /api/members 는 vercel.json 주소 연결로 api/update.js 가 받아 여기로 넘긴다.
//
// 지점장: "일정관리기 및 자료검색 앱에서 로그인한 목록은 내 관리자 계정으로 회원 리스트를 이메일로 알고 싶어."
//
//   POST /api/members  {app: "planner"|"kb", ver}   Authorization: Bearer <그 앱의 구글 접근 토큰>
//        → 200 {ok}        서버가 그 토큰으로 구글에 '누구냐' 를 직접 물어 이메일을 정한다(앱이 보낸 이메일은 믿지 않는다)
//   GET  /api/members                                Authorization: Bearer <관리자 계정 토큰>
//        → 200 {members: [{email, apps: {planner|kb: {first, last, ver, n}}}]}   관리자가 아니면 403
//   503 {error: "not_configured" | "no_store"}       서버 설정 · 저장소(Blob)가 아직이면
//
// 저장: 비공개 Blob members/<이메일 해시>.json — 내용도 로그인 쿠키와 같은 열쇠로 한 번 더 잠근다(_session.seal).
// 토큰은 저장하지 않는다. 관리자 = python/planner/config.py RATES_ADMINS 와 같다(검사가 대조한다).
const crypto = require("node:crypto");
const s = require("./_session.js");

const ADMINS = ["wodud1903@gmail.com"];
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

module.exports = async (req, res) => {
  if (req.method !== "POST" && req.method !== "GET") { s.send(res, 405, { error: "method" }); return; }
  if (!s.configured()) { s.send(res, 503, { error: "not_configured" }); return; }
  if (!storeReady()) { s.send(res, 503, { error: "no_store" }); return; }
  const email = await who(bearer(req));
  if (!email) { s.send(res, 401, { error: "auth" }); return; }
  const st = store();
  if (req.method === "POST") {
    const b = body(req);
    const app = String(b.app || "");
    if (!APPS.has(app)) { s.send(res, 400, { error: "app" }); return; }
    const ver = String(b.ver || "").slice(0, 20);
    const id = idOf(email);
    const at = now().toISOString();
    const rec = (await st.get(id)) || { email, apps: {} };
    const a = rec.apps[app] || { first: at, n: 0 };
    rec.email = email;
    rec.apps[app] = { first: a.first || at, last: at, ver, n: (a.n || 0) + 1 };
    await st.put(id, rec);
    s.send(res, 200, { ok: true });
    return;
  }
  if (!ADMINS.includes(email)) { s.send(res, 403, { error: "admin" }); return; }
  const ids = await st.list();
  const recs = (await Promise.all(ids.map((id) => st.get(id).catch(() => null)))).filter((r) => r && r.email);
  const last = (r) => Object.values(r.apps || {}).map((x) => x.last || "").sort().pop() || "";
  recs.sort((x, y) => (last(y) > last(x) ? 1 : last(y) < last(x) ? -1 : 0));
  s.send(res, 200, { members: recs });
};

module.exports._test = {
  ADMINS,
  setWho: (fn) => { _who = fn; },
  setStore: (st) => { _store = st; },
  setClock: (fn) => { _clock = fn; },
};
