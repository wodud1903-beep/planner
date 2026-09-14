// 웹앱을 진짜 브라우저(headless Chromium)로 띄워 확인한다.
//   NODE_PATH=/opt/node22/lib/node_modules PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
//     node web/verify/verify_web.mjs
import { createRequire } from "node:module";

// ⚠️ ESM 의 import 는 NODE_PATH 를 보지 않는다. 이 컨테이너의 playwright 는
//    전역(/opt/node22/lib/node_modules)에만 있어서 `import "playwright"` 가 죽는다.
//    CommonJS 의 require 는 NODE_PATH 를 보므로 이 길로 부른다.
//    (저장소에 npm 으로 깔아도 그대로 동작한다 — 그쪽이 먼저 잡힌다)
const { chromium } = createRequire(import.meta.url)("playwright");
import { serve } from "./serve.mjs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { readFileSync, readdirSync, statSync } from "node:fs";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
let fails = 0;
const ok = (name, cond, extra = "") => {
  console.log((cond ? "  OK  " : "  ** FAIL **  ") + name + (extra ? "  " + extra : ""));
  if (!cond) fails++;
};

// ---------------------------------------------------------------- 정적 검사
console.log("\n[1] 경로 — Pages 는 /planner/ 하위다");
const files = [];
(function walk(d, base = "") {
  for (const n of readdirSync(d)) {
    if (n === "verify" || n === "node_modules") continue;
    const p = join(d, n);
    if (statSync(p).isDirectory()) walk(p, base + n + "/");
    else files.push(base + n);
  }
})(WEB);
const texts = files.filter((f) => /\.(html|js|css|webmanifest|json)$/.test(f));
let absBad = [];
for (const f of texts) {
  const s = readFileSync(join(WEB, f), "utf-8");
  for (const m of s.matchAll(/(?:src|href)="(\/[^/][^"]*)"/g)) absBad.push(`${f}: ${m[1]}`);
}
ok("절대경로(src=\"/…\")가 없다", absBad.length === 0, absBad.join(", "));
const mani = JSON.parse(readFileSync(join(WEB, "manifest.webmanifest"), "utf-8"));
ok("매니페스트 start_url/scope 가 상대경로", mani.start_url === "./" && mani.scope === "./");
ok("아이콘 192·512·maskable 이 다 있다",
   mani.icons.length === 3 && mani.icons.some((i) => i.purpose === "maskable"));
ok("한국어로 표시된다", mani.lang === "ko" && mani.display === "standalone");

console.log("\n[2] 프리캐시 목록이 실제 파일과 맞는지");
const sw = readFileSync(join(WEB, "sw.js"), "utf-8");
const pre = [...sw.matchAll(/"(\.\/[^"]+)"/g)].map((m) => m[1].slice(2)).filter((x) => x);
const onDisk = new Set(files);
const missing = pre.filter((p) => p && p !== "" && p !== "CHANGELOG.md" && !onDisk.has(p));
ok("프리캐시에 적힌 파일이 전부 있다", missing.length === 0, missing.join(", "));
// sw.js 와 version.json 은 일부러 뺀다.
//   sw.js  — 서비스워커 자신. 브라우저가 캐시를 거치지 않고 직접 받아야
//            새 판으로 갈아탈 수 있다. 캐시에 넣으면 영영 옛 워커에 갇힌다.
//   version.json — 매번 no-store 로 찍어 보는 파일이라 캐시하면 뜻이 없다.
const SELF = new Set(["sw.js", "version.json"]);
const notPre = texts.filter((f) => !pre.includes(f) && !SELF.has(f));
ok("모든 파일이 프리캐시에 올라 있다", notPre.length === 0, notPre.join(", "));

// ---------------------------------------------------------------- 브라우저
const s = await serve(WEB, { port: 8123, build: "A" });
const browser = await chromium.launch();

async function page(ctx) {
  const p = await ctx.newPage();
  p.on("pageerror", (e) => { console.log("  ** 페이지 오류 **", e.message); fails++; });
  return p;
}

console.log("\n[3] 뜬다 · 화면이 그려진다");
let ctx = await browser.newContext();
let p = await page(ctx);
const reqs = [];
p.on("request", (r) => reqs.push(r.url()));
await p.goto(s.url, { waitUntil: "networkidle" });
ok("탭 네 개가 보인다", (await p.locator("nav.tabs a").count()) === 4);
ok("제목이 나온다", (await p.locator("header h1").textContent()).includes("일정관리기"));
const b404 = reqs.filter((u) => u.startsWith("http://localhost") && !u.includes("gsi"));
const statuses = await Promise.all(b404.map(async (u) => (await p.request.get(u)).status()));
ok("불러온 파일이 전부 200 이다",
   statuses.every((x) => x === 200), statuses.filter((x) => x !== 200).join(","));

