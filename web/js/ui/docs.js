// 고객정보 서류 — 드라이브 폴더를 앱 안에서 본다.
//
// 쓰는 모양: 고객 이름으로 찾아 → 그 폴더 열어 → 서류 한 장 본다.
// 그래서 **맨 윗 겹(고객 폴더 목록)만 저장해 두고** 거기서 초성으로 찾는다.
// 폴더 안쪽까지 통째로 훑지 않는다 — 폰에서 그건 너무 비싸고, 실제로 찾는 건
// 늘 고객 이름이다.
import { html, raw, esc, render, $, $$ } from "./dom.js";
import * as store from "../store.js";
import * as drive from "../drive.js";
import * as sheets from "../sheets.js";
import * as hangul from "../hangul.js";
import { setBody, markTab, paintState } from "./chrome.js";
import * as router from "../router.js";

let _rootId = "";
let _top = [];           // 맨 윗 겹 (대개 고객 폴더들)
let _prep = [];
let _q = "";
let _err = "";
let _timer = 0;
let _blob = "";          // 지금 보고 있는 파일의 blob 주소 (반드시 되돌려준다)
const SEARCH_DELAY = 130;
const RECENT_MAX = 8;

// ---------------------------------------------------------------- 설정·목록
const setFolderRef = (v) => store.put("meta", "driveFolder", v);
const folderRef = () => store.get("meta", "driveFolder").then((v) => v || "");

export async function load({ refresh = true } = {}) {
  const cached = await store.get("data", "driveTop");
  if (cached && cached.items) { _rootId = cached.rootId; setTop(cached.items); }
  if (!refresh) return;
  const ref = await folderRef();
  if (!ref) return;
  try {
    const id = _rootId || await drive.folderId(ref);
    if (!id) { _err = `'${ref}' 폴더를 찾지 못했습니다.`; paintList(); return; }
    _rootId = id;
    const items = await drive.listFolder(id);
    _err = "";
    await store.put("data", "driveTop", { rootId: id, items, at: Date.now() });
    setTop(items);
    return true;
  } catch (e) {
    if (e instanceof sheets.WrongAccount) {
      _err = "이 계정으로는 그 폴더를 열 수 없습니다. 계정을 확인해 주세요.";
    } else if (e instanceof sheets.NeedSignIn || e instanceof sheets.Offline) _err = "";
    else _err = e.message || "드라이브를 읽지 못했습니다.";
    paintState();
    paintList();
  }
  return false;
}

function setTop(items) {
  _top = (items || []).slice().sort(byFolderThenName);
  _prep = _top.map((f) => hangul.prepare(f.name));
  const cur = router.current();
  if (cur && cur.path === "/docs") paintList();
}

const byFolderThenName = (a, b) => {
  const ad = a.mimeType === drive.FOLDER_MIME, bd = b.mimeType === drive.FOLDER_MIME;
  if (ad !== bd) return ad ? -1 : 1;
  return String(a.name).localeCompare(String(b.name), "ko");
};

// 최근 열어본 고객 — 이 화면을 여는 이유는 대개 방금 통화한 고객이다.
async function recent() {
  const all = (await store.all("recent")) || [];
  return all.filter((r) => r.kind === "docs")
            .sort((a, b) => b.at - a.at).slice(0, RECENT_MAX);
}
async function touch(id, name) {
  await store.put("recent", null, { uid: "docs:" + id, kind: "docs", id, name, at: Date.now() });
}

// ---------------------------------------------------------------- 화면
export async function screen(m) {
  markTab("/docs");
  freeBlob();
  const path = router.current() ? router.current().path : "/docs";
  const ref = await folderRef();
  if (!ref) return setupScreen();
  if (m && m[1]) return folderScreen(decodeURIComponent(m[1]), m[2] ? decodeURIComponent(m[2]) : "");

  const ui = await store.ui();
  _q = ui.dQuery || "";
  setBody(html`
    <div class="pane">
      <div class="searchbar">
        <input id="dq" type="search" value="${_q}" autocomplete="off" enterkeyhint="search"
               placeholder="고객 폴더 검색 (초성도 됩니다)">
      </div>
      <div id="drecent"></div>
      <ul class="list" id="dlist"></ul>
      <p class="synced"><button class="linky" id="dsetup">서류 폴더 바꾸기</button></p>
    </div>`);
  const input = $("#dq");
  const run = () => { _q = input.value; store.ui({ dQuery: _q }); paintList(); };
  input.addEventListener("input", () => {
    clearTimeout(_timer); _timer = setTimeout(run, SEARCH_DELAY);
  });
  input.addEventListener("compositionend", () => { clearTimeout(_timer); run(); });
  $("#dsetup").onclick = () => setupScreen();

  paintRecent();
  paintList();
  if (!_top.length) await load(); else load();
}

