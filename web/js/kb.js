// 업무자료 검색·표시 — planner/kb.py + kb_tab.body_to_html 을 옮긴 것.
import { prepare, matchesPrepared, rank } from "./hangul.js";

export const CATEGORIES = ["심사서류", "캐피탈", "전자약정", "연락처", "진행절차", "기타"];
const HEAD_MARK = "■";

// 항목마다 세 갈래로 미리 다듬어 둔다 — 순위를 가르기 위해서다.
export function index(items) {
  return (items || []).map((it, i) => ({
    it, i,
    t0: prepare(it.title || ""),
    t1: prepare(`${it.finance || ""} ${it.tags || ""}`),
    t2: prepare([it.category, it.body, (it.checklist || []).join(" ")].join(" ")),
  }));
}

// 제목 0순위 / 금융사·태그 1순위 / 나머지 2순위. 그 안에서는 rank() 로, 같으면 원래 순서.
export function search(idx, query, category) {
  const q = (query || "").trim();
  const cat = (category || "").trim();
  const hits = [];
  for (const e of idx) {
    if (cat && (e.it.category || "") !== cat) continue;
    let tier = -1;
    if (!q) tier = 0;
    else if (matchesPrepared(e.t0, q)) tier = 0;
    else if (matchesPrepared(e.t1, q)) tier = 1;
    else if (matchesPrepared(e.t2, q)) tier = 2;
    if (tier < 0) continue;
    hits.push([tier, q ? rank(e.it.title || "", q) : 3, e.i, e.it]);
  }
  hits.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  return hits.map((h) => h[3]);
}

const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;");

// ⚠️ 주소를 **먼저 가른 뒤** 나머지만 escape 한다. 줄 전체를 먼저 escape 하면
//    주소 안의 & 가 &amp; 로 바뀌어 링크가 깨진다 — 파이썬 쪽에 같은 사고 기록이 있다.
const URL_RE = /(https?:\/\/[^\s<>"']+)/g;
function linkify(line) {
  let out = "", last = 0, m;
  URL_RE.lastIndex = 0;
  while ((m = URL_RE.exec(line)) !== null) {
    out += esc(line.slice(last, m.index));
    let url = m[0];
    let tail = "";
    while (url && ".,);]".includes(url[url.length - 1])) {
      tail = url[url.length - 1] + tail;
      url = url.slice(0, -1);
    }
    out += `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a>` + esc(tail);
    last = m.index + m[0].length;
  }
  out += esc(line.slice(last));
  return out;
}

// '■ 머리글' 은 굵은 소제목 + 앞에 구분선. 머리글이 없는 글에는 선을 안 긋는다.
export function bodyToHtml(text) {
  const out = ['<div class="kbbody">'];
  let firstHead = true;
  for (const line of String(text || "").split("\n")) {
    if (line.trimStart().startsWith(HEAD_MARK)) {
      if (!firstHead) out.push('<hr class="kbsep">');
      firstHead = false;
      out.push(`<p class="kbhead">${linkify(line.trim())}</p>`);
    } else if (line.trim()) {
      out.push(`<p class="kbline">${linkify(line)}</p>`);
    } else {
      out.push('<p class="kbgap"></p>');
    }
  }
  out.push("</div>");
  return out.join("");
}
