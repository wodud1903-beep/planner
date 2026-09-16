// 주간 요약 — PC 앱의 그 화면을 폰에서 본다.
//
// 새 통신이 없다. 고객 탭이 이미 받아 둔 줄로 계산한다(weekly.sections).
// 그래서 오프라인에서도 열린다.
import { html, raw, esc, render, $, $$ } from "./dom.js";
import * as weekly from "../weekly.js";
import { setBody, markTab } from "./chrome.js";
import * as router from "../router.js";

// PC 앱의 안내말 중 폰에 안 맞는 것만 바꿔 넣는다.
// (weekly.js 는 파이썬과 글자까지 같게 두고, 고치는 일은 여기서 한다)
const HINTS = {
  "[고객관리] 탭에서 [이력] 로 상담 내역을 보고 재계약을 준비하세요.":
    "고객을 눌러 계약 내용을 보고 재계약을 준비하세요.",
};

let _rows = () => [];

/** 고객 탭이 자기 줄을 넘겨준다 — 주간 요약은 그걸 계산만 한다. */
export function useRows(fn) { _rows = fn; }

export function screen() {
  markTab("/customers");
  const today = new Date();
  const rows = _rows() || [];
  const secs = weekly.sections(rows, today);

  setBody(html`
    <div class="pane">
      <button class="chip backbtn2" id="wkback">← 고객 목록</button>
      <h2 style="margin:10px 0 2px">주간 요약</h2>
      <p class="s" style="color:var(--sub);margin:0 0 14px">${weekly.titleLine(today)}</p>
      ${raw(rows.length ? "" : `<p class="notice">고객 목록을 아직 못 읽었습니다.
        고객 탭에서 한 번 불러온 뒤 다시 열어 주세요.</p>`)}
      ${raw(secs.map((x) => sec(x, rowIndex(rows))).join(""))}
      <p class="synced">${rows.length}명으로 계산했습니다</p>
    </div>`);

  $("#wkback").onclick = () => router.go("/customers");
  for (const b of $$("#body .wkitem")) {
    b.onclick = () => {
      const r = b.dataset.row;
      if (r) router.go("/customers/" + r);
    };
  }
}

/** 고객 이름 → 줄 번호. 같은 이름이 둘이면 누를 수 없게 둔다.
 *
 * ⚠️ weekly.sections 가 돌려주는 항목에는 줄 번호가 없다. 넣고 싶었지만
 *    그러면 파이썬이 낸 정답표와 어긋나 대조가 통째로 무의미해진다.
 *    옮긴 계산은 건드리지 않고, 여기서 이름으로 되찾는다.
 *    동명이인이면 아무 데도 안 보낸다 — 엉뚱한 고객을 여는 것보다 낫다.
 */
function rowIndex(rows) {
  const by = new Map();
  for (const cr of rows) {
    const k = String((cr.values || {}).customer || "").trim();
    if (!k) continue;
    if (by.has(k)) by.set(k, null);          // 둘 이상 → 못 고른다
    else by.set(k, cr.row);
  }
  return by;
}

function sec(s, idx) {
  const n = s.count !== undefined ? s.count : s.items.length;
  const hint = HINTS[s.hint] || s.hint || "";
  return html`
    <section class="wksec ${s.color || ""}">
      <p class="wkhead">${raw(esc(s.icon) + " ")}${s.title}
        ${raw(n ? `<span class="wkn">${n}건</span>` : "")}</p>
      ${raw(s.items.length
        ? `<ul class="list">${s.items.map((it) => item(it, idx)).join("")}</ul>`
        : `<p class="empty">${esc(s.empty || "없습니다")}</p>`)}
      ${raw(s.note ? `<p class="wknote">${esc(s.note)}</p>` : "")}
      ${raw(s.more ? `<p class="synced">외 ${s.more}건 더 있습니다</p>` : "")}
      ${raw(hint && s.items.length ? `<p class="wkhint">${esc(hint)}</p>` : "")}
    </section>`;
}

function item(it, idx) {
  // 고객을 누르면 그 고객 상세로 간다.
  const row = (idx && idx.get(String(it.text || "").trim())) || "";
  return html`<li><button class="row wkitem" data-row="${row}">
      <span class="meta"><span class="tag">${it.lead}</span></span>
      <span class="t">${it.text}</span>
      ${raw(it.sub ? `<span class="s">${esc(it.sub)}</span>` : "")}
    </button></li>`;
}
