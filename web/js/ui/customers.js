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
import { parseRows, statuses, choices, FIELDS, HeaderNotFound, filesFrom, legacyAtt }
  from "../customers.js";
import * as drive from "../drive.js";
import * as appdata from "../appdata.js";
import * as viewer from "./viewer.js";
import * as weeklyui from "./weekly.js";
import { DEF_SHEET_ID, DEF_SHEET_NAME } from "../config.js";
import { setBody, markTab, paintState } from "./chrome.js";
import * as feed from "./feed.js";
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

// 주간 요약은 고객 탭이 받아 둔 줄로 계산한다 — 새 통신이 없다
weeklyui.useRows(() => _rows);

export async function loadSettings() {
  const s = (await store.get("meta", "sheet")) || {};
  _sheetId = s.id || DEF_SHEET_ID;
  _sheetTab = s.tab || DEF_SHEET_NAME;
}
// 이 기기의 시트 설정을 바꾸고 옛 시트의 고객 목록을 비운다. 계정 설정(PC·다른 기기)에서 바뀌었을 때도 쓴다(v1.30).
export async function adoptSheet(id, tab) {
  _sheetId = id || DEF_SHEET_ID;
  _sheetTab = tab || DEF_SHEET_NAME;
  await store.put("meta", "sheet", { id: _sheetId, tab: _sheetTab });
  await store.del("data", "customers");
  _rows = []; _prep = []; _syncedAt = 0;
}
async function saveSettings(id, tab) {
  await adoptSheet(id, tab);
  // 계정에도 남긴다 — 다른 기기에서 로그인해도 다시 넣지 않게.
  // ⚠️ 기다리지 않는다. 이 기기에는 이미 저장됐고, 이건 덤이다.
  appdata.saveSettings({ sheetId: _sheetId, sheetTab: _sheetTab }).catch(() => {});
}

