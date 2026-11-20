// 업무자료검색 웹 — 위 메뉴의 [수입차 프로모션] · [수당계산기] 화면(v1.34.2). [자료검색](app.js)과 오간다.
//
// · 수입차 프로모션: 회사 프로모션 시트('수입차 프로모션' 탭)를 **읽기만** 한다. 해석·검색은 일정관리기와 같은
//   promo.js(PC promo.py 를 옮긴 것). 시트는 비공개라 [구글 로그인](구글 동기화와 같은 로그인)이 필요하고,
//   그 로그인은 시트 **보기 권한(spreadsheets.readonly)** 만 받는다 — 이 화면은 시트를 고칠 수 없다.
// · 수당계산기: 일정관리기와 같은 계산식(commission.js — 파이썬 정답표로 검사한 것)과 같은 수당율 표
//   (회사 시트 '수당율' 탭 — /api/rates, 로그인 없이). 표를 못 받으면 앱에 든 기본 표로 계산한다.
// 화면 고르기는 주소(#…)를 쓰지 않는다 — #… 는 자료검색이 '보던 자료' 로 쓴다. 마지막에 본 화면만 기억한다.
import * as promo from "./promo.js";
import * as cm from "./commission.js";
import * as fmt from "./fmt.js";
import { matches } from "./hangul.js";
import * as sync from "./sync.js";

const SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets";
const VIEW_KEY = "kbsearch:view:v1";
const PROMO_KEY = "kbsearch:promo:v1";
const RATES_KEY = "kbsearch:rates:v1";
const CALC_KEY = "kbsearch:calc:v1";
const VIEWS = ["kb", "promo", "calc"];

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const lsGet = (k) => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (e) { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* 꽉 참 */ } };

let opts = { login: () => {} };
let view = "kb";
let off = false;

export function init(o) {
  opts = { ...opts, ...o };
  for (const b of $$("#views button")) b.onclick = () => show(b.dataset.v);
  $("#promoq").addEventListener("input", (e) => { pq = e.target.value; clearTimeout(pTimer); pTimer = setTimeout(paintPromo, 120); });
  $("#promo-reload").onclick = () => loadPromo(true);
  initCalc();
  const saved = lsGet(VIEW_KEY);
  show(VIEWS.includes(saved) ? saved : "kb", false);
}

export const current = () => view;

/** 화면 바꾸기 — 처음 여는 화면은 그때 자료를 받는다. */
export function show(v, remember = true) {
  if (!VIEWS.includes(v)) v = "kb";
  view = v;
  if (remember) lsSet(VIEW_KEY, v);
  for (const b of $$("#views button")) b.setAttribute("aria-selected", String(b.dataset.v === v));
  paintVisible();
  if (off) return;
  if (v === "promo") {
    if (!pBlocks.length) restorePromo();
    paintPromo();
    if (!pFresh || Date.now() - pFresh > promo.STALE_MS) loadPromo(false);
  } else if (v === "calc") {
    loadRates();
    paintCalc();
  }
}

/** 서버가 꺼졌으면(관리자 [서버 끄기]) 메뉴와 두 화면도 함께 감춘다. */
export function setOff(isOff) {
  off = !!isOff;
  paintVisible();
}

function paintVisible() {
  $("#views").hidden = off;
  $("#split").hidden = off || view !== "kb";
  $("#promo-view").hidden = off || view !== "promo";
  $("#calc-view").hidden = off || view !== "calc";
}

// ================================================================== 수입차 프로모션
let pBlocks = [], pGid = null, pAt = 0, pFresh = 0, pErr = "", pNeed = "", pBusy = false;
let pq = "", pBrand = "", pTimer = 0, pShown = [], pMsg = "";

function take(o) {
  pBlocks = promo.parse(o.values || [], o.merges || []);
  pGid = Number.isInteger(o.gid) ? o.gid : null;
  pAt = o.at || 0;
}