function setupScreen() {
  setBody(html`
    <div class="pane">
      <h2>서류 폴더 정하기</h2>
      <p style="color:var(--sub)">고객 서류가 들어 있는 <b>내 드라이브</b> 폴더를
        알려 주세요. 드라이브 앱에서 그 폴더의 <b>링크를 복사</b>해 붙여넣는 게
        가장 쉽습니다. 폴더 이름을 그대로 적어도 됩니다.</p>
      <div class="searchbar">
        <input id="dref" type="text" placeholder="폴더 이름 또는 링크 붙여넣기"
               autocomplete="off" enterkeyhint="done">
      </div>
      <button class="bigcopy" id="dsave">이 폴더 쓰기</button>
      <p class="empty" id="dmsg"></p>
    </div>`);
  folderRef().then((v) => { if (v) $("#dref").value = v; });
  $("#dsave").onclick = async () => {
    const v = $("#dref").value.trim();
    const msg = $("#dmsg");
    const p = drive.parseFolderRef(v);
    if (p.kind === "none") { msg.textContent = "폴더 이름이나 링크를 적어 주세요."; return; }
    if (p.kind === "bad") {
      msg.textContent = "드라이브 폴더 링크가 아닌 것 같습니다. "
                      + "주소에 /folders/ 가 들어 있어야 합니다.";
      return;
    }
    msg.textContent = "찾는 중…";
    try {
      const id = await drive.folderId(v);
      if (!id) { msg.textContent = "그런 폴더를 찾지 못했습니다. 이름이 맞는지 봐 주세요."; return; }
      _rootId = id;
      await setFolderRef(v);
      await store.del("data", "driveTop");
      _top = []; _prep = [];
      router.go("/docs");
      await load();
    } catch (e) {
      msg.textContent = e instanceof sheets.NeedSignIn
        ? "구글 로그인이 필요합니다." : (e.message || "폴더를 찾지 못했습니다.");
    }
  };
}

async function paintRecent() {
  const box = $("#drecent");
  if (!box) return;
  const rs = await recent();
  if (!rs.length || _q) { render(box, ""); return; }
  render(box, html`<p class="kbhead">최근 본 고객</p>
    <div class="cats">${raw(rs.map((r) =>
      `<button data-id="${esc(r.id)}" data-name="${esc(r.name)}">${esc(r.name)}</button>`
    ).join(""))}</div>`);
  for (const b of $$("#drecent button")) {
    b.onclick = () => router.go(`/docs/${encodeURIComponent(b.dataset.id)}`);
  }
}

function paintList() {
  const el = $("#dlist");
  if (!el) return;
  const q = (_q || "").trim();
  const hits = q ? _top.filter((_, i) => hangul.matchesPrepared(_prep[i], q)) : _top;
  if (!hits.length) {
    render(el, html`<li class="empty">${_err
      ? _err : (_top.length ? "찾는 폴더가 없습니다." : "폴더를 읽는 중입니다…")}</li>`);
    return;
  }
  render(el, hits.map((f) => rowFor(f)).join(""));
  wireRows(el);
}

const icon = (f) => f.mimeType === drive.FOLDER_MIME ? "📁"
  : (drive.isPdf(f.name) ? "📕" : (drive.isImage(f.name) ? "🖼" : "📄"));