// ---------------------------------------------------------------- 자료 받기
export async function load({ refresh = true } = {}) {
  const cached = await store.get("data", "customers");
  if (cached && cached.rows) setRows(cached.rows, cached.at || 0);
  else if (!refresh) { await loadSettings(); setRows([], 0); }   // 계정이 바뀌어 지운 뒤
  if (!refresh) return;
  if (!sheetId()) {
    // 기본 주소를 없앴다 — 쓰는 사람이 자기 시트를 넣어야 한다.
    _err = "고객관리 시트를 아직 정하지 않았습니다.\n아래 [시트 설정] 에서 "
         + "스프레드시트 주소를 넣어 주세요.";
    paintList();
    return false;
  }
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
  // 홈(대시보드)의 이번 주·다음 주 요약도 이 줄로 계산한다
  dispatchEvent(new CustomEvent("planner:rows"));
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
          <p class="synced">
            <button class="linky" id="cboard">진행 보드</button>
            <span style="color:var(--line)"> · </span>
            <button class="linky" id="cweek">주간 요약</button>
            <span style="color:var(--line)"> · </span>
            <button class="linky" id="cconf">시트 설정</button>
          </p>
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
  $("#cweek").onclick = () => router.go("/customers/week");
  $("#cboard").onclick = () => router.go("/customers/board");

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

    <p style="margin:0 0 14px">
      <button class="chip" id="cedit">고치기</button></p>

    <p class="kbhead">이력 · 메모</p>
    <div id="cfeed"></div>

    <p class="kbhead">첨부 서류</p>
    <div id="cdoc"><p class="empty">확인 중…</p></div>
    <div id="cdocview"></div>

    <p class="kbhead">고객 안내멘트</p>
    <div id="cment"><p class="empty">불러오는 중…</p></div>`);

  const back = $("#cback");
  if (back) back.onclick = () => { split.classList.remove("detail"); router.go("/customers"); };
  const ed = $("#cedit");
  if (ed) ed.onclick = () => router.go(`/customers/${r.row}/edit`);

  loadDoc(r.row);
  feed.paint($("#cfeed"), r, { sheetId: sheetId(), tab: sheetTab() });

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


// ---------------------------------------------------------------- 첨부 서류(PC v1.33)
//
// PC 에서 고객마다 올린 견적서·자동차등록증·계약확인서 등(시트 V열 목록) + 예전 견적서 그림(S열).
// 파일은 그 계정의 구글 드라이브에 있고 링크 공개를 하지 않는다 — 내 로그인으로 받아 띄운다.
// [크게] 는 같은 고객의 다른 서류로 ◀ ▶ · ← → · 밀기로 넘긴다. [보내기] 는 폰 공유 창(카톡 등).
let _doc = { files: [], blobs: new Map(), urls: [], view: null, seq: 0 };

function dropDocs() {
  for (const u of _doc.urls) URL.revokeObjectURL(u);
  if (_doc.view) _doc.view.close();
  _doc = { files: [], blobs: new Map(), urls: [], view: null, seq: _doc.seq + 1 };
}

async function docBlob(f) {
  if (_doc.blobs.has(f.id)) return _doc.blobs.get(f.id);
  let b = null;
  try { b = await drive.download(f.id); } catch (e) { b = null; }
  if (b) _doc.blobs.set(f.id, b);
  return b;
}

const canShareFiles = () => {
  try {
    return typeof navigator.share === "function" && typeof navigator.canShare === "function"
      && navigator.canShare({ files: [new File(["x"], "x.png", { type: "image/png" })] });
  } catch (e) { return false; }
};

async function loadDoc(row) {
  const box = $("#cdoc");
  if (!box) return;
  dropDocs();
  const seq = _doc.seq;
  let doc = "", cell = "", who = { uid: "" };
  try {
    [doc, cell, who] = await Promise.all([
      sheets.readDocFormula(sheetId(), sheetTab(), row),
      sheets.readFilesCell(sheetId(), sheetTab(), row),
      sheets.readUid(sheetId(), sheetTab(), row).catch(() => ({ uid: "" })),
    ]);
  } catch (e) {
    render(box, html`<p class="empty">${e instanceof sheets.NeedScope
      ? "권한이 없습니다. 위 [다시 로그인] 을 눌러 주세요."
      : "첨부 서류를 확인하지 못했습니다."}</p>`);
    return;
  }
  if (seq !== _doc.seq || !$("#cdoc")) return;        // 그사이 다른 고객을 열었다
  const files = filesFrom(cell, who.uid);
  const old = legacyAtt(doc);
  if (old && !files.some((f) => f.id === old.id)) files.unshift(old);
  _doc.files = files;
  if (!files.length) {
    render(box, html`<p class="empty">올라온 서류가 없습니다. PC 일정관리기의 [수정] 에서 올립니다.</p>`);
    return;
  }
  const send = canShareFiles() ? "보내기" : "저장";
  render(box, `<div class="kbatt" id="cdocs">${files.map((f, i) => `<div class="attcard" data-k="${i}">
      <button class="attthumb" data-act="open" aria-label="${esc(f.name)} 크게 보기">${drive.isPdf(f.name)
        ? '<span class="attpdf">PDF</span>' : `<img class="attimg" alt="${esc(f.name)}">`}</button>
      <span class="attname">${esc(f.name)}</span>
      <span class="attbtns"><button class="chip" data-act="open">크게</button>
        <button class="chip" data-act="send">${send}</button></span></div>`).join("")}</div>`);
  files.forEach(async (f, i) => {
    const card = $(`#cdocs .attcard[data-k="${i}"]`);
    if (!card) return;
    card.onclick = (e) => {
      const act = e.target.closest("[data-act]");
      if (!act) return;
      if (act.dataset.act === "open") openDoc(i, true);
      else sendDoc(f, act);
    };
    if (drive.isPdf(f.name)) return;
    const b = await docBlob(f);
    if (seq !== _doc.seq) return;
    const img = $(".attimg", card);
    if (b && img) {
      const u = URL.createObjectURL(b);
      _doc.urls.push(u);
      img.src = u;
    } else if (img) {
      img.alt = "받지 못함";
    }
  });
}

