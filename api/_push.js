// 아침 브리핑 폰 알림(웹 푸시) — 공용 도우미. 밑줄(_)로 시작해 주소로 나가지 않는다.
//
// 흐름
//   폰 [알림 켜기] → /api/push/subscribe : 폰의 알림 주소 + 로그인 쿠키의 갱신 토큰을
//                                          잠가서(seal) 비공개 Blob 에 둔다
//   Vercel 예약 작업 → /api/push/cron     : 오전 8:50 이 지나면 하루 한 번, 갱신 토큰으로
//                                          구글에서 오늘 일정·할일·출고·뉴스를 읽어 알림을 보낸다
//
// 지키는 것
//   · 저장소는 비공개(private) Blob, 그 안의 내용도 쿠키와 같은 열쇠로 한 번 더 잠근다.
//   · 알림 서명 열쇠(VAPID)는 클라이언트 비밀에서 뽑는다 — 따로 설정할 값이 없다.
//   · 브리핑 내용은 보내고 버린다(저장하지 않는다).
//   · 알림을 끄거나, 구글에서 권한을 빼거나, 폰이 알림 주소를 버리면 기록을 지운다.
//
// ⚠️ Vercel 무료(Hobby) 예약 작업은 하루 한 번씩, 정한 '시' 안 아무 때나 돈다(±59분).
//    그래서 8시대·9시대·10시대에 여러 번 걸어 두고, 8:50 이 지난 첫 번째에 보낸다.
const crypto = require("node:crypto");
const s = require("./_session.js");

const SEND_FROM = { h: 8, m: 50 };       // 이 시각(한국) 이후 첫 예약 작업에 보낸다
const SEND_UNTIL_H = 12;                 // 이 시각이 지나면 그날은 건너뛴다(늦은 아침 알림은 쓸모없다)
const DEF_NEWS_DOC = "1KhvgFvtETklf2wAoJjSzCJLh3iyKCYB19LaH_j03rqI";   // PC config.DEF_NEWS_DOC
const G = "https://www.googleapis.com";

// ---------------------------------------------------------------- VAPID 열쇠
const N = BigInt("0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551");   // P-256 위수

function vapid() {
  const sec = process.env.GOOGLE_CLIENT_SECRET || "";
  if (!sec) return null;
  for (let i = 0; i < 4; i++) {
    const k = Buffer.from(crypto.hkdfSync("sha256", sec, "jyplanner", "web-push-vapid-v1:" + i, 32));
    const n = BigInt("0x" + k.toString("hex"));
    if (n === 0n || n >= N) continue;          // 거의 안 일어난다 — 다음 값으로
    const ecdh = crypto.createECDH("prime256v1");
    ecdh.setPrivateKey(k);
    return { publicKey: ecdh.getPublicKey().toString("base64url"), privateKey: k.toString("base64url") };
  }
  return null;
}

// ---------------------------------------------------------------- 저장소(비공개 Blob)
// Vercel 에서 Blob 저장소를 이 프로젝트에 연결하면 둘 중 하나가 생긴다.
// 없으면 알림 기능 전체가 '준비 전'(503) — 화면은 그렇게 안내한다.
const storeReady = () => !!(_store || process.env.BLOB_READ_WRITE_TOKEN || process.env.BLOB_STORE_ID);

const subId = (endpoint) => crypto.createHash("sha256").update(String(endpoint)).digest("hex").slice(0, 32);
const path = (id) => `push/${id}.json`;

