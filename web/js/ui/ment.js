// 멘트 · 명함 보내기(v1.37, H2) — 폰에서 채널마다 [상담후] [부재중] [명함] 을 눌러 카카오톡으로.
//
// 지점장: "폰 웹 멘트·명함 보내기". PC [멘트복사] 와 같은 글 · 같은 명함(계산은 ../ment.js).
//   · 누르면 폰의 공유 창이 열린다 → 카카오톡을 고르면 끝. 글은 클립보드에도 넣어 둔다(붙여넣기도 되게).
//   · 공유 창이 없는 기기(PC 브라우저 등)는 복사만 — '복사했어요' 로 알린다.
//   · 명함은 그림 파일로 공유한다. 누르자마자 보내지게(그래야 폰이 공유 창을 열어 준다) 화면을 열 때 미리 받아 둔다.
//   · PC 에서 명함을 올리지 않은 채널은 [명함] 이 꺼진다(PC 와 같다). 고치는 곳은 PC 한 곳.
import { html, raw, esc, render, $, $$ } from "./dom.js";
import * as store from "../store.js";
import * as router from "../router.js";
import * as auth from "../auth.js";
import * as appdata from "../appdata.js";
import * as sheets from "../sheets.js";
import * as M from "../ment.js";
import { setBody, markTab, paintState, toast } from "./chrome.js";
import { icon } from "./icons.js";

let _items = [];          // [{name, after, miss}]
let _cards = {};          // 열쇠 → {md5, blob}
let _keys = [];           // _items 와 같은 차례의 명함 열쇠
let _err = "";
let _at = 0;
let _loading = false;

const here = () => { const c = router.current(); return !!c && c.path === "/ment" && !!$("#mentlist"); };

export async function screen() {
  markTab("/agenda");
  setBody(html`
    <div class="pane narrow">
      <button class="chip backbtn2" id="mentback">← 홈</button>
      <section class="card" style="margin-top:10px">
        <div class="cardhead">
          <h3 class="cardtitle">${raw(icon("send", 18))}멘트 · 명함 보내기</h3>
          <span class="grow"></span>
        </div>
        <p class="s mentnote">누르면 공유 창이 열립니다 — <b>카카오톡</b>을 고르세요. 글은 클립보드에도 복사됩니다.</p>
        <div id="mentlist"></div>
      </section>
      <p class="synced" id="mentsync"></p>
    </div>`);
  $("#mentback").onclick = () => router.go("/agenda");
  if (!_items.length) {
    const c = await store.get("data", "ment");
    if (c && Array.isArray(c.items)) { _items = c.items; _cards = c.cards || {}; _keys = c.keys || []; _at = c.at || 0; }
  }
  paint();
  load();
}

/** 계정에서 글(PC 묶음) · 명함(앱 전용 공간)을 받는다 — 바뀐 명함만 새로 받는다.
 *  refresh=false: 계정이 바뀌었다 — 앞사람 것을 비우고(저장본도 이미 지워졌다) 받지는 않는다. */
export async function load({ refresh = true } = {}) {
  if (!refresh) {
    const c = await store.get("data", "ment");
    _items = c && Array.isArray(c.items) ? c.items : [];
    _cards = (c && c.cards) || {};
    _keys = (c && c.keys) || [];
    _at = (c && c.at) || 0;
    _err = "";
    return;
  }
  if (_loading) return;
  _loading = true;
  try {
    const files = await appdata.readPcFiles(["greetings.json", "deleted.json"]);
    const items = M.liveGreetings(files["greetings.json"], files["deleted.json"]);
    const keys = await Promise.all(items.map((it) => M.bizKey(it.name)));
    const list = await appdata.listApp("bizcard_");
    const cards = {};
    for (const key of keys) {
      const f = list[M.cardFile(key)];
      if (!f) continue;
      const had = _cards[key];
      if (had && had.blob && had.md5 && had.md5 === f.md5) { cards[key] = had; continue; }
      const blob = await appdata.readAppBlob(f.id);
      if (blob && blob.size) cards[key] = { md5: f.md5, blob };
    }
    _items = items;
    _keys = keys;
    _cards = cards;
    _err = "";
    _at = Date.now();
    try { await store.put("data", "ment", { items, keys, cards, at: _at }); } catch (e) { /* 저장 못 해도 화면은 된다 */ }
  } catch (e) {
    _err = e instanceof sheets.NeedSignIn ? "구글 로그인이 필요합니다. 위 [로그인] 을 눌러 주세요."
      : e instanceof sheets.Offline ? "인터넷에 연결되지 않았습니다 — 저장해 둔 것으로 보여 드립니다."
      : e instanceof sheets.NeedScope ? "권한이 아직 없습니다. 위 [다시 로그인] 을 눌러 허용해 주세요."
      : (e && e.message) || "멘트를 불러오지 못했습니다.";
    paintState();
  } finally {
    _loading = false;
  }
  if (here()) paint();
}

