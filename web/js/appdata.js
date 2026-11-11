// 계정에 붙는 설정 보관소 — 구글 드라이브의 **앱 전용 숨김 폴더**(appDataFolder).
//
// 시트 주소와 서류 폴더를 브라우저에 두면 기기마다 다시 넣어야 하고, 브라우저
// 자료를 지우면 사라진다. 계정에 붙여 두면 어느 기기에서 로그인해도 따라온다.
//
// PC 앱이 이미 같은 폴더에 planner_sync.json 으로 설정을 올리고 있다.
// 그래서 **처음 폰에서 로그인하면 PC 에 넣어 둔 값을 그대로 물려받는다** —
// 폰에서 따로 입력할 일이 없다.
import { token, setOffline, down, reached } from "./auth.js";
import { NeedSignIn, WrongAccount, Offline, NeedScope } from "./sheets.js";

const FILES = "https://www.googleapis.com/drive/v3/files";
const UPLOAD = "https://www.googleapis.com/upload/drive/v3/files";

const WEB_FILE = "planner_web.json";     // 웹앱이 쓰던 파일(v1.29 까지 — 이제 읽기만)
const ACCT_FILE = "account_settings.json"; // PC·웹이 같이 쓰는 시트·서류 폴더(v1.30, planner/account_settings.py)
const PC_FILE = "planner_sync.json";     // PC 앱이 올리는 묶음
const PC_CFG = "plan_cfg.json";          // 그 묶음 안의 설정 파일