async function openDoc(i, first) {
  const f = _doc.files[i];
  const box = $("#cdocview");
  if (!f || !box) return;
  const seq = _doc.seq;
  const mount = (blob, pending) => {
    if (_doc.view) _doc.view.close();
    _doc.view = viewer.mount(box, {
      blob, pending, name: f.name, isPdf: drive.isPdf(f.name), driveUrl: drive.openInDrive(f.id),
      nav: { pos: i, count: _doc.files.length, go: (j) => openDoc(j, false) },
    });
    _doc.view.onClose(() => { if (_doc.view) _doc.view.close(); _doc.view = null; render(box, ""); });
  };
  let b = _doc.blobs.get(f.id) || null;
  if (!b) {
    mount(null, true);                          // '받는 중' — 다 받으면 그 자리에
    b = await docBlob(f);
    if (seq !== _doc.seq) return;
  }
  if (!b && first) { window.open(drive.openInDrive(f.id), "_blank", "noopener"); return; }
  mount(b, false);
  if (first) box.scrollIntoView({ block: "start", behavior: "smooth" });
  for (const j of [i + 1, i - 1]) if (_doc.files[j]) docBlob(_doc.files[j]);   // 옆 서류는 미리
}

async function sendDoc(f, btn) {
  const b = await docBlob(f);
  if (!b) { btn.textContent = "받지 못함"; return; }
  const type = b.type || f.mime || (drive.isPdf(f.name) ? "application/pdf" : "image/png");
  const file = new File([b], f.name, { type });
  if (canShareFiles() && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file], title: f.name }); } catch (e) { /* 닫음 */ }
    return;
  }
  const a = document.createElement("a");
  const u = URL.createObjectURL(b);
  _doc.urls.push(u);
  a.href = u;
  a.download = f.name;
  document.body.appendChild(a);
  a.click();
  a.remove();
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
      <p style="color:var(--sub);margin:0 0 8px">PC 앱 [설정] 에 넣으신 것과 같은
        시트여야 합니다. 브라우저에서 그 시트를 열고 <b>주소창을 통째로 복사</b>해
        붙여넣는 게 가장 쉽습니다.</p>
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


// ---------------------------------------------------------------- 고치기
//
// ⚠️ 이 앱이 시트에 **쓰는** 유일한 자리다. 규칙은 sheets.js 의 writeCells 에
//    적어 두었다(수식 칸 보존·금액 콤마 제거·USER_ENTERED).
//    여기서는 화면과 '저장 직전 확인' 만 맡는다.

// 쓰지 않는 칸. 견적서(S열)는 =IMAGE() 수식이라 되돌려 쓰면 그림이 지워진다.
const NO_WRITE = ["doc"];
const MONEY_KEYS = ["price", "fee", "incentive"];
const DATE_KEYS = ["contract_date", "deliver_date"];
const AREA_KEYS = ["note"];
const WRITABLE = FIELDS.filter(([, k]) => !NO_WRITE.includes(k));

const LABEL = Object.fromEntries(FIELDS.map(([, k, l]) => [k, l]));