let _store = null;
function store() {
  if (_store) return _store;
  const b = require("@vercel/blob");
  const opts = { access: "private", addRandomSuffix: false, contentType: "text/plain" };
  _store = {
    async put(id, rec, etag) {
      await b.put(path(id), s.seal(rec), etag ? { ...opts, ifMatch: etag } : { ...opts, allowOverwrite: true });
    },
    async get(id) {
      const r = await b.get(path(id), { access: "private", useCache: false });
      if (!r || r.statusCode !== 200) return null;
      const rec = s.unseal(await new Response(r.stream).text());
      return rec ? { rec, etag: r.blob.etag } : null;
    },
    async list() {
      const out = [];
      let cursor;
      do {
        const r = await b.list({ prefix: "push/", cursor });
        for (const x of r.blobs) out.push(x.pathname.replace(/^push\//, "").replace(/\.json$/, ""));
        cursor = r.hasMore ? r.cursor : undefined;
      } while (cursor);
      return out;
    },
    async del(id) { await b.del(path(id)); },
  };
  return _store;
}

let _clock = null;
const now = () => (_clock ? _clock() : new Date());

let _send = null;
function send(sub, payload) {
  if (_send) return _send(sub, payload);
  const wp = require("web-push");
  const k = vapid();
  return wp.sendNotification(sub, JSON.stringify(payload), {
    TTL: 6 * 3600, urgency: "normal",
    vapidDetails: { subject: s.ORIGIN, publicKey: k.publicKey, privateKey: k.privateKey },
  });
}

// ---------------------------------------------------------------- 한국 시각
const KST = 9 * 3600e3;
const pad = (n) => String(n).padStart(2, "0");
function kst(now = new Date()) {
  const d = new Date(now.getTime() + KST);
  return { y: d.getUTCFullYear(), mo: d.getUTCMonth() + 1, d: d.getUTCDate(), h: d.getUTCHours(),
           mi: d.getUTCMinutes(), wd: d.getUTCDay(),
           ymd: `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}` };
}
function dueNow(now = new Date()) {
  const t = kst(now);
  const m = t.h * 60 + t.mi;
  return m >= SEND_FROM.h * 60 + SEND_FROM.m && t.h < SEND_UNTIL_H;
}

// ---------------------------------------------------------------- 구글 읽기
async function gget(token, url) {
  const r = await fetch(url, { headers: { Authorization: "Bearer " + token } });
  if (!r.ok) throw new Error(`google ${r.status}`);
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}

async function appdataFile(token, name) {
  const q = encodeURIComponent(`name='${name}'`);
  const j = await gget(token, `${G}/drive/v3/files?spaces=appDataFolder&q=${q}&fields=files(id)`);
  const f = (j.files || [])[0];
  if (!f) return null;
  const txt = await gget(token, `${G}/drive/v3/files/${f.id}?alt=media`);
  try { return typeof txt === "string" ? JSON.parse(txt) : txt; } catch (e) { return null; }
}

/** 이 계정의 설정 — 웹앱 파일 먼저, 없으면 PC 묶음의 plan_cfg.json.
 *  PC 묶음에서 안내멘트 '보냄' 기록(ment_copied.json)·만기 재계약 기록(renewals.json)도 꺼낸다. */
async function settings(token) {
  const out = { sheetId: "", tab: "미출고차량", newsDoc: DEF_NEWS_DOC, sent: new Set(), renew: {} };
  try {
    const web = await appdataFile(token, "planner_web.json");
    if (web && web.sheetId) { out.sheetId = web.sheetId; out.tab = web.sheetTab || out.tab; }
  } catch (e) { /* 없으면 PC 것 */ }
  try {
    const pc = await appdataFile(token, "planner_sync.json");
    const files = (pc && pc.files) || {};
    const cfg = files["plan_cfg.json"] ? JSON.parse(files["plan_cfg.json"]) : null;
    if (cfg) {
      if (!out.sheetId && cfg.sheetId) { out.sheetId = cfg.sheetId; out.tab = cfg.sheetName || out.tab; }
      if (typeof cfg.newsDoc === "string") out.newsDoc = docIdFrom(cfg.newsDoc);
    }
    try {
      const sent = JSON.parse(files["ment_copied.json"] || "[]");
      if (Array.isArray(sent)) out.sent = new Set(sent.map(String));
    } catch (e) { /* 없으면 아무도 안 보낸 것으로 */ }
    try {
      const rn = JSON.parse(files["renewals.json"] || "{}");
      if (rn && typeof rn === "object" && !Array.isArray(rn)) out.renew = rn;
    } catch (e) { /* 없으면 정리한 것 없음 */ }
  } catch (e) { /* 기본값으로 */ }
  return out;
}

function docIdFrom(v) {
  const m = String(v || "").match(/\/document\/d\/([A-Za-z0-9_-]{20,})/);
  if (m) return m[1];
  return /^[A-Za-z0-9_-]{20,}$/.test(String(v || "").trim()) ? String(v).trim() : "";
}

const rfc = (y, mo, d) => `${y}-${pad(mo)}-${pad(d)}T00:00:00+09:00`;

async function todayEvents(token, t) {
  const list = await gget(token, `${G}/calendar/v3/users/me/calendarList?fields=items(id,selected,primary)`);
  const cals = (list.items || []).filter((c) => c.id && (c.selected || c.primary));
  const next = new Date(Date.UTC(t.y, t.mo - 1, t.d + 1));
  const qs = `timeMin=${encodeURIComponent(rfc(t.y, t.mo, t.d))}`
    + `&timeMax=${encodeURIComponent(rfc(next.getUTCFullYear(), next.getUTCMonth() + 1, next.getUTCDate()))}`
    + "&singleEvents=true&orderBy=startTime&maxResults=50&fields=items(summary,start)";
  const got = await Promise.all(cals.map((c) =>
    gget(token, `${G}/calendar/v3/calendars/${encodeURIComponent(c.id)}/events?${qs}`)
      .then((j) => j.items || []).catch(() => [])));
  return got.flat().map((e) => {
    const dt = (e.start || {}).dateTime;
    const hm = dt ? kst(new Date(dt)) : null;
    return { at: dt ? `${pad(hm.h)}:${pad(hm.mi)}` : "", summary: e.summary || "(제목 없음)" };
  }).sort((a, b) => (a.at || "00:00").localeCompare(b.at || "00:00"));
}

async function dueTasks(token, t) {
  const lists = await gget(token, "https://tasks.googleapis.com/tasks/v1/users/@me/lists?fields=items(id)");
  const got = await Promise.all((lists.items || []).map((l) =>
    gget(token, `https://tasks.googleapis.com/tasks/v1/lists/${encodeURIComponent(l.id)}/tasks`
      + "?showCompleted=false&showHidden=false&maxResults=100&fields=items(title,due)")
      .then((j) => j.items || []).catch(() => [])));
  // 기한이 오늘이거나 지난 것(기한은 날짜만 — 'YYYY-MM-DDT00:00:00.000Z')
  return got.flat().filter((x) => (x.title || "").trim() && x.due && x.due.slice(0, 10) <= t.ymd)
    .map((x) => ({ title: x.title.trim(), late: x.due.slice(0, 10) < t.ymd }));
}

/** 고객 줄 + 고객ID(U열). U 는 따로 읽는다 — U열이 없는 시트에서 목록까지 실패하지 않게
 *  (PC sheets.read_uids 와 같은 까닭). */
async function sheetRows(token, set) {
  const C = await import("../web/js/customers.js");
  const rng = (a) => encodeURIComponent(`'${set.tab}'!${a}`);
  const base = `https://sheets.googleapis.com/v4/spreadsheets/${set.sheetId}`;
  const j = await gget(token, `${base}/values:batchGet?ranges=${rng("A1:Q")}&ranges=${rng("S1:T")}`
    + "&valueRenderOption=FORMATTED_VALUE&dateTimeRenderOption=FORMATTED_STRING");
  const [left, right] = (j.valueRanges || []).map((v) => v.values || []);
  const { rows } = C.parseRows(left || [], right || [], set.tab);
  try {
    const u = await gget(token, `${base}/values/${rng("U1:U")}`);
    const vals = (u && u.values) || [];
    for (const cr of rows) cr.uid = String(((vals[cr.row - 1] || [])[0]) || "").trim();
  } catch (e) { /* 고객ID 가 없으면 순번|이름 열쇠로 */ }
  return rows;
}

/** 오늘 출고·계약 + 내일 출고 · 안내멘트 미발송 · 30일 넘게 멈춤 · 이번 달 만기(v1.26). */
async function sheetToday(token, set, t) {
  if (!set.sheetId) return null;
  const B = await import("../web/js/brief.js");
  const rows = await sheetRows(token, set);
  return B.items(rows, new Date(t.y, t.mo - 1, t.d), { sent: set.sent, renew: set.renew });
}

/** 오늘 뉴스 문서의 제목들 — 오늘 고쳐진 문서일 때만(어제 뉴스를 오늘 것처럼 보내지 않게). */
async function newsTitles(token, docId, t) {
  if (!docId) return null;
  const meta = await gget(token, `${G}/drive/v3/files/${docId}?fields=modifiedTime`);
  if (!meta.modifiedTime || kst(new Date(meta.modifiedTime)).ymd !== t.ymd) return null;
  const txt = await gget(token, `${G}/drive/v3/files/${docId}/export?mimeType=text/plain`);
  return titlesFrom(String(txt));
}

const TONES = ["호재", "악재", "중립"];
function titlesFrom(text) {
  const bold = [...String(text).matchAll(/\*\*(.+?)\*\*/gs)].map((m) => m[1].replace(/\\/g, "").trim());
  const out = [];
  for (let i = 0; i < bold.length - 1; i++) {
    if (TONES.includes(bold[i])) out.push({ tone: bold[i], title: bold[i + 1] });
  }
  return out;
}

// ---------------------------------------------------------------- 브리핑 글
const WD = ["일", "월", "화", "수", "목", "금", "토"];
const cut = (x, n) => (x.length > n ? x.slice(0, n - 1) + "…" : x);

function compose(t, { events, tasks, sheet, news }) {
  const lines = [];
  const head = [];
  if (events) head.push(`일정 ${events.length}`);
  if (tasks) head.push(`할일 ${tasks.length}`);
  if (sheet) head.push(`출고 ${sheet.deliver.length}`);
  if (head.length) lines.push(head.join(" · "));
  if (events && events.length) {
    lines.push("📅 " + events.slice(0, 2).map((e) => `${e.at ? e.at + " " : ""}${cut(e.summary, 22)}`)
      .join(" / ") + (events.length > 2 ? ` 외 ${events.length - 2}` : ""));
  }
  if (tasks && tasks.length) {
    const late = tasks.filter((x) => x.late).length;
    lines.push(`✅ ${cut(tasks[0].title, 24)}` + (tasks.length > 1 ? ` 외 ${tasks.length - 1}` : "")
      + (late ? ` (지난 기한 ${late})` : ""));
  }
  const list = (xs, n = 3) => cut(xs.slice(0, n).join(", "), 40) + (xs.length > n ? ` 외 ${xs.length - n}` : "");
  if (sheet && sheet.deliver.length) lines.push(`🚗 오늘 출고: ${cut(sheet.deliver.join(", "), 40)}`);
  // v1.26 — 오늘 할 일로 이어지는 것들(내일 출고 준비 · 멘트 · 멈춘 건 · 만기)
  if (sheet && (sheet.tomorrow || []).length) lines.push(`🚚 내일 출고(준비 확인): ${list(sheet.tomorrow)}`);
  if (sheet && (sheet.unsent || []).length) lines.push(`💬 안내멘트 안 보냄: ${list(sheet.unsent)}`);
  if (sheet && (sheet.stale || []).length) lines.push(`⏳ 30일 넘게 멈춤 ${sheet.stale.length}: ${list(sheet.stale, 2)}`);
  if (sheet && (sheet.expiry || []).length) lines.push(`🔔 이번 달 만기 ${sheet.expiry.length}: ${list(sheet.expiry, 2)}`);
  if (sheet && sheet.contract.length) lines.push(`📝 오늘 계약: ${cut(sheet.contract.join(", "), 40)}`);
  if (news && news.length) {
    lines.push(`📰 [${news[0].tone}] ${cut(news[0].title, 30)}` + (news.length > 1 ? ` 외 ${news.length - 1}` : ""));
  }
  if (!lines.length || (lines.length === 1 && head.length)) lines.push("오늘은 일정·할일이 없어요. 좋은 하루 보내세요!");
  return {
    title: `☀️ ${t.mo}/${t.d}(${WD[t.wd]}) 오늘 브리핑`,
    body: lines.join("\n"),
    url: "./#/agenda",
    tag: "brief-" + t.ymd,
  };
}

/** 갱신 토큰으로 오늘 브리핑을 만든다. 칸마다 따로 — 하나가 탈나도 나머지는 보낸다. */
async function buildBrief(accessToken, now = new Date()) {
  const t = kst(now);
  const safe = (p) => p.catch(() => null);
  const set = await settings(accessToken).catch(() => ({ sheetId: "", tab: "", newsDoc: DEF_NEWS_DOC,
                                                         sent: new Set(), renew: {} }));
  const [events, tasks, sheet, news] = await Promise.all([
    safe(todayEvents(accessToken, t)), safe(dueTasks(accessToken, t)),
    safe(sheetToday(accessToken, set, t)), safe(newsTitles(accessToken, set.newsDoc, t)),
  ]);
  return compose(t, { events, tasks, sheet, news });
}

// ---------------------------------------------------------------- 금요일 주간 보고(v1.26)
// 금요일 17시 무렵 한 번 — 이번 주 출고·계약·수수료를 알림으로, 누르면 주간 요약 화면에서
// [복사] 해 본사 보고방에 붙여 넣는다. 예약 작업은 17시대·18시대 두 번 걸어 두고(±59분)
// 처음 맞는 것에 보낸다(같은 주에 두 번 안 보낸다 — rec.lastWeekly).
const WEEKLY_FROM = { h: 16, m: 50 };
const WEEKLY_UNTIL_H = 21;

function dueWeekly(now = new Date()) {
  const t = kst(now);
  const m = t.h * 60 + t.mi;
  return t.wd === 5 && m >= WEEKLY_FROM.h * 60 + WEEKLY_FROM.m && t.h < WEEKLY_UNTIL_H;
}

/** 그 주(월요일 시작)의 열쇠 — 월요일 날짜. */
function weekKey(now = new Date()) {
  const t = kst(now);
  const d = new Date(Date.UTC(t.y, t.mo - 1, t.d));
  d.setUTCDate(d.getUTCDate() - ((t.wd + 6) % 7));
  return d.toISOString().slice(0, 10);
}

function composeWeekly(t, secs) {
  return {
    title: `📊 ${t.mo}/${t.d}(${WD[t.wd]}) 이번 주 실적`,
    body: secs.lines.join("\n"),
    url: "./#/customers/week",
    tag: "weekly-" + secs.week,
  };
}

async function buildWeekly(accessToken, now = new Date()) {
  const t = kst(now);
  const set = await settings(accessToken).catch(() => ({ sheetId: "", tab: "" }));
  if (!set.sheetId) {
    return composeWeekly(t, { week: weekKey(now), lines: ["고객 시트를 아직 정하지 않아 주간 실적을 셀 수 없어요."] });
  }
  const W = await import("../web/js/weekly.js");
  const B = await import("../web/js/brief.js");
  const rows = await sheetRows(accessToken, set);
  const secs = W.sections(rows, new Date(t.y, t.mo - 1, t.d));
  return composeWeekly(t, { week: weekKey(now), lines: B.weeklyLines(secs) });
}

async function accessFrom(rt) {
  const g = await s.google({ refresh_token: rt, grant_type: "refresh_token" });
  if (!g.ok || !g.j.access_token) {
    const e = new Error(g.j.error || "google");
    e.revoked = g.j.error === "invalid_grant";
    throw e;
  }
  return g.j.access_token;
}

async function readBody(req) {
  if (req.body && typeof req.body === "object") return req.body;
  if (typeof req.body === "string") { try { return JSON.parse(req.body); } catch (e) { return {}; } }
  let raw = "";
  try { for await (const c of req) raw += c; } catch (e) { return {}; }
  try { return JSON.parse(raw || "{}"); } catch (e) { return {}; }
}

/** 알림 주소 모양 확인 — 브라우저 푸시 서비스의 https 주소 + 열쇠 둘. */
function validSub(sub) {
  return !!(sub && typeof sub.endpoint === "string" && /^https:\/\//.test(sub.endpoint)
    && sub.endpoint.length < 1000 && sub.keys && typeof sub.keys.p256dh === "string"
    && typeof sub.keys.auth === "string");
}

module.exports = {
  vapid, subId, store, storeReady, send, now, kst, dueNow, buildBrief, compose, titlesFrom, accessFrom,
  readBody, validSub, docIdFrom, SEND_FROM, SEND_UNTIL_H,
  dueWeekly, weekKey, buildWeekly, composeWeekly,
  _setStore: (x) => { _store = x; }, _setSend: (fn) => { _send = fn; },
  _setClock: (fn) => { _clock = fn; },
};
