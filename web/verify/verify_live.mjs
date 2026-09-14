// 진짜로 배포된 사이트를 검사한다.
//
//   NODE_PATH=/opt/node22/lib/node_modules PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
//     node web/verify/verify_live.mjs [주소]
//
// 왜 내려받아서 돌리나:
//   이 컨테이너의 크로미움은 프록시 터널로 TLS 를 못 맺어 바깥 주소에 직접 못 간다
//   (curl 은 된다 — 신뢰 저장소가 다르다). 그래서 curl 로 **배포된 바이트 그대로**를
//   받아 와서 /planner/ 하위에 띄우고 그걸 돌린다.
//   이러면 CI 가 빌드 번호를 제대로 박았는지, 올라간 파일 목록이 맞는지,
//   그 파일들로 앱이 실제로 뜨는지가 진짜로 검사된다.
//   (Pages 자체의 헤더·라우팅은 아래 curl 단계에서 상태코드로 본다)
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { serve } from "./serve.mjs";

const { chromium } = createRequire(import.meta.url)("playwright");
const BASE = (process.argv[2] || "https://wodud1903-beep.github.io/planner").replace(/\/$/, "");
const REPO = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

let fails = 0;
const ok = (n, c, x = "") => {
  console.log((c ? "  OK  " : "  ** FAIL **  ") + n + (x ? "  " + x : ""));
  if (!c) fails++;
};
const curl = (args) => execFileSync("curl", ["-sS", ...args], { encoding: "buffer" });

// ------------------------------------------------------------- 내려받기
console.log(`\n[1] 배포본 내려받기 — ${BASE}`);
const sw = String(curl(["-f", `${BASE}/sw.js`]));
const FILES = ["index.html", "manifest.webmanifest", "sw.js", "version.json", "CHANGELOG.md",
  ...[...sw.matchAll(/"\.\/([^"]+)"/g)].map((m) => m[1]).filter((f) => f && f !== "CHANGELOG.md")];
const dir = mkdtempSync(join(tmpdir(), "live-"));
const got = [];
for (const f of [...new Set(FILES)]) {
  const dst = join(dir, f);
  mkdirSync(dirname(dst), { recursive: true });
  try { writeFileSync(dst, curl(["-f", "-o", "-", `${BASE}/${f}`])); got.push(f); }
  catch { ok(`받기: ${f}`, false, "404 이거나 못 받았다"); }
}
ok("프리캐시에 적힌 파일이 배포본에 다 있다", got.length === new Set(FILES).size,
   `${got.length}/${new Set(FILES).size}개`);

console.log("\n[2] 배포본이 저장소와 같은지 — CI 가 바꾼 것만 달라야 한다");
const CI_REWRITES = new Set(["sw.js", "version.json"]);   // 빌드 번호를 박는 두 개
const diff = [];
for (const f of got) {
  const src = f === "CHANGELOG.md" ? join(REPO, "CHANGELOG.md") : join(REPO, "web", f);
  let same;
  try { same = Buffer.compare(readFileSync(src), readFileSync(join(dir, f))) === 0; }
  catch { same = false; }
  if (!same && !CI_REWRITES.has(f)) diff.push(f);
}
ok("CI 가 안 건드리는 파일은 저장소와 한 바이트도 안 다르다", diff.length === 0, diff.join(", "));

const ver = JSON.parse(readFileSync(join(dir, "version.json"), "utf-8"));
const cfgVer = /^APP_VERSION = "(.*)"$/m.exec(
  readFileSync(join(REPO, "python", "planner", "config.py"), "utf-8"))[1];
ok("빌드 번호가 자리표가 아니라 진짜 값이다",
   /^[0-9a-f]{12}$/.test(ver.build) && ver.version === cfgVer, JSON.stringify(ver));
ok("서비스워커 캐시 이름에 그 빌드 번호가 들어 있다",
   String(readFileSync(join(dir, "sw.js"))).includes(`"${ver.build}"`));

console.log("\n[3] 안 올라가야 하는 것");
const code = (p) => String(execFileSync("curl",
  ["-sS", "-o", "/dev/null", "-w", "%{http_code}", `${BASE}/${p}`], { encoding: "utf-8" }));
ok("검사 스크립트는 안 올라간다(404)", code("verify/verify_web.mjs") === "404");

// ------------------------------------------------------------- 띄워 보기
console.log("\n[4] 그 파일들로 앱이 실제로 뜨는지");
const S = await serve(dir, { port: 8131 });
const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 412, height: 900 } })).newPage();
const errs = [], bad = [], blocked = [];
p.on("pageerror", (e) => errs.push(e.message));
p.on("requestfailed", (r) => (r.url().includes("localhost:8131") ? bad : blocked).push(r.url()));
p.on("response", (r) => { if (r.status() >= 400) bad.push(r.status() + " " + r.url()); });

