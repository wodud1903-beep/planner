// 수당계산기 — PC 앱과 같은 계산식. 차종을 고르고 차량가를 넣으면 바로 나온다.
//
// 수당율 표는 회사 공용 시트('수당율' 탭)에서 받는다. PC 앱과 같은 곳을 보므로
// 누가 고치든 폰에도 그대로 반영된다.
import { html, raw, esc, render, $, $$ } from "./dom.js";
import * as store from "../store.js";
import * as sheets from "../sheets.js";
import * as hangul from "../hangul.js";
import * as fmt from "../fmt.js";
import * as cm from "../commission.js";
import { RATES_SHEET_ID } from "../config.js";
import { setBody, markTab, paintState } from "./chrome.js";

const RATES_TAB = "수당율";

// 시트를 못 읽어도 계산은 되어야 한다 — PC 앱이 그렇게 동작한다.
// 시트를 읽으면 그쪽이 언제나 이긴다.
let _rates = cm.DEFAULT_RATES;
let _fromSheet = false;
let _brand = "hyundai";
let _pick = -1;            // 고른 차종 (지금 브랜드 안에서의 번호)
let _price = "";
let _pay = String(cm.DEF_PAY_RATE | 0);
let _free = false;
let _err = "";
let _q = "";

export async function load({ refresh = true } = {}) {
  const c = await store.get("data", "rates");
  if (c && c.rates) { _rates = c.rates; _fromSheet = true; repaint(); }
  else if (!refresh) { _rates = cm.DEFAULT_RATES; _fromSheet = false; _pick = -1; repaint(); }
  if (!refresh) return;
  try {
    const rows = await sheets.values(RATES_SHEET_ID, RATES_TAB, "A1:D");
    const got = cm.parseRates(rows);
    if (got) {
      _rates = got;
      _fromSheet = true;
      _err = "";
      await store.put("data", "rates", { rates: got, at: Date.now() });
    } else if (!_fromSheet) {
      _err = `공용 시트에 '${RATES_TAB}' 표가 아직 없어 앱에 든 기본 표로 계산합니다.`;
    }
  } catch (e) {
    if (e instanceof sheets.BadRange) {
      _err = _fromSheet ? "" :
        `공용 시트에 '${RATES_TAB}' 탭이 없어 앱에 든 기본 표로 계산합니다.\n`
        + "PC 앱 [설정] → 수당율에서 한 번 저장하면 탭이 생깁니다.";
    } else if (e instanceof sheets.NeedScope) {
      _err = "시트 권한이 아직 없습니다. 위 [다시 로그인] 을 눌러 주세요.";
    } else if (!(e instanceof sheets.NeedSignIn || e instanceof sheets.Offline)) {
      _err = e.message || "수당율을 불러오지 못했습니다.";
    }
    paintState();
  }
  repaint();
}

const items = () => (_rates && _rates[_brand]) || [];
const picked = () => (_pick >= 0 && _pick < items().length) ? items()[_pick] : null;

export async function screen() {
  markTab("/calc");
  const ui = await store.ui();
  _brand = ui.calcBrand || "hyundai";
  _pay = ui.calcPay || String(cm.DEF_PAY_RATE | 0);
  setBody(html`
    <div class="pane calcpane">
      <div class="cats" id="cbrand">
        ${raw(cm.BRANDS.map((b) =>
          `<button data-b="${b}" aria-pressed="${String(b === _brand)}">${
            esc(cm.BRAND_NAMES[b])}</button>`).join(""))}
      </div>

      <label class="flab" for="ccar">차종</label>
      <div class="searchbar" style="padding-top:0">
        <input id="ccar" type="search" value="${_q}" autocomplete="off"
               placeholder="차종 검색 (초성도 됩니다)">
      </div>
      <ul class="list carlist" id="ccars"></ul>

      <label class="flab" for="cprice">차량가 (₩)</label>
      <input id="cprice" class="bigin" type="text" inputmode="numeric"
             value="${_price}" placeholder="차량가를 입력하세요">

      <div class="calcrow">
        <div style="flex:1">
          <label class="flab" for="cpay">지급율 (%)</label>
          <input id="cpay" class="bigin" type="text" inputmode="decimal" value="${_pay}">
        </div>
        <label class="freechk"><input id="cfree" type="checkbox"> 면세 차량</label>
      </div>

      <div class="calcout">
        <span>최종 지급수수료</span>
        <b id="cres">₩ 0</b>
      </div>
      <p class="s" id="crate" style="color:var(--sub);text-align:right;margin:0 0 10px"></p>
      <button class="bigcopy" id="ccopy">결과 복사</button>
      <p class="synced" id="csrc"></p>
      <p class="synced"><button class="linky" id="creset">초기화</button></p>
      <p class="empty" id="cerr"></p>
    </div>`);

  for (const b of $$("#cbrand button")) {
    b.onclick = () => {
      _brand = b.dataset.b; _pick = -1;
      store.ui({ calcBrand: _brand });
      for (const x of $$("#cbrand button")) {
        x.setAttribute("aria-pressed", String(x.dataset.b === _brand));
      }
      repaint();
    };
  }
  $("#ccar").addEventListener("input", (e) => { _q = e.target.value; paintCars(); });
  // 차량가는 치는 동안 1,000 단위로 보기 좋게 바꿔 준다 — PC 앱과 같다
  const pe = $("#cprice");
  pe.addEventListener("input", () => {
    const atEnd = pe.selectionStart >= pe.value.length;
    const shown = fmt.fmtMoney(pe.value);
    if (shown !== pe.value) {
      pe.value = shown;
      if (atEnd) pe.setSelectionRange(shown.length, shown.length);
    }
    _price = pe.value;
    recalc();
  });
  $("#cpay").addEventListener("input", (e) => {
    _pay = e.target.value; store.ui({ calcPay: _pay }); recalc();
  });
  $("#cfree").addEventListener("change", (e) => { _free = e.target.checked; recalc(); });
  $("#ccopy").onclick = copy;
  $("#creset").onclick = () => {
    _price = ""; _pay = String(cm.DEF_PAY_RATE | 0); _free = false; _pick = -1; _q = "";
    $("#cprice").value = ""; $("#cpay").value = _pay;
    $("#cfree").checked = false; $("#ccar").value = "";
    repaint();
  };

  repaint();
  if (!_rates) await load(); else load();
}

