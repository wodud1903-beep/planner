// 정보 — 버전, 변경 이력, 로그인 계정, 화면 크기(진단용).
// 변경 이력은 PC 앱과 **같은 CHANGELOG.md** 를 읽는다.
import { html, raw, render, $, $$ } from "./dom.js";
import { bodyToHtml } from "../kb.js";
import { setBody, markTab } from "./chrome.js";
import * as auth from "../auth.js";

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
    <div class="pane">
      <h2 style="margin:6px 0">일정관리기</h2>
      <p style="color:var(--sub);margin:0 0 4px">
        버전 ${v.version || "?"} · 빌드 ${(v.build || "?").slice(0, 7)}</p>
      <p style="color:var(--sub);margin:0 0 14px" id="whoami">
        ${auth.email() ? "로그인: " + auth.email() : "로그인하지 않음"}</p>
      <p><button class="chip" id="relogin">계정 바꾸기</button>
         <button class="chip" id="diag">화면 정보</button></p>
      <p id="diagout" style="color:var(--sub);font-size:13px"></p>
      <h3 style="margin:18px 0 6px">변경 이력</h3>
      <div id="clog" class="empty">불러오는 중…</div>
    </div>`);

  $("#relogin").onclick = () => auth.signIn().then(() => location.reload());
  $("#diag").onclick = () => {
    // 폴드7의 실제 CSS 크기를 확인할 때 쓴다 — 짐작하지 않으려고 둔다
    render($("#diagout"), html`화면 ${innerWidth} × ${innerHeight} ·
      배율 ${devicePixelRatio} · ${matchMedia("(display-mode: standalone)").matches
        ? "설치형으로 실행 중" : "브라우저에서 실행 중"}`);
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
      <summary style="padding:9px 0;border-bottom:1px solid var(--line);cursor:pointer">
        <b>v${s.version}</b> ${s.title}
        <span style="color:var(--sub);font-size:12px">${s.date}</span>
      </summary>
      ${raw(bodyToHtml(s.body))}
    </details>`).join(""));
}

export async function version() {
  try {
    const r = await fetch("./version.json", { cache: "no-store" });
    if (r.ok) return await r.json();
  } catch (e) {}
  return {};
}
