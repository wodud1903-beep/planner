// 자료검색 — 캐피탈 정보·심사서류. 회사 공용 시트의 '업무자료' 탭 하나를 읽는다.
import { html, raw, render, $, $$, topIndex, scrollToIndex } from "./dom.js";
import * as store from "../store.js";
import * as sheets from "../sheets.js";
import * as kb from "../kb.js";
import { RATES_SHEET_ID, KB_TAB } from "../config.js";
import { setBody, markTab, paintState } from "./chrome.js";
import * as router from "../router.js";
import * as drive from "../drive.js";
import * as viewer from "./viewer.js";
import { attach } from "./split.js";
import * as kbedits from "../kbedits.js";
import { toast } from "./chrome.js";

let _shared = [];        // 회사 공통 자료(시트 그대로)
let _edits = {};         // 내 계정에서 고친 것 {제목: 기록} — kb_edits.json(v1.30)
let _me = {};            // 내 정보(팩스·이름·연락처·이메일) — 본문의 {내 팩스} 자리에 넣는다(v1.32)
let _items = [];         // 화면에 보이는 것 = 회사 자료 + 내가 고친 것 + 내 정보를 채운 본문(_src = 채우기 전)
const MINE = "__mine";   // 분류 단추 '내가 고친 것'
let _idx = [];
let _q = "";
let _cat = "";
let _timer = 0;

const SEARCH_DELAY = 130;   // 타자가 멎으면 찾는다. 한 자마다 훑으면 밀린다.

export async function load({ refresh = true } = {}) {
  const cached = await store.get("data", "kb");
  _edits = (await store.get("data", "kbEdits")) || {};
  _me = kbedits.cleanMe(await store.get("data", "kbMe"));
  if (cached && cached.length) { _shared = cached; setItems(); }
  else if (!refresh) { _shared = []; setItems(); }   // 계정이 바뀌어 지운 뒤 — 앞사람 것을 남기지 않는다
  if (!refresh) return;
  let ok = false, cut = false;
  try {
    const got = await sheets.readKb(RATES_SHEET_ID, KB_TAB);
    if (got && got.length) {
      await store.put("data", "kb", got);
      await store.put("meta", "kbSyncedAt", Date.now());
      _shared = got;
      setItems();
      ok = true;
    }
  } catch (e) {
    cut = e instanceof sheets.Offline || e instanceof sheets.NeedSignIn;
    paintState();               // 로그인·오프라인 상태만 바꾸고 화면은 그대로 둔다
  }
  // 통신이 끊겼거나 로그인 전이면 건너뛴다 — 다시 붙으면 처음부터 다시 받는다(boot.js)
  if (!cut) await refreshEdits();
  return ok;
}

/** 내 계정에서 고친 자료를 다시 본다(바뀌었을 때만 받는다 — 30초마다 · 돌아올 때 boot.js). 바뀌면 true. */
export async function refreshEdits() {
  try {
    const { edits, me, changed } = await kbedits.read();
    if (!changed) return false;
    // 내 정보 — 나중에 고친 쪽. 예전 판이 계정 파일에서 빼먹었으면 이 기기 것을 다시 올린다
    const mm = kbedits.mergeMe(_me, me);
    const meCh = JSON.stringify(mm.me) !== JSON.stringify(_me);
    if (meCh) { _me = mm.me; await store.put("data", "kbMe", _me); }
    if (mm.push) kbedits.saveMe(_me, _me.at || null).catch(() => {});
    if (JSON.stringify(edits) === JSON.stringify(_edits) && !meCh) return false;
    _edits = edits;
    await store.put("data", "kbEdits", edits);
    setItems();
    const cur = router.current();
    const m = cur && cur.path.match(/^\/kb\/(\d+)$/);
    if (m && !$("#kbeditor") && !$("#kbmeform")) showDetail(parseInt(m[1], 10));   // 보고 있던 자료도 새 내용으로(고치는 중이면 그대로)
    return true;
  } catch (e) {
    return false;               // 로그인 전 · 오프라인 — 저장본으로 계속 보인다
  }
}