export async function editScreen(m) {
  markTab("/customers");
  const rowNo = m && m[1] ? parseInt(m[1], 10) : 0;
  const r = _rows.find((x) => x.row === rowNo);
  if (!r) {
    setBody(html`<div class="pane"><p class="empty">그 고객을 찾지 못했습니다.</p>
      <button class="chip" onclick="location.hash='/customers'">← 목록</button></div>`);
    return;
  }
  const before = { ...r.values };          // 불러왔을 때의 값 — 충돌 확인에 쓴다
  const cand = choices(_rows);

  const field = ([ci, key]) => {
    const v = before[key] || "";
    const lab = LABEL[key] || key;
    if (DATE_KEYS.includes(key)) {
      const d = fmt.parseDate(v);
      return html`
        <label class="flab" for="e_${key}">${lab}</label>
        <div class="calcrow">
          <input id="e_${key}" class="bigin" type="date" value="${fmt.isoDate(d)}"
                 style="flex:1" ${raw(d ? "" : "disabled")}>
          <label class="freechk"><input type="checkbox" id="u_${key}"
            ${raw(d ? "" : "checked")}> 미정</label>
        </div>`;
    }
    if (AREA_KEYS.includes(key)) {
      return html`<label class="flab" for="e_${key}">${lab}</label>
        <textarea id="e_${key}" class="bigin" rows="3">${v}</textarea>`;
    }
    const list = cand[key];
    return html`
      <label class="flab" for="e_${key}">${lab}</label>
      <input id="e_${key}" class="bigin" type="text" value="${v}"
             inputmode="${MONEY_KEYS.includes(key) ? "numeric" : "text"}"
             ${raw(list ? `list="dl_${key}"` : "")}>
      ${raw(list && list.length
        ? `<datalist id="dl_${key}">${list.map((x) =>
            `<option value="${esc(x)}"></option>`).join("")}</datalist>` : "")}`;
  };

  setBody(html`
    <div class="pane">
      <button class="chip backbtn2" id="ecancel">← 취소</button>
      <h2 style="margin:10px 0 12px">${before.customer || "고객"} 고치기</h2>
      ${raw(WRITABLE.map(field).join(""))}
      <button class="bigcopy" id="esave" style="margin-top:18px">저장</button>
      <p class="empty" id="emsg"></p>
      <p class="synced">첨부 서류(견적서·등록증 등)는 PC 일정관리기의 [수정] 에서 올립니다.</p>
    </div>`);

  // 금액은 치는 동안 1,000 단위
  for (const k of MONEY_KEYS) {
    const el = $(`#e_${k}`);
    if (!el) continue;
    el.addEventListener("input", () => {
      const atEnd = el.selectionStart >= el.value.length;
      const shown = fmt.fmtMoney(el.value);
      if (shown !== el.value) {
        el.value = shown;
        if (atEnd) el.setSelectionRange(shown.length, shown.length);
      }
    });
  }
  // '미정' 을 끄면 날짜 칸이 살아난다
  for (const k of DATE_KEYS) {
    const chk = $(`#u_${k}`), de = $(`#e_${k}`);
    if (!chk || !de) continue;
    chk.addEventListener("change", () => {
      de.disabled = chk.checked;
      if (!chk.checked && !de.value) de.value = fmt.isoDate(new Date());
    });
  }

  $("#ecancel").onclick = () => router.go("/customers/" + r.row);
  $("#esave").onclick = () => save(r, before);
}

/** 화면에서 읽어 **바뀐 칸만** 모은다. */
function collect(before) {
  const out = {};
  for (const [, key] of WRITABLE) {
    let v;
    if (DATE_KEYS.includes(key)) {
      const chk = $(`#u_${key}`), de = $(`#e_${key}`);
      if (!chk || !de) continue;
      v = chk.checked ? "" : fmt.fmtSheetDate(
        de.value ? new Date(de.value + "T00:00:00") : null);
    } else {
      const el = $(`#e_${key}`);
      if (!el) continue;
      v = el.value.trim();
    }
    // 안 바뀐 칸은 아예 안 보낸다 — 건드릴 이유가 없다
    const was = String(before[key] || "");
    if (MONEY_KEYS.includes(key)) {
      if (fmt.digitsOnly(v) === fmt.digitsOnly(was)) continue;
    } else if (v === was) continue;
    out[key] = v;
  }
  return out;
}

async function save(r, before) {
  const msg = $("#emsg");
  const btn = $("#esave");
  const patch = collect(before);
  if (!Object.keys(patch).length) {
    msg.textContent = "바뀐 것이 없습니다.";
    return;
  }
  btn.disabled = true;
  msg.textContent = "저장하는 중…";
  try {
    // ⚠️ 폰은 저장해 둔 목록으로 그린다. 한 시간 전 것을 보고 있는데 그 사이
    //    PC 에서 같은 고객을 고쳤다면, 그냥 쓰면 그 수정이 조용히 지워진다.
    //    쓰기 직전에 그 줄만 다시 읽어, 내가 고치려는 칸이 그 사이 바뀌었으면 묻는다.
    const clash = await conflicts(r, before, patch);
    if (clash === MOVED) {
      // 그 줄에 이제 **다른 고객**이 있다(정렬·추가·삭제로 줄이 밀림).
      // 그대로 쓰면 엉뚱한 고객이 고쳐진다 — 묻지도 않고 멈춘다.
      msg.textContent = "시트가 그 사이 바뀌어 이 고객의 줄이 달라졌습니다. "
        + "목록으로 돌아가 새로 불러온 뒤 다시 고쳐 주세요. (저장하지 않았습니다)";
      btn.disabled = false;
      return;
    }
    if (clash.length) {
      const what = clash.map((k) => LABEL[k] || k).join(", ");
      if (!confirm(`그 사이 다른 곳에서 이 고객을 고쳤습니다 (${what}).\n`
                 + "덮어쓸까요?\n\n[취소] 를 누르면 저장하지 않습니다.")) {
        msg.textContent = "저장하지 않았습니다. 뒤로 갔다 다시 열면 최신으로 보입니다.";
        btn.disabled = false;
        return;
      }
    }
    await sheets.writeCells(sheetId(), sheetTab(), r.row, patch, WRITABLE, MONEY_KEYS);
    // 화면과 저장해 둔 것에도 반영
    r.values = { ...r.values, ...patch };
    await store.put("data", "customers", { rows: _rows, at: _syncedAt });
    setRows(_rows, _syncedAt);
    router.go("/customers/" + r.row);
  } catch (e) {
    btn.disabled = false;
    msg.textContent = e instanceof sheets.NeedScope
      ? "고칠 권한이 아직 없습니다. 위 [다시 로그인] 을 한 번 눌러 주세요."
      : e instanceof sheets.WrongAccount
        ? "이 계정으로는 이 시트를 고칠 수 없습니다."
        : e instanceof sheets.Offline
          ? "인터넷이 안 됩니다. 연결되면 다시 눌러 주세요."
          : (e.message || "저장하지 못했습니다.");
    paintState();
  }
}

