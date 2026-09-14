// 일정 / 할일 — PC 앱의 그 화면을 폰에서 본다.
//
// 일정은 보기만 하고, 할일은 **체크까지** 한다. 밖에서 '했다' 를 누르는 게
// 이 화면을 여는 가장 큰 이유다.
import { html, raw, esc, render, $, $$ } from "./dom.js";
import * as store from "../store.js";
import * as gcal from "../gcal.js";
import * as sheets from "../sheets.js";
import { setBody, markTab, paintState } from "./chrome.js";
import * as router from "../router.js";

const DAY = ["일", "월", "화", "수", "목", "금", "토"];
const FORWARD = 30;

let _ev = [];
let _tk = [];
let _warn = "";
let _err = "";
let _at = 0;
let _done = new Set();       // 방금 체크한 것 (서버 응답을 기다리지 않고 지운다)

export async function load({ refresh = true } = {}) {
  const c = await store.get("data", "agenda");
  if (c) { _ev = revive(c.events || []); _tk = reviveT(c.tasks || []); _at = c.at || 0; paint(); }
  if (!refresh) return;
  try {
    const [e, t] = await Promise.all([gcal.events({ forwardDays: FORWARD }), gcal.tasks()]);
    _ev = e.events;
    _tk = t.tasks;
    _err = "";
    const bad = [...e.failed, ...t.failed];
    // ⚠️ 일부만 불러온 걸 성공처럼 보여주면 안 된다. 안 보이는 일정이 있는데
    //    '일정 없음' 으로 읽으면 약속을 놓친다.
    _warn = bad.length ? `${bad.join(", ")} 을(를) 불러오지 못했습니다.` : "";
    _at = Date.now();
    await store.put("data", "agenda", { events: _ev, tasks: _tk, at: _at });
  } catch (err) {
    _err = err instanceof sheets.NeedScope
      ? "일정·할일 권한이 아직 없습니다. 위 [다시 로그인] 을 눌러 허용해 주세요."
      : err instanceof sheets.WrongAccount
        ? "이 계정으로는 일정을 볼 수 없습니다."
        : (err instanceof sheets.NeedSignIn || err instanceof sheets.Offline)
          ? "" : (err.message || "일정을 불러오지 못했습니다.");
    paintState();
  }
  paint();
  return true;
}

// IndexedDB 는 Date 를 그대로 돌려주지만, 혹시 문자열로 남았을 때를 대비한다
const revive = (a) => a.map((x) => ({ ...x, at: new Date(x.at) }));
const reviveT = (a) => a.map((x) => ({
  ...x, due: x.due ? { ...x.due, at: new Date(x.due.at) } : null }));

export async function screen() {
  markTab("/agenda");
  setBody(html`
    <div class="pane">
      <div id="agwarn"></div>
      <p class="kbhead">할일</p>
      <ul class="list" id="agtasks"></ul>
      <p class="kbhead" style="margin-top:18px">앞으로 ${FORWARD}일 일정</p>
      <ul class="list" id="agevents"></ul>
      <p class="synced" id="agsync"></p>
    </div>`);
  paint();
  if (!_ev.length && !_tk.length) await load(); else load();
}

const sameDay = (a, b) => a.getFullYear() === b.getFullYear()
  && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

function dayLabel(d) {
  const today = new Date();
  const t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const diff = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - t0) / 86400000);
  const base = `${d.getMonth() + 1}.${d.getDate()}(${DAY[d.getDay()]})`;
  if (diff === 0) return { text: "오늘 " + base, tone: "today" };
  if (diff === 1) return { text: "내일 " + base, tone: "tomorrow" };
  if (diff < 0) return { text: base, tone: "past" };
  return { text: base, tone: "" };
}

function paint() {
  const w = $("#agwarn");
  if (w) {
    render(w, _err ? html`<p class="notice bad">${_err}</p>`
         : _warn ? html`<p class="notice">${_warn}</p>` : "");
  }
  const sync = $("#agsync");
  if (sync) {
    sync.textContent = _at
      ? new Date(_at).toLocaleString("ko-KR",
          { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) + " 기준"
      : "";
  }

  // ---- 할일
  const tl = $("#agtasks");
  if (tl) {
    const live = _tk.filter((t) => !_done.has(t.id));
    if (!live.length) {
      render(tl, html`<li class="empty">${_tk.length ? "할일을 다 했습니다 👍"
        : (_err ? "" : "할일이 없습니다.")}</li>`);
    } else {
      render(tl, live.map((t) => {
        const d = t.due ? dayLabel(t.due.at) : null;
        return html`<li class="taskrow">
          <button class="tickbtn" data-id="${t.id}" data-list="${t.listId}"
                  aria-label="했음으로 표시">○</button>
          <div class="taskbody">
            <span class="t">${t.title}</span>
            ${raw(t.notes ? `<span class="s">${esc(t.notes)}</span>` : "")}
            <span class="meta">${raw(d
              ? `<span class="tag ${d.tone}">${esc(d.text)}</span>` : "")}${raw(
              t.listName ? `<span class="d">${esc(t.listName)}</span>` : "")}</span>
          </div></li>`;
      }).join(""));
      for (const b of $$("#agtasks .tickbtn")) b.onclick = () => tick(b);
    }
  }

  // ---- 일정
  const el = $("#agevents");
  if (!el) return;
  if (!_ev.length) {
    render(el, html`<li class="empty">${_err ? "" : "일정이 없습니다."}</li>`);
    return;
  }
  let last = null;
  const out = [];
  for (const e of _ev) {
    if (!last || !sameDay(last, e.at)) {
      const d = dayLabel(e.at);
      out.push(html`<li class="daysep ${d.tone}">${d.text}</li>`);
      last = e.at;
    }
    const time = e.hasTime
      ? `${String(e.at.getHours()).padStart(2, "0")}:${String(e.at.getMinutes()).padStart(2, "0")}`
      : "종일";
    out.push(html`<li class="evrow"><span class="evtime">${time}</span>
      <span class="evbody"><span class="t">${e.summary}</span>${raw(
        e.calName ? `<span class="d">${esc(e.calName)}</span>` : "")}</span></li>`);
  }
  render(el, out.join(""));
}

async function tick(btn) {
  const { id, list } = btn.dataset;
  btn.disabled = true;
  btn.textContent = "…";
  // 눌렀으면 바로 지운다. 통신을 기다리면 두 번 누르게 된다.
  _done.add(id);
  paint();
  try {
    await gcal.completeTask(list, id);
    _tk = _tk.filter((t) => t.id !== id);
    await store.put("data", "agenda", { events: _ev, tasks: _tk, at: _at });
  } catch (e) {
    // 못 바꿨으면 되돌린다 — 지운 채로 두면 안 한 일을 한 줄 안다
    _done.delete(id);
    _err = e instanceof sheets.NeedScope
      ? "할일을 고칠 권한이 없습니다. 위 [다시 로그인] 을 눌러 허용해 주세요."
      : (e.message || "할일을 바꾸지 못했습니다.");
    paintState();
  }
  paint();
}
