// 머리말·메뉴·상태 알약·알림 — 모든 화면이 공유하는 틀.
//
// 생김새는 PC 앱(v1.23 대시보드)과 같게 — 연보라 포인트, 흰 둥근 카드, 선 아이콘.
// 폰은 아래 탭(고른 탭은 연보라 알약), 펼친 화면·PC 는 왼쪽 메뉴가 된다(app.css).
import { html, render, $, raw, esc } from "./dom.js";
import { icon } from "./icons.js";
import * as auth from "../auth.js";

// 여섯 칸이다. 접힌 커버 화면(~400px)에서 한 칸이 66px 남짓이라 글자는 짧게.
// ⚠️ 주소(#/agenda)는 그대로 둔다 — 홈 화면 아이콘·북마크가 그 주소를 들고 있다.
const TABS = [
  ["/agenda", "grid", "홈"],
  ["/docs", "folder", "서류"],
  ["/customers", "people", "고객"],
  ["/calc", "calc", "수당"],
  ["/kb", "search", "자료"],
  ["/about", "info", "정보"],
];

export function shell() {
  return html`
    <header>
      <span class="brand">${raw(icon("logo", 22, "logo"))}<h1>일정관리기</h1></span>
      <span class="grow"></span>
      <button class="chip" id="statechip" hidden></button>
      <span class="who" id="whochip" hidden></span>
    </header>
    <main id="body"></main>
    <nav class="tabs">
      ${raw(TABS.map(([p, i, t]) =>
        `<a href="#${p}" data-tab="${p}"><span class="pill">${icon(i)}</span>`
        + `<span class="lbl">${t}</span></a>`).join(""))}
    </nav>
    <div class="toast" id="toast" role="status" hidden></div>`;
}

export function markTab(path) {
  for (const a of document.querySelectorAll("nav.tabs a")) {
    const p = a.dataset.tab;
    if (path === p || path.startsWith(p + "/")) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

// 권한이 모자란다는 답(NeedScope)을 받았다 — 로그인은 됐어도 [다시 로그인] 을 보인다
let _scope = false;
addEventListener("planner:needscope", () => { _scope = true; paintState(); });

/** [로그인] — 서버 방식은 화면이 넘어갔다가 돌아온다. 예전 방식(팝업)은 여기서 끝난다. */
export function signIn(opts) {
  return auth.signIn(opts).then((t) => {
    if (t) { _scope = false; window.dispatchEvent(new CustomEvent("planner:reauthed")); }
    return t;
  });
}

// 상태 알약 — 로그인이 필요하거나 오프라인일 때만 보인다.
// ⚠️ 모달도 빈 화면도 띄우지 않는다. 캐시가 있으면 화면은 그대로 쓰인다.
export function paintState() {
  // 누구로 로그인했는지 늘 보이게 한다. 계정을 바꿔 가며 쓰는 자리라
  // 지금 보고 있는 게 누구 자료인지 헷갈리면 안 된다.
  const who = $("#whochip");
  if (who) {
    const m = auth.email() || "";
    who.textContent = m;
    who.dataset.initial = m ? m[0].toUpperCase() : "";
    who.hidden = !m;
  }
  const el = $("#statechip");
  if (!el) return;
  const s = auth.state();
  const scope = s === auth.STATE.AUTHED && (_scope || auth.missing().length > 0);
  if (s !== auth.STATE.NEED && s !== auth.STATE.OFFLINE && !scope) { el.hidden = true; return; }
  el.hidden = false;
  if (s === auth.STATE.OFFLINE) {
    el.textContent = "오프라인";
    el.className = "chip";
    el.onclick = () => location.reload();
  } else {
    // 처음 쓰는 기기면 '로그인', 쓰다가 끊겼거나 권한이 모자라면 '다시 로그인'
    el.textContent = auth.email() || scope ? "다시 로그인" : "로그인";
    el.className = "chip bad";
    // 앱을 통째로 다시 띄우지 않는다 — 보던 화면 그대로 자료만 다시 받는다
    // (계정이 바뀌면 boot 의 onEmail 이 앞사람 자료를 지우고 다시 그린다)
    el.onclick = () => signIn();
  }
}

// ---------------------------------------------------------------- 알림
// 아래쪽에 잠깐 뜨는 한 줄. 단추를 하나 달 수 있다(예: [다시 로그인]).
// sticky 면 닫을 때까지 남는다.
let _toastTimer = 0;
export function toast(msg, { action = "", onAction = null, tone = "", sticky = false } = {}) {
  const el = $("#toast");
  if (!el) return;
  clearTimeout(_toastTimer);
  render(el, `<span class="msg">${esc(msg)}</span>`
    + (action ? `<button class="chip act">${esc(action)}</button>` : "")
    + `<button class="x" aria-label="닫기">${icon("plus", 18, "ico x45")}</button>`);
  el.className = "toast" + (tone ? " " + tone : "");
  el.hidden = false;
  const close = () => { el.hidden = true; clearTimeout(_toastTimer); };
  el.querySelector(".x").onclick = close;
  const a = el.querySelector(".act");
  if (a) a.onclick = () => { close(); if (onAction) onAction(); };
  if (!sticky) _toastTimer = setTimeout(close, 4000);
}

export function body() { return $("#body"); }
export function setBody(markup) { return render($("#body"), markup); }
