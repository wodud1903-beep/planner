// 업무자료검색 웹 — 회사 공통 자료를 로그인 없이 검색 + 관리자 서버 on/off.
// 공통 자료를 **이 기기에서만** 고칠 수 있다(팩스번호·내 연락처 등 — PC 의 '이 PC 에서 고침' 과 같다).
// 폰: 홈 화면에 앱으로 설치(sw.js — 인터넷이 끊겨도 받아 둔 자료) · [카톡으로 보내기] ·
//     구글 로그인하면 PC·일정관리기의 '내 메모' 도 본다(보기만).
// 검색·본문 모양은 일정관리기 폰 웹앱의 kb.js · hangul.js 를 그대로 쓴다(초성 검색 포함).
//
// 첫 화면을 빨리:
//   · 자료 받기는 index.html 머리의 짧은 스크립트가 이미 시작해 두었다(window.__boot).
//   · 이 브라우저가 전에 받아 둔 자료가 있으면 그것부터 바로 그리고, 새 자료가 오면 바꾼다.
//   · 처음이면 목록 모양의 빈 자리(skeleton)를 먼저 보여 준다.
import * as kb from "./kb.js";
import * as sync from "./sync.js";

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
let shared = [];                   // 받은 회사 원본(고친 것을 덮기 전)

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

// ------------------------------------------------------------------ 이 기기에서만 고친 공통 자료
// 지점장 요청: "PC 버전은 자료수정이 잘 되는데 웹 버전은 안 돼 — 개인적으로 들어가 있는 팩스번호 등".
// PC 프로그램의 kb_local.json('공통 · 이 PC 에서 고침')과 같은 생각이다 — 회사 원본(시트)과 다른
// 사람에게는 가지 않고 **이 브라우저에만** 남는다. 회사 자료를 새로 받아도 그대로 덮어 보여 준다.
// 열쇠는 PC 와 같다 — [제목, 같은 제목 중 몇 번째](kb.shared_keys).
const LOCAL_KEY = "kbsearch:local:v1";
const keyStr = (k) => JSON.stringify(k);

function loadLocal() {
  try {
    const a = JSON.parse(localStorage.getItem(LOCAL_KEY) || "[]");
    return Array.isArray(a) ? a.filter((r) => r && Array.isArray(r.key) && r.key.length === 2
                                              && r.item && typeof r.item === "object") : [];
  } catch (e) { return []; }
}
function saveLocal(recs) {
  try { localStorage.setItem(LOCAL_KEY, JSON.stringify(recs)); return true; } catch (e) { return false; }
}
function sharedKeys(list) {
  const seen = {};
  return list.map((it) => {
    const t = String(it.title || "").trim();
    const n = seen[t] || 0;
    seen[t] = n + 1;
    return [t, n];
  });
}
/** 회사 원본 위에 이 기기에서 고친 것을 덮은 목록. 꼬리표: _key · _local · _base · _stale · _orphan */
function merged(list) {
  const recs = new Map(loadLocal().map((r) => [keyStr(r.key), r]));
  const keys = sharedKeys(list);
  const out = list.map((it, i) => {
    const r = recs.get(keyStr(keys[i]));
    if (!r) return { ...it, _key: keys[i] };
    recs.delete(keyStr(keys[i]));
    const x = { ...it, body: String(r.item.body ?? ""), _key: keys[i], _local: true, _base: it };
    if (r.base && String(r.base.body ?? "") !== String(it.body ?? "")) x._stale = true;   // 회사가 원본을 또 고쳤다
    return x;
  });
  for (const r of recs.values()) {     // 회사 자료에서 없어졌거나 제목이 바뀌었다 — 고친 것은 남긴다
    out.push({ ...r.item, body: String(r.item.body ?? ""), _key: r.key, _local: true, _orphan: true });
  }
  return out;
}
const localCount = () => loadLocal().length;

// 되돌린 세 심사서류 {제목: 시각} — 구글 동기화가 '되돌림' 도 PC 에 전하게(sync.js)
const DEAD_KEY = "kbsearch:dead:v1";
function loadDead() {
  try { const o = JSON.parse(localStorage.getItem(DEAD_KEY) || "{}"); return o && typeof o === "object" ? o : {}; }
  catch (e) { return {}; }
}
function saveDead(o) {
  try { localStorage.setItem(DEAD_KEY, JSON.stringify(o)); return true; } catch (e) { return false; }
}
function markDead(key, on) {
  if (!sync.isSyncKey(key)) return;
  const d = loadDead();
  if (on) d[key[0]] = sync.stamp(); else delete d[key[0]];
  saveDead(d);
}

// ------------------------------------------------------------------ 내 메모(보기만)
// PC 업무자료검색·일정관리기의 '내 메모' — 구글 동기화로 로그인하면 내 드라이브 앱 공간의 동기화
// 묶음에서 메모 칸만 읽어 온다(sync.readMemos). 웹에서는 고치지 않는다 — 그 묶음에 일정관리기
// 할일·고객메모가 함께 있어서 잘못 쓰면 일정관리기 자료가 다친다. 인터넷이 끊겨도 보도록 이
// 브라우저에 받아 두고, 로그아웃하거나 다른 계정으로 바꾸면 지운다.
const MINE_KEY = "kbsearch:mine:v1";
const MINE_CAT = "__mine__";           // 분류 칩 '내 메모'
function readMine() {
  try {
    const o = JSON.parse(localStorage.getItem(MINE_KEY) || "null");
    return o && Array.isArray(o.items) ? o : null;
  } catch (e) { return null; }
}
/** 지금 로그인한 계정의 메모만(받아 둔 것이 다른 계정 것이면 안 보인다). */
function loadMine() {
  const o = readMine();
  return o && o.email && o.email === savedAcct() ? o.items : [];
}
function saveMine(email, list, stamp = "") {
  try { localStorage.setItem(MINE_KEY, JSON.stringify({ email, items: list, stamp, at: Date.now() })); } catch (e) { /* 꽉 참 */ }
}
function dropMine() {
  try { localStorage.removeItem(MINE_KEY); } catch (e) { /* 무시 */ }
}
const mineView = () => loadMine().map((it, i) => ({ ...it, _mine: true, _key: [MINE_CAT, i] }));
/** 화면 목록 — 회사 자료(이 기기에서 고친 것을 덮은) + 내 메모. */
const buildItems = () => merged(shared).concat(mineView());