console.log("\n[4] 로그인 없이도 화면이 산다");
await p.click('nav.tabs a[data-tab="/about"]');
await p.waitForTimeout(400);
ok("정보 화면이 열린다", (await p.locator("#clog").count()) === 1);
await p.waitForFunction(() => document.querySelector("#clog details"), null, { timeout: 4000 })
  .catch(() => {});
const nsec = await p.locator("#clog details").count();
ok("변경 이력을 읽어 절로 나눈다", nsec > 50, nsec + "개 버전");
ok("첫 절이 펼쳐져 있다", await p.locator("#clog details[open]").count() === 1);
ok("■ 소제목이 그려진다", (await p.locator("#clog .kbhead").count()) > 0);

console.log("\n[5] 자료검색 — 로그인 전에도 빈 화면이 아니다");
await p.click('nav.tabs a[data-tab="/kb"]');
await p.waitForTimeout(300);
ok("검색창이 있다", (await p.locator("#kbq").count()) === 1);
ok("탭 표시가 자료로 옮겨간다",
   (await p.locator('nav.tabs a[data-tab="/kb"][aria-current="page"]').count()) === 1);

console.log("\n[6] 서비스워커 — 켤 때 자동으로 새 판을 집는다");
await p.waitForFunction(() => navigator.serviceWorker.controller !== null, null, { timeout: 8000 })
  .catch(() => {});
const swOn = await p.evaluate(() => !!navigator.serviceWorker.controller);
ok("서비스워커가 화면을 맡는다", swOn);
const cachesA = await p.evaluate(() => caches.keys());
ok("빌드 이름이 붙은 캐시가 하나다",
   cachesA.length === 1 && cachesA[0] === "app-A", cachesA.join(","));
// 배포를 바꾼 척하고 다시 연다
await s.close();
const s2 = await serve(WEB, { port: 8123, build: "B" });
const reqB = [];
p.on("request", (r) => reqB.push(r.url()));
await p.evaluate(() => { /* 만진 적 없음으로 되돌린다 */ });
await p.reload({ waitUntil: "networkidle" });
await p.waitForFunction(async () => (await caches.keys()).includes("app-B"),
                        null, { timeout: 10000 }).catch(() => {});
const cachesB = await p.evaluate(() => caches.keys());
ok("새 빌드 캐시로 갈아탄다", cachesB.includes("app-B"), cachesB.join(","));
ok("옛 캐시는 지워진다", !cachesB.includes("app-A"), cachesB.join(","));

console.log("\n[7] 오프라인에서도 뜬다");
await ctx.setOffline(true);
await p.reload({ waitUntil: "domcontentloaded" }).catch(() => {});
await p.waitForTimeout(600);
ok("오프라인에서 화면이 그려진다",
   (await p.locator("nav.tabs a").count()) === 4);
await ctx.setOffline(false);

console.log("\n[8] 폴드 — 접었다 펴기");
await p.setViewportSize({ width: 412, height: 900 });
await p.click('nav.tabs a[data-tab="/kb"]');
await p.waitForTimeout(300);
const narrow = await p.evaluate(() =>
  getComputedStyle(document.querySelector("#app")).flexDirection);
ok("좁으면 세로로 쌓인다(아래 탭바)", narrow === "column", narrow);
await p.setViewportSize({ width: 880, height: 1100 });
await p.waitForTimeout(300);
const wide = await p.evaluate(() =>
  getComputedStyle(document.querySelector("#app")).flexDirection);
ok("넓으면 옆으로 눕는다(왼쪽 레일)", wide === "row-reverse", wide);
const rail = await p.evaluate(() => {
  const r = document.querySelector("nav.tabs").getBoundingClientRect();
  const b = document.querySelector("#body").getBoundingClientRect();
  return { w: r.width, x: r.x, bodyX: b.x };
});
ok("레일이 세로로 선다", rail.w < 200, Math.round(rail.w) + "px");
// 세로로 서 있기만 보면 #app 이 안 눕는 버그를 놓친다(실제로 놓쳤다).
// 레일이 본문 **왼쪽**에 있는지까지 봐야 잡힌다.
ok("레일이 본문 왼쪽에 붙는다", rail.x < rail.bodyX,
   `rail=${Math.round(rail.x)} body=${Math.round(rail.bodyX)}`);

await browser.close();
await s2.close();
console.log("\n" + (fails ? `${fails}건 실패` : "전부 통과"));
process.exit(fails ? 1 : 0);
