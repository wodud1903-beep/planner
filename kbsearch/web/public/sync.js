// 구글 동기화 — 회사 공통 자료에서 **나만 고친 것**(팩스번호 등)을 내 구글 계정으로 PC 와 맞춘다.
//
// 지점장 요청: "PC 에서 동기화해서 수정하는 것처럼 웹도 구글 동기화 단추 — 둘 중 한 곳에서 고치면
// 같은 구글 아이디는 양쪽 모두 반영." 처음엔 심사서류 3종만이었고, 이제 모든 회사 자료다(2026-11-09 —
// "회사 공통 자료도 로그인한 계정에 한해 내 계정에만 수정"). 일정관리기 자료검색도 같은 파일을 쓴다.
//
// 주고받는 곳: 내 구글 드라이브의 '앱 전용 공간'(appDataFolder, 일정관리기·업무자료검색 PC 와 같은 곳)의
// kb_edits.json 하나. PC 프로그램(kbsearch/sync.py)과 **같은 모양 · 같은 규칙**이다.
//   { "v": 1, "edits": { "개인 심사서류": { "item": {...본문 등} | null, "base": {...}, "at": "UTC" } } }
//   · item 이 null 이면 '회사 자료로 되돌림' 이다(되돌린 것도 다른 쪽에 전한다).
//   · 제목마다 **나중에 고친 쪽(at)** 이 이긴다. 시각은 'YYYY-MM-DDTHH:MM:SSZ'(글자로 견준다).
//   · 같은 제목이 여럿인 자료는 첫 번째만 주고받는다(나머지는 이 기기에만).
// 로그인·토큰은 이 주소의 서버(api/auth/*)가 맡는다 — 화면 코드는 1시간짜리 토큰만 쓴다.
export const SYNC_TITLES = ["개인 심사서류", "개인사업자 심사서류", "법인 심사서류"];
export const EDITS_FILE = "kb_edits.json";
// 내 메모 — 일정관리기·PC 업무자료검색의 드라이브 동기화 묶음. 웹은 **읽기만** 한다
// (묶음에 일정관리기 할일·고객메모가 함께 들어 있어, 메모 칸만 꺼내고 나머지는 버린다).
export const PLANNER_FILE = "planner_sync.json";
const MINE_KEY = "kb_mine.json";
const TOMBS_KEY = "deleted.json";
const DRIVE = "https://www.googleapis.com/drive/v3/files";
const UPLOAD = "https://www.googleapis.com/upload/drive/v3/files";

// SYNC_TITLES 는 처음 주고받던 셋(검사가 쓴다). 이제는 같은 제목 중 첫 번째인 자료는 모두 주고받는다.
export const isSyncKey = (k) => Array.isArray(k) && k[1] === 0 && !!String(k[0] || "").trim();
export const stamp = (d = new Date()) => d.toISOString().slice(0, 19) + "Z";

const goodRec = (r) => r && typeof r === "object" && typeof r.at === "string"
  && (r.item === null || (r.item && typeof r.item === "object"));

/**
 * 이 기기 것과 드라이브 것을 합친다(계산만 — 저장은 부르는 쪽이).
 *   recs : 이 기기에서 고친 것 [{key, base, item, at?}] (세 자료 말고 것도 섞여 있다)
 *   dead : 이 기기에서 되돌린 세 자료 {제목: at}
 *   remote: 드라이브 파일의 edits {제목: {item, base, at}}
 * 돌려줌 {recs, dead, edits, changedTitles, pushNeeded}
 */