function setItems() {
  // 본문의 {내 팩스|기본값} 자리를 내 정보로 채워 보여 준다 — 찾기·복사도 채운 글로. 고칠 때는 _src(자리 그대로).
  const items = kbedits.overlay(_shared, _edits).map((it) => {
    const body = kbedits.fillMe(it.body, _me);
    return body === it.body ? { ...it, _src: it } : { ...it, body, _src: it, _filled: true };
  });
  _items = items;
  _idx = kb.index(items);
  if (router.current() && router.current().path.startsWith("/kb")) { paintCats(); paintList(); }
}

export async function screen(m) {
  markTab("/kb");
  const ui = await store.ui();
  _q = ui.kbQuery || "";
  _cat = ui.kbCat || "";
  setBody(html`
    <div class="split" id="kbsplit">
      <div class="left">
        <div class="pane">
          <div class="searchbar">
            <input id="kbq" type="search" placeholder="캐피탈·서류·연락처 검색 (초성도 됩니다)"
                   value="${_q}" autocomplete="off" enterkeyhint="search">
            <button class="chip" id="kbme" title="자료 본문의 '내 팩스' 자리에 들어갈 내 정보">내 정보</button>
          </div>
          <div class="cats" id="kbcats"></div>
          <ul class="list" id="kblist"></ul>
        </div>
      </div>
      <div class="right"><div class="pane" id="kbdetail"></div></div>
    </div>`);
  attach($("#kbsplit"), "kb");

  const input = $("#kbq");
  const run = () => {
    _q = input.value;
    store.ui({ kbQuery: _q });
    paintList();
  };
  input.addEventListener("input", () => {
    clearTimeout(_timer);
    _timer = setTimeout(run, SEARCH_DELAY);
  });
  input.addEventListener("compositionend", () => { clearTimeout(_timer); run(); });

  $("#kbme").onclick = () => openMe();
  paintCats();
  paintList();
  if (!_items.length) await load();
  // 상세 경로면 그 항목을 연다
  const i = m && m[1] !== undefined ? parseInt(m[1], 10) : -1;
  if (i >= 0) showDetail(i);
}

function paintCats() {
  const box = $("#kbcats");
  if (!box) return;
  const cats = ["", ...kb.CATEGORIES.filter((c) =>
    _items.some((it) => (it.category || "") === c))];
  // 내 계정에서 고친 자료가 있으면 그것만 모아 보는 단추(v1.32)
  const mine = _items.filter((it) => it._local).length;
  if (mine) cats.push(MINE);
  else if (_cat === MINE) _cat = "";
  render(box, cats.map((c) =>
    html`<button data-cat="${c}" aria-pressed="${String(c === _cat)}">${
      c === MINE ? `내가 고친 것 ${mine}` : c || "전체"}</button>`
  ).join(""));
  for (const b of $$("#kbcats button")) {
    b.onclick = () => {
      _cat = b.dataset.cat;
      store.ui({ kbCat: _cat });
      paintCats();
      paintList();
    };
  }
}

