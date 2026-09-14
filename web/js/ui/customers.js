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
import { attach } from "./split.js";

let _rows = [];
let _prep = [];          // 미리 다듬어 둔 검색 재료 (칠 때마다 다시 만들지 않는다)
let _q = "";
let _st = "";            // 고른 진행현황
let _err = "";
let _badTab = false;   // 탭 이름이 안 맞는다 → 설정을 권한다
let _timer = 0;
let _syncedAt = 0;
const SEARCH_DELAY = 130;

// 시트 주소·탭 이름은 바꿀 수 있다. PC 앱 설정에서 다른 시트를 쓰고 계실 수 있고,
// 탭 이름이 다르면 구글이 400 을 돌려주는데 그것만 봐서는 원인을 알 수 없다.
let _sheetId = DEF_SHEET_ID;
let _sheetTab = DEF_SHEET_NAME;
const sheetId = () => _sheetId;
const sheetTab = () => _sheetTab;

export async function loadSettings() {
  const s = (await store.get("meta", "sheet")) || {};
  _sheetId = s.id || DEF_SHEET_ID;
  _sheetTab = s.tab || DEF_SHEET_NAME;
}
async function saveSettings(id, tab) {
  _sheetId = id || DEF_SHEET_ID;
  _sheetTab = tab || DEF_SHEET_NAME;
  await store.put("meta", "sheet", { id: _sheetId, tab: _sheetTab });
  await store.del("data", "customers");
  _rows = []; _prep = []; _syncedAt = 0;
}

// ---------------------------------------------------------------- 자료 받기
export async function load({ refresh = true } = {}) {
  const cached = await store.get("data", "customers");
  if (cached && cached.rows) setRows(cached.rows, cached.at || 0);
  if (!refresh) return;
  try {
    const { left, right } = await sheets.readCustomers(sheetId(), sheetTab());
    const { rows } = parseRows(left, right, sheetTab());
    _err = ""; _badTab = false;
    await store.put("data", "customers", { rows, at: Date.now() });
    setRows(rows, Date.now());
    return true;
  } catch (e) {
    // ⚠️ 실패해도 화면을 바꾸지 않는다. 캐시가 있으면 그대로 계속 쓴다.
    if (e instanceof sheets.BadRange) {
      // 거의 언제나 탭 이름이 다른 경우다. 사람이 고칠 수 있게 안내한다.
      _err = `'${sheetTab()}' 탭을 찾지 못했습니다. 아래 [시트 설정] 에서 탭을 골라 주세요.\n`
           + (e.message || "");
      _badTab = true;
    } else if (e instanceof HeaderNotFound) _err = e.message;
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
          <p class="synced"><button class="linky" id="cconf">시트 설정</button></p>
        </div>
      </div>
      <div class="right"><div class="pane" id="cdetail"></div></div>
    </div>`);
  attach($("#csplit"), "customers");

  const input = $("#cq");
  const run = () => { _q = input.value; store.ui({ cQuery: _q }); paintList(); };
  input.addEventListener("input", () => {
    clearTimeout(_timer);
    _timer = setTimeout(run, SEARCH_DELAY);
  });
  // 한글은 조합이 끝나야 글자가 된다. 조합 끝에는 기다리지 않고 바로 찾는다.
  input.addEventListener("compositionend", () => { clearTimeout(_timer); run(); });

  $("#cconf").onclick = () => settingsScreen();

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


// ---------------------------------------------------------------- 시트 설정
// 탭 이름이 틀리면 구글은 그냥 400 을 돌려준다. 손으로 다시 치게 하지 말고
// **그 스프레드시트에 실제로 있는 탭 목록**을 받아 눌러 고르게 한다.
export function settingsScreen() {
  markTab("/customers");
  setBody(html`
    <div class="pane">
      <button class="chip backbtn2" id="sback">← 뒤로</button>
      <h2 style="margin:10px 0 8px">고객관리 시트</h2>
      <p style="color:var(--sub);margin:0 0 8px">PC 앱에서 쓰는 시트와 같아야 합니다.
        스프레드시트 주소를 붙여넣어도 됩니다.</p>
      <div class="searchbar"><input id="sid" type="text" value="${sheetId()}"
        placeholder="스프레드시트 ID 또는 주소" autocomplete="off"></div>
      <p class="kbhead">탭</p>
      <div class="cats" id="stabs"><button aria-pressed="true">${sheetTab()}</button></div>
      <button class="bigcopy" id="sload">이 시트의 탭 목록 불러오기</button>
      <p class="empty" id="smsg"></p>
    </div>`);
  $("#sback").onclick = () => router.go("/customers");

  let picked = sheetTab();
  const msg = $("#smsg");
  const drawTabs = (tabs) => {
    render($("#stabs"), tabs.map((t) =>
      html`<button data-tab="${t}" aria-pressed="${String(t === picked)}">${t}</button>`).join(""));
    for (const b of $$("#stabs button")) {
      b.onclick = async () => {
        picked = b.dataset.tab;
        drawTabs(tabs);
        await saveSettings(idFrom($("#sid").value), picked);
        msg.textContent = `'${picked}' 탭으로 맞췄습니다. 불러오는 중…`;
        const okd = await load();
        if (okd) router.go("/customers");
        else msg.textContent = _err || "그래도 읽지 못했습니다.";
      };
    }
  };
  $("#sload").onclick = async () => {
    const id = idFrom($("#sid").value);
    if (!id) { msg.textContent = "스프레드시트 ID 나 주소를 적어 주세요."; return; }
    msg.textContent = "불러오는 중…";
    try {
      const { title, tabs } = await sheets.tabNames(id);
      await saveSettings(id, picked);
      msg.textContent = title ? `'${title}' — 탭을 골라 주세요.` : "탭을 골라 주세요.";
      drawTabs(tabs);
    } catch (e) {
      msg.textContent = e instanceof sheets.NeedSignIn ? "구글 로그인이 필요합니다."
        : e instanceof sheets.WrongAccount ? "이 계정으로는 그 시트를 열 수 없습니다."
        : (e.message || "시트를 읽지 못했습니다.");
    }
  };
}

/** 주소를 붙여넣어도 되게 한다 — 폰에서 44자 ID 를 손으로 치는 건 무리다. */
export function idFrom(s) {
  const t = String(s || "").trim();
  const m = t.match(/\/spreadsheets\/d\/([A-Za-z0-9_-]{10,})/);
  return m ? m[1] : t;
}
