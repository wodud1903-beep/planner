// 서비스워커 — 열면 자동으로 최신이 되게, 단 반쯤 바뀌지 않게.
//
// 핵심 두 가지
//  1) 캐시 이름에 빌드 번호를 넣고, install 에서 **통째로** 받는다(addAll). 그래서
//     한 페이지는 언제나 한 세대의 파일만 본다 — 옛 화면이 새 파일을 섞어 쓰는 일이 없다.
//  2) skipWaiting() 을 **함부로 부르지 않는다.** 그게 반쯤 갱신된 앱을 내보내는
//     대표적인 방법이다. 화면 쪽이 '지금은 안전하다' 고 알려 줄 때만 부른다.

const BUILD = "__BUILD_ID__";
const CACHE = "app-" + BUILD;

// ⚠️ 새 모듈을 만들면 **반드시 여기에도 적어야 한다.** 빌드 단계가 없어서
//    이 목록은 손으로 관리한다. 빼먹으면 온라인에서는 멀쩡히 돌다가
//    오프라인에서만 죽는다 — 제일 늦게 발견되는 종류의 고장이다.
//    verify_web.mjs 의 [2] 가 web/ 의 파일과 이 목록을 대조해 막아 준다.
const PRECACHE = [
  "./", "./index.html", "./manifest.webmanifest", "./CHANGELOG.md",
  "./home.html", "./privacy.html", "./terms.html",
  "./css/app.css",
  "./js/boot.js", "./js/config.js", "./js/store.js", "./js/auth.js",
  "./js/sheets.js", "./js/hangul.js", "./js/fmt.js", "./js/kb.js",
  "./js/customers.js", "./js/drive.js", "./js/commission.js", "./js/gcal.js", "./js/appdata.js",
  "./js/weekly.js",
  "./js/router.js", "./js/theme.js",
  "./js/ui/dom.js", "./js/ui/chrome.js", "./js/ui/kb.js", "./js/ui/about.js",
  "./js/ui/customers.js", "./js/ui/docs.js",
  "./js/ui/split.js", "./js/ui/viewer.js",
  "./js/ui/agenda.js", "./js/ui/calc.js", "./js/ui/weekly.js", "./js/ui/icons.js",
  "./js/notes.js", "./js/ui/feed.js", "./js/board.js", "./js/ui/board.js", "./js/push.js",
  "./js/brief.js", "./js/kbedits.js",
  "./icons/icon-192.png", "./icons/icon-512.png", "./icons/icon-512-maskable.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)));
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;      // 구글 API 는 건드리지 않는다
  if (url.pathname.endsWith("/version.json")) return;    // 늘 새로 받아야 한다
  const path = url.pathname;
  const base = self.location.pathname.replace(/sw\.js$/, "");
  const rel = "./" + (path.startsWith(base) ? path.slice(base.length) : path);
  const key = (rel === "./" || rel === "./index.html") ? "./index.html" : rel;
  if (!PRECACHE.includes(key) && !PRECACHE.includes(rel)) return;
  e.respondWith(
    caches.open(CACHE).then((c) =>
      c.match(key).then((r) => r || c.match(rel) || fetch(e.request))));
});

// ---------------------------------------------------------------- 아침 브리핑 알림
// 서버(api/push/cron)가 보낸 {title, body, url, tag} 를 알림으로 띄운다.
// (주소를 점-빗금으로 시작하는 따옴표 글자로 쓰지 않는다 — 검사가 그 모양을 프리캐시 목록으로 읽는다)
const HOME = "#/agenda";
// tag 가 같으면(같은 날) 새 알림이 옛 것을 바꿔 끼운다 — 두 번 와도 하나만 남는다.
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "일정관리기", {
    body: d.body || "", tag: d.tag || "brief", icon: "./icons/icon-192.png",
    data: { url: d.url || HOME },
  }));
});

// 알림을 누르면 앱을 연다(이미 열려 있으면 그 창으로)
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || HOME,
                      self.registration.scope).href;
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) {
      if (c.url.startsWith(self.registration.scope)) {
        try { await c.navigate(url); } catch (x) { /* 다른 화면이어도 그냥 앞으로 */ }
        return c.focus();
      }
    }
    return self.clients.openWindow(url);
  })());
});