function paintList() {
  const el = $("#kblist");
  if (!el) return;
  const hits = _cat === MINE ? kb.search(_idx, _q, "").filter((it) => it._local) : kb.search(_idx, _q, _cat);
  if (!hits.length) {
    render(el, html`<li class="empty">${_items.length
      ? "찾는 자료가 없습니다." : "자료를 불러오는 중입니다…"}</li>`);
    return;
  }
  render(el, hits.map((it) => {
    const i = _items.indexOf(it);
    const sub = [it.finance, it.category, it._local ? "내 계정에서 고침" : ""].filter(Boolean).join(" · ");
    return html`<li><button class="row" data-i="${i}">
        <span class="t">${it.title}</span>
        ${raw(sub ? `<span class="s">${esc2(sub)}</span>` : "")}
      </button></li>`;
  }).join(""));
  for (const b of $$("#kblist button.row")) {
    b.onclick = () => router.go("/kb/" + b.dataset.i);
  }
}
const esc2 = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export function showDetail(i) {
  const it = _items[i];
  const box = $("#kbdetail");
  const split = $("#kbsplit");
  if (!it || !box) return;
  if (split) split.classList.add("detail");
  render(box, html`
    <button class="chip backbtn" id="kbback">← 목록</button>
    <h2 style="margin:10px 0 2px">${it.title}</h2>
    <p class="s" style="color:var(--sub);margin:0 0 10px">
      ${[it.finance, it.category].filter(Boolean).join(" · ")}</p>
    ${raw(it._local ? `<p class="s" id="kbmine" style="color:var(--accent);margin:0 0 10px">회사 공통 · 내 계정에서 고침 — 나만 보입니다</p>` : "")}
    ${raw(it._stale ? `<p class="s" style="color:var(--sub);margin:0 0 10px">회사에서 이 자료를 새로 고쳤습니다. 새 내용으로 바꾸려면 [회사 자료로 되돌리기] 를 누르세요.</p>` : "")}
    ${raw(it.body.includes("〔내 ") ? `<p class="s" style="margin:0 0 10px">내 정보가 비어 있는 자리가 있어요.
      <button class="chip" id="kbmego">내 정보 적기</button></p>` : "")}
    <div id="kbbodybox">${raw(kb.bodyToHtml(it.body))}</div>
    <p style="margin-top:16px">
      <button class="chip" id="kbcopy">본문 복사</button>
      <button class="chip" id="kbedit">내 계정에서만 고치기</button>
      ${raw(it._local ? `<button class="chip" id="kbrevert">회사 자료로 되돌리기</button>` : "")}
    </p>
    ${raw(attachHtml(it.files || []))}
    <div id="kbview"></div>`);
  paintAttachments(it.files || []);
  const ed = $("#kbedit");
  if (ed) ed.onclick = () => openEditor(i);
  const mg = $("#kbmego");
  if (mg) mg.onclick = () => openMe(i);
  const rv = $("#kbrevert");
  if (rv) rv.onclick = () => saveMine(i, null);
  const back = $("#kbback");
  if (back) back.onclick = () => { split.classList.remove("detail"); router.go("/kb"); };
  const copy = (text, btn) => {
    navigator.clipboard.writeText(text).then(() => {
      btn.textContent = "복사됨 ✓";
      setTimeout(() => { btn.textContent = btn.dataset.t; }, 1200);
    }).catch(() => { btn.textContent = "복사 실패"; });
  };
  const c1 = $("#kbcopy");
  if (c1) { c1.dataset.t = c1.textContent; c1.onclick = () => copy(it.body, c1); }
  // 체크리스트는 자료검색에 보여 주지 않는다(PC 와 같게) — 고객관리 서류 체크의 재료로만 쓴다
}

// ---------------------------------------------------------------- 내 계정에서만 고치기(v1.30)
//
// 회사 공통 자료를 나만 바꿔 쓴다(예: 팩스번호를 내 것으로). 이 기기가 아니라 **내 구글 계정**에
// 저장되어(kb_edits.json) PC 일정관리기·업무자료검색에도 그대로 보인다. 회사 자료·다른 사람 화면은 그대로다.
async function openEditor(i) {
  const it = _items[i];
  const box = $("#kbbodybox");
  if (!it || !box) return;
  const who = (await store.account()) || "";
  const src = it._src || it;          // 고칠 때는 {내 팩스} 자리를 채우기 전의 글
  render(box, html`
    <div id="kbeditor">
      <p class="kbhead">내 계정에서만 고치기 — 나만 보입니다</p>
      <textarea id="kbbody" class="bigin" rows="14" style="width:100%;box-sizing:border-box">${src.body || ""}</textarea>
      ${raw(String(src.body || "").includes("{내 ") ? `<p class="s" style="color:var(--sub)">{내 팩스} 같은 자리는
        [내 정보] 에 적은 값으로 바뀌어 보입니다 — 그대로 두면 됩니다.</p>` : "")}
      <p class="kbhead" style="margin-top:12px">체크리스트 <span class="s" style="color:var(--sub);font-weight:400">— 한 줄에
        하나(고객관리 서류 체크에 쓰입니다)</span></p>
      <textarea id="kbcheck" class="bigin" rows="5" style="width:100%;box-sizing:border-box">${(src.checklist || []).join("\n")}</textarea>
      <p class="s" style="color:var(--sub)">저장하면 내 구글 계정${who ? `(${who})` : ""}으로 PC 일정관리기·업무자료검색에도
        반영됩니다. 회사 자료와 다른 사람 화면은 그대로입니다.</p>
      <p><button class="chip" id="kbsave">저장</button> <button class="chip" id="kbcancel">취소</button>
         <span class="s" id="kbmsg" style="color:var(--sub)"></span></p>
    </div>`);
  const ta = $("#kbbody");
  if (ta) ta.focus();
  $("#kbcancel").onclick = () => showDetail(i);
  $("#kbsave").onclick = () => saveMine(i, $("#kbbody").value, $("#kbcheck").value);
}

