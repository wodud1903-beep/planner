// 인증번호(v1.32) — 폰에서 오늘 온 인증번호를 크게 보고, 눌러서 복사한다.
//
// PC 앱은 팝업으로 띄운다. 밖에서(PC 가 없을 때) 폰으로 확인할 길이 없어서 이 화면을 둔다.
// 보고 있는 동안만 4초마다 시트 맨 위 몇 줄을 읽는다 — 다른 화면으로 가거나 폰을 끄면 멈춘다.
import { html, raw, esc, render, $, $$ } from "./dom.js";
import * as otp from "../otp.js";
import * as sheets from "../sheets.js";
import * as store from "../store.js";
import * as router from "../router.js";
import * as auth from "../auth.js";
import { setBody, markTab, paintState, toast } from "./chrome.js";
import { icon } from "./icons.js";

let _where = null;       // {id, tab}
let _items = [];
let _seen = null;        // 이 화면을 연 뒤 본 줄 열쇠(새로 온 것을 가려 강조한다)
let _fresh = new Set();
let _err = "";
let _timer = 0;
let _busy = false;
let _wait = 0;           // 탈나면 이만큼 건너뛴다(끝없이 조르지 않게)

const here = () => { const c = router.current(); return !!c && c.path === "/otp" && !!$("#otplist"); };

function stop() { clearInterval(_timer); _timer = 0; }

async function where() {
  if (_where) return _where;
  // PC 설정에서 시트를 바꿨으면 그쪽을 따른다(boot.js 가 켤 때 받아 둔다) — 없으면 지점 기본 시트
  _where = otp.whereOf(await store.get("meta", "pcCfg"));
  return _where;
}

async function tick() {
  if (!here()) { stop(); return; }
  if (_busy || document.visibilityState !== "visible") return;
  if (_wait > 0) { _wait -= 1; return; }
  _busy = true;
  try {
    const got = await otp.read(await where());
    if (_seen) for (const it of got) if (!_seen.has(it.key)) _fresh.add(it.key);
    const first = !_seen;
    _seen = new Set([...(first ? [] : _seen), ...got.map((x) => x.key)]);
    const news = got.filter((x) => _fresh.has(x.key)).length;
    const changed = JSON.stringify(got.map((x) => x.key)) !== JSON.stringify(_items.map((x) => x.key));
    _items = got;
    _err = "";
    if (changed && !first && news) { try { navigator.vibrate && navigator.vibrate(120); } catch (e) { /* 없어도 된다 */ } }
  } catch (e) {
    _err = e instanceof sheets.NeedSignIn ? "구글 로그인이 필요합니다. 위 [로그인] 을 눌러 주세요."
      : e instanceof sheets.Offline ? "인터넷에 연결되지 않았습니다."
      : e instanceof sheets.NeedScope ? "시트 권한이 아직 없습니다. 위 [다시 로그인] 을 눌러 허용해 주세요."
      : (e instanceof sheets.WrongAccount || e instanceof sheets.BadRange)
        ? "이 계정으로는 인증문자 시트를 볼 수 없습니다. 지점장에게 시트 공유를 요청하세요."
        : (e && e.message) || "인증문자 시트를 읽지 못했습니다.";
    // 권한이 없으면 기다려도 안 풀린다 → 드물게만 다시 본다(약 2분). 그 밖엔 30초쯤 뒤
    _wait = (e instanceof sheets.WrongAccount || e instanceof sheets.BadRange) ? 30 : 7;
    paintState();
  } finally {
    _busy = false;
  }
  paint();
}

function paint() {
  const box = $("#otplist");
  if (!box) return;
  const live = $("#otplive");
  if (live) {
    live.className = "otplive" + (_err ? " off" : "");
    live.textContent = _err ? "멈춤" : "새 문자를 기다리는 중 — 오면 바로 보입니다";
  }
  if (_err && !_items.length) {
    render(box, `<p class="empty">${esc(_err)}</p>`);
    return;
  }
  if (!_items.length) {
    render(box, `<p class="empty">${_seen ? "오늘 온 인증번호가 없습니다." : "불러오는 중…"}</p>`);
    return;
  }
  render(box, (_err ? `<p class="s" style="color:var(--bad)">${esc(_err)}</p>` : "")
    + _items.map((it, i) => `<div class="otpcard${_fresh.has(it.key) ? " fresh" : ""}">
        <button class="otpcode" data-i="${i}" aria-label="인증번호 ${esc(it.code)} 복사">${esc(it.code)}</button>
        <div class="otpmeta"><b>${esc(it.sender || "인증번호")}${_fresh.has(it.key) ? " · 방금" : ""}</b>
          <span>${esc(it.body)}</span></div>
        <button class="chip" data-i="${i}">복사</button>
      </div>`).join(""));
  for (const b of $$("#otplist [data-i]")) {
    b.onclick = () => {
      const it = _items[+b.dataset.i];
      if (!it) return;
      navigator.clipboard.writeText(it.code)
        .then(() => toast(`${it.code} 복사했어요.`))
        .catch(() => toast("복사하지 못했습니다 — 번호를 길게 눌러 복사하세요.", { tone: "bad" }));
    };
  }
}

export async function screen() {
  markTab("/agenda");
  _seen = null;
  _fresh = new Set();
  _wait = 0;
  _where = null;           // 그사이 PC 설정이 바뀌었을 수 있다
  setBody(html`
    <div class="pane narrow">
      <button class="chip backbtn2" id="otpback">← 홈</button>
      <section class="card" style="margin-top:10px">
        <div class="cardhead">
          <h3 class="cardtitle">${raw(icon("check", 18))}휴대폰 인증번호</h3>
          <span class="grow"></span><span class="otplive" id="otplive"></span>
        </div>
        <div id="otplist"></div>
      </section>
      <p class="synced">${auth.email() ? esc(auth.email()) + " · " : ""}오늘 온 문자만 보입니다 ·
        번호를 누르면 복사됩니다 · 이 화면을 보고 있는 동안만 확인합니다</p>
    </div>`);
  $("#otpback").onclick = () => router.go("/agenda");
  paint();
  stop();
  _timer = setInterval(tick, otp.POLL_MS);
  tick();
}

// 화면으로 돌아오면 바로 한 번 본다(폰을 켰을 때 4초를 기다리지 않게)
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && here()) { _wait = 0; tick(); }
});

/** 계정이 바뀌면 앞사람이 보던 것을 지운다(boot.js). */
export async function load({ refresh = true } = {}) {
  if (!refresh) { _items = []; _seen = null; _fresh = new Set(); _where = null; _err = ""; paint(); }
}
