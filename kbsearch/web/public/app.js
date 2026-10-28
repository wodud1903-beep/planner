// 업무자료검색 웹 — 회사 공통 자료를 로그인 없이 검색(읽기 전용) + 관리자 서버 on/off.
// 검색·본문 모양은 일정관리기 폰 웹앱의 kb.js · hangul.js 를 그대로 쓴다(초성 검색 포함).
//
// 첫 화면을 빨리:
//   · 자료 받기는 index.html 머리의 짧은 스크립트가 이미 시작해 두었다(window.__boot).
//   · 이 브라우저가 전에 받아 둔 자료가 있으면 그것부터 바로 그리고, 새 자료가 오면 바꾼다.
//   · 처음이면 목록 모양의 빈 자리(skeleton)를 먼저 보여 준다.
import * as kb from "./kb.js";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const CACHE_KEY = "kbsearch:items:v1";
const SEARCH_DELAY = 120;          // PC 와 같다 — 타자가 멎으면 한 번 찾는다
const COLORS = { "심사서류": "violet", "캐피탈": "blue", "전자약정": "green",
                 "연락처": "orange", "진행절차": "pink", "기타": "gray" };
const colorOf = (cat) => "c-" + (COLORS[cat] || "gray");
const initial = (cat) => (cat || "자").trim().charAt(0) || "자";

let items = [], idx = [], q = "", cat = "", cur = -1, timer = 0;

// ------------------------------------------------------------------ 브라우저에 받아 둔 자료
function readCache() {
  try {
    const o = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
    return o && Array.isArray(o.items) && o.items.length ? o : null;
  } catch (e) { return null; }
}
function writeCache(list, at) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ items: list, at })); } catch (e) { /* 꽉 참·막힘 */ }
}
function dropCache() {
  try { localStorage.removeItem(CACHE_KEY); } catch (e) { /* 무시 */ }
}

// ------------------------------------------------------------------ 자료 받기
const timeText = (iso) => {
  const t = iso ? new Date(iso) : null;
  return t && !isNaN(t) ? t.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }) : "";
};
function setFoot(text, kind = "") {
  $("#foot").className = "foot" + (kind ? " " + kind : "");
  $("#foot-text").textContent = text;
}

function setItems(list, at, fromCache) {
  const painted = items.length > 0;
  const same = painted && JSON.stringify(list) === JSON.stringify(items);
  // 보던 자료는 새 목록에서도 제목으로 다시 찾는다(바꾸기 **전에** 적어 둔다)
  const keep = cur >= 0 ? (items[cur] || {}).title : decodeURIComponent(location.hash.slice(1));
  items = list;
  idx = kb.index(items);
  const t = timeText(at);
  setFoot(`회사 공통 자료 ${items.length}건` + (fromCache ? " · 새로 받는 중…" : t ? ` · ${t} 받음` : ""),
          fromCache ? "" : "live");
  if (same) return;                        // 받아 둔 것과 같으면 화면을 다시 그리지 않는다
  cur = -1;
  paintCats();
  paintList();
  if (keep) {
    const i = items.findIndex((it) => it.title === keep);
    if (i >= 0) show(i, false);
  }
}

async function load(boot) {
  const p = boot || {
    kb: fetch("/api/kb").then((r) => r.json().catch(() => ({})).then((j) => ({ status: r.status, j })))
      .catch(() => ({ status: 0, j: {} })),
    st: fetch("/api/status").then((r) => r.json()).catch(() => null),
  };
  const [res, st] = await Promise.all([p.kb, p.st]);
  if ((st && st.on === false) || (res.status === 503 && res.j.off)) {
    dropCache();
    return showOff((st && st.on === false ? st.message : res.j.message) || "");
  }
  if (res.status !== 200 || !Array.isArray(res.j.items)) {
    if (!items.length) paintList();
    setFoot(res.status === 0 ? "인터넷 연결을 확인해 주세요." : (res.j.error || "자료를 받지 못했습니다."), "bad");
    return;
  }
  showOn();
  writeCache(res.j.items, res.j.at);
  setItems(res.j.items, res.j.at, false);
}

