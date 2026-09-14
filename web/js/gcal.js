// 일정(캘린더)과 할일(Tasks) — planner/google_client.py 의 조회 부분을 옮긴 것.
import { CALENDAR_API, TASKS_API } from "./config.js";
import { token, setOffline } from "./auth.js";
import { NeedSignIn, WrongAccount, Offline, NeedScope } from "./sheets.js";

async function call(url, { method = "GET", body = null } = {}) {
  let tok = await token();
  if (!tok) throw new NeedSignIn();
  const go = () => fetch(url, {
    method,
    headers: {
      Authorization: "Bearer " + tok,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  let r;
  try { r = await go(); } catch (e) { setOffline(true); throw new Offline(); }
  if (r.status === 401) {
    tok = await token({ interactive: false });
    if (!tok) throw new NeedSignIn();
    try { r = await go(); } catch (e) { setOffline(true); throw new Offline(); }
  }
  if (r.status === 403) {
    let m = "";
    try { m = ((await r.clone().json()).error || {}).message || ""; } catch (x) {}
    if (/insufficient|scope/i.test(m)) throw new NeedScope(m);
    throw new WrongAccount();
  }
  if (r.status === 204) return null;
  if (!r.ok) throw new Error(`구글에서 읽지 못했습니다 (HTTP ${r.status})`);
  return r.json();
}

// ---------------------------------------------------------------- 일정
const pad = (n) => String(n).padStart(2, "0");
function rfc3339(d) {
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const a = Math.abs(off);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
       + `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
       + `${sign}${pad(Math.floor(a / 60))}:${pad(a % 60)}`;
}

/** '2026-08-14' 또는 '2026-08-14T09:00:00+09:00' → {at, hasTime} */
export function parseWhen(s) {
  const t = String(s || "");
  if (!t) return null;
  // ⚠️ 종일 일정('2026-08-14')을 new Date() 에 그냥 넣으면 **UTC 자정**으로 읽혀
  //    한국에서는 전날로 밀린다. 날짜만 있을 때는 직접 만든다.
  const m = t.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return { at: new Date(+m[1], +m[2] - 1, +m[3]), hasTime: false };
  const d = new Date(t);
  return isNaN(d) ? null : { at: d, hasTime: true };
}

/** 앞으로 forwardDays 동안의 일정. 보이는 캘린더만 본다(숨긴 구독·공휴일 제외). */
export async function events({ backDays = 0, forwardDays = 30 } = {}) {
  const now = new Date();
  const base = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const min = new Date(base); min.setDate(min.getDate() - backDays);
  const max = new Date(base); max.setDate(max.getDate() + forwardDays);

  const list = await call(`${CALENDAR_API}/users/me/calendarList`
    + `?fields=${encodeURIComponent("items(id,summary,selected,primary)")}`);
  let cals = (list.items || []).filter((c) => c.id && (c.selected || c.primary));
  if (!cals.length) cals = (list.items || []).filter((c) => c.id);

  const qs = `timeMin=${encodeURIComponent(rfc3339(min))}`
           + `&timeMax=${encodeURIComponent(rfc3339(max))}`
           + `&singleEvents=true&orderBy=startTime&maxResults=250`
           + `&fields=${encodeURIComponent("items(start,end,summary,description,id)")}`;

  // 캘린더 하나가 탈나도 나머지는 보여 준다. 다만 **조용히 삼키지는 않는다** —
  // 일정이 빠졌는데 '일정 없음' 으로 보이면 약속을 놓친다.
  const failed = [];
  const got = await Promise.all(cals.map(async (c) => {
    try {
      const j = await call(`${CALENDAR_API}/calendars/${encodeURIComponent(c.id)}/events?${qs}`);
      return (j.items || []).map((it) => {
        const w = parseWhen((it.start || {}).dateTime || (it.start || {}).date);
        if (!w) return null;
        return {
          at: w.at, hasTime: w.hasTime,
          summary: it.summary || "(제목 없음)",
          description: it.description || "",
          calId: c.id, calName: c.summary || "", id: it.id || "",
        };
      }).filter(Boolean);
    } catch (e) {
      if (e instanceof NeedSignIn || e instanceof NeedScope) throw e;
      failed.push(c.summary || c.id);
      return [];
    }
  }));
  const out = got.flat().sort((a, b) => a.at - b.at);
  return { events: out, failed };
}

// ---------------------------------------------------------------- 할일
export async function tasks() {
  const lists = await call(`${TASKS_API}/users/@me/lists`
    + `?fields=${encodeURIComponent("items(id,title)")}`);
  const ls = (lists.items || []).filter((l) => l.id);
  const failed = [];
  const got = await Promise.all(ls.map(async (l) => {
    try {
      const j = await call(`${TASKS_API}/lists/${encodeURIComponent(l.id)}/tasks`
        + `?showCompleted=false&showHidden=false&maxResults=100`
        + `&fields=${encodeURIComponent("items(id,title,notes,due,status)")}`);
      return (j.items || []).filter((t) => (t.title || "").trim()).map((t) => ({
        id: t.id, listId: l.id, listName: l.title || "",
        title: t.title, notes: t.notes || "",
        due: t.due ? parseWhen(String(t.due).slice(0, 10)) : null,
      }));
    } catch (e) {
      if (e instanceof NeedSignIn || e instanceof NeedScope) throw e;
      failed.push(l.title || l.id);
      return [];
    }
  }));
  // 기한이 있는 것부터, 이른 순으로. 기한 없는 것은 뒤에.
  const out = got.flat().sort((a, b) => {
    if (!a.due && !b.due) return a.title.localeCompare(b.title, "ko");
    if (!a.due) return 1;
    if (!b.due) return -1;
    return a.due.at - b.due.at;
  });
  return { tasks: out, failed };
}

/** 할일을 '했다' 로 바꾼다. 밖에서 누르는 게 이 화면의 쓸모다. */
export function completeTask(listId, taskId) {
  return call(`${TASKS_API}/lists/${encodeURIComponent(listId)}`
            + `/tasks/${encodeURIComponent(taskId)}`,
              { method: "PATCH", body: { status: "completed" } });
}
