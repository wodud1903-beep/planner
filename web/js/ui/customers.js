// 고객관리 조회 — 읽기 전용. PC 앱의 '미출고차량' 목록을 폰에서 본다.
//
// 이 화면을 쓰는 이유는 대개 **밖에서 고객 전화를 받았을 때**다. 그래서
//  · 안내멘트를 카톡에 붙여 넣을 수 있게 큰 [복사] 단추를 둔다
//  · 고객센터·사고접수는 눌러서 바로 걸리게 tel: 로 만든다
import { html, raw, esc, render, $, $$, topIndex, scrollToIndex } from "./dom.js";
import * as store from "../store.js";
import * as sheets from "../sheets.js";
import * as hangul from "../hangul.js";
import * as fmt from "../fmt.js";
import { parseRows, statuses, HeaderNotFound } from "../customers.js";
import { DEF_SHEET_ID, DEF_SHEET_NAME } from "../config.js";
import { setBody, markTab, paintState } from "./chrome.js";
import * as router from "../router.js";

let _rows = [];
let _prep = [];          // 미리 다듬어 둔 검색 재료 (칠 때마다 다시 만들지 않는다)
let _q = "";
let _st = "";            // 고른 진행현황
let _err = "";
let _timer = 0;
let _syncedAt = 0;
const SEARCH_DELAY = 130;

const sheetId = () => DEF_SHEET_ID;
const sheetTab = () => DEF_SHEET_NAME;

// ---------------------------------------------------------------- 자료 받기
export async function load({ refresh = true } = {}) {
  const cached = await store.get("data", "customers");
  if (cached && cached.rows) setRows(cached.rows, cached.at || 0);
  if (!refresh) return;
  try {
    const { left, right } = await sheets.readCustomers(sheetId(), sheetTab());
    const { rows } = parseRows(left, right, sheetTab());
    _err = "";
    await store.put("data", "customers", { rows, at: Date.now() });
    setRows(rows, Date.now());
    return true;
  } catch (e) {
    // ⚠️ 실패해도 화면을 바꾸지 않는다. 캐시가 있으면 그대로 계속 쓴다.
    if (e instanceof HeaderNotFound) _err = e.message;
    else if (e instanceof sheets.WrongAccount) {
      _err = "이 계정으로는 고객관리 시트를 열 수 없습니다. 계정을 확인해 주세요.";
    } else if (e instanceof sheets.NeedSignIn) _err = "";
    else if (e instanceof sheets.Offline) _err = "";
    else _err = e.message || "고객 목록을 읽지 못했습니다.";
    paintState();
    paintList();
  }
  return false;
}

function setRows(rows, at) {
  _rows = rows || [];
  _syncedAt = at || 0;
  // 검색 재료를 미리 다듬어 둔다 — 이름·차종·금융사·진행현황을 한 덩어리로.
  _prep = _rows.map((r) => hangul.prepare(
    [r.values.customer, r.values.model, r.values.finance,
     r.values.status, r.values.note].filter(Boolean).join(" ")));
  const cur = router.current();
  if (cur && cur.path.startsWith("/customers")) { paintChips(); paintList(); }
}

// ---------------------------------------------------------------- 화면
export async function screen(m) {
  markTab("/customers");
  const ui = await store.ui();
  _q = ui.cQuery || "";
  _st = ui.cStatus || "";
  setBody(html`
    <div class="split" id="csplit">
      <div class="left">
        <div class="pane">
          <div class="searchbar">
            <input id="cq" type="search" value="${_q}" autocomplete="off"
                   enterkeyhint="search"
                   placeholder="고객명·차종·금융사 검색 (초성도 됩니다)">
          </div>
          <div class="cats" id="cchips"></div>
          <ul class="list" id="clist"></ul>
          <p class="synced" id="csynced"></p>
        </div>
      </div>
      <div class="right"><div class="pane" id="cdetail"></div></div>
    </div>`);

  const input = $("#cq");
  const run = () => { _q = input.value; store.ui({ cQuery: _q }); paintList(); };
  input.addEventListener("input", () => {
    clearTimeout(_timer);
    _timer = setTimeout(run, SEARCH_DELAY);
  });
  // 한글은 조합이 끝나야 글자가 된다. 조합 끝에는 기다리지 않고 바로 찾는다.
  input.addEventListener("compositionend", () => { clearTimeout(_timer); run(); });

  paintChips();
  paintList();
  if (!_rows.length) await load(); else load();     // 캐시로 먼저, 갱신은 조용히

  const want = m && m[1] ? parseInt(m[1], 10) : 0;
  if (want) showDetail(want);
}

function paintChips() {
  const el = $("#cchips");
  if (!el) return;
  // ⚠️ 진행현황은 하드코딩하지 않는다 — 시트에 실제로 있는 값에서 뽑는다.
  const list = ["", ...statuses(_rows)];
  render(el, list.map((s) =>
    html`<button data-st="${s}" aria-pressed="${String(s === _st)}">${s || "전체"}</button>`
  ).join(""));
  for (const b of $$("#cchips button")) {
    b.onclick = () => {
      _st = b.dataset.st;
      store.ui({ cStatus: _st });
      paintChips();
      paintList();
    };
  }
}

function hits() {
  const q = (_q || "").trim();
  const out = [];
  for (let i = 0; i < _rows.length; i++) {
    const r = _rows[i];
    if (_st && (r.values.status || "").trim() !== _st) continue;
    if (q && !hangul.matchesPrepared(_prep[i], q)) continue;
    out.push(r);
  }
  return out;
}

