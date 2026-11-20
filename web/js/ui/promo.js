// 수입차 프로모션(v1.34.2) — PC 일정관리기의 왼쪽 메뉴 '수입차 프로모션' 과 같은 표를 폰에서.
//
// 회사 프로모션 시트('수입차 프로모션' 탭)를 **읽기만** 한다. 브랜드마다 시트 4행 제목을 그대로 칸 이름으로 쓰고,
// 모델명은 치는 대로 찾는다(자료검색과 같은 초성 · 끝 글자 조합 중). 줄을 누르면 한 줄로 복사된다(카톡에 붙이기).
// 화면을 처음 열 때 읽는다(켤 때는 안 읽는다 — 시트 읽기 한도를 아낀다). 받아 둔 것은 이 기기에 둔다.
import { html, esc, render, $, $$ } from "./dom.js";
import * as store from "../store.js";
import * as sheets from "../sheets.js";
import * as promo from "../promo.js";
import * as auth from "../auth.js";
import { setBody, markTab, paintState, toast } from "./chrome.js";
import { icon } from "./icons.js";

let _blocks = [];
let _gid = null;
let _at = 0;            // 받은 때(ms)
let _fresh = 0;         // 이번에 연 뒤 시트에서 새로 읽은 때
let _where = null;      // {sid, tab}
let _err = "";
let _busy = false;
let _q = "";
let _brand = "";
let _timer = 0;
let _shown = [];        // 화면의 줄 → [블록, 줄]

const here = () => !!$("#promolist");

/** PC 설정에서 프로모션 시트를 바꿨으면 그쪽(boot.js 가 받아 둔 pcCfg) — 비어 있으면 회사 시트. */
async function where() {
  const c = (await store.get("meta", "pcCfg")) || {};
  const sid = String(c.promoSheet || "").trim() || promo.DEF_SHEET_ID;
  let tab = String(c.promoTab || "").trim();
  if (!tab && sid === promo.DEF_SHEET_ID) tab = promo.DEF_TAB;
  promo.protect(sid);
  return { sid, tab };
}

function take(o) {
  _blocks = promo.parse(o.values || [], o.merges || []);
  _gid = Number.isInteger(o.gid) ? o.gid : null;
  _at = o.at || 0;
}

/** 받아 둔 것부터 — refresh 면 시트에서 새로 읽는다. 계정이 바뀌면 boot.js 가 refresh:false 로 불러 비운다. */
export async function load({ refresh = true } = {}) {
  const w = await where();
  const same = _where && _where.sid === w.sid && _where.tab === w.tab;
  _where = w;
  const c = await store.get("data", "promo");
  if (c && c.sid === w.sid && c.tab === w.tab) { if (!same || !_blocks.length) take(c); }
  else { _blocks = []; _gid = null; _at = 0; _fresh = 0; }
  if (!refresh) { _err = ""; paint(); return; }
  if (_busy) return;
  _busy = true;
  paintFoot();
  try {
    const got = await sheets.readPromo(w.sid, w.tab);
    take(got);
    _fresh = Date.now();
    _err = "";
    await store.put("data", "promo", { sid: w.sid, tab: w.tab, values: got.values, merges: got.merges,
                                       gid: got.gid, at: got.at });
  } catch (e) {
    _err = e instanceof sheets.NeedSignIn ? "구글 로그인 후 볼 수 있습니다. 위 [로그인] 을 눌러 주세요."
      : e instanceof sheets.Offline ? "인터넷에 연결되지 않았습니다."
      : e instanceof sheets.NeedScope ? "시트 권한이 아직 없습니다. 위 [다시 로그인] 을 눌러 허용해 주세요."
      : e instanceof sheets.WrongAccount
        ? "이 계정으로는 프로모션 시트를 볼 수 없습니다 — 시트 주인에게 '뷰어'(보기)로 공유해 달라고 하세요."
      : e instanceof sheets.BadRange ? `시트에 '${w.tab}' 탭이 없습니다 — PC [설정] → [화면·기타] 의 탭 이름을 확인하세요.`
      : (e && e.message) || "프로모션 시트를 읽지 못했습니다.";
    paintState();
  } finally {
    _busy = false;
  }
  paint();
}

export async function screen() {
  markTab("/promo");
  setBody(html`
    <div class="pane promopane">
      <div class="searchbar">
        <input id="promoq" type="search" value="${_q}" autocomplete="off" enterkeyhint="search"
               placeholder="모델명 — 예: E300 · X5 · Q5 스포트백 · 전기차">
      </div>
      <div class="cats" id="promobrands"></div>
      <div id="promolist"></div>
      <p class="synced" id="promofoot"></p>
    </div>`);
  $("#promoq").addEventListener("input", (e) => {
    _q = e.target.value;
    clearTimeout(_timer);
    _timer = setTimeout(paint, 120);      // 타자가 멎으면 한 번만
  });
  paint();
  const stale = !_fresh || Date.now() - _fresh > promo.STALE_MS;
  if (stale && auth.email()) load();
  else if (!auth.email() && !_blocks.length) load();
}

