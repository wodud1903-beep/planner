// 아주 작은 DOM 도우미.
//
// html`` 안에 끼워 넣는 값은 **기본이 escape** 다. 시트에 든 글은 전부 사람이 쓴 것이라
// 그대로 넣으면 위험하다. 이미 다듬어 둔 HTML 은 raw() 로 감싸 명시적으로 넣는다.

const RAW = Symbol("raw");
export const raw = (s) => ({ [RAW]: String(s == null ? "" : s) });

export function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

export function html(strings, ...vals) {
  let out = strings[0];
  for (let i = 0; i < vals.length; i++) {
    const v = vals[i];
    if (v && typeof v === "object" && RAW in v) out += v[RAW];
    else if (Array.isArray(v)) out += v.map((x) =>
      (x && typeof x === "object" && RAW in x) ? x[RAW] : esc(x)).join("");
    else out += esc(v);
    out += strings[i + 1];
  }
  return out;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function render(el, markup) {
  if (el) el.innerHTML = markup;
  return el;
}

// 목록 스크롤 위치를 '몇 번째 줄' 로 기억한다.
// ⚠️ 픽셀로 기억하면 폰을 펼 때(너비가 바뀔 때) 엉뚱한 데로 튄다.
export function topIndex(listEl) {
  if (!listEl) return 0;
  const kids = listEl.children;
  const top = listEl.getBoundingClientRect().top;
  for (let i = 0; i < kids.length; i++) {
    if (kids[i].getBoundingClientRect().bottom > top + 1) return i;
  }
  return 0;
}
export function scrollToIndex(listEl, i) {
  if (!listEl || !listEl.children[i]) return;
  listEl.children[i].scrollIntoView({ block: "start" });
}
