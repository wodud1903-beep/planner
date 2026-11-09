// 업무자료검색 웹 — 홈 화면 앱 · 인터넷 없이 열기(서비스워커).
//
// 화면 파일(HTML·JS·CSS·아이콘)만 받아 둔다. 자료는 app.js 가 브라우저 저장소에 따로 둔다.
//   · 늘 **인터넷 먼저** — 새로 배포한 것을 바로 쓴다(지금과 같다).
//   · 화면(HTML)은 인터넷이 끊겼거나 2.5초 안에 답이 없으면 받아 둔 것을 쓴다(지하 주차장 등).
//     그렇게 연 창은 JS·CSS 도 받아 둔 것을 쓴다 — 새 HTML 에 옛 JS 가 섞이면 화면이 깨질 수 있어서다.
//   · 받아 둔 것은 인터넷으로 제대로 연 때에만 새로 바꾼다(늘 한 벌로 맞게).
//   · /api/*(자료·로그인·스위치·첨부)와 다른 주소(구글 등)는 건드리지 않는다
//     — 로그인과 '서버 끄기' 가 그대로 돈다.
// 화면 파일 목록(SHELL)을 바꾸면 VERSION 도 올린다 → 새 판이 깔리며 한꺼번에 새로 받는다.
const VERSION = "kbweb-2026-11-09";
const SHELL = [
  "/", "/app.js", "/kb.js", "/hangul.js", "/sync.js", "/style.css", "/icon.svg",
  "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png",
  "/icons/maskable-512.png", "/icons/apple-touch-icon.png",
];
const SLOW_MS = 2500;
const fromCache = new Set();        // 받아 둔 화면으로 연 창(clientId)

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(VERSION);
    // 하나가 안 받아져도 나머지는 받아 둔다(설치가 통째로 실패하지 않게)
    await Promise.all(SHELL.map((u) => fetch(new Request(u, { cache: "reload" }))
      .then((r) => (r.ok ? c.put(u, r) : null)).catch(() => null)));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== VERSION) await caches.delete(k);
    await self.clients.claim();
  })());
});

/** 화면(HTML) — 인터넷 먼저. 끊겼거나 느리면 받아 둔 것. */
async function page(e) {
  const c = await caches.open(VERSION);
  const saved = await c.match("/");
  const net = fetch(e.request);
  if (!saved) return net;                    // 받아 둔 것이 없으면 기다릴 수밖에
  net.catch(() => {});                       // 늦게 실패해도 오류를 남기지 않게
  let timer = 0;
  const slow = new Promise((ok) => { timer = setTimeout(() => ok("slow"), SLOW_MS); });
  try {
    const r = await Promise.race([net, slow]);
    if (r !== "slow") {
      clearTimeout(timer);
      if (r.ok && r.type === "basic") await c.put("/", r.clone()).catch(() => {});
      return r;
    }
  } catch (err) { /* 인터넷이 끊겼다 */ }
  clearTimeout(timer);
  if (e.resultingClientId) fromCache.add(e.resultingClientId);
  return saved;
}

/** JS·CSS·아이콘 — 받아 둔 화면으로 연 창이면 받아 둔 것, 아니면 인터넷 먼저(끊기면 받아 둔 것). */
async function asset(e, key) {
  const c = await caches.open(VERSION);
  if (e.clientId && fromCache.has(e.clientId)) {
    const saved = await c.match(key);
    if (saved) return saved;
  }
  try {
    const r = await fetch(e.request);
    if (r.ok && r.type === "basic") c.put(key, r.clone()).catch(() => {});
    return r;
  } catch (err) {
    const saved = await c.match(key);
    if (saved) return saved;
    throw err;
  }
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const u = new URL(req.url);
  if (u.origin !== self.location.origin) return;            // 구글·글꼴 등은 브라우저가 알아서
  if (u.pathname.startsWith("/api/") || u.pathname === "/sw.js") return;
  if (req.mode === "navigate") {
    // 어떤 주소로 열어도(/?auth=… · /#자료) 화면은 하나다
    if (u.pathname === "/" || u.pathname === "/index.html") e.respondWith(page(e));
    return;
  }
  if (SHELL.includes(u.pathname) && !u.search) e.respondWith(asset(e, u.pathname));
});