// ---------------------------------------------------------------- 내 정보(v1.32)
//
// 회사 자료 본문에 관리자가 {내 팩스|0504-…} 같은 자리를 넣어 두면, 여기 적은 값이 그 자리에 들어가 보인다
// (직원마다 팩스번호가 달라 자료마다 따로 고치던 것을 한 번에). 내 구글 계정에 저장되어 PC 에도 똑같이 보인다.
async function openMe(backTo = -1) {
  const box = $("#kbdetail");
  const split = $("#kbsplit");
  if (!box) return;
  if (split) split.classList.add("detail");
  const who = (await store.account()) || "";
  const types = { fax: "tel", phone: "tel", email: "email", name: "text" };
  render(box, html`
    <button class="chip backbtn" id="kbback">← 목록</button>
    <div id="kbmeform">
      <h2 style="margin:10px 0 2px">내 정보</h2>
      <p class="s" style="color:var(--sub);margin:0 0 12px">여기 적어 두면 자료 본문의 '내 팩스' 같은 자리에
        저절로 들어갑니다. 나만 보이고, 내 구글 계정${who ? `(${who})` : ""}으로 PC 에도 반영됩니다.</p>
      ${raw(kbedits.ME_FIELDS.map(([k, label]) => `<p style="margin:0 0 10px"><label class="flab" for="kbme_${k}">${label}</label>
        <input id="kbme_${k}" class="bigin" type="${types[k]}" maxlength="80" autocomplete="off"
               style="width:100%;box-sizing:border-box" value="${esc2(_me[k] || "")}"></p>`).join(""))}
      <p><button class="primary" id="kbmesave">저장</button> <button class="chip" id="kbmecancel">취소</button>
         <span class="s" id="kbmemsg" style="color:var(--sub)"></span></p>
    </div>`);
  const done = () => {
    if (backTo >= 0) showDetail(backTo);
    else { if (split) split.classList.remove("detail"); render(box, ""); }
  };
  $("#kbback").onclick = done;
  $("#kbmecancel").onclick = done;
  $("#kbmesave").onclick = async () => {
    const vals = {};
    for (const [k] of kbedits.ME_FIELDS) vals[k] = $("#kbme_" + k).value;
    const btn = $("#kbmesave");
    const msg = $("#kbmemsg");
    btn.disabled = true;
    msg.textContent = "내 계정에 저장하는 중…";
    try {
      _me = await kbedits.saveMe(vals);
      await store.put("data", "kbMe", _me);
      setItems();
      done();
      toast("내 정보를 저장했어요 — 자료 본문과 PC 에도 반영됩니다.");
    } catch (e) {
      btn.disabled = false;
      msg.textContent = "저장하지 못했습니다 — " + (e instanceof sheets.NeedSignIn ? "구글 로그인이 필요합니다."
        : e instanceof sheets.Offline ? "인터넷에 연결되지 않았습니다." : (e && e.message) || "잠시 뒤 다시 해 주세요.");
    }
  };
}

