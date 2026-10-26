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

let _items = [];
let _idx = [];
let _q = "";
let _cat = "";
let _timer = 0;

const SEARCH_DELAY = 130;   // 타자가 멎으면 찾는다. 한 자마다 훑으면 밀린다.

export async function load({ refresh = true } = {}) {
  const cached = await store.get("data", "kb");
  if (cached && cached.length) setItems(cached);
  else if (!refresh) setItems([]);      // 계정이 바뀌어 지운 뒤 — 앞사람 것을 남기지 않는다
  if (!refresh) return;
  try {
    const got = await sheets.readKb(RATES_SHEET_ID, KB_TAB);
    if (got && got.length) {
      await store.put("data", "kb", got);
      await store.put("meta", "kbSyncedAt", Date.now());
      setItems(got);
      return true;
    }
  } catch (e) {
    paintState();               // 로그인·오프라인 상태만 바꾸고 화면은 그대로 둔다
  }
  return false;
}

function setItems(items) {
  _items = items;
  _idx = kb.index(items);
  if (router.current() && router.current().path.startsWith("/kb")) paintList();
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

  paintCats();
  paintList();
  if (!_items.length) await load();
  // 상세 경로면 그 항목을 연다
  const i = m && m[1] !== undefined ? parseInt(m[1], 10) : -1;
  if (i >= 0) showDetail(i);
}

function paintCats() {
  const cats = ["", ...kb.CATEGORIES.filter((c) =>
    _items.some((it) => (it.category || "") === c))];
  render($("#kbcats"), cats.map((c) =>
    html`<button data-cat="${c}" aria-pressed="${String(c === _cat)}">${c || "전체"}</button>`
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
  const hits = kb.search(_idx, _q, _cat);
  if (!hits.length) {
    render(el, html`<li class="empty">${_items.length
      ? "찾는 자료가 없습니다." : "자료를 불러오는 중입니다…"}</li>`);
    return;
  }
  render(el, hits.map((it) => {
    const i = _items.indexOf(it);
    const sub = [it.finance, it.category].filter(Boolean).join(" · ");
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
    ${raw(kb.bodyToHtml(it.body))}
    <p style="margin-top:16px">
      <button class="chip" id="kbcopy">본문 복사</button>
    </p>
    ${raw(attachHtml(it.files || []))}
    <div id="kbview"></div>`);
  paintAttachments(it.files || []);
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
  let b = null;
  try { b = await drive.download(f.id); } catch (e) { b = null; }
  if (b) _att.blobs.set(f.id, b);
  return b;
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
      if (act) onAttach(f, act.dataset.act, act);
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

async function onAttach(f, act, btn) {
  const b = await blobOf(f);
  if (act === "open") {
    if (!b) { window.open(drive.openInDrive(f.id), "_blank", "noopener"); return; }
    const box = $("#kbview");
    if (!box) return;
    if (_att.view) _att.view.close();
    _att.view = viewer.mount(box, { blob: b, name: f.name, isPdf: drive.isPdf(f.name),
                                    driveUrl: drive.openInDrive(f.id) });
    _att.view.onClose(() => { _att.view.close(); _att.view = null; render(box, ""); });
    box.scrollIntoView({ block: "start", behavior: "smooth" });
    return;
  }
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