export function mergeEdits(recs, dead, remote, now = stamp()) {
  const outRecs = (recs || []).filter((r) => !isSyncKey(r.key));
  const outDead = {};
  const edits = { ...(remote || {}) };
  const changedTitles = [];
  let pushNeeded = false;
  // 이 기기에서 고친 것 · 되돌린 것 · 드라이브에 있는 것의 제목을 다 본다(PC 와 같은 차례)
  const titles = [];
  for (const t of [...(recs || []).filter((r) => isSyncKey(r.key)).map((r) => r.key[0]),
                   ...Object.keys(dead || {}), ...Object.keys(remote || {})]) {
    if (t && !titles.includes(t)) titles.push(t);
  }
  for (const t of titles) {
    const lr = (recs || []).find((r) => Array.isArray(r.key) && r.key[0] === t && r.key[1] === 0);
    let L = lr ? { item: lr.item, base: lr.base || null, at: String(lr.at || "") }
              : (dead || {})[t] ? { item: null, base: null, at: String(dead[t]) } : null;
    const R = goodRec((remote || {})[t]) ? remote[t] : null;
    // 동기화 전에 고친 것(시각 없음) — 드라이브에 아무것도 없을 때만 지금 고친 것으로 올린다.
    // 드라이브에 있으면 그쪽(다른 곳에서 동기화하며 고친 것)이 이긴다.
    if (L && !L.at) L = { ...L, at: R ? "" : now };
    // 나중 쪽이 이긴다. 시각이 같으면 드라이브 쪽 — 단, 내용까지 같으면 이 기기 것을 그대로 둔다(PC 와 같다)
    const same = L && R && JSON.stringify(R.item || null) === JSON.stringify(L.item || null);
    const W = !L ? R : !R ? L : (R.at > L.at || (R.at === L.at && !same) ? R : L);
    if (!W) continue;
    if (W.item) {
      outRecs.push(W === L && lr ? { ...lr, at: W.at } : { key: [t, 0], base: W.base || null, item: W.item, at: W.at });
    } else {
      outDead[t] = W.at;
    }
    const before = lr ? String(lr.item.body ?? "") : null;
    const after = W.item ? String(W.item.body ?? "") : null;
    if (W !== L && before !== after) changedTitles.push(t);
    const rec = { item: W.item || null, base: W.base || null, at: W.at };
    if (JSON.stringify(rec) !== JSON.stringify(R ? { item: R.item || null, base: R.base || null, at: R.at } : null)) {
      edits[t] = rec;
      pushNeeded = true;
    }
  }
  return { recs: outRecs, dead: outDead, edits, changedTitles, pushNeeded };
}

// ------------------------------------------------------------------ 로그인 · 토큰
let tok = null;                    // {access_token, exp, email}
export const account = () => (tok && tok.email) || "";

/** 쓸 토큰. 로그인 안 했으면 null, 서버가 잠깐 탈났으면 throw. */
export async function token(force = false) {
  if (!force && tok && tok.exp - Date.now() > 120e3) return tok;
  const r = await fetch("/api/auth/token", { method: "POST", credentials: "same-origin" });
  const j = await r.json().catch(() => ({}));
  if (r.status === 401) { tok = null; return null; }
  if (!r.ok || !j.access_token) throw new Error("로그인 서버에 닿지 못했습니다 — 잠시 뒤 다시 해 주세요.");
  tok = { access_token: j.access_token, exp: Date.now() + (j.expires_in || 3600) * 1000,
          email: j.email || "", missing: j.missing || [] };
  return tok;
}

export async function logout() {
  tok = null;
  try { await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }); } catch (e) { /* 무시 */ }
}

// ------------------------------------------------------------------ 드라이브 앱 전용 공간
async function g(t, url, init = {}) {
  const r = await fetch(url, { ...init, headers: { ...(init.headers || {}), Authorization: `Bearer ${t.access_token}` } });
  if (r.status === 401 || r.status === 403) {
    const e = new Error(r.status === 403 ? "구글 드라이브 권한이 없습니다 — 다시 로그인해 '앱 데이터' 항목을 체크해 주세요."
                                         : "로그인이 끝났습니다 — 다시 해 주세요.");
    e.auth = true;
    throw e;
  }
  if (!r.ok) throw new Error(`구글 드라이브에 닿지 못했습니다 (HTTP ${r.status})`);
  return r;
}

async function findMeta(t, name) {
  const q = new URLSearchParams({ spaces: "appDataFolder", q: `name='${name}'`, fields: "files(id,modifiedTime)" });
  const list = await (await g(t, `${DRIVE}?${q}`)).json();
  const f = ((list && list.files) || [])[0];
  return f && f.id ? { id: f.id, at: String(f.modifiedTime || "") } : null;
}
const findFile = async (t, name) => (await findMeta(t, name))?.id || null;
const readFile = async (t, fid) => (await g(t, `${DRIVE}/${encodeURIComponent(fid)}?alt=media`)).text();

/** 드라이브 파일 → {fid, edits}. 없으면 {fid:null, edits:{}}. **못 읽으면 throw — 그때는 쓰지 않는다.** */
export async function readRemote(t) {
  const fid = await findFile(t, EDITS_FILE);
  if (!fid) return { fid: null, edits: {} };
  const text = await readFile(t, fid);
  let o;
  try { o = text.trim() ? JSON.parse(text) : {}; } catch (e) {
    throw new Error("드라이브의 고친 자료 파일이 깨져 있어 동기화를 멈췄습니다.");
  }
  return { fid, edits: o && typeof o.edits === "object" && o.edits ? o.edits : {} };
}