async function saveMine(i, body, checklist = undefined) {
  const it = _items[i];
  if (!it) return;
  const src = it._src || it;          // 내 정보를 채우기 전의 것(채운 글을 원본으로 삼으면 자리가 사라진다)
  const msg = $("#kbmsg");
  const lines = (v) => (Array.isArray(v) ? v : String(v || "").split("\n")).map((x) => String(x).trim()).filter(Boolean);
  const sameCheck = checklist === undefined || JSON.stringify(lines(checklist)) === JSON.stringify(lines(src.checklist));
  // 고친 것이 없으면 계정에 쓰지 않는다(v1.31.3) — 예전엔 그대로 [저장] 해도 '되돌림' 기록을 계정에 남겼다
  if (body !== null && kbedits.norm(body) === kbedits.norm(src.body) && sameCheck) {
    showDetail(i);
    toast("바뀐 내용이 없어요.");
    return;
  }
  const btns = [$("#kbsave"), $("#kbrevert")].filter(Boolean);
  for (const b of btns) b.disabled = true;
  if (msg) msg.textContent = "내 계정에 저장하는 중…";
  try {
    _edits = body === null ? await kbedits.revert(src) : await kbedits.save(src, body, sameCheck ? undefined : checklist);
    await store.put("data", "kbEdits", _edits);
    setItems();
    showDetail(i);
    toast(body === null ? "회사 자료로 되돌렸어요 — PC 에도 반영됩니다."
                        : "내 계정에 저장했어요 — PC 일정관리기·업무자료검색에도 반영됩니다.");
  } catch (e) {
    for (const b of btns) b.disabled = false;
    const why = e instanceof sheets.NeedSignIn ? "구글 로그인이 필요합니다."
      : e instanceof sheets.Offline ? "인터넷에 연결되지 않았습니다."
      : (e && e.message) || "저장하지 못했습니다.";
    if (msg) msg.textContent = "저장하지 못했습니다 — " + why;
    else toast("저장하지 못했습니다 — " + why, { tone: "bad" });
  }
}

// ---------------------------------------------------------------- 첨부(그림·PDF)
//
// PC 앱이 자료에 붙여 둔 그림·PDF. 그림은 바로 보이고, [크게] 로 확대·PDF 장 넘기기,
// [보내기] 로 폰의 공유 창(카카오톡 고르기)에 넘긴다. 공유를 못 하는 브라우저면
// [저장] 으로 내려받는다.
let _att = { urls: [], blobs: new Map(), view: null };

function releaseAttachments() {
  for (const u of _att.urls) URL.revokeObjectURL(u);
  if (_att.view) _att.view.close();
  _att = { urls: [], blobs: new Map(), view: null };
}

export function attachHtml(files) {
  if (!files.length) return "";
  const cards = files.map((f, i) => {
    const pdf = drive.isPdf(f.name);
    return `<div class="attcard" data-k="${i}">
        <button class="attthumb" data-act="open" aria-label="${esc2(f.name)} 크게 보기">${pdf
          ? '<span class="attpdf">PDF</span>'
          : `<img class="attimg" alt="${esc2(f.name)}">`}</button>
        <span class="attname">${esc2(f.name)}</span>
        <span class="attbtns">
          <button class="chip" data-act="open">크게</button>
          <button class="chip" data-act="send">보내기</button>
        </span>
      </div>`;
  }).join("");
  return `<p class="kbhead">첨부 (${files.length})</p><div class="kbatt" id="kbatt">${cards}</div>`;
}

const canShareFiles = () => {
  try {
    return typeof navigator.share === "function" && typeof navigator.canShare === "function"
      && navigator.canShare({ files: [new File(["x"], "x.png", { type: "image/png" })] });
  } catch (e) { return false; }
};

async function blobOf(f) {
  if (_att.blobs.has(f.id)) return _att.blobs.get(f.id);
  // 받는 중이면 그 받기를 같이 기다린다(작은 그림을 받는 사이 [크게] 를 눌러도 두 번 받지 않게)
  const att = _att;
  if (!att.wait) att.wait = new Map();
  if (att.wait.has(f.id)) return att.wait.get(f.id);
  const p = (async () => {
    let b = null;
    try { b = await drive.download(f.id); } catch (e) { b = null; }
    if (b) att.blobs.set(f.id, b);
    att.wait.delete(f.id);
    return b;
  })();
  att.wait.set(f.id, p);
  return p;
}

