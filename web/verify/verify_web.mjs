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

console.log("\n[9] 고객관리 — 가짜 시트를 물려 화면 전체를 돌려 본다");
{
  // 구글에 실제로 못 가므로 (a) 토큰을 미리 넣어 두고 (b) 시트 API 를 가로챈다.
  // 그래야 목록 → 검색 → 상세 → 멘트 복사까지 진짜 코드로 확인할 수 있다.
  const ctx3 = await browser.newContext({ viewport: { width: 412, height: 900 } });
  await ctx3.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      // ⚠️ 토큰은 반드시 ASCII 여야 한다. HTTP 헤더 값은 Latin-1 만 되므로
      //    한글을 넣으면 fetch 가 요청을 보내기도 전에 예외를 던지고,
      //    앱은 그걸 '오프라인' 으로 읽는다. 가짜 시트가 안 물려서 한참 헤맸다.
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3,
      email: "me@example.com" }));
  });
  const HDR = ["순번", "고객명/사업자", "금융사", "차종", "차량가격", "금융수수료",
               "대리점 수당", "합계", "특판/대리점", "계약일(발주)", "출고일", "진행현황",
               "계약조건", "내용", "출고유형", "고객센터 번호", "사고접수연락처"];
  const SHEET = [
    ["", "", "", "", "", "", "", "", "", "", "", "", "", "이번달 대수", "3"],
    HDR,
    ["1", "김상현", "우리금융캐피탈", "쏘나타 디 엣지", "35,000,000", "300,000",
     "200,000", "500,000", "대리점", "2026. 8. 1", "2026. 8. 20", "출고완료",
     "60/2만", "메모1", "신차", "1588-1111", "1588-2222"],
    ["2", "박영희", "KB캐피탈", "아이오닉5", "52,000,000", "", "", "", "특판",
     "2026. 8. 5", "", "심사중", "48/3만", "", "신차", "1599-3333", "1599-4444"],
    ["3", "", "", ""],                                    // 지운 줄 — 안 나와야 한다
    ["4", "최민수", "BNK캐피탈", "쏘렌토", "45,000,000", "", "", "", "대리점",
     "2026. 8. 9", "", "심사중", "", "", "신차", "", ""],
  ];
  const MENT = "김상현 고객님 안녕하세요.\n계약이 정상 접수되었습니다.\n감사합니다.";
  const seen = [];
  const p3 = await page(ctx3);
  await ctx3.route("**/accounts.google.com/**", (r) => r.abort());
  await ctx3.route("**/oauth2/v3/userinfo", (r) =>
    r.fulfill({ json: { email: "me@example.com" } }));
  await ctx3.route("**/sheets.googleapis.com/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    seen.push(u);
    if (u.includes("batchGet")) {
      return r.fulfill({ json: { valueRanges: [
        { values: SHEET.map((x) => x.slice(0, 17)) },
        { values: SHEET.map(() => []) },
      ] } });
    }
    if (/!R\d+:R\d+/.test(u)) return r.fulfill({ json: { values: [[MENT]] } });
    if (u.includes("A1:F")) return r.fulfill({ json: { values: [
      ["심사서류", "KB캐피탈", "개인 심사서류", "서류", "■ 준비물\n· 신분증", "신분증"] ] } });
    return r.fulfill({ json: { values: [] } });
  });

  await p3.goto(s.url + "#/customers", { waitUntil: "networkidle" });
  await p3.waitForSelector("#clist button.row", { timeout: 10000 });
  const names = await p3.locator("#clist .t").allTextContents();
  ok("고객 목록이 그려진다", names.length === 3, names.join(", "));
  ok("고객명 없는 줄(지운 행)은 안 나온다", !names.includes(""), names.join(", "));

  // ⚠️ R열은 목록에서 받으면 안 된다 — 한 건당 20줄이라 폰에서 제일 큰 낭비다.
  ok("목록을 받을 때 R열(안내멘트)은 안 받는다",
     !seen.some((u) => /!R\d+:R\d+/.test(u)), seen.filter((u) => /!R/.test(u)).join(" "));
  ok("목록을 받을 때 U열(고객ID)도 안 받는다",
     !seen.some((u) => /!U/.test(u)));

  const chips = await p3.locator("#cchips button").allTextContents();
  ok("진행현황 칩을 시트 값에서 뽑는다",
     JSON.stringify(chips) === JSON.stringify(["전체", "심사중", "출고완료"]), chips.join("|"));

  // 초성 검색
  await p3.fill("#cq", "ㄱㅅㅎ");
  await p3.waitForTimeout(300);
  ok("초성으로 걸러진다",
     JSON.stringify(await p3.locator("#clist .t").allTextContents()) === '["김상현"]');
  await p3.fill("#cq", "아이오닉");
  await p3.waitForTimeout(300);
  ok("차종으로도 걸러진다",
     JSON.stringify(await p3.locator("#clist .t").allTextContents()) === '["박영희"]');
  await p3.fill("#cq", "");
  await p3.waitForTimeout(300);

  // 칩으로 거르기
  await p3.click('#cchips button[data-st="심사중"]');
  await p3.waitForTimeout(200);
  ok("진행현황 칩으로 걸러진다",
     (await p3.locator("#clist button.row").count()) === 2);
  await p3.click('#cchips button[data-st=""]');
  await p3.waitForTimeout(200);

  // 상세
  await p3.locator("#clist button.row").first().click();
  await p3.waitForSelector("#cment .bigcopy", { timeout: 10000 });
  ok("상세에 이름이 나온다", (await p3.locator("#cdetail h2").textContent()) === "김상현");
  ok("금액이 서식대로 나온다",
     (await p3.locator("#cdetail .kv").first().innerText()).includes("35,000,000"));
  ok("멘트는 열 때 그 한 칸만 받는다",
     seen.filter((u) => /!R\d+:R\d+/.test(u)).length === 1);
  ok("멘트 본문이 그려진다", (await p3.locator("pre.ment").textContent()).includes("정상 접수"));
  const tels = await p3.locator("#cdetail a.tel").evaluateAll((a) => a.map((x) => x.href));
  ok("연락처가 눌러서 걸리는 tel: 링크다",
     tels.length === 2 && tels[0] === "tel:15881111" && tels[1] === "tel:15882222",
     tels.join(" "));
  const copyH = await p3.locator("#cmentcopy").evaluate((b) => b.getBoundingClientRect().height);
  ok("복사 단추가 엄지로 누를 만큼 크다", copyH >= 48, Math.round(copyH) + "px");

  // 뒤로 → 목록
  await p3.click("#cback");
  await p3.waitForTimeout(300);
  ok("목록으로 돌아온다", (await p3.locator("#clist button.row").count()) === 3);

  // 껐다 켜도 캐시로 바로 뜨는지 (시트를 아예 막아 둔다)
  await ctx3.route("**/sheets.googleapis.com/**", (r) => r.abort());
  const p4 = await page(ctx3);
  await p4.goto(s.url + "#/customers");
  await p4.waitForSelector("#clist button.row", { timeout: 10000 });
  ok("시트를 못 읽어도 캐시로 목록이 뜬다",
     (await p4.locator("#clist button.row").count()) === 3);
  ok("시트를 못 읽어도 빈 화면이 되지 않는다",
     (await p4.locator("nav.tabs a").count()) === 4);
  await ctx3.close();
}

