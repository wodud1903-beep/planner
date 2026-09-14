// 켤 때 하는 일.
//
// 순서가 중요하다: **캐시로 먼저 그리고**, 그 다음에 조용히 새로 받는다.
// 로그인이나 네트워크를 기다리며 빈 화면을 보여 주지 않는다.
import { shell, paintState } from "./ui/chrome.js";
import * as router from "./router.js";
import * as auth from "./auth.js";
import * as store from "./store.js";
import * as kbui from "./ui/kb.js";
import * as cust from "./ui/customers.js";
import * as docs from "./ui/docs.js";
import * as about from "./ui/about.js";

const BUILD_CHECK_MS = 5 * 60 * 1000;
let _lastCheck = 0;
let _touched = false;          // 사용자가 이 화면을 만졌나 (갱신을 미룰지 판단)

document.getElementById("app").innerHTML = shell();
addEventListener("pointerdown", () => { _touched = true; }, { once: true, capture: true });
addEventListener("keydown", () => { _touched = true; }, { once: true, capture: true });

auth.init();
auth.onChange(paintState);
paintState();

router.on(/^\/kb\/(\d+)$/, (m) => kbui.screen(m));
router.on(/^\/kb$/, () => kbui.screen(null));
router.on(/^\/about$/, () => about.screen());
router.on(/^\/customers\/settings$/, () => cust.settingsScreen());
router.on(/^\/customers\/(\d+)$/, (m) => cust.screen(m));
router.on(/^\/customers$/, () => cust.screen(null));
router.on(/^\/docs\/([^/]+)$/, (m) => docs.screen(m));
router.on(/^\/docs$/, () => docs.screen(null));


(async function start() {
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
  }, 0);

  registerSW();
})();

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