function paintAttachments(files) {
  releaseAttachments();
  const box = $("#kbatt");
  if (!box || !files.length) return;
  if (!canShareFiles()) {
    for (const b of $$('button[data-act="send"]', box)) b.textContent = "저장";
  }
  files.forEach(async (f, i) => {
    const card = $(`.attcard[data-k="${i}"]`, box);
    if (!card) return;
    card.onclick = (e) => {
      const act = e.target.closest("[data-act]");
      if (!act) return;
      if (act.dataset.act === "open") openViewer(files, i, true);
      else onAttach(f, act.dataset.act, act);
    };
    if (drive.isPdf(f.name)) return;
    const img = $(".attimg", card);
    const b = await blobOf(f);
    if (b) {
      const u = URL.createObjectURL(b);
      _att.urls.push(u);
      img.src = u;
    } else {
      // 로그인이 안 됐거나 못 받으면 — 공개 첨부는 드라이브 작은 그림으로라도 보여 준다
      img.src = `https://drive.google.com/thumbnail?id=${encodeURIComponent(f.id)}&sz=w800`;
    }
  });
}

// [크게] — 확대 보기. 같은 자료의 첨부가 여럿이면 그 안에서 ◀ ▶ · ← → · 밀기로 넘긴다
// (예전엔 닫고 다음 카드의 [크게] 를 다시 눌러야 했다).
let _navSeq = 0;

function mountAt(files, i, blob, pending) {
  const box = $("#kbview");
  if (!box) return;
  const f = files[i];
  if (_att.view) _att.view.close();
  _att.view = viewer.mount(box, {
    blob, pending, name: f.name, isPdf: drive.isPdf(f.name), driveUrl: drive.openInDrive(f.id),
    nav: { pos: i, count: files.length, go: (j) => openViewer(files, j, false) },
  });
  _att.view.onClose(() => {
    _navSeq++;                       // 받는 중이던 것이 뒤늦게 다시 열지 않게
    if (_att.view) _att.view.close();
    _att.view = null;
    render(box, "");
  });
}

async function openViewer(files, i, first) {
  const f = files[i];
  if (!f || !$("#kbview")) return;
  const seq = ++_navSeq;
  const gen = _att;                  // 다른 자료로 옮기면 _att 가 새것이 된다
  let b = _att.blobs.get(f.id) || null;
  if (!b) {
    if (!first) mountAt(files, i, null, true);      // '받는 중' — 다 받으면 그 자리에 뜬다
    b = await blobOf(f);
    if (seq !== _navSeq || gen !== _att) return;   // 그사이 다른 첨부·자료로 옮겼다
  }
  if (!b && first) { window.open(drive.openInDrive(f.id), "_blank", "noopener"); return; }
  mountAt(files, i, b, false);
  if (first) $("#kbview").scrollIntoView({ block: "start", behavior: "smooth" });
  // 옆 첨부를 미리 받아 둔다(그림은 카드가 이미 받는다 — PDF 도 기다리지 않게)
  for (const j of [i + 1, i - 1]) if (files[j]) blobOf(files[j]);
}

async function onAttach(f, act, btn) {
  const b = await blobOf(f);
  // 보내기 — 폰의 공유 창으로(카카오톡을 고르면 그 대화로 간다)
  if (!b) {
    btn.textContent = "받지 못함";
    setTimeout(() => { btn.textContent = canShareFiles() ? "보내기" : "저장"; }, 1500);
    return;
  }
  const type = b.type || f.mime || (drive.isPdf(f.name) ? "application/pdf" : "image/png");
  const file = new File([b], f.name, { type });
  if (canShareFiles() && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file], title: f.name }); } catch (e) { /* 닫음 */ }
    return;
  }
  const a = document.createElement("a");
  const u = URL.createObjectURL(b);
  _att.urls.push(u);
  a.href = u;
  a.download = f.name;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