const MOVED = "moved";

/** 진행현황만 바꾼다(진행 보드에서 카드를 옮길 때). 고치기와 같은 확인을 거친다 —
 *  쓰기 직전에 그 줄을 다시 읽어, 다른 고객이 와 있으면 멈추고 그 사이 바뀌었으면 묻는다.
 *  썼으면 true, 사람이 [취소] 했으면 false. */
export async function setStatus(rowNo, status) {
  const r = _rows.find((x) => x.row === rowNo);
  if (!r) throw new Error("그 고객을 찾지 못했습니다. 고객 목록을 새로 불러와 주세요.");
  const before = { ...r.values };
  const patch = { status };
  if (String(before.status || "").trim() === status) return true;
  const clash = await conflicts(r, before, patch);
  if (clash === MOVED) {
    throw new Error("시트가 그 사이 바뀌어 이 고객의 줄이 달라졌습니다. 고객 목록을 새로 불러와 주세요.");
  }
  if (clash.length && !confirm("그 사이 다른 곳에서 이 고객의 진행현황을 고쳤습니다.\n덮어쓸까요?")) {
    return false;
  }
  await sheets.writeCells(sheetId(), sheetTab(), r.row, patch, WRITABLE, MONEY_KEYS);
  r.values = { ...r.values, ...patch };
  await store.put("data", "customers", { rows: _rows, at: _syncedAt });
  setRows(_rows, _syncedAt);
  return true;
}

/** 내가 고치려는 칸 중, 불러온 뒤 시트에서 바뀐 것들.
 *  그 줄에 이제 다른 고객이 있으면(고객명이 다르면) MOVED. */
async function conflicts(r, before, patch) {
  let now;
  try {
    now = await sheets.readRow(sheetId(), sheetTab(), r.row);
  } catch (e) {
    return [];              // 확인을 못 했다고 저장을 막지는 않는다
  }
  const { rows } = parseRowsOne(now, r.row);
  if (!rows) return [];
  // ⚠️ 고친 칸만 비교하면, 그 줄에 다른 고객이 와 있어도 그 칸 값이 우연히 같으면
  //    그냥 써 버린다. 먼저 **같은 고객인지**(고객명)부터 본다.
  if (String(rows.customer || "").trim() !== String(before.customer || "").trim()) return MOVED;
  const out = [];
  for (const key of Object.keys(patch)) {
    const nowV = String(rows[key] || "").trim();
    const wasV = String(before[key] || "").trim();
    if (nowV !== wasV) out.push(key);
  }
  return out;
}

/** 한 줄짜리 응답을 필드로 편다 (머리글 탐지 없이). */
function parseRowsOne(got, rowNo) {
  const a = (got.left || [])[0] || [];
  const b = (got.right || [])[0] || [];
  const cells = [...a];
  while (cells.length < 17) cells.push("");
  cells.push("");                       // R 자리
  const bb = [...b];
  while (bb.length < 2) bb.push("");
  cells.push(...bb);
  const out = {};
  for (const [ci, key] of FIELDS) out[key] = String(cells[ci] || "").trim();
  return { rows: out };
}