function restorePromo() {
  const c = lsGet(PROMO_KEY);
  // 로그인한 계정으로 받은 것만 — 다른 계정·로그아웃 뒤에는 보이지 않는다
  if (c && c.email && c.email === sync.account() && Array.isArray(c.values)) take(c);
}

/** 이 화면은 GET 만 한다 — 다른 방법을 부르면 그 자리에서 멈춘다(읽기 전용). */
async function getJson(url, t) {
  promo.readOnlyGuard("GET", url);
  return fetch(url, { headers: { Authorization: `Bearer ${t.access_token}` } });
}

async function loadPromo(manual) {
  if (pBusy) return;
  pBusy = true; pErr = ""; pNeed = "";
  paintPromoFoot();
  try {
    let t = await sync.token();
    if (!t) { pNeed = "login"; pBlocks = []; return; }
    if (!t.sheets) t = await sync.token(true);             // 들고 있던 것이 예전 로그인 것일 수 있다 — 새로 받아 본다
    if (!t) { pNeed = "login"; pBlocks = []; return; }
    if (!t.sheets) { pNeed = "scope"; return; }
    const u = promo.readUrls(SHEETS_API, promo.DEF_SHEET_ID, promo.DEF_TAB);
    let r = await getJson(u.values, t);
    if (r.status === 401) {
      t = await sync.token(true);
      if (!t) { pNeed = "login"; return; }
      r = await getJson(u.values, t);
    }
    if (r.status === 403) {
      const j = await r.json().catch(() => ({}));
      const m = String((j.error && j.error.message) || "");
      if (/insufficient|scope/i.test(m)) { pNeed = "scope"; return; }
      pErr = "이 계정으로는 프로모션 시트를 볼 수 없습니다 — 시트 주인에게 '뷰어'(보기)로 공유해 달라고 하세요.";
      return;
    }
    if (r.status === 429) { pErr = "구글 시트 사용 한도(1분)에 잠깐 걸렸습니다 — 1분쯤 뒤 [새로고침] 을 눌러 주세요."; return; }
    if (!r.ok) { pErr = `프로모션 시트를 읽지 못했습니다 (HTTP ${r.status})`; return; }
    const j = await r.json();
    let meta = { merges: [], gid: null };
    try {
      const m = await getJson(u.meta, t);
      if (m.ok) meta = promo.metaOf(await m.json(), promo.DEF_TAB);
    } catch (e) { /* 병합을 몰라도 읽을 수는 있다 */ }
    const o = { values: j.values || [], merges: meta.merges, gid: meta.gid, at: Date.now(), email: t.email || "" };
    take(o);
    pFresh = Date.now();
    lsSet(PROMO_KEY, o);
    if (manual) pMsg = "새로 읽었습니다.";
  } catch (e) {
    pErr = navigator.onLine === false ? "인터넷에 연결되지 않았습니다." : (e && e.message) || "프로모션 시트를 읽지 못했습니다.";
  } finally {
    pBusy = false;
    paintPromo();
  }
}