console.log("\n[10] 탭 이름이 틀렸을 때 — 400 을 사람이 고칠 수 있게 알려 주나");
{
  const ctx4 = await browser.newContext({ viewport: { width: 412, height: 900 } });
  await ctx4.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const p5 = await page(ctx4);
  await ctx4.route("**/accounts.google.com/**", (r) => r.abort());
  await ctx4.route("**/sheets.googleapis.com/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    // 구글이 실제로 돌려주는 모양 그대로
    if (u.includes("batchGet")) return r.fulfill({ status: 400, json: { error: {
      code: 400, status: "INVALID_ARGUMENT",
      message: "Unable to parse range: '미출고차량'!A1:Q" } } });
    if (u.includes("fields=properties.title")) return r.fulfill({ json: {
      properties: { title: "고객관리리스트" },
      sheets: [{ properties: { title: "출고완료차량" } },
               { properties: { title: "미출고차량(신)" } }] } });
    return r.fulfill({ json: { values: [] } });
  });
  await p5.goto(s.url + "#/customers", { waitUntil: "networkidle" });
  await p5.waitForTimeout(1200);
  const emptyTxt = await p5.locator("#clist .empty").textContent();
  ok("400 을 그냥 'HTTP 400' 으로 흘리지 않는다", !/^시트를 읽지 못했습니다 \(HTTP 400\)$/.test(emptyTxt.trim()));
  ok("탭 이름 문제라고 짚어 준다", emptyTxt.includes("탭"), emptyTxt.slice(0, 60));

  // 설정 → 진짜 탭 목록을 받아 눌러 고른다
  await p5.click("#cconf");
  await p5.waitForSelector("#sload");
  await p5.click("#sload");
  await p5.waitForTimeout(800);
  const tabs = await p5.locator("#stabs button").allTextContents();
  ok("시트에 실제로 있는 탭 목록을 보여 준다",
     JSON.stringify(tabs) === JSON.stringify(["출고완료차량", "미출고차량(신)"]), tabs.join("|"));
  ok("스프레드시트 이름을 알려 준다",
     (await p5.locator("#smsg").textContent()).includes("고객관리리스트"));
  await ctx4.close();
}