// 주소 끝(#…)으로 보던 자료를 다시 연다 — 내 메모는 'm:' 를 붙여 같은 제목의 회사 자료와 가른다
const hashOf = (it) => (it._mine ? "m:" : "") + (it.title || "");
function findByHash(h) {
  if (!h) return -1;
  if (h.startsWith("m:")) return items.findIndex((it) => it._mine && it.title === h.slice(2));
  const i = items.findIndex((it) => !it._mine && it.title === h);
  return i >= 0 ? i : items.findIndex((it) => it.title === h);
}

/** 고친 것을 다시 덮어 그리고, 보던 자료를 다시 보여 준다(없어졌으면 첫 화면으로). */
function remerge(key) {
  items = buildItems();
  idx = kb.index(items);
  if (cat === MINE_CAT && !items.some((it) => it._mine)) cat = "";
  paintCats();
  paintList();
  paintFoot();
  const i = key ? items.findIndex((x) => keyStr(x._key) === keyStr(key)) : -1;
  if (i >= 0) show(i, false);
  else if (key) hideDetail();
}

const HELLO = $("#detail").innerHTML;       // 아무것도 안 고른 첫 화면
function hideDetail() {
  cur = -1;
  $("#split").classList.remove("detail");
  $("#detail").innerHTML = HELLO;
}