function paintPromo() {
  const box = $("#promolist");
  if (!box || view !== "promo") return;
  const q = pq.trim();
  const found = promo.search(pBlocks, q, pBrand);
  const counts = q ? promo.hitCount(promo.search(pBlocks, q, "")) : {};
  // 브랜드 단추
  if (!pBlocks.find((b) => b.key === pBrand)) pBrand = "";
  const sum = (o) => Object.values(o).reduce((a, c) => a + c, 0);
  $("#promobrands").innerHTML = [["", "전체"], ...pBlocks.map((b) => [b.key, b.brand])].map(([k, n]) =>
    `<button type="button" data-k="${esc(k)}" aria-pressed="${k === pBrand}">${esc(n)}`
    + (q ? `<span class="n">${k ? (counts[k] || 0) : sum(counts)}</span>` : "") + "</button>").join("");
  for (const b of $$("#promobrands button")) b.onclick = () => { pBrand = b.dataset.k; paintPromo(); };
  pShown = [];
  if (!pBlocks.length) {
    let h = "";
    if (pNeed === "login") {
      h = `<div class="pempty"><b>구글 로그인이 필요합니다</b><p>프로모션 시트는 회사 계정만 볼 수 있어 로그인해야 합니다.<br>`
        + `로그인하면 시트를 <b>보기만</b> 합니다(고칠 수 없습니다).</p>`
        + `<button type="button" class="btn primary" id="promo-login">구글 로그인</button></div>`;
    } else if (pNeed === "scope") {
      h = `<div class="pempty"><b>시트 보기 권한이 필요합니다</b><p>구글 동의 화면에서 <b>스프레드시트 보기</b> 항목을 체크해 주세요.<br>`
        + `보기 권한이라 시트를 고칠 수 없습니다.</p>`
        + `<button type="button" class="btn primary" id="promo-login">다시 로그인</button></div>`;
    } else {
      h = `<p class="pempty">${esc(pBusy || (!pErr && !pAt) ? "프로모션 시트를 불러오는 중…" : pErr || "프로모션 시트에 표가 없습니다.")}</p>`;
    }
    box.innerHTML = h;
    const lb = $("#promo-login");
    if (lb) lb.onclick = () => opts.login(pNeed === "scope");
    paintPromoFoot();
    return;
  }
  if (!found.length) {
    const [typed] = promo.splitQuery(q);
    const others = sum(counts);
    box.innerHTML = `<p class="pempty">${esc(pBrand && !typed.size && others
      ? `'${q}' — 이 브랜드에는 없습니다. 다른 브랜드: ` + pBlocks.filter((b) => counts[b.key]).map((b) => `${b.brand} ${counts[b.key]}`).join(" · ")
      : `'${q}' 에 맞는 모델이 없습니다. 모델명 일부(예: E300 · X5 · Q5)나 초성으로 찾아 보세요.`)}</p>`;
    paintPromoFoot(counts);
    return;
  }
  const out = [];
  for (const [b, rows] of found) {
    const named = (promo.brandOf(b.title) || [""])[0] === b.key;
    const title = b.title ? (named ? b.title : `${b.brand} · ${b.title}`) : b.brand;
    const groups = b.groups.map(([k0, w, t]) => `${esc(t)}: ${esc(b.headers.slice(k0, k0 + w).filter(Boolean).join("·"))}`)
      .join(" &nbsp;|&nbsp; ");
    let body = "";
    for (const r of rows) {
      const i = pShown.push([b, r]) - 1;
      if (r.kind === "section") body += `<h4 class="psec">${esc(r.cells[0])}</h4>`;
      else if (r.kind === "note") body += `<button type="button" class="pnote" data-i="${i}">${esc(r.cells[0])}</button>`;
      else {
        let vs = "";
        for (let k = 1; k < r.cells.length; k++) {
          const v = r.cells[k];
          if (!v) continue;
          const tone = promo.toneOf(v);
          vs += `<span class="pv${tone ? " " + tone : ""}"><i>${esc(b.headers[k] || "")}</i>${esc(v)}</span>`;
        }
        body += `<button type="button" class="prow" data-i="${i}" title="시트 ${r.row}행 — 누르면 복사">`
          + `<b class="pm">${esc(r.cells[0] || "—")}</b><span class="pvs">${vs}</span></button>`;
      }
    }
    out.push(`<section class="promoblk"><h3>${esc(title)}</h3>${groups ? `<p class="pgroups">${groups}</p>` : ""}${body}</section>`);
  }
  box.innerHTML = out.join("");
  for (const el of $$("#promolist [data-i]")) el.onclick = () => copyPromo(+el.dataset.i);
  paintPromoFoot(counts);
}

