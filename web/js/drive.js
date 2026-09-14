// 구글 드라이브 읽기 — planner/google_client.py 의 drive_* 함수들을 옮긴 것.
// 고객 서류 폴더는 **내 드라이브** 에 있다(공유 드라이브가 아니라서 driveId 류
// 매개변수가 필요 없다 — 나중에 공유 드라이브로 옮기면 여기를 고쳐야 한다).
import { token, setOffline } from "./auth.js";
import { NeedSignIn, WrongAccount, Offline, NeedScope } from "./sheets.js";

const FILES = "https://www.googleapis.com/drive/v3/files";
export const FOLDER_MIME = "application/vnd.google-apps.folder";

async function call(url, { raw = false } = {}) {
  let tok = await token();
  if (!tok) throw new NeedSignIn();
  const go = () => fetch(url, { headers: { Authorization: "Bearer " + tok } });
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
  if (!r.ok) throw new Error(`드라이브를 읽지 못했습니다 (HTTP ${r.status})`);
  return raw ? r.blob() : r.json();
}

/** 사용자가 적어 준 것에서 폴더를 알아낸다 — 이름이든, id 든, 주소를 붙여넣든.
 *
 * 폰에서는 긴 id 를 손으로 치기 어렵다. 드라이브 앱에서 '링크 복사' 한 것을
 * 그대로 붙여넣는 게 가장 쉬운 길이라 주소 모양도 받아 준다.
 * 통신을 하지 않는 순수 계산이라 따로 시험한다. */
export function parseFolderRef(s) {
  const t = String(s || "").trim();
  if (!t) return { kind: "none", value: "" };
  // https://drive.google.com/drive/folders/<id>?usp=... / .../drive/u/0/folders/<id>
  // 주소 안의 /folders/ 뒤는 길이를 따지지 않는다 — 경로 모양만으로 이미 폴더 id 다.
  let m = t.match(/\/folders\/([A-Za-z0-9_-]+)/);
  if (m) return { kind: "id", value: m[1] };
  // https://drive.google.com/open?id=<id>  ·  ...?id=<id>&...
  m = t.match(/[?&]id=([A-Za-z0-9_-]+)/);
  if (m) return { kind: "id", value: m[1] };
  // 주소를 붙여넣었는데 폴더 id 를 못 찾았다면 이름으로 오해하면 안 된다
  if (/^https?:\/\//i.test(t)) return { kind: "bad", value: t };
  // 드라이브 id 에는 공백이 없고 보통 25자가 넘는다
  if (!/\s/.test(t) && /^[A-Za-z0-9_-]{20,}$/.test(t)) return { kind: "id", value: t };
  return { kind: "name", value: t };
}

/** 이름·id·주소 → 폴더 id. 못 찾으면 빈 값. */
export async function folderId(ref) {
  const p = parseFolderRef(ref);
  if (p.kind === "none" || p.kind === "bad") return "";
  if (p.kind === "id") {
    const j = await call(`${FILES}/${p.value}?fields=id,mimeType`);
    if (j && j.mimeType === FOLDER_MIME) return j.id;
    return "";
  }
  // 이름이 같은 폴더가 여럿이면 가장 최근 것 — 파이썬 쪽과 같은 규칙이다.
  const q = encodeURIComponent(
    `name='${p.value.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`
    + ` and mimeType='${FOLDER_MIME}' and trashed=false`);
  const j = await call(`${FILES}?q=${q}&fields=files(id,name,modifiedTime)`
                     + `&orderBy=modifiedTime desc&pageSize=10`);
  const f = (j && j.files) || [];
  return f.length ? f[0].id : "";
}

/** 폴더 바로 밑의 폴더·파일. 페이지가 나뉘면 끝까지 모은다. */
export async function listFolder(id) {
  const out = [];
  let pageToken = "";
  for (let guard = 0; guard < 50; guard++) {     // 5만 개면 충분하다
    const q = encodeURIComponent(`'${id}' in parents and trashed=false`);
    let url = `${FILES}?q=${q}&pageSize=1000&orderBy=folder,modifiedTime desc`
            + `&fields=${encodeURIComponent("nextPageToken,files(id,name,mimeType,size,modifiedTime)")}`;
    if (pageToken) url += "&pageToken=" + encodeURIComponent(pageToken);
    const j = await call(url);
    if (!j) break;
    out.push(...(j.files || []));
    pageToken = j.nextPageToken || "";
    if (!pageToken) break;
  }
  return out;
}

/** 파일 내용을 그대로 받는다(그림·PDF 보기용). */
export function download(fileId) {
  return call(`${FILES}/${fileId}?alt=media`, { raw: true });
}

// ---------------------------------------------------------------- 파일 종류
// 팩스가 TIFF 로 오기도 해서 파이썬 쪽 목록에 맞춰 둔다. 다만 **브라우저는
// TIFF 를 못 그린다** — 목록에는 나오되 보기는 드라이브 앱에 넘긴다.
const IMG = ["jpg", "jpeg", "png", "gif", "bmp", "webp"];
const BROWSER_CANT = ["tif", "tiff"];

export const ext = (name) => {
  const m = String(name || "").toLowerCase().match(/\.([a-z0-9]+)$/);
  return m ? m[1] : "";
};
export const isImage = (name) => IMG.includes(ext(name));
export const isPdf = (name) => ext(name) === "pdf";
export const canPreview = (name) => isImage(name) || isPdf(name);
export const needsDriveApp = (name) => BROWSER_CANT.includes(ext(name));
export const openInDrive = (id) => `https://drive.google.com/file/d/${id}/view`;