/** 동기화 뒤 — 고치는 중이면 고치는 칸은 그대로 두고 목록만 새로. */
function rebuild() {
  if ($("#ed-body")) {
    items = buildItems(); idx = kb.index(items); paintCats(); paintList(); paintFoot();
    return;
  }
  remerge(cur >= 0 && items[cur] ? items[cur]._key : null);
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

let footAt = "", footCache = false, footOffline = false;
function paintFoot() {
  const t = timeText(footAt), n = localCount(), m = loadMine().length;
  const tail = footOffline ? ` · 인터넷이 끊겨 받아 둔 자료${t ? `(${t} 받음)` : ""}`
             : footCache ? " · 새로 받는 중…" : t ? ` · ${t} 받음` : "";
  setFoot(`회사 공통 자료 ${shared.length}건` + (m ? ` · 내 메모 ${m}건` : "")
          + (n ? ` · 이 기기에서 고친 것 ${n}건` : "") + tail, footOffline ? "bad" : footCache ? "" : "live");
}

function setItems(list, at, fromCache) {
  const painted = items.length > 0;
  const same = painted && JSON.stringify(list) === JSON.stringify(shared);
  // 보던 자료는 새 목록에서도 제목으로 다시 찾는다(바꾸기 **전에** 적어 둔다)
  const keep = cur >= 0 && items[cur] ? hashOf(items[cur]) : decodeURIComponent(location.hash.slice(1));
  shared = list;
  items = buildItems();
  idx = kb.index(items);
  footAt = at;
  footCache = fromCache;
  paintFoot();
  if (same) return;                        // 받아 둔 것과 같으면 화면을 다시 그리지 않는다
  cur = -1;
  paintCats();
  paintList();
  if (keep) {
    const i = findByHash(keep);
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
    if (res.status === 0 && items.length) {        // 인터넷이 끊겼다 — 받아 둔 자료를 그대로 쓴다
      footOffline = true; footCache = false;
      paintFoot();
      return;
    }
    if (!items.length) paintList();
    setFoot(res.status === 0 ? "인터넷 연결을 확인해 주세요." : (res.j.error || "자료를 받지 못했습니다."), "bad");
    return;
  }
  footOffline = false;
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
  const mineN = items.filter((it) => it._mine).length;
  const used = kb.CATEGORIES.filter((c) => count(c));
  const extra = [...new Set(items.map((it) => it.category || "").filter((c) => c && !used.includes(c)))];
  const cats = ["", ...(mineN ? [MINE_CAT] : []), ...used, ...extra];
  const label = (c) => (c === MINE_CAT ? "내 메모" : c || "전체");
  const num = (c) => (c === MINE_CAT ? mineN : c ? count(c) : items.length);
  $("#cats").innerHTML = cats.map((c) =>
    `<button type="button" data-cat="${esc(c)}" aria-pressed="${c === cat}"${c === MINE_CAT ? ' class="mine"' : ""}>${esc(label(c))}`
    + `<span class="n">${num(c)}</span></button>`).join("");
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
  const hits = cat === MINE_CAT ? kb.search(idx, q, "").filter((it) => it._mine) : kb.search(idx, q, cat);
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
      <span class="tx"><span class="t">${esc(it.title)}</span>${sub || it._mine
        ? `<span class="s">${esc(sub)}${it._mine ? '<i class="minepill">내 메모</i>' : ""}</span>` : ""}</span>
      ${clip}</button></li>`;
  }).join("");
  for (const b of el.querySelectorAll("button.row")) b.onclick = () => show(+b.dataset.i, true);
}

// ------------------------------------------------------------------ 내용
const thumb = (id, w = 800) => `https://drive.google.com/thumbnail?id=${encodeURIComponent(id)}&sz=w${w}`;
const pdfView = (id) => `https://drive.google.com/file/d/${encodeURIComponent(id)}/preview`;
const view = (id) => `https://drive.google.com/file/d/${encodeURIComponent(id)}/view`;
const down = (id) => `https://drive.google.com/uc?export=download&id=${encodeURIComponent(id)}`;
const isPdf = (f) => /\.pdf$/i.test(f.name || "") || /pdf/.test(f.mime || "");
const COPY_ICON = '<svg viewBox="0 0 24 24"><rect x="8.5" y="8.5" width="11" height="11" rx="2.5"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/></svg>';
const EDIT_ICON = '<svg viewBox="0 0 24 24"><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/></svg>';
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
          ${it._mine ? '<span class="tag mine">내 메모</span>'
            : it._local ? `<span class="tag edited">${syncedHere(it) ? "공통 · 내 계정에서 고침" : "공통 · 이 기기에서 고침"}</span>`
            : '<span class="tag plain">회사 공통</span>'}
        </div>
      </div>
    </div>
    ${it._stale ? '<p class="note">고친 뒤에 회사가 이 자료의 원본을 바꿨습니다. 새 원본을 보려면 [회사 자료로 되돌리기] 를 누르세요.</p>' : ""}
    ${it._orphan ? '<p class="note">회사 자료에서 없어졌거나 제목이 바뀐 자료입니다 — 이 기기에서 고친 것만 남아 있습니다.</p>' : ""}
    ${it._mine ? '<p class="note mine">내 메모는 PC 업무자료검색·일정관리기에서 고칩니다. 웹에서는 보기만 합니다.</p>' : ""}
    <div id="bodybox">${kb.bodyToHtml(it.body || "")}</div>
    <div class="actions" id="acts">
      <button type="button" class="btn primary" id="copy" ${(it.body || "").trim() ? "" : "disabled"}>${COPY_ICON}<span>본문 복사</span></button>
      ${canShare() ? `<button type="button" class="btn ghost" id="share" ${(it.body || "").trim() || sendable(it).length ? "" : "disabled"}>${SEND_ICON}<span>카톡으로 보내기</span></button>` : ""}
      ${it._mine ? "" : `<button type="button" class="btn ghost" id="edit">${EDIT_ICON}<span>수정</span></button>`}
      ${it._local ? '<button type="button" class="btn ghost" id="revert">회사 자료로 되돌리기</button>' : ""}
    </div>
    ${files.length ? `<p class="sec">첨부 <span class="n">${files.length}</span></p><div class="atts">${files.map((f, k) => `
      <div class="att">
        <a class="thumb" href="${view(f.id)}" data-k="${k}" target="_blank" rel="noopener" aria-label="${esc(f.name)} 크게 보기">
          ${isPdf(f) ? '<span class="pdf"><span>PDF</span></span>' : `<img src="${thumb(f.id)}" alt="${esc(f.name)}" loading="lazy" decoding="async">`}
        </a>
        <span class="name">${esc(f.name)}</span>
        <span class="links"><a href="${view(f.id)}" data-k="${k}" target="_blank" rel="noopener">크게 보기</a>
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
  if ($("#edit")) $("#edit").onclick = () => startEdit(i);
  if ($("#revert")) $("#revert").onclick = () => revert(i);
  if ($("#share")) $("#share").onclick = () => openShare(it, $("#share"));
  // 그림을 못 받으면(내 메모의 내 드라이브 그림 · 인터넷 끊김) 깨진 그림 대신 이름 자리만
  for (const im of $("#detail").querySelectorAll(".att img")) {
    im.addEventListener("error", () => { im.replaceWith(Object.assign(document.createElement("span"), { className: "noimg", textContent: "그림" })); }, { once: true });
  }
  // 크게 보기는 이 화면 안에서 — 드라이브 새 탭으로 가면 다음 첨부를 보려고 닫았다 열어야 했다
  for (const a of $("#detail").querySelectorAll("a[data-k]")) {
    a.onclick = (e) => {
      if (e.ctrlKey || e.metaKey || e.shiftKey) return;       // 새 탭으로 열려는 뜻이면 그대로
      e.preventDefault();
      openViewer(files, +a.dataset.k);
    };
  }
  if (push) history.pushState({ i }, "", "#" + encodeURIComponent(hashOf(it)));
}

// ------------------------------------------------------------------ 이 기기에서 고치기
function startEdit(i) {
  const it = items[i];
  if (!it || it._mine) return;
  $("#bodybox").innerHTML = `
    <div class="editor">
      <label for="ed-body">본문 — 팩스번호·내 연락처처럼 나에게 맞게 고쳐 쓰세요</label>
      <textarea id="ed-body" rows="14" spellcheck="false"></textarea>
      <p class="hint">${esc(editHint(it))}</p>
    </div>`;
  const ta = $("#ed-body");
  ta.value = it.body || "";
  ta.style.height = Math.min(560, Math.max(260, ta.scrollHeight + 8)) + "px";
  $("#acts").innerHTML = `
    <button type="button" class="btn primary" id="ed-save">${CHECK_ICON}<span>저장</span></button>
    <button type="button" class="btn ghost" id="ed-cancel">취소</button>`;
  $("#ed-cancel").onclick = () => remerge(it._key);
  $("#ed-save").onclick = () => saveEdit(it, ta.value);
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); remerge(it._key); }
    else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); saveEdit(it, ta.value); }
  });
  ta.focus();
}

