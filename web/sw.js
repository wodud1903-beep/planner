// 서비스워커 — 열면 자동으로 최신이 되게, 단 반쯤 바뀌지 않게.
//
// 핵심 두 가지
//  1) 캐시 이름에 빌드 번호를 넣고, install 에서 **통째로** 받는다(addAll). 그래서
//     한 페이지는 언제나 한 세대의 파일만 본다 — 옛 화면이 새 파일을 섞어 쓰는 일이 없다.
//  2) skipWaiting() 을 **함부로 부르지 않는다.** 그게 반쯤 갱신된 앱을 내보내는
//     대표적인 방법이다. 화면 쪽이 '지금은 안전하다' 고 알려 줄 때만 부른다.

const BUILD = "__BUILD_ID__";
const CACHE = "app-" + BUILD;

const PRECACHE = [
  "./", "./index.html", "./manifest.webmanifest", "./CHANGELOG.md",
  "./css/app.css",
  "./js/boot.js", "./js/config.js", "./js/store.js", "./js/auth.js",
  "./js/sheets.js", "./js/hangul.js", "./js/fmt.js", "./js/kb.js",
  "./js/router.js",
  "./js/ui/dom.js", "./js/ui/chrome.js", "./js/ui/kb.js", "./js/ui/about.js",
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