function paintBrands(counts) {
  const el = $("#promobrands");
  if (!el) return;
  const q = _q.trim();
  const all = [["", "전체"], ..._blocks.map((b) => [b.key, b.brand])];
  if (!_blocks.find((b) => b.key === _brand)) _brand = "";
  render(el, all.map(([k, n]) => {
    const c = q ? (k ? (counts[k] || 0) : Object.values(counts).reduce((a, b) => a + b, 0)) : null;
    return `<button data-k="${esc(k)}" aria-pressed="${String(k === _brand)}">${esc(n)}${c === null ? "" : " " + c}</button>`;
  }).join(""));
  for (const b of $$("#promobrands button")) {
    b.onclick = () => { _brand = b.dataset.k; paint(); };
  }
}

function cellHtml(b, r) {
  const parts = [];
  for (let k = 1; k < r.cells.length; k++) {
    const v = r.cells[k];
    if (!v) continue;
    const tone = promo.toneOf(v);
    parts.push(`<span class="pv${tone ? " " + tone : ""}"><i>${esc(b.headers[k] || "")}</i>${esc(v)}</span>`);
  }
  return parts.join("");
}

function paint() {
  const box = $("#promolist");
  if (!box) return;
  const q = _q.trim();
  const found = promo.search(_blocks, q, _brand);
  const counts = q ? promo.hitCount(promo.search(_blocks, q, "")) : {};
  paintBrands(counts);
  _shown = [];
  if (!_blocks.length) {
    render(box, `<p class="empty">${esc(_busy || (!_err && !_at) ? "프로모션 시트를 불러오는 중…" : _err || "프로모션 시트에 표가 없습니다.")}</p>`);
    paintFoot();
    return;
  }
  if (!found.length) {
    const [typed] = promo.splitQuery(q);
    const others = Object.values(counts).reduce((a, c) => a + c, 0);
    const msg = _brand && !typed.size && others
      ? `'${q}' — 이 브랜드에는 없습니다. 다른 브랜드에 있습니다: `
        + _blocks.filter((b) => counts[b.key]).map((b) => `${b.brand} ${counts[b.key]}`).join(" · ")
      : `'${q}' 에 맞는 모델이 없습니다. 모델명 일부(예: E300 · X5 · Q5)나 초성으로 찾아 보세요.`;
    render(box, `<p class="empty">${esc(msg)}</p>`);
    paintFoot();
    return;
  }
  const out = [];
  for (const [b, rows] of found) {
    const named = (promo.brandOf(b.title) || [""])[0] === b.key;
    const title = b.title ? (named ? b.title : `${b.brand} · ${b.title}`) : b.brand;
    const groups = b.groups.map(([k0, w, t]) =>
      `${esc(t)}: ${esc(b.headers.slice(k0, k0 + w).filter(Boolean).join("·"))}`).join(" &nbsp;|&nbsp; ");
    let body = "";
    for (const r of rows) {
      const i = _shown.push([b, r]) - 1;
      if (r.kind === "section") body += `<h4 class="psec">${esc(r.cells[0])}</h4>`;
      else if (r.kind === "note") body += `<button class="pnote" data-i="${i}">${esc(r.cells[0])}</button>`;
      else {
        body += `<button class="prow" data-i="${i}" title="시트 ${r.row}행 — 누르면 복사">`
          + `<b class="pm">${esc(r.cells[0] || "—")}</b><span class="pvs">${cellHtml(b, r)}</span></button>`;
      }
    }
    out.push(`<section class="card promoblk">
      <div class="cardhead"><h3 class="cardtitle">${icon("car", 18)}${esc(title)}</h3></div>
      ${groups ? `<p class="pgroups">${groups}</p>` : ""}
      ${body}</section>`);
  }
  render(box, out.join(""));
  for (const el of $$("#promolist [data-i]")) {
    el.onclick = () => copyRow(+el.dataset.i);
  }
  paintFoot(counts);
}

function paintFoot(counts) {
  const f = $("#promofoot");
  if (!f) return;
  const q = _q.trim();
  const bits = [];
  if (_blocks.length) {
    bits.push(q && counts ? `찾은 모델 ${Object.values(counts).reduce((a, c) => a + c, 0)}개`
                          : `모델 ${promo.modelCount(_blocks)}개`);
    if (_at) {
      const d = new Date(_at);
      bits.push(`${_fresh ? "시트에서" : "받아 둔 것 ·"} ${d.getMonth() + 1}/${d.getDate()} `
        + `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")} 읽음`);
    }
    bits.push("줄을 누르면 복사 · 읽기 전용");
  }
  if (_busy) bits.push("새로 읽는 중…");
  render(f, esc(bits.join(" · "))
    + (_err && _blocks.length ? `<br><span style="color:var(--bad)">${esc(_err)}</span>` : "")
    + (_where ? ` <a class="linky" href="${esc(promo.sheetUrl(_where.sid, _gid))}" target="_blank" rel="noopener">시트 열기</a>` : ""));
}

function copyRow(i) {
  const it = _shown[i];
  if (!it) return;
  const [b, r] = it;
  const text = promo.rowText(b, r);
  navigator.clipboard.writeText(text)
    .then(() => toast("복사했어요 — 카톡에 붙여 넣으세요."))
    .catch(() => toast("복사하지 못했습니다 — 길게 눌러 복사하세요.", { tone: "bad" }));
}

/** 다른 화면에서 돌아와도 보던 검색 그대로 — 계정이 바뀌면 boot.js 가 load({refresh:false}). */
export const isHere = here;