function saveEdit(it, text) {
  if (!it || it._mine) return;
  const body = String(text || "").replace(/\r\n?/g, "\n").split("\n").map((l) => l.trimEnd()).join("\n").trim();
  const recs = loadLocal();
  const k = keyStr(it._key);
  const prev = recs.find((r) => keyStr(r.key) === k);
  const rest = recs.filter((r) => keyStr(r.key) !== k);
  const base = it._orphan ? (prev && prev.base) || null : (it._local ? it._base : it);
  let reverted = false;
  if (!it._orphan && body === String((base || {}).body || "").trim()) {
    // 회사 원본과 같아졌다 — 고친 것을 지운다(= 회사 자료로 되돌림)
    reverted = !!prev;
  } else {
    const keepItem = {};
    for (const f of ["category", "finance", "title", "tags", "files"]) if (it[f] !== undefined) keepItem[f] = it[f];
    rest.push({ key: it._key, base: base ? { title: base.title || "", body: String(base.body || "") } : null,
                item: { ...keepItem, body }, at: sync.stamp() });
  }
  if (!saveLocal(rest)) {
    alert("저장하지 못했습니다 — 이 브라우저의 저장 공간을 쓸 수 없습니다(사생활 보호 창 등).");
    return;
  }
  if (reverted) markDead(it._key, true);
  else if (rest.length > recs.length - (prev ? 1 : 0)) markDead(it._key, false);   // 새로 고친 것을 남겼다
  remerge(it._key);
  if (sync.isSyncKey(it._key)) soonSync();
}

function revert(i) {
  const it = items[i];
  if (!it || !it._local) return;
  if (!confirm(it._orphan ? "이 기기에서 고친 자료를 지울까요?\n(회사 자료에서는 이미 없어진 자료입니다)"
                          : "이 기기에서 고친 것을 지우고 회사 자료로 되돌릴까요?")) return;
  saveLocal(loadLocal().filter((r) => keyStr(r.key) !== keyStr(it._key)));
  markDead(it._key, true);
  if (sync.isSyncKey(it._key)) soonSync();
  if (it._orphan) {
    items = buildItems(); idx = kb.index(items); paintCats(); paintList(); paintFoot();
    $("#split").classList.remove("detail");
    $("#detail").innerHTML = '<div class="hello"><h2>지웠습니다</h2><p>왼쪽 목록에서 다른 자료를 골라 주세요.</p></div>';
    cur = -1;
    return;
  }
  remerge(it._key);
}

// ------------------------------------------------------------------ 카톡으로 보내기
// 폰의 '보내기' 화면(Web Share)을 연다 — 거기서 카카오톡을 고르면 된다. 글 · 그림 · PDF 는 따로 보낸다
// (섞어서 넘기면 카톡이 보내기 목록에 안 뜨거나 하나만 받는 일이 있다). 첨부는 이 주소의 /api/file 이 회사
// 첨부만 받아 준다(구글 드라이브 파일은 브라우저가 바로 못 받는다). 4MB 가 넘는 PDF 처럼 파일로 못
// 보내는 첨부는 링크로 보낸다. 내 메모의 첨부는 내 드라이브에만 있어 보내지 않는다(받는 사람이 못 연다).
const SEND_ICON = '<svg viewBox="0 0 24 24"><path d="M21 3 10.5 13.5"/><path d="M21 3l-6.5 18-4-7.5L3 9.5 21 3Z"/></svg>';
const FILE_MAX = 4 * 1024 * 1024;
// 폰·태블릿에서만 — 컴퓨터의 공유 창에는 카톡이 없을 수 있다(컴퓨터는 PC 프로그램 · [본문 복사])
const canShare = () => typeof navigator.share === "function" && matchMedia("(pointer: coarse)").matches;
const sendable = (it) => (it && !it._mine ? it.files || [] : []);
const shdlg = $("#sharedlg");
let shareItem = null, shareReady = null;