function paintPromoFoot(counts) {
  const f = $("#promo-foot-text");
  if (!f) return;
  const bits = [];
  if (pBlocks.length) {
    bits.push(pq.trim() && counts ? `찾은 모델 ${Object.values(counts).reduce((a, c) => a + c, 0)}개`
                                  : `모델 ${promo.modelCount(pBlocks)}개`);
    if (pAt) {
      const d = new Date(pAt);
      bits.push(`${pFresh ? "" : "받아 둔 것 · "}${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")} 읽음`);
    }
    bits.push("줄을 누르면 복사 · 읽기 전용");
  }
  if (pBusy) bits.push("새로 읽는 중…");
  if (pMsg) { bits.push(pMsg); pMsg = ""; }
  f.textContent = bits.join(" · ");
  const foot = $("#promo-foot");
  foot.classList.toggle("bad", !!(pErr && pBlocks.length));
  if (pErr && pBlocks.length) f.textContent += " · " + pErr;
  const a = $("#promo-open");
  a.href = promo.sheetUrl(promo.DEF_SHEET_ID, pGid);
  a.hidden = !pBlocks.length;
}

function copyPromo(i) {
  const it = pShown[i];
  if (!it) return;
  const text = promo.rowText(it[0], it[1]);
  navigator.clipboard.writeText(text).then(() => {
    $("#promo-foot-text").textContent = "복사했습니다 — 카톡에 붙여 넣으세요: " + (text.length > 40 ? text.slice(0, 40) + "…" : text);
    $("#promo-foot").classList.remove("bad");
  }).catch(() => { $("#promo-foot-text").textContent = "복사하지 못했습니다 — 길게 눌러 복사하세요."; });
}

/** 로그인·로그아웃·계정이 바뀌었다(app.js 의 동기화 창) — 프로모션을 그 계정 것으로. */
export function accountChanged() {
  pBlocks = []; pAt = 0; pFresh = 0; pErr = ""; pNeed = "";
  if (view === "promo" && !off) { restorePromo(); paintPromo(); loadPromo(false); }
}

// ================================================================== 수당계산기
let rates = cm.DEFAULT_RATES, fromSheet = false, rErr = "", rLoaded = false;
let cBrand = "hyundai", cPick = -1, cPrice = "", cPay = String(cm.DEF_PAY_RATE | 0), cFree = false, cq = "";

function initCalc() {
  const s = lsGet(CALC_KEY) || {};
  if (cm.BRANDS.includes(s.brand)) cBrand = s.brand;
  if (s.pay) cPay = String(s.pay);
  const c = lsGet(RATES_KEY);
  if (c && c.rates) { rates = c.rates; fromSheet = true; }
  $("#cbrand").innerHTML = cm.BRANDS.map((b) =>
    `<button type="button" data-b="${b}" aria-pressed="${b === cBrand}">${esc(cm.BRAND_NAMES[b])}</button>`).join("");
  for (const b of $$("#cbrand button")) {
    b.onclick = () => {
      cBrand = b.dataset.b; cPick = -1;
      lsSet(CALC_KEY, { brand: cBrand, pay: cPay });
      for (const x of $$("#cbrand button")) x.setAttribute("aria-pressed", String(x.dataset.b === cBrand));
      paintCalc();
    };
  }
  $("#ccar").addEventListener("input", (e) => { cq = e.target.value; paintCars(); });
  const pe = $("#cprice");
  pe.addEventListener("input", () => {
    const atEnd = pe.selectionStart >= pe.value.length;
    const shown = fmt.fmtMoney(pe.value);             // 치는 동안 1,000 단위로 — PC 와 같다
    if (shown !== pe.value) { pe.value = shown; if (atEnd) pe.setSelectionRange(shown.length, shown.length); }
    cPrice = pe.value;
    recalc();
  });
  $("#cpay").value = cPay;
  $("#cpay").addEventListener("input", (e) => { cPay = e.target.value; lsSet(CALC_KEY, { brand: cBrand, pay: cPay }); recalc(); });
  $("#cfree").addEventListener("change", (e) => { cFree = e.target.checked; recalc(); });
  $("#ccopy").onclick = copyCalc;
  $("#creset").onclick = () => {
    cPrice = ""; cPay = String(cm.DEF_PAY_RATE | 0); cFree = false; cPick = -1; cq = "";
    $("#cprice").value = ""; $("#cpay").value = cPay; $("#cfree").checked = false; $("#ccar").value = "";
    paintCalc();
  };
}