function repaint() { paintCars(); recalc(); paintErr(); }

function paintErr() {
  const e = $("#cerr");
  if (e) e.textContent = _err;
  // 어느 표로 계산하고 있는지 늘 보이게 한다 — 금액만 보고는 알 수 없다.
  const src = $("#csrc");
  if (src) {
    src.textContent = _fromSheet ? "공용 시트의 수당율" : "앱에 든 기본 수당율";
    src.className = "synced" + (_fromSheet ? "" : " warnsrc");
  }
}

function paintCars() {
  const el = $("#ccars");
  if (!el) return;
  const all = items();
  if (!all.length) {
    render(el, html`<li class="empty">차종이 없습니다.</li>`);
    return;
  }
  const q = (_q || "").trim();
  const rows = all.map((it, i) => [it, i])
    .filter(([it]) => !q || hangul.matches(it[0], q));
  if (!rows.length) { render(el, html`<li class="empty">그런 차종이 없습니다.</li>`); return; }
  render(el, rows.map(([[name, rate, truck], i]) =>
    html`<li><button class="row carrow" data-i="${i}"
        aria-pressed="${String(i === _pick)}">
        <span class="t">${name}</span>
        <span class="s">${String(rate)}% · ${truck ? "화물차" : "승용차"}</span>
      </button></li>`).join(""));
  for (const b of $$("#ccars button")) {
    b.onclick = () => { _pick = Number(b.dataset.i); paintCars(); recalc(); };
  }
}

function num(s, def = 0) {
  const t = String(s || "").replace(/,/g, "").trim();
  const v = parseFloat(t);
  return isFinite(v) ? v : def;
}

function recalc() {
  const res = $("#cres");
  if (!res) return;
  const it = picked();
  const rate = it ? it[1] : 0;
  const truck = it ? it[2] : false;
  const won = cm.calc(num(_price), rate, truck, num(_pay, cm.DEF_PAY_RATE), _free);
  res.textContent = "₩ " + won.toLocaleString("ko-KR");
  const r = $("#crate");
  if (r) {
    r.textContent = it
      ? `${it[0]} · 수당율 ${it[1]}% · ${truck ? "화물차" : "승용차"} 기준`
      + (_free ? " · 면세" : "")
      : "차종을 골라 주세요";
  }
}

function copy() {
  const it = picked();
  const won = cm.calc(num(_price), it ? it[1] : 0, it ? it[2] : false,
                      num(_pay, cm.DEF_PAY_RATE), _free);
  const text = [
    it ? `${cm.BRAND_NAMES[_brand]} ${it[0]}` : cm.BRAND_NAMES[_brand],
    `차량가 ${fmt.fmtMoney(_price) || "0"}원`,
    it ? `수당율 ${it[1]}% (${it[2] ? "화물차" : "승용차"})` : "",
    `지급율 ${num(_pay, cm.DEF_PAY_RATE)}%`,
    _free ? "면세 차량" : "",
    `최종 지급수수료 ${won.toLocaleString("ko-KR")}원`,
  ].filter(Boolean).join("\n");
  const b = $("#ccopy");
  navigator.clipboard.writeText(text).then(() => {
    b.textContent = "복사됐습니다 ✓";
    b.classList.add("done");
    setTimeout(() => { b.textContent = "결과 복사"; b.classList.remove("done"); }, 1600);
  }).catch(() => { b.textContent = "복사 실패"; });
}