function paintList() {
  const el = $("#clist");
  if (!el) return;
  const keep = topIndex(el);
  const rows = hits();
  const note = $("#csynced");
  if (note) {
    note.textContent = _syncedAt
      ? `${_rows.length}건 · ${new Date(_syncedAt).toLocaleString("ko-KR",
          { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })} 기준`
      : "";
  }
  if (!rows.length) {
    render(el, html`<li class="empty">${_err
      ? _err
      : (_rows.length ? "찾는 고객이 없습니다." : "고객 목록을 불러오는 중입니다…")}</li>`);
    return;
  }
  render(el, rows.map((r) => {
    const v = r.values;
    const sub = [v.finance, v.model].filter(Boolean).join(" · ");
    const date = v.deliver_date || v.contract_date || "";
    return html`<li><button class="row" data-row="${r.row}">
        <span class="t">${v.customer}</span>
        ${raw(sub ? `<span class="s">${esc(sub)}</span>` : "")}
        <span class="meta">${raw(v.status
          ? `<span class="tag">${esc(v.status)}</span>` : "")}${raw(
          date ? `<span class="d">${esc(date)}</span>` : "")}</span>
      </button></li>`;
  }).join(""));
  for (const b of $$("#clist button.row")) {
    b.onclick = () => router.go("/customers/" + b.dataset.row);
  }
  scrollToIndex(el, keep);
}

// ---------------------------------------------------------------- 한 고객
const money = (s) => { const m = fmt.fmtMoney(s); return m || s || ""; };

const ROWS = [
  ["금융사", (v) => v.finance],
  ["차종", (v) => v.model],
  ["차량가격", (v) => money(v.price)],
  ["금융수수료", (v) => money(v.fee)],
  ["대리점 수당", (v) => money(v.incentive)],
  ["특판/대리점", (v) => v.channel],
  ["계약일(발주)", (v) => v.contract_date],
  ["출고일", (v) => v.deliver_date],
  ["진행현황", (v) => v.status],
  ["계약조건", (v) => v.terms],
  ["출고유형", (v) => v.kind],
  ["내용", (v) => v.note],
];

export async function showDetail(rowNo) {
  const r = _rows.find((x) => x.row === rowNo);
  const box = $("#cdetail");
  const split = $("#csplit");
  if (!box) return;
  if (!r) {
    render(box, html`<div class="empty"><p>그 고객을 찾지 못했습니다.</p></div>`);
    return;
  }
  if (split) split.classList.add("detail");
  const v = r.values;
  const tel = (n) => {
    const d = String(n || "").replace(/[^0-9+]/g, "");
    return d ? `<a class="tel" href="tel:${d}">${esc(n)}</a>` : "";
  };
  render(box, html`
    <button class="chip backbtn" id="cback">← 목록</button>
    <h2 style="margin:10px 0 2px">${v.customer}</h2>
    <p class="s" style="color:var(--sub);margin:0 0 12px">
      ${[v.finance, v.model].filter(Boolean).join(" · ")}
      ${raw(r.total ? ` · 합계 <b>${esc(money(r.total))}</b>` : "")}</p>

    <div class="kv">
      ${raw(ROWS.map(([k, f]) => {
        const val = (f(v) || "").trim();
        return val ? `<div class="k">${esc(k)}</div><div class="v">${esc(val)}</div>` : "";
      }).join(""))}
    </div>

    ${raw(r.center || r.accident ? `
      <p class="kbhead">연락처</p>
      <div class="kv">
        ${r.center ? `<div class="k">고객센터</div><div class="v">${tel(r.center)}</div>` : ""}
        ${r.accident ? `<div class="k">사고접수</div><div class="v">${tel(r.accident)}</div>` : ""}
      </div>` : "")}

    <p class="kbhead">고객 안내멘트</p>
    <div id="cment"><p class="empty">불러오는 중…</p></div>`);

  const back = $("#cback");
  if (back) back.onclick = () => { split.classList.remove("detail"); router.go("/customers"); };

  // 멘트는 여기서만 받는다 — 목록에 넣으면 한 건당 20줄이라 폰에서 제일 큰 낭비다.
  const key = "ment:" + sheetId() + ":" + r.row;
  const cached = await store.get("meta", key);
  if (cached) paintMent(cached);
  let text = cached || "";
  try {
    const got = await sheets.readMent(sheetId(), sheetTab(), r.row);
    if (got) { text = got; await store.put("meta", key, got); }
  } catch (e) { paintState(); }
  paintMent(text);
}

function paintMent(text) {
  const box = $("#cment");
  if (!box) return;
  if (!text) {
    render(box, html`<p class="empty">안내멘트가 없습니다.</p>`);
    return;
  }
  render(box, html`
    <button class="bigcopy" id="cmentcopy">안내멘트 복사</button>
    <pre class="ment">${text}</pre>`);
  const b = $("#cmentcopy");
  b.onclick = () => navigator.clipboard.writeText(text).then(() => {
    b.textContent = "복사됐습니다 ✓";
    b.classList.add("done");
    setTimeout(() => { b.textContent = "안내멘트 복사"; b.classList.remove("done"); }, 1600);
  }).catch(() => { b.textContent = "복사 실패 — 길게 눌러 직접 복사하세요"; });
}