console.log("\n[11] 서류 — 드라이브를 물려 폴더·파일·보기를 돌려 본다");
{
  const ctx5 = await browser.newContext({ viewport: { width: 412, height: 900 } });
  await ctx5.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const F = "application/vnd.google-apps.folder";
  const TOP = [
    { id: "f1", name: "김상현", mimeType: F, modifiedTime: "2026-08-01T00:00:00Z" },
    { id: "f2", name: "박영희", mimeType: F, modifiedTime: "2026-08-02T00:00:00Z" },
    { id: "f3", name: "쏘나타 견적", mimeType: F, modifiedTime: "2026-08-03T00:00:00Z" },
  ];
  const INSIDE = [
    { id: "d1", name: "계약서.pdf", mimeType: "application/pdf", size: "204800" },
    { id: "d2", name: "신분증.jpg", mimeType: "image/jpeg", size: "51200" },
    { id: "d3", name: "팩스.tif", mimeType: "image/tiff", size: "102400" },
  ];
  // 1x1 PNG
  const PNG = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    "base64");
  const p6 = await page(ctx5);
  const dl = [];
  await ctx5.route("**/accounts.google.com/**", (r) => r.abort());
  await ctx5.route("**/www.googleapis.com/drive/v3/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    if (u.includes("alt=media")) { dl.push(u); return r.fulfill({ body: PNG, contentType: "image/png" }); }
    if (/files\/1AbCdEfGhIjKlMnOpQrStUvWxYz01234\?/.test(u)) return r.fulfill({ json: { id: "1AbCdEfGhIjKlMnOpQrStUvWxYz01234", mimeType: F } });
    if (u.includes("'1AbCdEfGhIjKlMnOpQrStUvWxYz01234' in parents")) return r.fulfill({ json: { files: TOP } });
    if (u.includes("'f1' in parents")) return r.fulfill({ json: { files: INSIDE } });
    if (u.includes("in parents")) return r.fulfill({ json: { files: [] } });
    if (u.includes("name=")) return r.fulfill({ json: { files: [{ id: "1AbCdEfGhIjKlMnOpQrStUvWxYz01234", name: "고객정보" }] } });
    return r.fulfill({ json: { files: [] } });
  });
  await ctx5.route("**/sheets.googleapis.com/**", (r) => r.fulfill({ json: { values: [] } }));

  await p6.goto(s.url + "#/docs", { waitUntil: "networkidle" });
  await p6.waitForSelector("#dsave", { timeout: 8000 });
  ok("폴더를 안 정했으면 정하는 화면부터 나온다", true);

  // 주소를 붙여넣어도 알아들어야 한다 — 폰에서 긴 id 를 손으로 치는 건 무리다
  await p6.fill("#dref", "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz01234?usp=sharing");
  await p6.click("#dsave");
  await p6.waitForSelector("#dlist button.row", { timeout: 8000 });
  const names = await p6.locator("#dlist .t").allTextContents();
  ok("드라이브 링크를 붙여넣어도 폴더를 찾는다", names.length === 3, names.join(", "));

  await p6.fill("#dq", "ㅂㅇㅎ");
  await p6.waitForTimeout(300);
  ok("고객 폴더를 초성으로 찾는다",
     (await p6.locator("#dlist .t").allTextContents()).join("").includes("박영희"));
  await p6.fill("#dq", "");
  await p6.waitForTimeout(300);

  await p6.locator("#dlist button.row").first().click();
  await p6.waitForSelector("#dlist button.row", { timeout: 8000 });
  await p6.waitForTimeout(400);
  const files = await p6.locator("#dlist .t").allTextContents();
  ok("폴더에 들어가면 파일이 보인다", files.length === 3, files.join(", "));

  // 그림 보기
  await p6.locator('#dlist button.row', { hasText: "신분증" }).click();
  await p6.waitForSelector(".vimg", { timeout: 8000 });
  ok("그림을 앱 안에서 연다", (await p6.locator(".vimg").getAttribute("src")).startsWith("blob:"));
  ok("파일 내용을 실제로 받아 온다", dl.length === 1, dl.length + "건");
  ok("두 손가락 확대를 막지 않는다",
     (await p6.locator(".vimg").evaluate((e) => getComputedStyle(e).touchAction)) === "pinch-zoom");

  // TIFF — 브라우저가 못 그린다. 팩스가 이 형식으로 오므로 안내가 정확해야 한다.
  await p6.locator('#dlist button.row', { hasText: "팩스" }).click();
  await p6.waitForTimeout(400);
  const tifTxt = await p6.locator("#dview").innerText();
  ok("TIFF 는 못 그린다고 정확히 말하고 드라이브로 넘긴다",
     tifTxt.includes("TIF") && tifTxt.includes("드라이브"), tifTxt.slice(0, 70));
  ok("TIFF 는 내려받지 않는다", dl.length === 1, dl.length + "건");

  // 최근 본 고객
  await p6.goto(s.url + "#/docs", { waitUntil: "networkidle" });
  await p6.waitForSelector("#drecent button", { timeout: 8000 });
  ok("최근 본 고객이 위에 남는다",
     (await p6.locator("#drecent button").allTextContents()).includes("김상현"));
  await ctx5.close();
}

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