function rowFor(f) {
  const dir = f.mimeType === drive.FOLDER_MIME;
  return html`<li><button class="row" data-id="${f.id}" data-name="${f.name}"
      data-dir="${String(dir)}">
      <span class="t">${raw(icon(f) + " ")}${f.name}</span>
      ${raw(dir ? "" : `<span class="s">${esc(sizeOf(f))}</span>`)}
    </button></li>`;
}
function sizeOf(f) {
  const n = Number(f.size || 0);
  if (!n) return "";
  return n < 1024 * 1024 ? `${Math.round(n / 1024)} KB`
                         : `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function wireRows(el) {
  for (const b of $$("button.row", el)) {
    b.onclick = () => {
      const { id, name, dir } = b.dataset;
      if (dir === "true") { touch(id, name); router.go(`/docs/${encodeURIComponent(id)}`); }
      else openFile(id, name);
    };
  }
}

// ---------------------------------------------------------------- 폴더 안
async function folderScreen(id, name) {
  setBody(html`
    <div class="pane">
      <button class="chip backbtn2" id="dback">← 뒤로</button>
      <h2 id="dtitle" style="margin:10px 0 8px">${name || "폴더"}</h2>
      <ul class="list" id="dlist"><li class="empty">읽는 중입니다…</li></ul>
      <div id="dview"></div>
    </div>`);
  $("#dback").onclick = () => history.length > 1 ? history.back() : router.go("/docs");
  const key = "folder:" + id;
  const cached = await store.get("data", key);
  if (cached && cached.items) drawFolder(cached.items, cached.name);
  try {
    const items = (await drive.listFolder(id)).sort(byFolderThenName);
    const nm = name || (_top.find((f) => f.id === id) || {}).name || "폴더";
    await store.put("data", key, { items, name: nm, at: Date.now() });
    drawFolder(items, nm);
  } catch (e) {
    paintState();
    if (!cached) {
      render($("#dlist"), html`<li class="empty">${e instanceof sheets.NeedSignIn
        ? "구글 로그인이 필요합니다." : (e.message || "폴더를 읽지 못했습니다.")}</li>`);
    }
  }
}

function drawFolder(items, name) {
  const t = $("#dtitle");
  if (t && name) t.textContent = name;
  const el = $("#dlist");
  if (!el) return;
  if (!items.length) { render(el, html`<li class="empty">빈 폴더입니다.</li>`); return; }
  render(el, items.map((f) => rowFor(f)).join(""));
  wireRows(el);
}

// ---------------------------------------------------------------- 파일 보기
function freeBlob() {
  if (_blob) { URL.revokeObjectURL(_blob); _blob = ""; }
}

async function openFile(id, name) {
  const box = $("#dview");
  if (!box) return;
  freeBlob();
  if (drive.needsDriveApp(name)) {
    // 브라우저는 TIFF 를 못 그린다. 팩스가 이 형식으로 오므로 안내를 정확히 한다.
    render(box, html`<div class="viewer">
      <p class="empty">이 형식(${drive.ext(name).toUpperCase()})은 브라우저가 그리지 못합니다.</p>
      <a class="bigcopy" href="${drive.openInDrive(id)}" target="_blank"
         rel="noopener">드라이브 앱에서 열기</a></div>`);
    box.scrollIntoView({ block: "start", behavior: "smooth" });
    return;
  }
  if (!drive.canPreview(name)) {
    render(box, html`<div class="viewer">
      <p class="empty">앱 안에서 볼 수 없는 형식입니다.</p>
      <a class="bigcopy" href="${drive.openInDrive(id)}" target="_blank"
         rel="noopener">드라이브 앱에서 열기</a></div>`);
    box.scrollIntoView({ block: "start", behavior: "smooth" });
    return;
  }
  render(box, html`<div class="viewer"><p class="empty">불러오는 중…</p></div>`);
  box.scrollIntoView({ block: "start", behavior: "smooth" });
  try {
    const blob = await drive.download(id);
    _blob = URL.createObjectURL(blob);
    render(box, html`<div class="viewer">
      <div class="vhead"><b>${name}</b>
        <a class="chip" href="${drive.openInDrive(id)}" target="_blank" rel="noopener">드라이브에서</a>
        <button class="chip" id="dclose">닫기</button></div>
      ${raw(drive.isPdf(name)
        ? `<iframe class="vpdf" src="${esc(_blob)}" title="${esc(name)}"></iframe>`
        : `<img class="vimg" src="${esc(_blob)}" alt="${esc(name)}">`)}</div>`);
    $("#dclose").onclick = () => { freeBlob(); render(box, ""); };
  } catch (e) {
    render(box, html`<div class="viewer"><p class="empty">${
      e instanceof sheets.NeedSignIn ? "구글 로그인이 필요합니다."
        : (e.message || "파일을 열지 못했습니다.")}</p>
      <a class="bigcopy" href="${drive.openInDrive(id)}" target="_blank"
         rel="noopener">드라이브 앱에서 열기</a></div>`);
  }
}