function fileName(f, type) {
  const base = String(f.name || "첨부").replace(/[\\/:*?"<>|]+/g, "_");
  const ext = { "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
                "application/pdf": ".pdf" }[type];
  if (!ext) return base;
  return /\.[a-z0-9]{2,5}$/i.test(base) ? base.replace(/\.[a-z0-9]{2,5}$/i, ext) : base + ext;
}

/** 첨부를 파일로 받아 둔다 → {imgs: 그림 파일, pdfs: PDF 파일, left: 파일로 못 보내 링크로 보낼 첨부} */
async function prepFiles(list) {
  const got = await Promise.all(list.map(async (f) => {
    if (isPdf(f) && f.size > FILE_MAX) return { f, file: null };
    try {
      const r = await fetch(`/api/file?id=${encodeURIComponent(f.id)}`);
      if (!r.ok) return { f, file: null };
      const blob = await r.blob();
      if (!blob.size || blob.size > FILE_MAX) return { f, file: null };
      const type = blob.type || f.mime || "application/octet-stream";
      return { f, file: new File([blob], fileName(f, type), { type }) };
    } catch (e) { return { f, file: null }; }
  }));
  const ok = (files) => files.length && (typeof navigator.canShare !== "function" || navigator.canShare({ files }));
  let imgs = got.filter((x) => x.file && x.file.type.startsWith("image/"));
  let pdfs = got.filter((x) => x.file && !x.file.type.startsWith("image/"));
  const left = got.filter((x) => !x.file).map((x) => x.f);
  // 이 폰이 파일 보내기를 못 하면 그 묶음은 링크로
  if (imgs.length && !ok(imgs.map((x) => x.file))) { left.push(...imgs.map((x) => x.f)); imgs = []; }
  if (pdfs.length && !ok(pdfs.map((x) => x.file))) { left.push(...pdfs.map((x) => x.f)); pdfs = []; }
  return { imgs: imgs.map((x) => x.file), pdfs: pdfs.map((x) => x.file), left };
}

const names = (files) => {
  const n = files.map((f) => f.name);
  return n.length > 2 ? `${n.slice(0, 2).join(", ")} 외 ${n.length - 2}개` : n.join(", ");
};
const linksText = (files) => files.map((f) => `${f.name}\n${view(f.id)}`).join("\n\n");

function flash(btn, text) {
  const html = btn.innerHTML;
  btn.innerHTML = `<span>${esc(text)}</span>`;
  setTimeout(() => { btn.innerHTML = html; }, 1600);
}

/** [카톡으로 보내기] — 첨부가 없으면 바로 글을, 있으면 무엇을 보낼지 고르는 창을 연다. */
function openShare(it, btn) {
  const files = sendable(it);
  const body = String(it.body || "").trim();
  if (!files.length) {
    navigator.share({ text: body }).catch((e) => {
      if (!e || e.name !== "AbortError") flash(btn, "보내지 못했습니다");
    });
    return;
  }
  shareItem = it;
  shareReady = null;
  const nImg = files.filter((f) => !isPdf(f)).length, nPdf = files.length - nImg;
  $("#share-err").textContent = "";
  $("#share-text").disabled = !body;
  $("#share-text-sub").textContent = body ? "서류 목록·팩스번호 등 글" : "본문이 없습니다";
  $("#share-imgs").hidden = !nImg;
  $("#share-imgs").disabled = true;
  $("#share-imgs-title").textContent = `그림 ${nImg}장 보내기`;
  $("#share-imgs-sub").textContent = "준비 중…";
  $("#share-pdfs").hidden = !nPdf;
  $("#share-pdfs").disabled = true;
  $("#share-pdfs-title").textContent = `PDF ${nPdf}개 보내기`;
  $("#share-pdfs-sub").textContent = "준비 중…";
  $("#share-links").hidden = true;
  if (!shdlg.open) shdlg.showModal();
  prepFiles(files).then((p) => {
    if (shareItem !== it) return;                // 그새 다른 자료를 열었다
    shareReady = p;
    for (const [kind, got, n, unit] of [["imgs", p.imgs, nImg, "장"], ["pdfs", p.pdfs, nPdf, "개"]]) {
      if (!n) continue;
      $(`#share-${kind}`).disabled = !got.length;
      $(`#share-${kind}-title`).textContent = `${kind === "imgs" ? "그림" : "PDF"} ${got.length || n}${unit} 보내기`;
      $(`#share-${kind}-sub`).textContent = got.length ? names(got) : "파일로 못 보냅니다 — 아래 링크로 보내세요";
    }
    if (p.left.length) {
      $("#share-links").hidden = false;
      $("#share-links-sub").textContent = `${p.left.length}개 — 커서 파일로 못 보내는 첨부 등(받는 사람이 눌러서 엽니다)`;
    }
  });
}

/** 창 안의 단추 — 보내기 화면을 연다. 취소하면 창은 그대로(다른 것을 고를 수 있게). */
async function sendFromDialog(data) {
  $("#share-err").textContent = "";
  try {
    await navigator.share(data);
    shdlg.close();
  } catch (e) {
    if (e && e.name === "AbortError") return;
    $("#share-err").textContent = e && e.name === "NotAllowedError"
      ? "폰이 막았습니다 — 한 번 더 눌러 주세요." : "보내지 못했습니다 — " + ((e && e.message) || e);
  }
}
$("#share-text").onclick = () => shareItem && sendFromDialog({ text: String(shareItem.body || "").trim() });
$("#share-imgs").onclick = () => shareReady && shareReady.imgs.length && sendFromDialog({ files: shareReady.imgs });
$("#share-pdfs").onclick = () => shareReady && shareReady.pdfs.length && sendFromDialog({ files: shareReady.pdfs });
$("#share-links").onclick = () => shareReady && shareReady.left.length && sendFromDialog({ text: linksText(shareReady.left) });
$("#share-close").onclick = () => shdlg.close();
shdlg.addEventListener("click", (e) => { if (e.target === shdlg) shdlg.close(); });
shdlg.addEventListener("close", () => { shareItem = null; shareReady = null; });

// ------------------------------------------------------------------ 첨부 크게 보기
// ◀ ▶ 단추 · 키보드 ← → · 폰은 옆으로 밀어서 같은 자료의 다른 첨부로 넘긴다. Esc 로 닫는다.
const vdlg = $("#viewer");
let vfiles = [], vk = 0;

function openViewer(files, k) {
  vfiles = files;
  if (!vdlg.open) vdlg.showModal();
  viewAt(k);
}

function viewAt(k) {
  if (k < 0 || k >= vfiles.length) return;
  vk = k;
  const f = vfiles[k];
  $("#v-name").textContent = f.name;
  $("#v-count").textContent = vfiles.length > 1 ? `${k + 1} / ${vfiles.length}` : "";
  $("#v-open").href = view(f.id);
  $("#v-down").href = down(f.id);
  $("#v-prev").hidden = $("#v-next").hidden = vfiles.length < 2;
  $("#v-prev").disabled = k === 0;
  $("#v-next").disabled = k === vfiles.length - 1;
  const stage = $("#v-stage");
  stage.innerHTML = isPdf(f)
    ? `<iframe src="${pdfView(f.id)}" title="${esc(f.name)}" allow="autoplay"></iframe>`
    : `<img src="${thumb(f.id, 2000)}" alt="${esc(f.name)}">`;
  const im = stage.querySelector("img");
  if (im) {
    im.addEventListener("error", () => {
      stage.innerHTML = `<div class="vfail"><p>여기서 그림을 열지 못했습니다.<br>
        (인터넷이 끊겼거나, 내 구글 드라이브에만 있는 그림입니다)</p>
        <a class="btn ghost small" href="${view(f.id)}" target="_blank" rel="noopener">원본 열기</a></div>`;
    }, { once: true });
  }
  // 옆 그림을 미리 받아 둔다 — 넘길 때 기다리지 않게
  for (const n of [vfiles[k + 1], vfiles[k - 1]]) {
    if (n && !isPdf(n)) new Image().src = thumb(n.id, 2000);
  }
  stage.focus({ preventScroll: true });   // PDF 칸이 ← → 를 먹지 않게 창에 둔다
}

$("#v-prev").onclick = () => viewAt(vk - 1);
$("#v-next").onclick = () => viewAt(vk + 1);
$("#v-close").onclick = () => vdlg.close();
vdlg.addEventListener("click", (e) => { if (e.target === vdlg) vdlg.close(); });   // 바깥을 누르면 닫기
vdlg.addEventListener("close", () => { $("#v-stage").innerHTML = ""; });
vdlg.addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft") { e.preventDefault(); viewAt(vk - 1); }
  else if (e.key === "ArrowRight") { e.preventDefault(); viewAt(vk + 1); }
});
let touchX = null;
vdlg.addEventListener("touchstart", (e) => { touchX = e.touches.length === 1 ? e.touches[0].clientX : null; }, { passive: true });
vdlg.addEventListener("touchend", (e) => {
  if (touchX == null) return;
  const dx = e.changedTouches[0].clientX - touchX;
  touchX = null;
  if (Math.abs(dx) > 50) viewAt(vk + (dx < 0 ? 1 : -1));
});

