// 홈(대시보드) — PC 앱 v1.23 의 대시보드와 같은 카드들.
//
//   내 할일(체크·추가) · 다가오는 일정 · 이번 주 요약 · 다음 주 요약
//
// 일정은 보기만 하고, 할일은 **체크·추가까지** 한다. 밖에서 '했다' 를 누르는 게
// 이 화면을 여는 가장 큰 이유다. 요약은 고객 탭이 받아 둔 줄로 계산한다(새 통신 없음).
import { html, raw, esc, render, $, $$ } from "./dom.js";
import * as store from "../store.js";
import * as gcal from "../gcal.js";
import * as sheets from "../sheets.js";
import * as weekly from "../weekly.js";
import * as weeklyui from "./weekly.js";
import { setBody, markTab, paintState, toast } from "./chrome.js";
import { icon } from "./icons.js";
import * as router from "../router.js";
import * as auth from "../auth.js";

const DAY = ["일", "월", "화", "수", "목", "금", "토"];
const FORWARD = 30;

/** 시간대별 인사 — PC 대시보드(dashboard.greeting)와 같은 말. */
export function greeting(now = new Date()) {
  const h = now.getHours();
  const tail = h >= 5 && h < 11 ? "좋은 아침이에요."
    : h >= 11 && h < 14 ? "점심 맛있게 드세요."
    : h >= 14 && h < 18 ? "오후도 힘내세요." : "오늘도 수고 많으셨어요.";
  return "안녕하세요! " + tail;
}

// 고객 줄이 새로 오면(고객 탭이 받았다) 요약 카드만 다시 그린다
addEventListener("planner:rows", () => paintWeeks());

let _ev = [];
let _tk = [];
let _warn = "";
let _err = "";
let _at = 0;
let _done = new Set();       // 방금 체크한 것 (서버 응답을 기다리지 않고 지운다)

export async function load({ refresh = true } = {}) {
  const c = await store.get("data", "agenda");
  if (c) { _ev = revive(c.events || []); _tk = reviveT(c.tasks || []); _at = c.at || 0; paint(); }
  else if (!refresh) { _ev = []; _tk = []; _at = 0; _done = new Set(); paint(); }
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
  const now = new Date();
  const head = (ico, title, id, extra = "") => `<div class="cardhead">
      <h3 class="cardtitle">${icon(ico, 18)}${esc(title)}</h3>
      <span class="cardcount" id="${id}"></span><span class="grow"></span>${extra}</div>`;
  setBody(html`
    <div class="pane dash">
      <div class="hello">
        <div class="grow">
          <h2 id="aghello">${greeting(now)}</h2>
          <p class="s">${now.getMonth() + 1}월 ${now.getDate()}일 ${DAY[now.getDay()]}요일</p>
        </div>
        <button class="primary" id="agadd">${raw(icon("plus", 18))}할일 추가</button>
      </div>
      <div id="agwarn"></div>
      <div class="dashgrid">
       <div class="dashcol">
        <section class="card" id="cardtodo">
          ${raw(head("tasks", "내 할일", "agtaskn"))}
          <form id="agform" class="addform" hidden>
            <input id="agtitle" class="bigin" type="text" placeholder="할일을 적어 주세요"
                   maxlength="300" enterkeyhint="done" autocomplete="off">
            <div class="addrow">
              <label class="flab" for="agdue">기한</label>
              <input id="agdue" class="bigin" type="date">
              <button type="submit" class="primary" id="agsave">추가</button>
              <button type="button" class="chip" id="agcancel">취소</button>
            </div>
          </form>
          <ul class="list" id="agtasks"></ul>
        </section>
        <section class="card" id="cardev">
          ${raw(head("calendar", "다가오는 일정", "agevn"))}
          <ul class="list" id="agevents"></ul>
        </section>
       </div>
       <div class="dashcol">
        <section class="card" id="cardthis">
          ${raw(head("grid", "이번 주 요약", "dthisn",
                     '<button class="chip" data-copy="this">복사</button>'))}
          <div id="dthis" class="wkbox"></div>
        </section>
        <section class="card" id="cardnext">
          ${raw(head("next", "다음 주 요약", "dnextn",
                     '<button class="chip" data-copy="next">복사</button>'))}
          <div id="dnext" class="wkbox"></div>
        </section>
       </div>
      </div>
      <p class="synced" id="agsync"></p>
    </div>`);
  wireAdd();
  for (const b of $$("#body [data-copy]")) b.onclick = () => copy(b);
  paint();
  if (!_ev.length && !_tk.length) await load(); else load();
}

// ---------------------------------------------------------------- 할일 추가
function wireAdd() {
  const form = $("#agform");
  const open = () => {
    form.hidden = false;
    $("#agtitle").focus();
  };
  const close = () => { form.hidden = true; form.reset(); };
  $("#agadd").onclick = () => (form.hidden ? open() : close());
  $("#agcancel").onclick = close;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const title = $("#agtitle").value.trim();
    if (!title) { $("#agtitle").focus(); return; }
    const v = $("#agdue").value;                       // "2026-10-28" 또는 ""
    const due = v ? new Date(+v.slice(0, 4), +v.slice(5, 7) - 1, +v.slice(8, 10)) : null;
    const btn = $("#agsave");
    btn.disabled = true;
    btn.textContent = "넣는 중…";
    try {
      await gcal.addTask(title, due);
      close();
      toast("할일을 넣었어요. PC 앱의 구글 할일에도 뜹니다.");
      await load();
    } catch (err) {
      toast(err instanceof sheets.NeedScope
        ? "할일을 넣을 권한이 없습니다. 위 [다시 로그인] 을 눌러 허용해 주세요."
        : err instanceof sheets.NeedSignIn ? "로그인한 뒤에 넣을 수 있어요."
        : err instanceof sheets.Offline ? "인터넷에 연결되지 않았어요."
        : (err.message || "할일을 넣지 못했습니다."), { tone: "bad" });
    }
    btn.disabled = false;
    btn.textContent = "추가";
  };
}

