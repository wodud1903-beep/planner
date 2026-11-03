// 고객 진행 보드(폰·폴드) — 플로우의 '업무 상태'. 칸 = 진행현황 값, 카드 = 고객.
//
// 폰에서는 끌어 놓기가 손에 안 맞아 카드마다 [옮기기] 를 둔다(고르면 바로 시트에 쓴다).
// 넓은 화면(폴드 펼침·PC 브라우저)에서는 끌어 놓기도 된다.
// 시트에 쓰는 일은 고객 고치기와 같은 길(customers.setStatus) — 쓰기 직전에 그 줄을
// 다시 읽어 다른 고객이 와 있으면 멈춘다.
import { html, raw, esc, render, $, $$ } from "./dom.js";
import * as boardlib from "../board.js";
import * as weeklyui from "./weekly.js";
import * as cust from "./customers.js";
import * as sheets from "../sheets.js";
import { setBody, markTab, paintState, toast } from "./chrome.js";
import * as router from "../router.js";

let _showCancel = false;
let _busy = new Set();          // 지금 옮기는 중인 줄

// 고객 줄이 새로 오면 다시 그린다
addEventListener("planner:rows", () => { if ($("#board")) paint(); });

export function screen() {
  markTab("/customers");
  setBody(html`
    <div class="pane boardpane">
      <div class="boardtop">
        <button class="chip backbtn2" id="bback">← 고객 목록</button>
        <h2>진행 보드</h2>
        <span class="grow"></span>
        <label class="bchk"><input type="checkbox" id="bcancel"> 취소·부결</label>
      </div>
      <p class="s bhint">카드를 누르면 고객 상세 · [옮기기] 로 진행현황을 바꿉니다
        (넓은 화면은 끌어 놓기도 됩니다)</p>
      <div class="board" id="board"></div>
    </div>
    <div class="sheet" id="bsheet" hidden></div>`);
  $("#bback").onclick = () => router.go("/customers");
  const c = $("#bcancel");
  c.checked = _showCancel;
  c.onchange = () => { _showCancel = c.checked; paint(); };
  paint();
  if (!weeklyui.rows().length) cust.load();
}

function cardHtml(k) {
  return html`<div class="bcard${raw(_busy.has(k.row) ? " busy" : "")}" draggable="true"
                   data-row="${k.row}">
      <button class="bopen" data-row="${k.row}">
        <span class="t">${k.name}</span>
        ${raw(k.sub ? `<span class="s">${esc(k.sub)}</span>` : "")}
        ${raw(k.chip ? `<span class="bchip ${esc(k.tone)}">${esc(k.chip)}</span>` : "")}
      </button>
      <button class="chip bmove" data-row="${k.row}">${_busy.has(k.row) ? "옮기는 중…" : "옮기기"}</button>
    </div>`;
}

function paint() {
  const box = $("#board");
  if (!box) return;
  const rows = weeklyui.rows();
  if (!rows.length) {
    render(box, html`<p class="empty">고객 목록을 불러오는 중입니다…<br>
      (고객 탭에서 시트를 한 번 불러오면 진행현황별로 놓입니다)</p>`);
    return;
  }
  const cols = boardlib.columns(rows, new Date(), _showCancel);
  render(box, cols.map((col) => html`
    <section class="bcol" data-status="${col.status}">
      <div class="bhead"><b>${col.status}</b><span class="cardcount">${col.count}</span></div>
      <div class="bcards">${raw(col.cards.map(cardHtml).join("")
        || '<p class="bempty">여기로 옮길 수 있어요</p>')}</div>
      ${raw(col.more ? `<p class="synced">지난 출고 ${col.more}건은 목록에서</p>` : "")}
    </section>`).join(""));

  for (const b of $$(".bopen", box)) b.onclick = () => router.go("/customers/" + b.dataset.row);
  for (const b of $$(".bmove", box)) b.onclick = () => pick(Number(b.dataset.row));
  // 넓은 화면 — 끌어 놓기
  for (const el of $$(".bcard", box)) {
    el.ondragstart = (e) => { e.dataTransfer.setData("text/plain", el.dataset.row); el.classList.add("drag"); };
    el.ondragend = () => el.classList.remove("drag");
  }
  for (const col of $$(".bcol", box)) {
    col.ondragover = (e) => { e.preventDefault(); col.classList.add("over"); };
    col.ondragleave = () => col.classList.remove("over");
    col.ondrop = (e) => {
      e.preventDefault();
      col.classList.remove("over");
      const row = Number(e.dataTransfer.getData("text/plain"));
      if (row) move(row, col.dataset.status);
    };
  }
}

/** [옮기기] — 아래에서 올라오는 칸 목록에서 고른다. */
function pick(row) {
  const r = weeklyui.rows().find((x) => x.row === row);
  if (!r) return;
  const cur = String(r.values.status || "").trim() || boardlib.NO_STATUS;
  const all = boardlib.columns(weeklyui.rows(), new Date(), true).map((c) => c.status);
  const sh = $("#bsheet");
  render(sh, html`<div class="sheetbox" role="dialog" aria-label="진행현황 옮기기">
      <p class="sheettitle"><b>${r.values.customer}</b> — 어디로 옮길까요?</p>
      <div class="sheetlist">${raw(all.filter((s) => s !== cur).map((s) =>
        html`<button class="row bto" data-to="${s}">${s}</button>`).join(""))}</div>
      <button class="chip" id="bclose">닫기</button>
    </div>`);
  sh.hidden = false;
  const close = () => { sh.hidden = true; render(sh, ""); };
  sh.onclick = (e) => { if (e.target === sh) close(); };
  $("#bclose").onclick = close;
  for (const b of $$(".bto", sh)) b.onclick = () => { close(); move(row, b.dataset.to); };
}

async function move(row, status) {
  const to = status === boardlib.NO_STATUS ? "" : status;
  const r = weeklyui.rows().find((x) => x.row === row);
  if (!r || String(r.values.status || "").trim() === to || _busy.has(row)) return;
  _busy.add(row);
  paint();
  try {
    if (await cust.setStatus(row, to)) {
      toast(`${r.values.customer} → ${to || "진행현황 없음"} (시트에 저장했어요)`);
    }
  } catch (e) {
    toast(e instanceof sheets.NeedScope ? "시트를 고칠 권한이 없습니다. 위 [다시 로그인] 을 눌러 주세요."
      : e instanceof sheets.Offline ? "인터넷에 연결되지 않았어요."
      : e instanceof sheets.WrongAccount ? "이 계정으로는 이 시트를 고칠 수 없습니다."
      : (e.message || "옮기지 못했습니다."), { tone: "bad", sticky: true });
    paintState();
  }
  _busy.delete(row);
  paint();
}