window.addEventListener("popstate", () => {
  const i = findByHash(decodeURIComponent(location.hash.slice(1)));
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
  if ($("#admin").open || vdlg.open || shdlg.open || sdlg.open) return;
  e.preventDefault();
  $("#q").focus();
  $("#q").select();
});

// ------------------------------------------------------------------ 구글 동기화
// 회사 자료에서 나만 고친 것(팩스번호 등)을 같은 구글 계정의 PC 업무자료검색·일정관리기와 맞춘다(sync.js).
// 한 번 로그인하면 이 브라우저는 계속 로그인돼 있다(서버 쿠키). 그 뒤로는 켤 때 · 세 자료를 고칠 때 ·
// 다시 이 창으로 돌아올 때 저절로 맞춘다. [구글 동기화] 를 누르면 바로 맞춘다.
const ACCT_KEY = "kbsearch:acct:v1";          // 마지막으로 동기화한 계정(로그인 여부를 빨리 알려고)
const sdlg = $("#syncdlg");
let syncing = false, syncAgain = false, lastSync = 0, syncMsg = "", syncBad = false, soonTimer = 0;

const savedAcct = () => { try { return localStorage.getItem(ACCT_KEY) || ""; } catch (e) { return ""; } };
const setAcct = (v) => { try { v ? localStorage.setItem(ACCT_KEY, v) : localStorage.removeItem(ACCT_KEY); } catch (e) { /* 무시 */ } };
const signedIn = () => !!(sync.account() || savedAcct());
const syncedHere = (it) => signedIn() && sync.isSyncKey(it._key);

function editHint(it) {
  if (!sync.isSyncKey(it._key)) return "이 기기(이 브라우저)에서만 바뀝니다. 회사 자료와 다른 사람 화면에는 그대로입니다.";
  return signedIn()
    ? `저장하면 내 구글 계정(${sync.account() || savedAcct()})으로 PC 업무자료검색·일정관리기에도 반영됩니다. 회사 자료와 다른 사람 화면은 그대로입니다.`
    : "지금은 이 기기에서만 바뀝니다. 위의 [구글 동기화] 로 로그인하면 같은 계정의 PC 업무자료검색·일정관리기에도 반영됩니다.";
}

function paintSync() {
  const who = sync.account() || savedAcct();
  const b = $("#btn-sync");
  b.classList.toggle("on", !!who);
  b.classList.toggle("busy", syncing);
  b.title = who ? `${who}${lastSync ? " · " + timeText(new Date(lastSync).toISOString()) + " 동기화" : ""}` : "구글 로그인하고 PC 와 맞추기";
  $("#sync-label").textContent = syncing ? "동기화 중…" : "구글 동기화";
  const st = $("#sync-state");
  st.className = "state " + (who ? "on" : "off");
  const nm = loadMine().length;
  st.innerHTML = who
    ? `<div>${esc(who)}<small>${syncing ? "맞추는 중…" : lastSync ? `${esc(timeText(new Date(lastSync).toISOString()))} 에 맞췄습니다` : "로그인돼 있습니다"}`
      + `${nm ? ` · 내 메모 ${nm}건` : ""}</small></div>`
    : "<div>로그인하지 않았습니다<small>PC 업무자료검색에서 쓰는 구글 계정으로 로그인하세요. 로그인하면 내 메모도 보입니다.</small></div>";
  const kakao = !who && inKakao();
  if (kakao) {
    st.innerHTML = "<div>카카오톡 안에서는 구글 로그인이 막혀 있습니다<small>크롬·사파리로 열어 로그인해 주세요.</small></div>";
  }
  $("#sync-err").textContent = syncMsg;
  $("#sync-err").classList.toggle("ok", !!syncMsg && !syncBad);
  $("#sync-go").hidden = !who;
  $("#sync-login").hidden = !!who;
  $("#sync-login").textContent = kakao ? "다른 브라우저로 열기" : "구글 로그인";
  $("#sync-switch").hidden = kakao;
  $("#sync-out").hidden = !who;
  $("#sync-go").disabled = syncing;
}

function login(choose = false) {
  const p = new URLSearchParams();
  const hint = savedAcct();
  if (choose) p.set("prompt", "select_account");
  else if (hint) p.set("hint", hint);
  location.href = "/api/auth/login" + (p.toString() ? "?" + p : "");
}