async function call(url, { method = "GET", body = null, raw = null, type = null } = {}) {
  let tok = await token();
  if (!tok) throw new NeedSignIn();
  const go = () => fetch(url, {
    method,
    headers: {
      Authorization: "Bearer " + tok,
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(type ? { "Content-Type": type } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
    ...(raw !== null ? { body: raw } : {}),
  });
  let r;
  try { r = await go(); } catch (e) { setOffline(true); throw new Offline(); }
  if (r.status === 401) {
    tok = await token({ fresh: true });   // 들고 있던 토큰은 버리고 새로
    if (!tok) throw new NeedSignIn();
    try { r = await go(); } catch (e) { setOffline(true); throw new Offline(); }
  }
  // 닿았다 — '오프라인' 을 걷는다. 5xx 는 구글이 잠깐 탈난 것 → 안내하고 조금 뒤 다시(boot.js)
  if (r.status >= 500) {
    down("google");
    throw new Error(`구글 서버가 잠시 응답하지 않습니다 (HTTP ${r.status}) — 잠시 뒤 다시 불러옵니다.`);
  }
  reached();
  if (r.status === 403) {
    let m = "";
    try { m = ((await r.clone().json()).error || {}).message || ""; } catch (x) {}
    if (/insufficient|scope/i.test(m)) throw new NeedScope(m);
    throw new WrongAccount();
  }
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`설정을 읽지 못했습니다 (HTTP ${r.status})`);
  return r;
}

async function findMeta(name) {
  const r = await call(`${FILES}?spaces=appDataFolder`
    + `&q=${encodeURIComponent(`name='${name}'`)}`
    + `&fields=${encodeURIComponent("files(id,name,modifiedTime)")}`);
  if (!r) return null;
  const j = await r.json();
  return (j.files || [])[0] || null;
}

async function findId(name) {
  const f = await findMeta(name);
  return f ? f.id : "";
}

// 작은 파일을 자주 들여다볼 때(30초마다 · 화면으로 돌아올 때) — 목록 한 번으로 바뀌었는지 보고,
// 바뀌었을 때만 내용을 받는다. {data, changed}. 파일이 없으면 data=null.
const _seen = new Map();     // 이름 → {mod, data}
export async function readIfChanged(name) {
  const f = await findMeta(name);
  const mod = f ? `${f.id}@${f.modifiedTime || ""}` : "";
  const had = _seen.get(name);
  if (had && had.mod === mod && mod) return { data: had.data, changed: false };
  let data = null;
  if (f) {
    const r = await call(`${FILES}/${f.id}?alt=media`);
    if (r) { try { data = JSON.parse(await r.text()); } catch (e) { data = null; } }
  }
  _seen.set(name, { mod, data });
  return { data, changed: !had || had.mod !== mod };
}

/** 앱 전용 공간의 JSON 파일을 통째로 쓴다(없으면 만든다). 다음 확인 때 다시 읽게 해 둔다. */
export async function writeAppJson(name, obj) {
  const id = await writeJson(name, obj);
  _seen.delete(name);
  return id;
}

async function readJson(name) {
  const id = await findId(name);
  if (!id) return null;
  const r = await call(`${FILES}/${id}?alt=media`);
  if (!r) return null;
  try { return JSON.parse(await r.text()); } catch (e) { return null; }
}

async function writeJson(name, obj) {
  let id = await findId(name);
  if (!id) {
    const r = await call(FILES, { method: "POST",
      body: { name, parents: ["appDataFolder"] } });
    if (!r) throw new Error("설정 파일을 만들지 못했습니다.");
    id = (await r.json()).id;
  }
  await call(`${UPLOAD}/${id}?uploadType=media`, {
    method: "PATCH", raw: JSON.stringify(obj),
    type: "application/json; charset=UTF-8",
  });
  return id;
}

// ---------------------------------------------------------------- 설정
/** 이 계정의 설정 {sheetId, sheetTab, driveFolder, from}. 없으면 null.
 *
 * v1.30: PC 와 웹이 같이 쓰는 **계정 설정 파일(account_settings.json)** 이 기준이다 — PC 는 설정 창에서
 * 시트·서류 폴더를 바꾸면 그 자리에서 이 파일에 쓰고, 웹도 바꾸면 여기에 쓴다(항목마다 나중에 바꾼 쪽).
 * 파일에 없는 항목만 예전 곳(PC 묶음의 plan_cfg.json · 웹 파일 planner_web.json)에서 고른다.
 *
 * light=true(30초마다 · 화면으로 돌아올 때): 계정 설정 파일만, 바뀌었을 때만 본다 — 안 바뀌었으면 null. */
export async function loadSettings({ light = false } = {}) {
  if (light) {
    const { data, changed } = await readIfChanged(ACCT_FILE);
    return changed ? pickSettings(null, null, data) : null;
  }
  const [web, pc, acct] = await Promise.all([
    readJson(WEB_FILE), readJson(PC_FILE), readIfChanged(ACCT_FILE).then((x) => x.data)]);
  _pcExtras = pcExtras(pc);
  return pickSettings(web, pc, acct);
}

// PC 설정에서 웹이 따라가는 나머지(v1.32) — 인증문자 시트 · 지점 공유 캘린더. 묶음을 읽는 김에 같이 뽑아 둔다.
let _pcExtras = null;
/** PC 묶음 → {otpSheet, otpTab, branchCal(PC 가 적은 적 없으면 undefined)}. PC 설정이 없으면 null. 통신 없는 계산. */
export function pcExtras(pc) {
  const txt = pc && pc.files && pc.files[PC_CFG];
  if (!txt) return null;
  let cfg = null;
  try { cfg = JSON.parse(txt); } catch (e) { cfg = null; }
  if (!cfg || typeof cfg !== "object") return null;
  const out = { otpSheet: String(cfg.otpSheet || "").trim(), otpTab: String(cfg.otpTab || "").trim() };
  if (typeof cfg.branchCal === "string") out.branchCal = cfg.branchCal.trim();
  return out;
}
/** 마지막으로 읽은 PC 설정의 나머지(loadSettings 를 가볍지 않게 부른 뒤). */
export const lastPcExtras = () => _pcExtras;

const when = (s) => { const t = Date.parse(String(s || "")); return isNaN(t) ? 0 : t; };

/** 세 곳의 설정 → 쓸 것 {sheetId, sheetTab, driveFolder, from}. 통신 없는 계산(검사용). */
export function pickSettings(web, pc, acct = null) {
  const w = web && typeof web === "object" ? web : null;
  let cfg = null, pcAt = 0;
  const txt = pc && pc.files && pc.files[PC_CFG];
  if (txt) {
    try { cfg = JSON.parse(txt); } catch (e) { cfg = null; }
    if (!cfg || typeof cfg !== "object") cfg = null;
    pcAt = when((pc.times || {})[PC_CFG] || pc.updatedAt);
  }
  const webAt = w ? when(w.updatedAt) : 0;
  const P = cfg ? { sheetId: String(cfg.sheetId || "").trim(), sheetTab: String(cfg.sheetName || "").trim(),
                    driveFolder: String(cfg.filesDriveFolder || "").trim() } : null;
  const W = w ? { sheetId: String(w.sheetId || "").trim(), sheetTab: String(w.sheetTab || "").trim(),
                  driveFolder: String(w.driveFolder || "").trim() } : null;
  // 시각이 같거나 웹앱 파일에 시각이 없으면 PC 쪽 — PC 가 원래 쓰는 곳이다
  const newer = (has) => {
    const pOk = P && has(P), wOk = W && has(W);
    if (pOk && wOk) return webAt > pcAt ? "web" : "pc";
    return pOk ? "pc" : wOk ? "web" : "";
  };
  let sheetFrom = newer((x) => !!x.sheetId), folderFrom = newer((x) => !!x.driveFolder);
  let S = sheetFrom === "pc" ? P : sheetFrom === "web" ? W : null;
  let F = folderFrom === "pc" ? P : folderFrom === "web" ? W : null;
  // 계정 설정 파일에 있는 항목이 언제나 먼저다(v1.30)
  const A = acct && typeof acct === "object" ? acct : null;
  const as = A && A.sheet && typeof A.sheet === "object" ? A.sheet : null;
  const af = A && A.folder && typeof A.folder === "object" ? A.folder : null;
  if (as && String(as.id || "").trim()) {
    S = { sheetId: String(as.id).trim(), sheetTab: String(as.tab || "").trim() };
    sheetFrom = "account";
  }
  if (af && String(af.ref || "").trim()) {
    F = { driveFolder: String(af.ref).trim() };
    folderFrom = "account";
  }
  const out = { sheetId: S ? S.sheetId : "", sheetTab: S ? S.sheetTab : "",
                driveFolder: F ? F.driveFolder : "", from: sheetFrom || folderFrom };
  return (out.sheetId || out.driveFolder) ? out : null;
}

/** 이 기기에서 바꾼 설정을 계정 설정 파일에 저장한다 — PC·다른 기기가 따라온다.
 *  patch: {sheetId, sheetTab} 또는 {driveFolder}. 실패해도 화면은 그대로 — 이 기기에는 이미 저장돼 있다.
 *  ⚠️ 못 읽으면 쓰지 않는다(다른 항목을 덮지 않게 — 예외가 그대로 올라간다). */
export async function saveSettings(patch) {
  const { data } = await readIfChanged(ACCT_FILE);
  const cur = data && typeof data === "object" ? { ...data } : {};
  const at = stamp();
  if ("sheetId" in patch) cur.sheet = { id: String(patch.sheetId || ""), tab: String(patch.sheetTab || ""), at, by: "web" };
  if ("driveFolder" in patch) cur.folder = { ref: String(patch.driveFolder || ""), at, by: "web" };
  cur.v = 1;
  cur.updatedAt = at;
  await writeAppJson(ACCT_FILE, cur);
  return cur;
}

// ---------------------------------------------------------------- PC 묶음 안의 파일
// PC 앱의 동기화 묶음(planner_sync.json)은 {files: {이름: 글}, times: {이름: 시각}} 이다.
// 폰에서 고객 메모를 남기면 그 안의 customer_notes.json 을 고치고 시각을 지금으로 둔다 —
// PC 는 다음 동기화 때 '원격이 더 최신' 으로 보고 자기 것과 **합친다**(sync.py).
// 시각 모양은 PC 와 같게: "2026-11-01T05:12:33Z" (글자로 크기를 견준다).
const stamp = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

/** PC 묶음 안 파일 하나(JSON). 없으면 null. */
export async function readPcFile(name) {
  const b = await readJson(PC_FILE);
  const txt = b && b.files && b.files[name];
  if (!txt) return null;
  try { return JSON.parse(txt); } catch (e) { return null; }
}

/** PC 묶음 안 파일 하나를 고친다. fn(지금 값|null) → 새 값. 고친 값을 돌려준다.
 *  ⚠️ 읽고 바로 쓴다(그 사이 몇백 ms). PC 가 그 틈에 올린 다른 파일을 덮지 않게
 *     묶음은 통째로 다시 읽은 것에 이 파일만 바꿔 끼운다. */
export async function updatePcFile(name, fn) {
  const b = (await readJson(PC_FILE)) || {};
  b.files = b.files && typeof b.files === "object" ? b.files : {};
  b.times = b.times && typeof b.times === "object" ? b.times : {};
  let cur = null;
  try { cur = b.files[name] ? JSON.parse(b.files[name]) : null; } catch (e) { cur = null; }
  const next = fn(cur);
  b.files[name] = JSON.stringify(next, null, 2);
  const now = stamp();
  b.times[name] = now;
  b.updatedAt = now;
  await writeJson(PC_FILE, b);
  return next;
}
