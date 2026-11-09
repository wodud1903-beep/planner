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

const WEB_FILE = "planner_web.json";     // 웹앱이 쓰는 파일
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

async function findId(name) {
  const r = await call(`${FILES}?spaces=appDataFolder`
    + `&q=${encodeURIComponent(`name='${name}'`)}`
    + `&fields=${encodeURIComponent("files(id,name,modifiedTime)")}`);
  if (!r) return "";
  const j = await r.json();
  const f = (j.files || [])[0];
  return f ? f.id : "";
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
/** 이 계정의 설정. 없으면 null.
 *
 * PC 앱이 올려 둔 것(planner_sync.json 의 plan_cfg.json)과 웹앱에서 바꾼 것(planner_web.json)
 * 가운데 **나중에 바꾼 쪽**을 쓴다(v1.29). 예전엔 웹앱 파일이 한 번 생기면 그것만 봐서, PC 에서
 * 시트·서류 폴더를 바꿔도 웹은 옛 것을 계속 썼다. 시트(주소+탭)와 서류 폴더는 따로 고른다. */
export async function loadSettings() {
  const [web, pc] = await Promise.all([readJson(WEB_FILE), readJson(PC_FILE)]);
  return pickSettings(web, pc);
}

const when = (s) => { const t = Date.parse(String(s || "")); return isNaN(t) ? 0 : t; };

/** 두 곳의 설정 → 쓸 것 {sheetId, sheetTab, driveFolder, from}. 통신 없는 계산(검사용). */
export function pickSettings(web, pc) {
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
  const sheetFrom = newer((x) => !!x.sheetId), folderFrom = newer((x) => !!x.driveFolder);
  const S = sheetFrom === "pc" ? P : sheetFrom === "web" ? W : null;
  const F = folderFrom === "pc" ? P : folderFrom === "web" ? W : null;
  const out = { sheetId: S ? S.sheetId : "", sheetTab: S ? S.sheetTab : "",
                driveFolder: F ? F.driveFolder : "", from: sheetFrom || folderFrom };
  return (out.sheetId || out.driveFolder) ? out : null;
}

/** 설정을 계정에 저장한다. 실패해도 화면은 그대로 — 이 기기에는 이미 저장돼 있다. */
export async function saveSettings(patch) {
  const cur = (await readJson(WEB_FILE)) || {};
  const next = { ...cur, ...patch, updatedAt: new Date().toISOString() };
  await writeJson(WEB_FILE, next);
  return next;
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
