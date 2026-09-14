// 계정에 붙는 설정 보관소 — 구글 드라이브의 **앱 전용 숨김 폴더**(appDataFolder).
//
// 시트 주소와 서류 폴더를 브라우저에 두면 기기마다 다시 넣어야 하고, 브라우저
// 자료를 지우면 사라진다. 계정에 붙여 두면 어느 기기에서 로그인해도 따라온다.
//
// PC 앱이 이미 같은 폴더에 planner_sync.json 으로 설정을 올리고 있다.
// 그래서 **처음 폰에서 로그인하면 PC 에 넣어 둔 값을 그대로 물려받는다** —
// 폰에서 따로 입력할 일이 없다.
import { token, setOffline } from "./auth.js";
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
    tok = await token({ interactive: false });
    if (!tok) throw new NeedSignIn();
    try { r = await go(); } catch (e) { setOffline(true); throw new Offline(); }
  }
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
 * 웹앱 파일을 먼저 보고, 없으면 **PC 앱이 올려 둔 것**에서 꺼내 쓴다.
 * 그래서 PC 에서 이미 쓰고 계신 분은 폰에서 아무것도 입력하지 않아도 된다. */
export async function loadSettings() {
  const web = await readJson(WEB_FILE);
  if (web && (web.sheetId || web.driveFolder)) {
    return { sheetId: web.sheetId || "", sheetTab: web.sheetTab || "",
             driveFolder: web.driveFolder || "", from: "web" };
  }
  const pc = await readJson(PC_FILE);
  const txt = pc && pc.files && pc.files[PC_CFG];
  if (!txt) return null;
  let cfg;
  try { cfg = JSON.parse(txt); } catch (e) { return null; }
  if (!cfg || typeof cfg !== "object") return null;
  const out = {
    sheetId: String(cfg.sheetId || "").trim(),
    sheetTab: String(cfg.sheetName || "").trim(),
    driveFolder: String(cfg.filesDriveFolder || "").trim(),
    from: "pc",
  };
  return (out.sheetId || out.driveFolder) ? out : null;
}

/** 설정을 계정에 저장한다. 실패해도 화면은 그대로 — 이 기기에는 이미 저장돼 있다. */
export async function saveSettings(patch) {
  const cur = (await readJson(WEB_FILE)) || {};
  const next = { ...cur, ...patch, updatedAt: new Date().toISOString() };
  await writeJson(WEB_FILE, next);
  return next;
}
