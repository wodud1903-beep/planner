// 고객 피드 — 고객 상세 아래 '이력 · 메모'. 플로우의 피드처럼 한 고객에게 있었던 일을
// 최신부터 한 줄씩 보여 주고, 맨 위에서 바로 메모를 남긴다.
//
//   자동 이력: 계약(발주) · 출고 · 만기 예정 — 시트가 이미 아는 것(저장하지 않는다)
//   메모     : PC 앱 고객 이력과 같은 메모(notes.js). 폰에서 남긴 것은 📱
//
// 밖에서 통화하고 바로 적는 게 이 칸의 쓸모라, 입력칸을 맨 위에 둔다.
import { html, raw, esc, render, $, $$ } from "./dom.js";
import * as notes from "../notes.js";
import * as sheets from "../sheets.js";
import * as store from "../store.js";
import { parseDate } from "../fmt.js";
import { expiryDate } from "../weekly.js";
import { paintState, toast } from "./chrome.js";

const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** 시트에서 파생되는 이력 [{date, kind, text}] — PC 의 customer_history._auto_events 와 같은 규칙. */
export function autoEvents(cr, today = new Date()) {
  const v = cr.values || {};
  const out = [];
  const cd = parseDate(v.contract_date);
  if (cd) out.push({ date: ymd(cd), kind: "계약",
                     text: `계약(발주) — ${[v.finance, v.model].filter(Boolean).join(" ")}`.trim() });
  const dd = parseDate(v.deliver_date);
  if (dd) out.push({ date: ymd(dd), kind: "출고", text: "차량 출고" });
  // 만기는 실제로 출고된 계약에만(발주만 하고 취소한 건이 섞이지 않게)
  if (String(v.status || "").trim().startsWith("출고") && dd) {
    const ex = expiryDate(cr);
    if (ex) {
      const t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
      const left = Math.round((ex - t0) / 86400000);
      const tail = left > 0 ? `D-${left}` : left === 0 ? "오늘" : `${-left}일 지남`;
      out.push({ date: ymd(ex), kind: "만기", text: `계약 만기 예정 (${tail})`, future: true });
    }
  }
  return out;
}

const TONE = { 계약: "violet", 출고: "green", 만기: "orange", 메모: "" };

function line(it) {
  const d = it.date ? it.date.slice(2).replace(/-/g, ".") : "날짜 미상";
  return html`<li class="fi ${TONE[it.kind] || ""}${raw(it.memo ? " memo" : "")}">
    <div class="fhead"><span class="ftag">${it.kind}</span>
      <span class="fdate">${d}${raw(it.time ? " " + esc(it.time) : "")}</span>
      ${raw(it.via === "web" ? '<span class="fvia" title="폰에서 남김">📱</span>' : "")}
      <span class="grow"></span>
      ${raw(it.memo ? `<button class="linky fdel" data-i="${it.i}">지우기</button>` : "")}</div>
    <div class="ftext">${it.text}</div></li>`;
}

/** 고객 상세의 피드 칸을 그리고 단다. ctx: {sheetId, tab} */
export async function paint(box, cr, ctx) {
  if (!box) return;
  const name = String((cr.values || {}).customer || "").trim();
  const ukey = `uid:${ctx.sheetId}:${cr.row}:${name}`;
  let uid = (await store.get("meta", ukey)) || "";
  let memo = uid ? await notes.cached(uid) : [];

  render(box, html`
    <form class="feedadd" id="fadd">
      <textarea id="fnote" rows="2" maxlength="500"
        placeholder="메모 남기기 — 예: 통화함, 보증금 문의 (PC 고객 이력에도 남습니다)"></textarea>
      <button class="primary" id="fsave" type="submit">남기기</button>
    </form>
    <ul class="feed" id="flist"><li class="empty">불러오는 중…</li></ul>`);

  const draw = () => {
    const list = $("#flist", box);
    if (!list) return;
    const vis = notes.visible(memo);
    const items = [
      ...autoEvents(cr).filter((e) => !e.future),
      ...vis.map((n) => ({ date: n.date, time: n.time, kind: "메모", text: n.text,
                           via: n.via, memo: true, i: memo.indexOf(n) })),
    ].sort((a, b) => (String(b.date) + (b.time || "")).localeCompare(String(a.date) + (a.time || "")));
    // 만기는 앞날이라 맨 아래 따로(지나온 기록을 가리지 않게) — PC 와 같다
    items.push(...autoEvents(cr).filter((e) => e.future));
    render(list, items.length ? items.map(line).join("")
      : html`<li class="empty">아직 기록이 없습니다. 위에 첫 메모를 남겨 보세요.</li>`);
    for (const b of $$(".fdel", list)) b.onclick = () => del(memo[Number(b.dataset.i)]);
  };
  draw();

  // 고객ID — 처음 열면 U열에서 읽는다(없으면 메모를 처음 남길 때 만든다)
  try {
    if (!uid) {
      const got = await sheets.readUid(ctx.sheetId, ctx.tab, cr.row);
      if (got.name && got.name !== name) throw new Error("moved");
      uid = got.uid;
      if (uid) await store.put("meta", ukey, uid);
    }
    if (uid) { memo = await notes.cached(uid); draw(); memo = await notes.load(uid); }
    draw();
  } catch (e) {
    if (e.message === "moved") {
      render($("#flist", box), html`<li class="empty">시트가 바뀌어 이 줄의 고객이 달라졌습니다.
        목록을 새로 불러온 뒤 다시 열어 주세요.</li>`);
      return;
    }
    draw();
    paintState();
  }

  async function ensureUid() {
    if (uid) return uid;
    const got = await sheets.readUid(ctx.sheetId, ctx.tab, cr.row);
    if (got.name !== name) throw new Error("이 줄의 고객이 바뀌었습니다. 목록을 새로 불러와 주세요.");
    uid = got.uid || sheets.newUid();
    if (!got.uid) {
      try { await sheets.writeUid(ctx.sheetId, ctx.tab, cr.row, uid); }
      catch (e) {
        if (e instanceof sheets.NeedSignIn || e instanceof sheets.Offline
            || e instanceof sheets.NeedScope) throw e;
        throw new Error("고객ID 칸(U열)이 아직 없습니다. PC 앱에서 이 고객의 [이력] 을 한 번 열어 주세요.");
      }
    }
    await store.put("meta", ukey, uid);
    return uid;
  }

  async function del(note) {
    if (!note || !confirm("이 메모를 지울까요?\n(PC 고객 이력에서도 지워집니다)")) return;
    try {
      memo = await notes.remove(await ensureUid(), note);
      draw();
    } catch (e) { fail(e); }
  }

  function fail(e) {
    toast(e instanceof sheets.NeedSignIn ? "로그인한 뒤에 남길 수 있어요."
      : e instanceof sheets.Offline ? "인터넷에 연결되지 않았어요."
      : e instanceof sheets.NeedScope ? "권한이 모자랍니다. 위 [다시 로그인] 을 눌러 주세요."
      : (e.message || "메모를 남기지 못했습니다."), { tone: "bad" });
    paintState();
  }

  $("#fadd", box).onsubmit = async (ev) => {
    ev.preventDefault();
    const ta = $("#fnote", box);
    const text = ta.value.trim();
    if (!text) { ta.focus(); return; }
    const btn = $("#fsave", box);
    btn.disabled = true;
    try {
      memo = await notes.add(await ensureUid(), text);
      ta.value = "";
      draw();
      toast("메모를 남겼어요. PC 고객 이력에도 뜹니다.");
    } catch (e) { fail(e); }
    btn.disabled = false;
  };
}
