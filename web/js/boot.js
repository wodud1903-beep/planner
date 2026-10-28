// 켤 때 하는 일.
//
// 순서가 중요하다: **캐시로 먼저 그리고**, 그 다음에 조용히 새로 받는다.
// 로그인이나 네트워크를 기다리며 빈 화면을 보여 주지 않는다.
import { shell, paintState, toast, signIn } from "./ui/chrome.js";
import * as router from "./router.js";
import * as theme from "./theme.js";
import * as auth from "./auth.js";
import * as store from "./store.js";
import * as appdata from "./appdata.js";
import * as kbui from "./ui/kb.js";
import * as cust from "./ui/customers.js";
import * as docs from "./ui/docs.js";
import * as agenda from "./ui/agenda.js";
import * as calc from "./ui/calc.js";
import * as weeklyui from "./ui/weekly.js";
import * as about from "./ui/about.js";

const BUILD_CHECK_MS = 5 * 60 * 1000;
let _lastCheck = 0;
let _touched = false;          // 사용자가 이 화면을 만졌나 (갱신을 미룰지 판단)

document.getElementById("app").innerHTML = shell();
addEventListener("pointerdown", () => { _touched = true; }, { once: true, capture: true });
addEventListener("keydown", () => { _touched = true; }, { once: true, capture: true });

// 로그인 화면에서 돌아왔으면 결과(?auth=…)를 먼저 읽는다 — init() 이 이 탭에 남은
// 앞 토큰을 집기 전에(계정을 바꿨으면 그 토큰은 앞사람 것이다)
const _authFlag = auth.takeReturn();
auth.init();
auth.onChange(paintState);
// 계정이 바뀌면 앞사람 자료를 지우고 화면을 다시 그린다.
// (저장한 것은 기기에 딸린 것이라 계정이 바뀌어도 그냥 남는다 — 그게 새어 나갔다)
auth.onEmail(async (mail) => {
  if (await store.useAccount(mail)) {
    for (const m of [kbui, cust, docs, agenda, calc]) {
      try { await m.load({ refresh: false }); } catch (e) { /* 지운 뒤라 비어 있다 */ }
    }
    router.handle();                 // 지금 화면을 다시 그린다
    for (const m of [kbui, cust, docs, agenda, calc]) {
      try { m.load(); } catch (e) { /* 새 계정으로 다시 받는다 */ }
    }
  }
  paintState();
});
paintState();
// [다시 로그인] 이 끝나면 — 새로고침 없이 보던 화면의 자료만 다시 받는다
addEventListener("planner:reauthed", async () => {
  paintState();
  if (await pullSettings()) await cust.loadSettings();
  for (const m of [kbui, cust, docs, agenda, calc]) {
    try { m.load(); } catch (e) { /* 하나가 탈나도 나머지는 받는다 */ }
  }
});

router.on(/^\/kb\/(\d+)$/, (m) => kbui.screen(m));
router.on(/^\/kb$/, () => kbui.screen(null));
router.on(/^\/about$/, () => about.screen());
router.on(/^\/agenda$/, () => agenda.screen());
router.on(/^\/calc$/, () => calc.screen());
router.on(/^\/customers\/settings$/, () => cust.settingsScreen());
router.on(/^\/customers\/week$/, () => weeklyui.screen());
router.on(/^\/customers\/(\d+)\/edit$/, (m) => cust.editScreen(m));
router.on(/^\/customers\/(\d+)$/, (m) => cust.screen(m));
router.on(/^\/customers$/, () => cust.screen(null));
router.on(/^\/docs\/([^/]+)$/, (m) => docs.screen(m));
router.on(/^\/docs$/, () => docs.screen(null));


(async function start() {
  theme.paintBar();                   // 고른 테마(index.html 이 먼저 넣음)에 위 막대 색을 맞춘다
  try {
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", theme.paintBar);
  } catch (e) { /* 옛 브라우저 */ }
  // ⚠️ 누구로 로그인했는지 **먼저** 알아낸다. 모르는 채로 그리면 앞사람 자료를
  //    그대로 보여 주고, 앞사람 시트를 조회하기까지 한다(실제로 그랬다).
  //    서버 쿠키 방식은 한 번 묻기(보통 0.3~0.6초)라 빠르다. 늦으면 2.5초에
  //    포기하고 이 기기의 마지막 사람으로 본다(예전엔 팝업을 4초씩 기다렸다).
  try {
    const who = await auth.ensureEmail({ timeoutMs: 2500 });
    if (who) await store.useAccount(who);
  } catch (e) { /* 못 알아내면 마지막 사람으로 본다 */ }

  // 이 기기에 아직 없는 설정은 **계정에 저장된 것**으로 채운다.
  // PC 앱이 올려 둔 것도 그대로 읽으므로, PC 에서 쓰시던 분은 폰에서
  // 시트 주소나 서류 폴더를 따로 넣을 일이 없다.
  // ⚠️ 토큰이 이미 있을 때만 기다린다. 없으면(예전 방식) 조용한 로그인 팝업을
  //    4초씩 기다리느라 첫 화면이 늦게 뜬다 — 그때는 화면을 띄운 뒤 뒤에서 한다.
  if (auth.state() === auth.STATE.AUTHED) await pullSettings();

  await cust.loadSettings();          // 시트 주소·탭은 라우팅 전에 읽어 둔다
  // 주소만 치거나 홈 화면 아이콘으로 열면 늘 일정 화면이다(router 기본값).
  // 마지막에 보던 화면으로 가지 않는다 — 업데이트로 다시 불러올 때는 주소의
  // #… 가 그대로 남으므로 보던 화면은 그대로 유지된다.
  router.start();
  tellAuth(_authFlag);

  // 화면이 뜬 다음에 조용히 로그인·자료 받기
  setTimeout(async () => {
    await auth.token();                 // 조용한 시도 (실패해도 화면은 그대로)
    paintState();
    if (await pullSettings()) await cust.loadSettings();
    kbui.load();
    cust.load();
    docs.load();
    agenda.load();
    calc.load();
    // 어느 로그인 방식인지 알아 두고(예전 방식이면 로그인 스크립트를 미리 받는다),
    // 동의 화면에서 빠진 항목이 있으면 알려 준다
    await auth.preload();
    paintState();
    if (auth.missing().length && !_authFlag) tellAuth("partial");
  }, 0);

  registerSW();
})();