/** 고친 심사서류 3종을 맞춘다. 그새 이 기기에서 또 고쳤으면 {retry} — 다음 번에 다시 한다. */
async function syncEdits(t) {
  const snap = () => JSON.stringify(loadLocal()) + JSON.stringify(loadDead());
  const before = snap();
  const got = await sync.readRemote(t);
  if (snap() !== before) return { retry: true, changed: [] };
  const m = sync.mergeEdits(loadLocal(), loadDead(), got.edits);
  if (m.pushNeeded) await sync.writeRemote(t, got.fid, m.edits);
  if (snap() !== before) return { retry: true, changed: [] };     // 올리는 사이에 고쳤다 — 덮지 않는다
  saveLocal(m.recs);
  saveDead(m.dead);
  return { changed: m.changedTitles };
}

/** 내 메모를 받아 이 브라우저에 둔다(보기만). 묶음이 그대로면 내려받지 않는다. */
async function syncMemos(t) {
  const o = readMine();
  const since = o && o.email === t.email ? String(o.stamp || "") : "";
  const got = await sync.readMemos(t, since);
  if (got.unchanged) return { changed: false, count: loadMine().length };
  const before = JSON.stringify(loadMine());
  saveMine(t.email, got.items, got.stamp);
  return { changed: JSON.stringify(got.items) !== before, count: got.items.length };
}

/** 한 번 맞춘다. quiet=true 면 실패해도 창을 띄우지 않는다(저절로 맞출 때). */
async function syncNow(quiet = false) {
  if (syncing) { syncAgain = true; return; }
  syncing = true; syncMsg = ""; syncBad = false;
  paintSync();
  let out = false;
  const signedOut = () => {                     // 로그인 전이거나 구글에서 권한을 뺐다
    if (out) return;
    out = true;
    const had = savedAcct();
    setAcct("");
    if (readMine()) { dropMine(); rebuild(); }  // 그 계정의 메모를 남기지 않는다
    if (had) { syncMsg = "로그인이 끝났습니다 — [구글 로그인] 을 다시 눌러 주세요."; syncBad = true; }
  };
  try {
    let t = await sync.token();
    if (!t) { signedOut(); return; }
    if (savedAcct() && t.email && t.email !== savedAcct()) { dropMine(); }   // 다른 계정 — 옛 계정 메모는 지운다
    setAcct(t.email);
    if ((t.missing || []).length) {
      syncMsg = "구글 동의 화면에서 권한 항목을 체크하지 않았습니다 — 다시 로그인해 모두 체크해 주세요.";
      syncBad = true;
      return;
    }
    // 토큰이 막 끝났을 수 있다 — 401 이면 한 번만 새로 받아 다시
    const again = async (fn) => {
      try { return await fn(t); } catch (e) {
        if (!e.auth) throw e;
        const t2 = await sync.token(true);
        if (!t2) { signedOut(); return null; }
        t = t2;
        return fn(t2);
      }
    };
    const [ed, me] = await Promise.allSettled([again(syncEdits), again(syncMemos)]);
    if (out) return;
    const msgs = [], errs = [];
    let changed = false;
    if (ed.status === "rejected") errs.push(ed.reason?.message || "고친 심사서류를 맞추지 못했습니다.");
    else if (ed.value && ed.value.retry) syncAgain = true;
    else if (ed.value && ed.value.changed.length) {
      msgs.push(`PC 등에서 고친 ${ed.value.changed.join(" · ")} 을(를) 받았습니다.`);
      changed = true;
    }
    if (me.status === "rejected") errs.push("내 메모를 받지 못했습니다 — " + (me.reason?.message || ""));
    else if (me.value) {
      if (me.value.changed) changed = true;
      msgs.push(`내 메모 ${me.value.count}건.`);
    }
    if (changed) rebuild();
    else paintFoot();
    if (errs.length) {
      syncMsg = errs.join(" ");
      syncBad = true;
      if (!quiet && !sdlg.open) sdlg.showModal();
    } else {
      lastSync = Date.now();
      syncMsg = (msgs.length === 1 && msgs[0].startsWith("내 메모") ? "맞췄습니다. " : "") + msgs.join(" ");
    }
  } catch (e) {
    syncMsg = e.message || "동기화하지 못했습니다.";
    syncBad = true;
    if (!quiet && !sdlg.open) sdlg.showModal();
  } finally {
    syncing = false;
    paintSync();
    if (syncAgain) { syncAgain = false; setTimeout(() => syncNow(quiet), 300); }
  }
}

/** 세 자료를 고친 뒤 — 로그인돼 있으면 곧 맞춘다(여러 번 고쳐도 한 번). */
function soonSync() {
  paintSync();
  if (!signedIn()) return;
  clearTimeout(soonTimer);
  soonTimer = setTimeout(() => syncNow(true), 600);
}

$("#btn-sync").onclick = () => {
  syncMsg = ""; syncBad = false;
  paintSync();
  if (!sdlg.open) sdlg.showModal();
  if (signedIn()) syncNow(false);
};
$("#sync-go").onclick = () => syncNow(false);
$("#sync-login").onclick = () => { if (inKakao()) location.href = kakaoOut(); else login(false); };
$("#sync-switch").onclick = () => login(true);
$("#sync-out").onclick = async () => {
  if (!confirm("구글 로그아웃할까요?\n이 기기에서 고친 것은 그대로 남습니다.")) return;
  await sync.logout();
  setAcct(""); lastSync = 0; syncMsg = "로그아웃했습니다."; syncBad = false;
  dropMine();                                   // 이 브라우저에 받아 둔 내 메모도 지운다
  paintSync();
  rebuild();
};
$("#sync-close").onclick = () => sdlg.close();
sdlg.addEventListener("click", (e) => { if (e.target === sdlg) sdlg.close(); });
// 내 계정과 맞추기 — 화면으로 돌아올 때(15초 넘었으면)와 켜 둔 동안 1분마다. PC 에서 고친 것(팩스번호 등)이
// 다시 열지 않아도 곧 보이게(지점장 요청 — "계정에 동기화되는 식으로").
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && signedIn() && Date.now() - lastSync > 15e3) syncNow(true);
});
setInterval(() => {
  if (document.visibilityState === "visible" && signedIn() && Date.now() - lastSync > 55e3) syncNow(true);
}, 60e3);

