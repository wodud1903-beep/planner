// 켤 때 하는 일.
//
// 순서가 중요하다: **캐시로 먼저 그리고**, 그 다음에 조용히 새로 받는다.
// 로그인이나 네트워크를 기다리며 빈 화면을 보여 주지 않는다.
import { shell, paintState } from "./ui/chrome.js";
import * as router from "./router.js";
import * as auth from "./auth.js";
import * as store from "./store.js";
import * as appdata from "./appdata.js";
import * as kbui from "./ui/kb.js";
import * as cust from "./ui/customers.js";
import * as docs from "./ui/docs.js";
import * as agenda from "./ui/agenda.js";
import * as calc from "./ui/calc.js";
import * as about from "./ui/about.js";

const BUILD_CHECK_MS = 5 * 60 * 1000;
let _lastCheck = 0;
let _touched = false;          // 사용자가 이 화면을 만졌나 (갱신을 미룰지 판단)

document.getElementById("app").innerHTML = shell();
addEventListener("pointerdown", () => { _touched = true; }, { once: true, capture: true });
addEventListener("keydown", () => { _touched = true; }, { once: true, capture: true });

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

router.on(/^\/kb\/(\d+)$/, (m) => kbui.screen(m));
router.on(/^\/kb$/, () => kbui.screen(null));
router.on(/^\/about$/, () => about.screen());
router.on(/^\/agenda$/, () => agenda.screen());
router.on(/^\/calc$/, () => calc.screen());
router.on(/^\/customers\/settings$/, () => cust.settingsScreen());
router.on(/^\/customers\/(\d+)$/, (m) => cust.screen(m));
router.on(/^\/customers$/, () => cust.screen(null));
router.on(/^\/docs\/([^/]+)$/, (m) => docs.screen(m));
router.on(/^\/docs$/, () => docs.screen(null));


(async function start() {
  // ⚠️ 누구로 로그인했는지 **먼저** 알아낸다. 모르는 채로 그리면 앞사람 자료를
  //    그대로 보여 주고, 앞사람 시트를 조회하기까지 한다(실제로 그랬다).
  //    통신이 늦으면 4초에 포기하고 이 기기의 마지막 사람으로 본다.
  try {
    const who = await auth.ensureEmail({ timeoutMs: 4000 });
    if (who) await store.useAccount(who);
  } catch (e) { /* 못 알아내면 마지막 사람으로 본다 */ }

  // 이 기기에 아직 없는 설정은 **계정에 저장된 것**으로 채운다.
  // PC 앱이 올려 둔 것도 그대로 읽으므로, PC 에서 쓰시던 분은 폰에서
  // 시트 주소나 서류 폴더를 따로 넣을 일이 없다.
  await pullSettings();

  await cust.loadSettings();          // 시트 주소·탭은 라우팅 전에 읽어 둔다
  const ui = await store.ui();
  if (!location.hash && ui.route) location.hash = ui.route;
  router.start();
  addEventListener("hashchange", () => store.ui({ route: location.hash.slice(1) }));

  // 화면이 뜬 다음에 조용히 로그인·자료 받기
  setTimeout(async () => {
    await auth.token();                 // 조용한 시도 (실패해도 화면은 그대로)
    paintState();
    kbui.load();
    cust.load();
    docs.load();
    agenda.load();
    calc.load();
  }, 0);

  registerSW();
})();

async function pullSettings() {
  try {
    const have = await store.get("meta", "sheet");
    const folder = await store.get("meta", "driveFolder");
    if (have && have.id && folder) return;      // 이 기기에 이미 다 있다
    const got = await appdata.loadSettings();
    if (!got) return;
    if ((!have || !have.id) && got.sheetId) {
      await store.put("meta", "sheet",
                      { id: got.sheetId, tab: got.sheetTab || "미출고차량" });
    }
    if (!folder && got.driveFolder) await store.put("meta", "driveFolder", got.driveFolder);
  } catch (e) {
    // 권한이 아직 없거나(다시 로그인 전) 통신이 안 되면 그냥 넘어간다.
    // 이 기기에 저장된 값이 있으면 그것으로 계속 쓴다.
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
    store.ui({ route: location.hash.slice(1) }).then(() => {
      w.postMessage({ type: "SKIP_WAITING" });
    });
  };
  swc.addEventListener("controllerchange", () => location.reload());
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