// 로그인 화면에서 돌아온 결과를 한 줄로 알린다.
function tellAuth(flag) {
  const again = { action: "로그인", onAction: () => signIn(), sticky: true };
  const say = {
    ok: ["로그인했어요. 이제 이 기기에서는 다시 로그인하지 않아도 됩니다.", {}],
    // 구글은 동의 화면에서 항목마다 체크를 받는다. 하나라도 빼면 그 화면이 안 열린다.
    partial: ["구글 동의 화면에서 빠진 항목이 있어요. [다시 로그인] 을 누르고 "
              + "'모두 선택' 에 체크해 주세요.", { ...again, action: "다시 로그인", tone: "bad" }],
    denied: ["로그인을 취소했어요.", again],
    expired: ["로그인 시간이 지났어요. 한 번만 더 눌러 주세요.", again],
    norefresh: ["로그인을 마무리하지 못했어요. 한 번만 더 로그인해 주세요.", again],
    error: ["로그인 중 문제가 생겼어요. 잠시 뒤 다시 해 주세요.", { ...again, tone: "bad" }],
    unconfigured: ["로그인 서버를 아직 설정하지 않아 예전 방식(팝업)으로 로그인합니다.", again],
  }[flag];
  if (say) toast(say[0], say[1]);
}

/** 새로 채운 것이 있으면 true. */
async function pullSettings() {
  try {
    const have = await store.get("meta", "sheet");
    const folder = await store.get("meta", "driveFolder");
    if (have && have.id && folder) return false;   // 이 기기에 이미 다 있다
    if (auth.state() !== auth.STATE.AUTHED) return false;
    const got = await appdata.loadSettings();
    if (!got) return false;
    let changed = false;
    if ((!have || !have.id) && got.sheetId) {
      await store.put("meta", "sheet",
                      { id: got.sheetId, tab: got.sheetTab || "미출고차량" });
      changed = true;
    }
    if (!folder && got.driveFolder) {
      await store.put("meta", "driveFolder", got.driveFolder);
      changed = true;
    }
    return changed;
  } catch (e) {
    // 권한이 아직 없거나(다시 로그인 전) 통신이 안 되면 그냥 넘어간다.
    // 이 기기에 저장된 값이 있으면 그것으로 계속 쓴다.
    return false;
  }
}

// ---------------------------------------------------------------- 자동 갱신
async function registerSW() {
  // ⚠️ `"serviceWorker" in navigator` 만 보면 안 된다. 속성은 있는데 값이 undefined
  //    이거나 손대면 예외가 나는 곳이 실제로 있다 — 카카오톡 인앱 브라우저,
  //    삼성 인터넷 시크릿 모드, https 가 아닌 주소. 카톡으로 링크를 받아 여는 게
  //    가장 흔한 경로라 여기서 죽으면 앱이 통째로 안 뜬다.
  //    자동 갱신만 못 할 뿐 앱은 멀쩡히 돌아야 한다.
  let swc;
  try { swc = navigator.serviceWorker; } catch (e) { return; }
  if (!swc || typeof swc.register !== "function") return;

  let reg;
  try { reg = await swc.register("./sw.js", { scope: "./" }); }
  catch (e) { return; }
  if (!reg) return;

  const applyIfSafe = () => {
    const w = reg.waiting;
    if (!w) return;
    // 방금 켰거나 방금 앞으로 돌아온 때만 바꾼다. 쓰는 중이면 미룬다.
    if (_touched && document.visibilityState === "visible") return;
    w.postMessage({ type: "SKIP_WAITING" });
  };
  // 새 판이 화면을 넘겨받으면 다시 불러온다. ⚠️ 처음 설치될 때(맡은 워커가 없던 때)도
  // 이 알림이 오는데, 그때 다시 불러오면 첫 방문이 두 번 뜬다 — 그건 건너뛴다.
  const hadController = !!swc.controller;
  swc.addEventListener("controllerchange", () => { if (hadController) location.reload(); });
  reg.addEventListener("updatefound", () => {
    const sw = reg.installing;
    if (sw) sw.addEventListener("statechange", () => {
      if (sw.state === "installed" && reg.waiting) applyIfSafe();
    });
  });

  // GitHub Pages 는 10분 캐시라 서비스워커 자동 확인이 늦다.
  // version.json 을 no-store 로 직접 찍어 보고 다르면 바로 확인시킨다.
  const probe = async () => {
    if (Date.now() - _lastCheck < BUILD_CHECK_MS) return;
    _lastCheck = Date.now();
    try {
      const r = await fetch("./version.json", { cache: "no-store" });
      if (!r.ok) return;
      const { build } = await r.json();
      const cur = (await caches.keys()).find((k) => k.startsWith("app-"));
      if (cur && build && cur !== "app-" + build) { await reg.update(); applyIfSafe(); }
    } catch (e) {}
  };
  probe();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") { _touched = false; probe(); }
  });
}