function showOff(message) {
  $("#split").hidden = true;
  $("#off").hidden = false;
  $("#off-msg").textContent = message;
}
function showOn() {
  $("#split").hidden = false;
  $("#off").hidden = true;
}

// ------------------------------------------------------------------ 목록
function paintSkeleton() {
  $("#list").innerHTML = Array.from({ length: 8 }, () =>
    '<li class="sk" aria-hidden="true"><span class="a"></span><span style="flex:1"><span class="b" style="display:block"></span><span class="c" style="display:block"></span></span></li>').join("");
}

function paintCats() {
  const count = (c) => items.filter((it) => (it.category || "") === c).length;
  const used = kb.CATEGORIES.filter((c) => count(c));
  const extra = [...new Set(items.map((it) => it.category || "").filter((c) => c && !used.includes(c)))];
  const cats = ["", ...used, ...extra];
  $("#cats").innerHTML = cats.map((c) =>
    `<button type="button" data-cat="${esc(c)}" aria-pressed="${c === cat}">${esc(c || "전체")}`
    + `<span class="n">${c ? count(c) : items.length}</span></button>`).join("");
  for (const b of $("#cats").querySelectorAll("button")) {
    b.onclick = () => { cat = b.dataset.cat; paintCats(); paintList(); };
  }
}

function paintList() {
  const el = $("#list");
  if (!items.length) {
    el.innerHTML = '<li class="empty-row">자료가 없습니다.</li>';
    return;
  }
  const hits = kb.search(idx, q, cat);
  if (!hits.length) {
    el.innerHTML = '<li class="empty-row">찾는 자료가 없습니다.<br>다른 말이나 초성으로 찾아 보세요.</li>';
    return;
  }
  el.innerHTML = hits.map((it) => {
    const i = items.indexOf(it);
    const fin = (it.finance || "").trim() === (it.title || "").trim() ? "" : it.finance;
    const sub = [fin, it.category].filter(Boolean).join(" · ");
    const clip = (it.files || []).length
      ? '<span class="clip" title="첨부 있음"><svg viewBox="0 0 24 24"><path d="M20 11.5 12.2 19.3a5 5 0 0 1-7.1-7.1l8.1-8.1a3.3 3.3 0 0 1 4.7 4.7l-8 8a1.7 1.7 0 0 1-2.4-2.4l7.3-7.3"/></svg></span>'
      : "";
    return `<li><button type="button" class="row" data-i="${i}" aria-current="${i === cur}">
      <span class="av ${colorOf(it.category)}" aria-hidden="true">${esc(initial(it.category))}</span>
      <span class="tx"><span class="t">${esc(it.title)}</span>${sub ? `<span class="s">${esc(sub)}</span>` : ""}</span>
      ${clip}</button></li>`;
  }).join("");
  for (const b of el.querySelectorAll("button.row")) b.onclick = () => show(+b.dataset.i, true);
}

// ------------------------------------------------------------------ 내용
const thumb = (id) => `https://drive.google.com/thumbnail?id=${encodeURIComponent(id)}&sz=w800`;
const view = (id) => `https://drive.google.com/file/d/${encodeURIComponent(id)}/view`;
const down = (id) => `https://drive.google.com/uc?export=download&id=${encodeURIComponent(id)}`;
const isPdf = (f) => /\.pdf$/i.test(f.name || "") || /pdf/.test(f.mime || "");
const COPY_ICON = '<svg viewBox="0 0 24 24"><rect x="8.5" y="8.5" width="11" height="11" rx="2.5"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/></svg>';
const CHECK_ICON = '<svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';

