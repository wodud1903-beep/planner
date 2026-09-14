// 머리말·탭·상태 알약 — 모든 화면이 공유하는 틀.
import { html, render, $, raw } from "./dom.js";
import * as auth from "../auth.js";

// 여섯 칸이다. 접힌 커버 화면(~400px)에서 한 칸이 66px 남짓이라
// 글자는 짧게, 그림은 하나씩만 쓴다.
const TABS = [
  ["/agenda", "🗓", "일정"],
  ["/docs", "📄", "서류"],
  ["/customers", "👥", "고객"],
  ["/calc", "🧮", "수당"],
  ["/kb", "📚", "자료"],
  ["/about", "ⓘ", "정보"],
];

export function shell() {
  return html`
    <header>
      <h1>일정관리기</h1>
      <span class="grow"></span>
      <button class="chip" id="statechip" hidden></button>
    </header>
    <main id="body"></main>
    <nav class="tabs">
      ${raw(TABS.map(([p, i, t]) =>
        `<a href="#${p}" data-tab="${p}"><span class="ico">${i}</span>${t}</a>`).join(""))}
    </nav>`;
}

export function markTab(path) {
  for (const a of document.querySelectorAll("nav.tabs a")) {
    const p = a.dataset.tab;
    if (path === p || path.startsWith(p + "/")) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

// 상태 알약 — 로그인이 필요하거나 오프라인일 때만 보인다.
// ⚠️ 모달도 빈 화면도 띄우지 않는다. 캐시가 있으면 화면은 그대로 쓰인다.
export function paintState() {
  const el = $("#statechip");
  if (!el) return;
  const s = auth.state();
  if (s === auth.STATE.AUTHED || s === auth.STATE.UNKNOWN) { el.hidden = true; return; }
  el.hidden = false;
  if (s === auth.STATE.OFFLINE) {
    el.textContent = "오프라인";
    el.className = "chip";
    el.onclick = () => location.reload();
  } else {
    el.textContent = "다시 로그인";
    el.className = "chip bad";
    el.onclick = () => auth.signIn().then(() => location.reload());
  }
}

export function body() { return $("#body"); }
export function setBody(markup) { return render($("#body"), markup); }