function paint() {
  const box = $("#mentlist");
  if (!box) return;
  if (!_items.length) {
    render(box, `<p class="empty">${esc(_err || "불러오는 중…")}</p>`);
  } else {
    render(box, (_err ? `<p class="s" style="color:var(--bad)">${esc(_err)}</p>` : "")
      + _items.map((it, i) => {
        const has = !!_cards[_keys[i]];
        return `<div class="mentrow">
          <b class="mentname">${esc(it.name)}</b>
          <div class="mentbtns">
            <button class="mentbtn after" data-act="after" data-i="${i}" ${it.after ? "" : "disabled"}>상담후</button>
            <button class="mentbtn miss" data-act="miss" data-i="${i}" ${it.miss ? "" : "disabled"}>부재중</button>
            <button class="mentbtn card" data-act="card" data-i="${i}" ${has ? "" : "disabled"}
              title="${has ? "명함 사진 보내기" : "PC [멘트복사] 에서 이 채널의 명함을 올리면 켜집니다"}">명함</button>
          </div>
        </div>`;
      }).join(""));
    for (const b of $$("#mentlist [data-act]")) b.onclick = () => act(b.dataset.act, +b.dataset.i);
  }
  const sync = $("#mentsync");
  if (sync) {
    const when = _at ? new Date(_at) : null;
    sync.textContent = (auth.email() ? auth.email() + " · " : "")
      + "PC [멘트복사] 의 글 · 명함 그대로 · 고치는 곳은 PC"
      + (when ? ` · ${when.getHours()}:${String(when.getMinutes()).padStart(2, "0")} 받음` : "");
  }
}

function act(kind, i) {
  const it = _items[i];
  if (!it) return;
  if (kind === "card") { sendCard(it, _cards[_keys[i]]); return; }
  sendText(it[kind] || "", `${it.name} ${kind === "after" ? "상담후" : "부재중"}`);
}

/** 글 — 클립보드에 넣고 공유 창을 연다(누른 그 자리에서 — 미루면 폰이 공유 창을 막는다). */
function sendText(text, label) {
  if (!text) return;
  let copied = null;
  try { copied = navigator.clipboard ? navigator.clipboard.writeText(text) : null; } catch (e) { copied = null; }
  if (navigator.share) {
    navigator.share({ text }).catch((e) => {
      if (e && e.name === "AbortError") return;           // 공유 창을 닫았다 — 클립보드엔 이미 있다
      told(copied, label);
    });
    return;
  }
  told(copied, label);
}

function told(copied, label) {
  if (!copied) { toast("복사하지 못했습니다 — 이 기기에서는 공유 · 복사를 쓸 수 없습니다.", { tone: "bad" }); return; }
  copied.then(() => toast(`${label} — 복사했어요. 카카오톡 대화창에 붙여 넣으세요.`),
    () => toast("복사하지 못했습니다.", { tone: "bad" }));
}

/** 명함 — 그림 파일로 공유. 공유를 못 하면 그림을 클립보드에, 그것도 안 되면 그림을 열어 길게 눌러 저장하게. */
function sendCard(it, card) {
  if (!card || !card.blob) { toast("이 채널은 아직 명함이 없습니다 — PC [멘트복사] 에서 올려 주세요."); return; }
  const file = new File([card.blob], M.cardName(it.name), { type: "image/png" });
  if (navigator.canShare && navigator.canShare({ files: [file] }) && navigator.share) {
    navigator.share({ files: [file] }).catch((e) => {
      if (e && e.name === "AbortError") return;
      copyImage(card.blob, it.name);
    });
    return;
  }
  copyImage(card.blob, it.name);
}

function copyImage(blob, name) {
  try {
    if (navigator.clipboard && window.ClipboardItem) {
      navigator.clipboard.write([new ClipboardItem({ "image/png": blob })])
        .then(() => toast(`${name} 명함 — 복사했어요. 카카오톡 대화창에 붙여 넣으세요.`),
          () => openImage(blob));
      return;
    }
  } catch (e) { /* 아래로 */ }
  openImage(blob);
}

function openImage(blob) {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  toast("명함을 새 창에 열었어요 — 길게 눌러 저장하거나 공유하세요.");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
