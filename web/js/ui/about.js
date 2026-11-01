// 정보 — 버전, 변경 이력, 로그인 계정, 화면 크기(진단용).
// 변경 이력은 PC 앱과 **같은 CHANGELOG.md** 를 읽는다.
import { html, raw, render, $, $$ } from "./dom.js";
import { bodyToHtml } from "../kb.js";
import { setBody, markTab } from "./chrome.js";
import * as auth from "../auth.js";
import * as theme from "../theme.js";
import * as store from "../store.js";
import { icon } from "./icons.js";
import * as push from "../push.js";

let _secs = null;

// '## v1.11.0 — 제목 (2026-09-13)' 을 절로 가른다 (PC 의 changelog.py 와 같은 규칙)
const SEC = /^## v(\d+\.\d+\.\d+)(?:\s*[—-]\s*(.*?))?\s*(?:\(([^)]*)\))?\s*$/;

export function parseChangelog(text) {
  const out = [];
  let cur = null;
  for (const line of String(text || "").split("\n")) {
    const m = line.match(SEC);
    if (m) {
      if (cur) out.push(cur);
      cur = { version: m[1], title: (m[2] || "").trim(), date: (m[3] || "").trim(), body: "" };
      continue;
    }
    if (cur) cur.body += line + "\n";
  }
  if (cur) out.push(cur);
  for (const s of out) s.body = s.body.replace(/^\n+|\n+$/g, "");
  return out;
}

async function load() {
  if (_secs) return _secs;
  try {
    const r = await fetch("./CHANGELOG.md", { cache: "no-cache" });
    if (r.ok) _secs = parseChangelog(await r.text());
  } catch (e) { /* 오프라인이면 프리캐시에서 온다 */ }
  return _secs || [];
}

export async function screen() {
  markTab("/about");
  const v = await version();
  setBody(html`
    <div class="pane narrow">
      <section class="card">
        <div class="appid">${raw(icon("logo", 34, "logo big"))}
          <div><h2>일정관리기</h2>
            <p class="s">버전 ${v.version || "?"} · 빌드 ${(v.build || "?").slice(0, 7)}</p></div>
        </div>
        <p class="s" id="whoami">
          ${auth.email() ? "로그인: " + auth.email() : "로그인하지 않음"}</p>
        <p class="btnrow"><button class="chip" id="relogin">계정 바꾸기</button>
           ${raw(auth.email() ? '<button class="chip" id="signout">로그아웃</button>' : "")}
           <button class="chip" id="diag">화면 정보</button></p>
        <p id="diagout" class="s"></p>
        <p class="s"><a href="./privacy.html">개인정보처리방침</a> ·
           <a href="./terms.html">서비스 약관</a></p>
      </section>
      <section class="card" id="pushcard">
        <h3 class="cardtitle">아침 브리핑 알림</h3>
        <p class="s">매일 아침(8:50~10시 사이) 오늘 일정 · 할일 · 출고 · 뉴스를 이 폰으로 알려 드려요.</p>
        <p class="btnrow" id="pushbtns"></p>
        <p class="s" id="pushmsg"></p>
      </section>
      <section class="card">
        <h3 class="cardtitle">테마</h3>
        <div class="cats" id="themes">${raw(theme.THEMES.map(([k, t]) => html`
          <button data-theme-pick="${k}" aria-pressed="${String(k === theme.current())}">${t}</button>`).join(""))}</div>
      </section>
      <section class="card">
        <h3 class="cardtitle">변경 이력</h3>
        <div id="clog" class="empty">불러오는 중…</div>
      </section>
    </div>`);

  for (const b of $$("#themes button")) {
    b.onclick = () => {
      theme.apply(b.dataset.themePick);
      for (const x of $$("#themes button"))
        x.setAttribute("aria-pressed", String(x === b));
    };
  }
  // 계정 바꾸기는 지금 로그인을 지우고 계정 고르는 화면을 띄운다
  // (그냥 다시 로그인은 같은 계정으로 바로 닫힌다)
  $("#relogin").onclick = () => auth.switchAccount().then((t) => { if (t) location.reload(); });
  const out = $("#signout");
  if (out) {
    // 남의 폰·공용 PC 에서 썼을 때 — 로그인도, 이 기기에 받아 둔 자료도 지운다
    out.onclick = async () => {
      if (!confirm("이 기기에서 로그아웃할까요?\n받아 둔 고객·일정 자료도 이 기기에서 지웁니다.")) return;
      await auth.signOut();
      try { await store.wipe(); await store.del("meta", "account"); } catch (e) { /* 그래도 나간다 */ }
      location.reload();
    };
  }
  paintPush();
  $("#diag").onclick = () => {
    // 폴드7의 실제 CSS 크기를 확인할 때 쓴다 — 짐작하지 않으려고 둔다
    render($("#diagout"), html`화면 ${innerWidth} × ${innerHeight} ·
      배율 ${devicePixelRatio} · ${matchMedia("(display-mode: standalone)").matches
        ? "설치형으로 실행 중" : "브라우저에서 실행 중"} · 로그인 방식 ${auth.mode() || "?"}`);
  };

  const secs = await load();
  const box = $("#clog");
  if (!secs.length) {
    render(box, "변경 이력을 불러오지 못했습니다.");
    return;
  }
  box.className = "";
  render(box, secs.map((s, i) => html`
    <details ${raw(i === 0 ? "open" : "")}>
      <summary>
        <b>v${s.version}</b> ${s.title}
        <span style="color:var(--sub);font-size:12px">${s.date}</span>
      </summary>
      ${raw(bodyToHtml(s.body))}
    </details>`).join(""));
}

// 아침 브리핑 알림 — 켜기/끄기/지금 받아 보기
async function paintPush() {
  const btns = $("#pushbtns");
  const msg = $("#pushmsg");
  if (!btns) return;
  const why = push.support();
  if (why) { render(msg, why); return; }
  const on = !!(await push.current());
  render(btns, on
    ? '<button class="chip" id="pushtest">지금 한 번 받아 보기</button>'
      + '<button class="chip bad" id="pushoff">알림 끄기</button>'
    : '<button class="primary" id="pushon">알림 켜기</button>');
  render(msg, on ? "켜져 있어요. 이 폰으로 매일 아침 한 번 옵니다." : "");
  const say = (t) => render(msg, html`${t}`);
  const b1 = $("#pushon");
  if (b1) b1.onclick = async () => {
    b1.disabled = true;
    say("켜는 중…");
    let err = "";
    try { err = await push.enable(); } catch (e) { err = "알림을 켜지 못했어요."; }
    if (err) { b1.disabled = false; say(err); return; }
    await paintPush();
    say("켰어요! 내일 아침부터 옵니다. [지금 한 번 받아 보기] 로 확인해 보세요.");
  };
  const b2 = $("#pushoff");
  if (b2) b2.onclick = async () => { await push.disable(); await paintPush(); say("껐어요."); };
  const b3 = $("#pushtest");
  if (b3) b3.onclick = async () => {
    b3.disabled = true;
    say("오늘 브리핑을 만드는 중…");
    const r = await push.test().catch(() => ({ error: "보내지 못했어요." }));
    b3.disabled = false;
    say(r.error || "보냈어요. 알림이 곧 뜹니다.");
  };
}

export async function version() {
  try {
    const r = await fetch("./version.json", { cache: "no-store" });
    if (r.ok) return await r.json();
  } catch (e) {}
  return {};
}
