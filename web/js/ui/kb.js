// 자료검색 — 캐피탈 정보·심사서류. 회사 공용 시트의 '업무자료' 탭 하나를 읽는다.
import { html, raw, render, $, $$, topIndex, scrollToIndex } from "./dom.js";
import * as store from "../store.js";
import * as sheets from "../sheets.js";
import * as kb from "../kb.js";
import { RATES_SHEET_ID, KB_TAB } from "../config.js";
import { setBody, markTab, paintState } from "./chrome.js";
import * as router from "../router.js";

let _items = [];
let _idx = [];
let _q = "";
let _cat = "";
let _timer = 0;

const SEARCH_DELAY = 130;   // 타자가 멎으면 찾는다. 한 자마다 훑으면 밀린다.

export async function load({ refresh = true } = {}) {
  const cached = await store.get("data", "kb");
  if (cached && cached.length) setItems(cached);
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
    ${raw(it.checklist && it.checklist.length
      ? `<p class="kbhead">체크리스트</p><ul class="chk">${
          it.checklist.map((c) => `<li>${esc2(c)}</li>`).join("")}</ul>`
      : "")}
    <p style="margin-top:16px">
      <button class="chip" id="kbcopy">본문 복사</button>
      ${raw(it.checklist && it.checklist.length
        ? ' <button class="chip" id="kbcopyc">체크리스트 복사</button>' : "")}
    </p>`);
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
  const c2 = $("#kbcopyc");
  if (c2) {
    c2.dataset.t = c2.textContent;
    c2.onclick = () => copy(it.checklist.map((x) => "· " + x).join("\n"), c2);
  }
}