/** 로그인에서 돌아왔을 때(?auth=…) — 알리고 주소에서 지운다. */
function takeAuthFlag() {
  const u = new URL(location.href);
  const f = u.searchParams.get("auth");
  if (!f) return "";
  u.searchParams.delete("auth");
  history.replaceState(history.state, "", u.pathname + u.search + u.hash);
  const MSG = {
    partial: "구글 동의 화면에서 권한 항목을 체크하지 않았습니다 — [구글 로그인] 을 다시 눌러 모두 체크해 주세요.",
    denied: "로그인을 취소했습니다.",
    expired: "로그인이 너무 오래 걸렸거나 다른 창에서 시작한 것입니다 — 다시 해 주세요.",
    norefresh: "구글이 로그인 정보를 주지 않았습니다 — 다시 해 주세요.",
    unconfigured: "로그인 서버 설정이 아직 끝나지 않았습니다.",
    error: "로그인하지 못했습니다 — 잠시 뒤 다시 해 주세요.",
  };
  if (f === "ok") return "ok";
  syncMsg = MSG[f] || MSG.error;
  syncBad = true;
  return f;
}

// ------------------------------------------------------------------ 홈 화면 앱(설치)
// 폰에서 처음 열면 위에 '홈 화면에 앱으로 설치' 띠를 띄운다(닫으면 다시 안 뜬다). 안드로이드 크롬은
// [설치] 한 번으로, 아이폰·카톡 안 브라우저 등은 방법을 알려 준다. 인터넷 없이 열리는 것은 sw.js.
const INSTALL_KEY = "kbsearch:install-dismissed:v1";
let installEvt = null;
// 카카오톡 안 브라우저 — 설치도, 구글 로그인도 안 된다(구글이 앱 안 브라우저의 로그인을 막는다).
// 카톡이 알아듣는 주소로 바깥 브라우저(크롬·사파리)를 열어 준다.
const inKakao = () => /KAKAOTALK/i.test(navigator.userAgent);
const kakaoOut = () => "kakaotalk://web/openExternal?url=" + encodeURIComponent(location.origin + location.pathname + location.hash);
const standalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const isPhone = () => matchMedia("(max-width: 760px)").matches && matchMedia("(pointer: coarse)").matches;
const installDismissed = () => { try { return localStorage.getItem(INSTALL_KEY) === "1"; } catch (e) { return false; } };
function dismissInstall() {
  try { localStorage.setItem(INSTALL_KEY, "1"); } catch (e) { /* 무시 */ }
  paintInstall();
}
function paintInstall() {
  $("#installbar").hidden = standalone() || installDismissed() || !isPhone();
  if (inKakao()) {
    $("#installbar p span").textContent = "카카오톡 안에서는 설치도 구글 로그인도 안 됩니다. 크롬·사파리로 열어 주세요.";
    $("#install-go").textContent = "다른 브라우저로 열기";
    $("#install-go").dataset.href = kakaoOut();
  }
}
function installHow() {
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/i.test(ua)) return "아래쪽(또는 주소창 옆)의 [공유] 단추(네모에 위 화살표) → [홈 화면에 추가] → [추가] 를 누르세요.";
  if (/SamsungBrowser/i.test(ua)) return "아래쪽 [≡] 메뉴 → [현재 페이지 추가] → [홈 화면] 을 누르세요.";
  return "브라우저 오른쪽 위 [⋮] 메뉴 → [홈 화면에 추가] 또는 [앱 설치] 를 누르세요.";
}
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();                          // 크롬이 제멋대로 띄우지 않게 — 우리 띠의 [설치] 로
  installEvt = e;
  paintInstall();
});
window.addEventListener("appinstalled", () => { installEvt = null; dismissInstall(); });
$("#install-go").onclick = async () => {
  if (inKakao()) { location.href = kakaoOut(); return; }
  if (installEvt) {
    const ev = installEvt;
    installEvt = null;
    try {
      await ev.prompt();
      const r = await ev.userChoice;
      if (r && r.outcome === "accepted") dismissInstall();
    } catch (e) { /* 이미 썼거나 막힘 */ }
    paintInstall();
    return;
  }
  $("#installbar p span").textContent = installHow();
  $("#install-go").hidden = true;
};
$("#install-close").onclick = dismissInstall;

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
const authFlag = takeAuthFlag();
paintSync();
if (authFlag && authFlag !== "ok") sdlg.showModal();
load(window.__boot).then(() => {
  // 방금 로그인했거나 전에 로그인해 둔 브라우저면 바로 맞춘다
  if (authFlag === "ok") { if (!sdlg.open) sdlg.showModal(); syncNow(false); }
  else if (savedAcct()) syncNow(true);
});
// 인터넷이 다시 붙으면 새 자료를 받고 맞춘다
window.addEventListener("online", () => {
  load().then(() => { if (savedAcct()) syncNow(true); });
});
paintInstall();
// 홈 화면 앱 · 인터넷 없이 열기 — 화면 파일을 받아 둔다(sw.js). 첫 화면을 늦추지 않게 다 뜬 뒤에.
if ("serviceWorker" in navigator && window.isSecureContext) {
  const reg = () => navigator.serviceWorker.register("/sw.js").catch(() => { /* 사생활 보호 창 등 */ });
  if (document.readyState === "complete") reg();
  else window.addEventListener("load", reg, { once: true });
}