// ---------------------------------------------------------------- 이번 주 · 다음 주 요약
const md = (d) => `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
const hm = (d) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
const endOf = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59);

/** 다음 주(월~일) — 구글 일정 · 할일 · (시트) 출고 예정 · 계약. PC 의 _next_week_sections 와 같다. */
function nextSections(rows) {
  const [mon, sun] = weekly.weekRange(new Date(), 1);
  const inWeek = (d) => d && d >= mon && d <= endOf(sun);
  const evs = _ev.filter((e) => inWeek(e.at));
  const secs = [{
    icon: "📅", title: "다음 주 일정", color: "blue",
    items: evs.slice(0, 20).map((e) => ({
      lead: weekly.dayLabel(e.at), text: e.summary, sub: e.hasTime ? hm(e.at) : "" })),
    count: evs.length, more: Math.max(0, evs.length - 20),
    empty: "다음 주 일정이 없습니다",
  }];
  const todo = _tk.filter((t) => t.due && inWeek(t.due.at) && !_done.has(t.id));
  secs.push({
    icon: "✅", title: "다음 주 할일", color: "green",
    items: todo.slice(0, 20).map((t) => ({ lead: weekly.dayLabel(t.due.at), text: t.title })),
    count: todo.length, more: Math.max(0, todo.length - 20),
    empty: "다음 주가 마감인 할일이 없습니다",
  });
  if (rows.length) {
    secs.push(...weekly.sections(rows, mon, undefined, { word: "다음 주", weekOnly: true }));
  }
  return secs;
}

const NEED_SHEET = (lead = "") => `<p class="empty">${esc(lead)}고객관리 시트를 읽은 뒤에
  만들어집니다.<br>[고객] 탭을 한 번 열어 주세요.</p>`;

function paintWeeks() {
  const box = $("#dthis");
  const nbox = $("#dnext");
  if (!box || !nbox) return;
  const today = new Date();
  const rows = weeklyui.rows();
  const idx = weeklyui.rowIndex(rows);
  const [mon, sun] = weekly.weekRange(today);
  const [nmon, nsun] = weekly.weekRange(today, 1);
  $("#dthisn").textContent = `${md(mon)} ~ ${md(sun)}`;
  $("#dnextn").textContent = `${md(nmon)} ~ ${md(nsun)}`;
  render(box, rows.length
    ? weekly.sections(rows, today).map((x) => weeklyui.sec(x, idx)).join("")
    : NEED_SHEET());
  render(nbox, nextSections(rows).map((x) => weeklyui.sec(x, idx)).join("")
    + (rows.length ? "" : NEED_SHEET("출고 예정·계약은 ")));
  weeklyui.wire(box);
  weeklyui.wire(nbox);
}

/** 카드 내용을 글로 복사 — 카톡에 붙여 넣는다(PC 의 [복사] 와 같은 글). */
function copy(btn) {
  const today = new Date();
  const rows = weeklyui.rows();
  let text;
  if (btn.dataset.copy === "this") {
    text = rows.length ? weekly.renderText(weekly.titleLine(today), weekly.sections(rows, today))
      : "고객관리 시트를 읽은 뒤에 만들어집니다.";
  } else {
    const [mon, sun] = weekly.weekRange(today, 1);
    const p2 = (n) => String(n).padStart(2, "0");
    text = weekly.renderText(`${mon.getFullYear()}년 ${p2(mon.getMonth() + 1)}월 ${p2(mon.getDate())}일`
      + ` ~ ${p2(sun.getMonth() + 1)}월 ${p2(sun.getDate())}일 다음 주 요약`, nextSections(rows));
  }
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = "복사됨 ✓";
    setTimeout(() => { btn.textContent = "복사"; }, 1600);
    toast("복사했어요. 카카오톡에 붙여 넣으세요.");
  }).catch(() => toast("복사하지 못했습니다.", { tone: "bad" }));
}

// 로그인 전이라 비어 있는 것 — '없습니다' 라고 하면 정말 없는 줄 안다
const signedOut = () => !_at && auth.state() === auth.STATE.NEED;

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

export function repaint() { paint(); }

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

  paintWeeks();

  // ---- 할일
  const tl = $("#agtasks");
  if (tl) {
    const live = _tk.filter((t) => !_done.has(t.id));
    const n = $("#agtaskn");
    if (n) n.textContent = live.length ? `${live.length}건` : "";
    if (!live.length) {
      render(tl, html`<li class="empty">${_tk.length ? "할일을 다 했습니다 👍"
        : signedOut() ? "로그인하면 구글 할일이 여기에 보입니다."
        : (_err ? "" : "할일이 없습니다.")}</li>`);
    } else {
      render(tl, live.map((t) => {
        const d = t.due ? dayLabel(t.due.at) : null;
        return html`<li class="taskrow">
          <button class="tickbtn" data-id="${t.id}" data-list="${t.listId}"
                  aria-label="했음으로 표시">${raw(icon("check", 20))}</button>
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
  const en = $("#agevn");
  if (en) en.textContent = _ev.length ? `앞으로 ${FORWARD}일 · ${_ev.length}건` : "";
  if (!_ev.length) {
    render(el, html`<li class="empty">${signedOut() ? "로그인하면 구글 캘린더 일정이 여기에 보입니다."
      : _err ? "" : "일정이 없습니다."}</li>`);
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