await p.goto(S.url, { waitUntil: "networkidle" });
ok("탭 여섯 개가 보인다", (await p.locator("nav.tabs a").count()) === 6);
ok("우리 파일 중 못 받은 게 없다", bad.length === 0, bad.join(" | "));

await p.click('nav.tabs a[data-tab="/about"]');
await p.waitForTimeout(1200);
ok("변경 이력이 렌더된다", (await p.locator("details").count()) > 50,
   (await p.locator("details").count()) + "개 버전");
await p.click('nav.tabs a[data-tab="/kb"]');
await p.waitForTimeout(400);
ok("자료검색 검색창이 있다", (await p.locator("#kbq").count()) === 1);

ok("서비스워커가 등록된다",
   await p.evaluate(async () => !!(await navigator.serviceWorker.getRegistration())));
const keys = await p.evaluate(() => caches.keys());
ok("배포된 빌드 번호로 캐시가 만들어진다", keys.includes("app-" + ver.build), keys.join(","));

await p.setViewportSize({ width: 880, height: 1100 });
await p.waitForTimeout(300);
// 펼치면 격자가 되고, 머리말은 **가로로** 누워야 한다.
// (flex 로 눕히면 머리말까지 오른쪽에 세로 띠로 서던 버그가 있었다)
const wide = await p.evaluate(() => {
  const g = (sel) => { const r = document.querySelector(sel).getBoundingClientRect();
                       return { x: r.x, y: r.y, w: r.width, h: r.height }; };
  return { display: getComputedStyle(document.querySelector("#app")).display,
           head: g("header"), body: g("#body"), tabs: g("nav.tabs") };
});
ok("펼치면 격자로 바뀐다", wide.display === "grid", wide.display);
ok("머리말이 가로로 눕고 본문 위에 있다",
   wide.head.w > 600 && wide.head.h < 120 && wide.head.y < wide.body.y,
   `머리말 ${Math.round(wide.head.w)}x${Math.round(wide.head.h)}`);
ok("탭 레일이 맨 왼쪽에 세로로 선다",
   wide.tabs.x === 0 && wide.tabs.w < 200 && wide.body.x >= wide.tabs.w,
   `rail x=${Math.round(wide.tabs.x)} w=${Math.round(wide.tabs.w)}`);

// 구글 로그인 스크립트는 이 컨테이너에서 막힌다 — 그래도 화면이 살아 있어야 한다.
// 그게 '로그인 실패해도 화면을 안 바꾼다' 는 약속이다.
const outside = [...new Set(blocked)];
ok("바깥으로 막힌 건 구글 로그인 스크립트뿐이다",
   outside.every((u) => /accounts\.google\.com|gstatic\.com/.test(u)), outside.join(", "));
ok("구글이 막혀도 페이지 오류가 없다",
   errs.filter((e) => !/gsi|accounts\.google|Failed to load resource/i.test(e)).length === 0,
   errs.join(" | "));

await b.close();
await S.close();
console.log("\n" + (fails ? `${fails}건 실패` : "전부 통과"));
process.exit(fails ? 1 : 0);
