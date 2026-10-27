// 업무자료검색 웹 — 회사 공통 자료를 로그인 없이 검색(읽기 전용) + 관리자 서버 on/off.
// 검색·본문 모양은 일정관리기 폰 웹앱의 kb.js · hangul.js 를 그대로 쓴다(초성 검색 포함).
import * as kb from "./kb.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let items = [], idx = [], q = "", cat = "", cur = -1, timer = 0;
const SEARCH_DELAY = 120;          // PC 와 같다 — 타자가 멎으면 한 번 찾는다

// ------------------------------------------------------------------ 자료 받기
async function load() {
  $("#foot").textContent = "자료를 받는 중…";
  let r;
  try {
    r = await fetch("/api/kb", { cache: "no-store" });
  } catch (e) {
    $("#foot").textContent = "인터넷 연결을 확인해 주세요.";
    return;
  }
  const j = await r.json().catch(() => ({}));
  if (r.status === 503 && j.off) return showOff(j.message);
  if (!r.ok) {
    $("#foot").textContent = j.error || "자료를 받지 못했습니다.";
    return;
  }
  showOn();
  items = j.items || [];
  idx = kb.index(items);
  const t = j.at ? new Date(j.at) : null;
  $("#foot").textContent = `회사 공통 자료 ${items.length}건`
    + (t ? ` · ${t.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })} 받음` : "");
  paintCats();
  paintList();
  const want = decodeURIComponent(location.hash.slice(1));
  if (want) {
    const i = items.findIndex((it) => it.title === want);
    if (i >= 0) show(i, false);
  }
}

function showOff(message) {
  $("#split").hidden = true;
  $("#off").hidden = false;
  $("#off-msg").textContent = message || "";
}
function showOn() {
  $("#split").hidden = false;
  $("#off").hidden = true;
}

// ------------------------------------------------------------------ 목록
function paintCats() {
  const used = kb.CATEGORIES.filter((c) => items.some((it) => (it.category || "") === c));
  const extra = [...new Set(items.map((it) => it.category || "").filter((c) => c && !used.includes(c)))];
  const cats = ["", ...used, ...extra];
  $("#cats").innerHTML = cats.map((c) =>
    `<button type="button" data-cat="${esc(c)}" aria-pressed="${c === cat}">${esc(c || "전체")}</button>`).join("");
  for (const b of $("#cats").querySelectorAll("button")) {
    b.onclick = () => { cat = b.dataset.cat; paintCats(); paintList(); };
  }
}

function paintList() {
  const hits = kb.search(idx, q, cat);
  const el = $("#list");
  if (!hits.length) {
    el.innerHTML = `<li class="empty">${items.length ? "찾는 자료가 없습니다." : "자료가 없습니다."}</li>`;
    return;
  }
  el.innerHTML = hits.map((it) => {
    const i = items.indexOf(it);
    const fin = (it.finance || "").trim() === (it.title || "").trim() ? "" : it.finance;
    const sub = [fin, it.category].filter(Boolean).join(" · ");
    return `<li><button type="button" class="row" data-i="${i}" aria-current="${i === cur}">
      ${esc(it.title)}${sub ? `<span class="s">${esc(sub)}</span>` : ""}</button></li>`;
  }).join("");
  for (const b of el.querySelectorAll("button.row")) b.onclick = () => show(+b.dataset.i, true);
}

// ------------------------------------------------------------------ 내용
const thumb = (id) => `https://drive.google.com/thumbnail?id=${encodeURIComponent(id)}&sz=w800`;
const view = (id) => `https://drive.google.com/file/d/${encodeURIComponent(id)}/view`;
const down = (id) => `https://drive.google.com/uc?export=download&id=${encodeURIComponent(id)}`;
const isPdf = (f) => /\.pdf$/i.test(f.name || "") || /pdf/.test(f.mime || "");