async function loadRates() {
  if (rLoaded) return;
  rLoaded = true;
  try {
    const r = await fetch("/api/rates");
    const j = await r.json().catch(() => ({}));
    if (r.status === 503 && j.off) return;                  // 서버를 껐다 — app.js 가 꺼짐 화면을 띄운다
    if (!r.ok || !Array.isArray(j.rows)) throw new Error(j.error || `수당율을 받지 못했습니다 (${r.status})`);
    const got = cm.parseRates(j.rows);
    if (got) { rates = got; fromSheet = true; rErr = ""; lsSet(RATES_KEY, { rates: got, at: Date.now() }); }
    else if (!fromSheet) rErr = "회사 시트에 수당율 표가 아직 없어 앱에 든 기본 표로 계산합니다.";
  } catch (e) {
    rLoaded = false;                                       // 다음에 열 때 다시 받는다
    if (!fromSheet) rErr = "수당율 표를 받지 못해 앱에 든 기본 표로 계산합니다.";
  }
  paintCalc();
}

const cItems = () => (rates && rates[cBrand]) || [];
const cPicked = () => (cPick >= 0 && cPick < cItems().length ? cItems()[cPick] : null);
const num = (s, def = 0) => { const v = parseFloat(String(s || "").replace(/,/g, "").trim()); return Number.isFinite(v) ? v : def; };

function paintCalc() {
  if (view !== "calc") return;
  paintCars();
  recalc();
  $("#cerr").textContent = rErr;
  const src = $("#csrc");
  src.textContent = fromSheet ? "회사 시트의 수당율로 계산합니다" : "앱에 든 기본 수당율로 계산합니다";
  src.classList.toggle("warn", !fromSheet);
}

function paintCars() {
  const el = $("#ccars");
  const all = cItems();
  const q = cq.trim();
  const rows = all.map((it, i) => [it, i]).filter(([it]) => !q || matches(it[0], q));
  if (!rows.length) { el.innerHTML = `<li class="cempty">${all.length ? "그런 차종이 없습니다." : "차종이 없습니다."}</li>`; return; }
  el.innerHTML = rows.map(([[name, rate, truck], i]) =>
    `<li><button type="button" class="carrow" data-i="${i}" aria-pressed="${i === cPick}">`
    + `<span class="t">${esc(name)}</span><span class="s">${esc(String(rate))}% · ${truck ? "화물차" : "승용차"}</span></button></li>`).join("");
  for (const b of $$("#ccars button")) b.onclick = () => { cPick = +b.dataset.i; paintCars(); recalc(); };
}

function won() {
  const it = cPicked();
  return cm.calc(num(cPrice), it ? it[1] : 0, it ? it[2] : false, num(cPay, cm.DEF_PAY_RATE), cFree);
}

function recalc() {
  const it = cPicked();
  $("#cres").textContent = "₩ " + won().toLocaleString("ko-KR");
  $("#crate").textContent = it
    ? `${it[0]} · 수당율 ${it[1]}% · ${it[2] ? "화물차" : "승용차"} 기준` + (cFree ? " · 면세" : "")
    : "차종을 골라 주세요";
}

function copyCalc() {
  const it = cPicked();
  const text = [
    it ? `${cm.BRAND_NAMES[cBrand]} ${it[0]}` : cm.BRAND_NAMES[cBrand],
    `차량가 ${fmt.fmtMoney(cPrice) || "0"}원`,
    it ? `수당율 ${it[1]}% (${it[2] ? "화물차" : "승용차"})` : "",
    `지급율 ${num(cPay, cm.DEF_PAY_RATE)}%`,
    cFree ? "면세 차량" : "",
    `최종 지급수수료 ${won().toLocaleString("ko-KR")}원`,
  ].filter(Boolean).join("\n");
  const b = $("#ccopy");
  navigator.clipboard.writeText(text).then(() => {
    b.textContent = "복사됐습니다 ✓"; b.classList.add("done");
    setTimeout(() => { b.textContent = "결과 복사"; b.classList.remove("done"); }, 1600);
  }).catch(() => { b.textContent = "복사 실패"; });
}