function show(i, push) {
  const it = items[i];
  if (!it) return;
  cur = i;
  for (const b of document.querySelectorAll("#list button.row")) {
    b.setAttribute("aria-current", String(+b.dataset.i === i));
  }
  const fin = (it.finance || "").trim() === (it.title || "").trim() ? "" : it.finance;
  const files = it.files || [];
  $("#detail").innerHTML = `
    <button type="button" class="btn ghost small backbtn" id="back">← 목록</button>
    <div class="dhead">
      <span class="av ${colorOf(it.category)}" aria-hidden="true">${esc(initial(it.category))}</span>
      <div>
        <h2>${esc(it.title)}</h2>
        <div class="tags">
          ${it.category ? `<span class="tag ${colorOf(it.category)}">${esc(it.category)}</span>` : ""}
          ${fin ? `<span class="tag plain">${esc(fin)}</span>` : ""}
          <span class="tag plain">회사 공통</span>
        </div>
      </div>
    </div>
    ${kb.bodyToHtml(it.body || "")}
    <div class="actions">
      <button type="button" class="btn primary" id="copy" ${(it.body || "").trim() ? "" : "disabled"}>${COPY_ICON}<span>본문 복사</span></button>
    </div>
    ${files.length ? `<p class="sec">첨부 <span class="n">${files.length}</span></p><div class="atts">${files.map((f) => `
      <div class="att">
        <a class="thumb" href="${view(f.id)}" target="_blank" rel="noopener" aria-label="${esc(f.name)} 크게 보기">
          ${isPdf(f) ? '<span class="pdf"><span>PDF</span></span>' : `<img src="${thumb(f.id)}" alt="${esc(f.name)}" loading="lazy" decoding="async">`}
        </a>
        <span class="name">${esc(f.name)}</span>
        <span class="links"><a href="${view(f.id)}" target="_blank" rel="noopener">크게 보기</a>
          <a href="${down(f.id)}" target="_blank" rel="noopener">내려받기</a></span>
      </div>`).join("")}</div>` : ""}`;
  $("#split").classList.add("detail");
  $("#detail").scrollTop = 0;
  const copy = $("#copy");
  copy.onclick = async () => {
    let done = false;
    try { await navigator.clipboard.writeText(it.body || ""); done = true; } catch (e) { done = false; }
    copy.classList.toggle("done", done);
    copy.innerHTML = done ? `${CHECK_ICON}<span>복사했습니다</span>` : "<span>복사하지 못했습니다</span>";
    setTimeout(() => { copy.classList.remove("done"); copy.innerHTML = `${COPY_ICON}<span>본문 복사</span>`; }, 1400);
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
// '/' 로 검색칸 — 다른 칸에 쓰는 중이면 그대로 둔다
document.addEventListener("keydown", (e) => {
  if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
  if ($("#admin").open) return;
  e.preventDefault();
  $("#q").focus();
  $("#q").select();
});

// ------------------------------------------------------------------ 관리자 — 서버 on/off
const dlg = $("#admin");
let pw = "";

function paintState(s) {
  const el = $("#admin-state");
  const when = s.at ? new Date(s.at).toLocaleString("ko-KR") : "";
  el.className = "state " + (s.on ? "on" : "off");
  el.innerHTML = "<div>" + (s.on ? "지금 켜져 있습니다" : "지금 꺼져 있습니다")
    + (when ? `<small>마지막으로 바꾼 때 ${esc(when)}</small>` : "")
    + (s.store === false ? "<small>⚠️ 스위치 저장소(Vercel Blob)가 아직 연결되지 않았습니다 — 켜고 끌 수 없습니다.</small>" : "")
    + "</div>";
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
  if ($("#admin-login").hidden) return;
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
});

async function flip(on) {
  if (!on && !confirm("서버를 끌까요?\n웹페이지와 직원 PC 의 업무자료검색이 멈춥니다.")) return;
  $("#admin-err2").textContent = "";
  $("#btn-on").disabled = $("#btn-off").disabled = true;
  try {
    const s = await callSwitch({ on, message: $("#offmsg").value });
    paintState(s);
    if (on) { showOn(); load(); } else { dropCache(); showOff(s.message); }
  } catch (err) {
    $("#admin-err2").textContent = err.message;
    $("#btn-on").disabled = $("#btn-off").disabled = false;
  }
}
$("#btn-off").onclick = () => flip(false);
$("#btn-on").onclick = () => flip(true);

// ------------------------------------------------------------------ 시작
const cached = readCache();
if (cached) setItems(cached.items, cached.at, true);
else paintSkeleton();
load(window.__boot);