function show(i, push) {
  const it = items[i];
  if (!it) return;
  cur = i;
  for (const b of document.querySelectorAll("#list button.row")) {
    b.setAttribute("aria-current", String(+b.dataset.i === i));
  }
  const fin = (it.finance || "").trim() === (it.title || "").trim() ? "" : it.finance;
  const meta = [fin, it.category].filter(Boolean).join(" · ");
  const files = it.files || [];
  $("#detail").innerHTML = `
    <button type="button" class="ghost backbtn" id="back">← 목록</button>
    <h2>${esc(it.title)}<span class="badge">공통</span></h2>
    ${meta ? `<p class="meta">${esc(meta)}</p>` : '<p class="meta"></p>'}
    ${kb.bodyToHtml(it.body || "")}
    <div class="actions">
      <button type="button" class="primary" id="copy" ${(it.body || "").trim() ? "" : "disabled"}>본문 복사</button>
    </div>
    ${files.length ? `<p class="kbhead">첨부 (${files.length})</p><div class="atts">${files.map((f) => `
      <div class="att">
        <a class="thumb" href="${view(f.id)}" target="_blank" rel="noopener" aria-label="${esc(f.name)} 크게 보기">
          ${isPdf(f) ? '<span class="pdf">PDF</span>' : `<img src="${thumb(f.id)}" alt="${esc(f.name)}" loading="lazy">`}
        </a>
        <span class="name">${esc(f.name)}</span>
        <span class="links"><a href="${view(f.id)}" target="_blank" rel="noopener">크게 보기</a>
          <a href="${down(f.id)}" target="_blank" rel="noopener">내려받기</a></span>
      </div>`).join("")}</div>` : ""}`;
  $("#split").classList.add("detail");
  $("#detail").scrollTop = 0;
  const copy = $("#copy");
  copy.onclick = async () => {
    try {
      await navigator.clipboard.writeText(it.body || "");
      copy.textContent = "복사됨 ✓";
    } catch (e) {
      copy.textContent = "복사 실패";
    }
    setTimeout(() => { copy.textContent = "본문 복사"; }, 1300);
  };
  $("#back").onclick = () => history.back();
  if (push) history.pushState({ i }, "", "#" + encodeURIComponent(it.title));
}

window.addEventListener("popstate", () => {
  const want = decodeURIComponent(location.hash.slice(1));
  const i = want ? items.findIndex((it) => it.title === want) : -1;
  if (i >= 0) show(i, false);
  else $("#split").classList.remove("detail");
});

$("#q").addEventListener("input", (e) => {
  clearTimeout(timer);
  timer = setTimeout(() => { q = e.target.value; paintList(); }, SEARCH_DELAY);
});
$("#q").addEventListener("compositionend", (e) => { clearTimeout(timer); q = e.target.value; paintList(); });
$("#q").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const first = $("#list button.row");
    if (first) first.click();
  }
});

// ------------------------------------------------------------------ 관리자 — 서버 on/off
const dlg = $("#admin");
let pw = "";

function paintState(s) {
  const el = $("#admin-state");
  const when = s.at ? new Date(s.at).toLocaleString("ko-KR") : "";
  el.className = "state " + (s.on ? "on" : "off");
  el.innerHTML = (s.on ? "지금 켜져 있습니다" : "지금 꺼져 있습니다")
    + (when ? `<small>마지막으로 바꾼 때 ${esc(when)}</small>` : "")
    + (s.store === false ? "<small>⚠️ 스위치 저장소가 아직 연결되지 않았습니다 — 켜고 끌 수 없습니다.</small>" : "");
  $("#btn-off").disabled = !s.on || s.store === false;
  $("#btn-on").disabled = s.on || s.store === false;
  if (!s.on && s.message) $("#offmsg").value = s.message;
}

async function callSwitch(payload) {
  const r = await fetch("/api/switch", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: pw, ...payload }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `실패했습니다 (${r.status})`);
  return j;
}

$("#btn-admin").onclick = () => {
  $("#admin-login").hidden = false;
  $("#admin-panel").hidden = true;
  $("#admin-err").textContent = "";
  $("#pw").value = "";
  dlg.showModal();
  $("#pw").focus();
};
$("#admin-cancel").onclick = $("#admin-close").onclick = () => { pw = ""; dlg.close(); };
$("#admin-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!$("#admin-login").hidden) {
    pw = $("#pw").value;
    $("#admin-go").disabled = true;
    $("#admin-err").textContent = "";
    try {
      const s = await callSwitch({});
      $("#admin-login").hidden = true;
      $("#admin-panel").hidden = false;
      $("#offmsg").value = "업무자료검색 서비스가 종료되었습니다.\n그동안 이용해 주셔서 감사합니다.";
      paintState(s);
    } catch (err) {
      $("#admin-err").textContent = err.message;
    } finally {
      $("#admin-go").disabled = false;
    }
  }
});

async function flip(on) {
  if (!on && !confirm("서버를 끌까요?\n웹페이지와 직원 PC 의 업무자료검색이 멈춥니다.")) return;
  $("#admin-err2").textContent = "";
  $("#btn-on").disabled = $("#btn-off").disabled = true;
  try {
    const s = await callSwitch({ on, message: $("#offmsg").value });
    paintState(s);
    if (on) load(); else showOff(s.message);
  } catch (err) {
    $("#admin-err2").textContent = err.message;
    $("#btn-on").disabled = $("#btn-off").disabled = false;
  }
}
$("#btn-off").onclick = () => flip(false);
$("#btn-on").onclick = () => flip(true);

load();