export async function writeRemote(t, fid, edits) {
  const body = JSON.stringify({ v: 1, updatedAt: stamp(), edits }, null, 1);
  if (fid) {
    await g(t, `${UPLOAD}/${encodeURIComponent(fid)}?uploadType=media`, {
      method: "PATCH", headers: { "Content-Type": "application/json; charset=UTF-8" }, body });
    return fid;
  }
  const b = "kbsearch" + Math.random().toString(36).slice(2);
  const multipart = `--${b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n`
    + JSON.stringify({ name: EDITS_FILE, parents: ["appDataFolder"] })
    + `\r\n--${b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${body}\r\n--${b}--`;
  const r = await g(t, `${UPLOAD}?uploadType=multipart&fields=id`, {
    method: "POST", headers: { "Content-Type": `multipart/related; boundary=${b}` }, body: multipart });
  return (await r.json()).id;
}

// ------------------------------------------------------------------ 내 메모(읽기만)
function cleanFiles(files) {
  const out = [];
  for (const f of Array.isArray(files) ? files : []) {
    if (!f || typeof f !== "object") continue;
    const id = String(f.id || "").trim(), name = String(f.name || "").trim();
    if (!id || !name || id.startsWith("local-")) continue;   // 아직 안 올린 첨부는 그 PC 에만 있다
    out.push({ id, name, mime: String(f.mime || "").trim(), size: Math.max(0, parseInt(f.size, 10) || 0) });
  }
  return out;
}

/** 메모 한 건을 화면에 쓸 모양으로(PC kb._clean 과 같은 칸). 제목이 없으면 버린다. */
export function cleanMemo(o) {
  if (!o || typeof o !== "object") return null;
  const title = String(o.title || "").trim();
  if (!title) return null;
  let checks = o.checklist || [];
  if (typeof checks === "string") checks = checks.split("\n");
  const it = {
    category: String(o.category || "").trim(), finance: String(o.finance || "").trim(), title,
    tags: String(o.tags || "").trim(),
    body: String(o.body || "").split("\n").map((l) => l.trimEnd()).join("\n"),
    checklist: (Array.isArray(checks) ? checks : []).map((c) => String(c).trim()).filter(Boolean),
  };
  const files = cleanFiles(o.files);
  if (files.length) it.files = files;
  if (o.at) it.at = String(o.at);
  return it;
}

/**
 * 동기화 묶음의 메모 칸 → 메모 목록. 지운 표식(deleted.json)보다 나중에 고치지 않은 메모는 뺀다
 * (PC sync.drop_dead 와 같은 규칙). 묶음이 없으면 {items: [], found: false}.
 */
export function memosFromBundle(b) {
  const files = (b && typeof b === "object" && b.files && typeof b.files === "object") ? b.files : {};
  let raw = [];
  try { raw = String(files[MINE_KEY] || "").trim() ? JSON.parse(files[MINE_KEY]) : []; } catch (e) { raw = []; }
  let tombs = {};
  try { tombs = String(files[TOMBS_KEY] || "").trim() ? JSON.parse(files[TOMBS_KEY]) : {}; } catch (e) { tombs = {}; }
  const dead = (tombs && typeof tombs[MINE_KEY] === "object" && tombs[MINE_KEY]) || {};
  const seen = new Set();
  const out = [];
  for (const o of Array.isArray(raw) ? raw : []) {
    const it = cleanMemo(o);
    if (!it || seen.has(it.title)) continue;
    if (it.title in dead && String(it.at || "") <= String(dead[it.title] || "")) continue;
    seen.add(it.title);
    out.push(it);
  }
  return out;
}

/**
 * 내 메모를 받는다. 못 읽으면 throw(받아 둔 것을 지우지 않게).
 * since = 지난번에 받은 묶음의 고친 시각 — 그대로면 내려받지 않는다({unchanged}). 묶음에는 일정관리기
 * 할일·고객메모 등이 함께 있어 클 수 있다(폰 데이터를 아낀다).
 */
export async function readMemos(t, since = "") {
  const meta = await findMeta(t, PLANNER_FILE);
  if (!meta) return { items: [], found: false, stamp: "" };
  if (since && meta.at && meta.at === since) return { unchanged: true, stamp: since };
  const text = await readFile(t, meta.id);
  let b;
  try { b = JSON.parse(text); } catch (e) {
    throw new Error("드라이브의 동기화 묶음을 읽을 수 없습니다(모양이 깨짐).");
  }
  return { items: memosFromBundle(b), found: true, stamp: meta.at };
}
