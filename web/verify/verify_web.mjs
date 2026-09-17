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
import { readFileSync, readdirSync, statSync, existsSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";

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

// 앱이 뜨기 전에 IndexedDB 에 미리 넣어 둔다(시트 주소·서류 폴더·계정).
// 기본 시트 주소를 없앴으므로 검사도 '정해 둔 상태' 를 만들어야 한다.
function seed(ctx, rec) {
  return ctx.addInitScript((r) => {
    const req = indexedDB.open("planner", 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta");
      if (!db.objectStoreNames.contains("data")) db.createObjectStore("data");
      if (!db.objectStoreNames.contains("recent")) db.createObjectStore("recent", { keyPath: "uid" });
    };
    req.onsuccess = () => {
      const t = req.result.transaction("meta", "readwrite").objectStore("meta");
      for (const [k, v] of Object.entries(r)) t.put(v, k);
    };
  }, rec);
}

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
ok("탭 여섯 개가 보인다", (await p.locator("nav.tabs a").count()) === 6);
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
   (await p.locator("nav.tabs a").count()) === 6);
await ctx.setOffline(false);

console.log("\n[9] 고객관리 — 가짜 시트를 물려 화면 전체를 돌려 본다");
{
  // 구글에 실제로 못 가므로 (a) 토큰을 미리 넣어 두고 (b) 시트 API 를 가로챈다.
  // 그래야 목록 → 검색 → 상세 → 멘트 복사까지 진짜 코드로 확인할 수 있다.
  const ctx3 = await browser.newContext({ viewport: { width: 412, height: 900 } });
  await seed(ctx3, { account: "me@example.com",
                     sheet: { id: "1L6UwkuywIEAffPvQX9GWwsP8Ix_6fP8uakNFfV1iAm8",
                              tab: "미출고차량" } });
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
  const docDl = [];
  const QPNG = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    "base64");
  const p3 = await page(ctx3);
  await ctx3.route("**/www.googleapis.com/drive/v3/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    if (u.includes("QUOTE1") && u.includes("alt=media")) {
      docDl.push(u);
      return r.fulfill({ body: QPNG, contentType: "image/png" });
    }
    return r.fulfill({ json: { files: [] } });
  });
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
    // S열은 수식으로 물어봐야 =IMAGE(...) 가 온다
    if (/!S\d+:S\d+/.test(u)) {
      return r.fulfill({ json: { values: [[u.includes("FORMULA")
        ? '=IMAGE("https://drive.google.com/uc?export=view&id=QUOTE1", 1)'
        : ""]] } });
    }
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

  // ⚠️ 견적서는 S열의 =IMAGE() **수식**이다. 표시값으로 읽으면 빈 문자열이라
  //    '견적서 없음' 과 구분되지 않는다 — 폰에서 안 보이던 이유가 이것이었다.
  await p3.waitForSelector("#cdoc .vimg", { timeout: 10000 });
  ok("견적서를 수식으로 읽는다",
     seen.some((u) => /!S\d+:S\d+/.test(u) && /FORMULA/.test(u)),
     seen.filter((u) => /!S\d+:S/.test(u)).map((u) => u.slice(-40)).join(" "));
  ok("견적서 이미지가 나온다",
     (await p3.locator("#cdoc .vimg").getAttribute("src")).startsWith("blob:"));
  ok("견적서를 드라이브 API 로 받아 온다", docDl.length === 1, docDl.length + "건");
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
     (await p4.locator("nav.tabs a").count()) === 6);
  await ctx3.close();
}

console.log("\n[10] 탭 이름이 틀렸을 때 — 400 을 사람이 고칠 수 있게 알려 주나");
{
  const ctx4 = await browser.newContext({ viewport: { width: 412, height: 900 } });
  await seed(ctx4, { account: "me@example.com",
                     sheet: { id: "1L6UwkuywIEAffPvQX9GWwsP8Ix_6fP8uakNFfV1iAm8",
                              tab: "미출고차량" } });
  await ctx4.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const p5 = await page(ctx4);
  await ctx4.route("**/accounts.google.com/**", (r) => r.abort());
  // 설정을 계정에서 읽으므로 드라이브도 막아 둬야 한다. 안 막으면 진짜 구글로
  // 나가려다 networkidle 이 영영 안 온다.
  await ctx4.route("**/www.googleapis.com/**", (r) => r.fulfill({ json: { files: [] } }));
  await ctx4.route("**/tasks.googleapis.com/**", (r) => r.fulfill({ json: { items: [] } }));
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
  await ctx5.route("**/upload/drive/v3/**", (r) => r.fulfill({ json: { id: "W" } }));
  await ctx5.route("**/tasks.googleapis.com/**", (r) => r.fulfill({ json: { items: [] } }));
  await ctx5.route("**/www.googleapis.com/drive/v3/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    // 앱 전용 폴더(설정 보관소) 조회는 서류 조회와 갈라 둔다. 안 그러면
    // 아래 name= 가지에 걸려 설정 파일을 서류인 줄 알고 내려받는다.
    if (u.includes("appDataFolder")) return r.fulfill({ json: { files: [] } });
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

  // ⚠️ 예전엔 .vimg 에 touch-action:pinch-zoom 을 걸어 두어 **한 손가락 스크롤이
  //    막혔다**. 그림 위에서 굴려도 아무 일도 안 나던 게 그 때문이다.
  const ta = await p6.locator(".vscroll").evaluate((e) => getComputedStyle(e).touchAction);
  ok("그림 위에서 스크롤을 막지 않는다", ta === "auto", ta);
  ok("그림 칸이 스크롤된다",
     (await p6.locator(".vscroll").evaluate((e) => getComputedStyle(e).overflow)) === "auto");

  // 눌러서 확대 → 다시 누르면 더 확대 → 끝까지 가면 처음으로
  const pctOf = () => p6.locator(".vpct").textContent();
  ok("처음엔 100%", (await pctOf()) === "100%");
  await p6.locator("#vin").click();
  ok("＋ 로 확대된다", (await pctOf()) === "150%", await pctOf());
  // ⚠️ 눌러서 확대되면 안 된다. 서류를 짚거나 스크롤하려고 손을 댈 때마다
  //    확대돼서 오히려 방해가 됐다. 확대는 ＋ − 와 두 손가락으로만.
  await p6.locator(".vimg").click({ position: { x: 5, y: 5 } });
  await p6.waitForTimeout(200);
  ok("그림을 눌러도 확대되지 않는다", (await pctOf()) === "150%", await pctOf());
  await p6.locator(".vimg").dblclick({ position: { x: 5, y: 5 } });
  await p6.waitForTimeout(200);
  ok("두 번 눌러도 확대되지 않는다", (await pctOf()) === "150%", await pctOf());
  await p6.locator("#vout").click();
  ok("− 로 축소된다", (await pctOf()) === "100%", await pctOf());
  await p6.locator("#vin").click();
  ok("확대하면 그림 폭이 커진다",
     (await p6.locator(".vpages").evaluate((e) => e.style.width)) === "150%");

  // 좁은 화면에서는 보는 동안 목록을 감춘다 — 412px 에 둘을 나란히 두면 둘 다 못 쓴다
  ok("좁은 화면에서는 보는 동안 목록을 감춘다",
     !(await p6.locator("#dlist").isVisible()));
  await p6.click("#vclose");
  await p6.waitForTimeout(300);
  ok("닫으면 목록으로 돌아온다", await p6.locator("#dlist").isVisible());

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

console.log("\n[12] 펼친 화면 — 머리말이 옆으로 서지 않는다 · 경계선을 끌 수 있다");
{
  const ctx6 = await browser.newContext({ viewport: { width: 1000, height: 1100 } });
  await ctx6.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const p7 = await page(ctx6);
  await ctx6.route("**/accounts.google.com/**", (r) => r.abort());
  await ctx6.route("**/sheets.googleapis.com/**", (r) => r.fulfill({ json: { values: [] } }));
  await ctx6.route("**/www.googleapis.com/drive/v3/**", (r) => r.fulfill({ json: { files: [] } }));
  await ctx6.route("**/upload/drive/v3/**", (r) => r.fulfill({ json: { id: "W" } }));
  await p7.goto(s.url + "#/kb", { waitUntil: "networkidle" });
  await p7.waitForSelector("#kbsplit .gutter", { timeout: 8000 });

  // ⚠️ 이게 이번에 잡은 진짜 버그다. #app 을 flex row 로 눕히면 자식이 셋
  //    (머리말·본문·탭) 이라 **머리말까지 오른쪽에 세로 띠로 선다.**
  //    제목 '일정관리기' 가 오른쪽 절반을 먹고 본문이 눌려 있었다.
  const box = await p7.evaluate(() => {
    const g = (s) => { const r = document.querySelector(s).getBoundingClientRect();
                       return { x: Math.round(r.x), w: Math.round(r.width), h: Math.round(r.height) }; };
    return { app: g("#app"), head: g("header"), body: g("#body"), tabs: g("nav.tabs") };
  });
  ok("머리말이 본문 위에 가로로 눕는다", box.head.w > box.app.w * 0.7,
     `머리말 ${box.head.w}px / 전체 ${box.app.w}px`);
  ok("머리말이 오른쪽 세로 띠가 아니다", box.head.h < 120, box.head.h + "px");
  ok("탭 레일은 맨 왼쪽에 세로로 선다",
     box.tabs.x === 0 && box.tabs.w < 200, `x=${box.tabs.x} w=${box.tabs.w}`);
  ok("본문이 레일 오른쪽을 다 쓴다",
     box.body.x === box.tabs.w && box.body.w > box.app.w * 0.7,
     `x=${box.body.x} w=${box.body.w}`);

  // 경계선 끌기
  const w0 = await p7.locator("#kbsplit > .left").evaluate((e) => e.getBoundingClientRect().width);
  const g = await p7.locator("#kbsplit > .gutter").boundingBox();
  await p7.mouse.move(g.x + g.width / 2, g.y + g.height / 2);
  await p7.mouse.down();
  await p7.mouse.move(g.x + g.width / 2 + 140, g.y + g.height / 2, { steps: 8 });
  await p7.mouse.up();
  const w1 = await p7.locator("#kbsplit > .left").evaluate((e) => e.getBoundingClientRect().width);
  ok("경계선을 끌면 목록이 넓어진다", Math.abs(w1 - (w0 + 140)) < 12, `${Math.round(w0)} → ${Math.round(w1)}`);

  // 너무 좁히면 이름이 잘려 쓸모가 없다 → 하한이 있어야 한다
  await p7.mouse.move(g.x + g.width / 2 + 140, g.y + g.height / 2);
  await p7.mouse.down();
  await p7.mouse.move(10, g.y + g.height / 2, { steps: 8 });
  await p7.mouse.up();
  const w2 = await p7.locator("#kbsplit > .left").evaluate((e) => e.getBoundingClientRect().width);
  ok("아무리 좁혀도 하한을 지킨다", w2 >= 219, Math.round(w2) + "px");

  // 정한 너비는 기억한다 — 탭마다 따로.
  // 저장은 손을 뗀 뒤에 하므로 새로고침 전에 잠깐 기다린다. (실제로 쓸 때는
  // 탭만 옮기지 새로고침을 하지 않아서 문제가 안 된다)
  await p7.waitForTimeout(400);
  await p7.reload({ waitUntil: "networkidle" });
  await p7.waitForSelector("#kbsplit .gutter");
  await p7.waitForTimeout(300);
  const w3 = await p7.locator("#kbsplit > .left").evaluate((e) => e.getBoundingClientRect().width);
  ok("다시 열어도 그 너비를 기억한다", Math.abs(w3 - w2) < 3, `${Math.round(w2)} → ${Math.round(w3)}`);

  await p7.click('nav.tabs a[data-tab="/customers"]');
  await p7.waitForSelector("#csplit .gutter", { timeout: 8000 });
  const wc = await p7.locator("#csplit > .left").evaluate((e) => e.getBoundingClientRect().width);
  ok("탭마다 너비를 따로 기억한다", Math.abs(wc - 340) < 3, Math.round(wc) + "px");

  // 세 탭 모두에 경계선이 있어야 한다
  // 서류는 폴더를 정해야 목록이 나온다
  await ctx6.unroute("**/www.googleapis.com/drive/v3/**");
  await ctx6.route("**/www.googleapis.com/drive/v3/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    if (u.includes("files/1AbCdEfGhIjKlMnOpQrStUvWxYz01234?")) {
      return r.fulfill({ json: { id: "1AbCdEfGhIjKlMnOpQrStUvWxYz01234",
        mimeType: "application/vnd.google-apps.folder" } });
    }
    return r.fulfill({ json: { files: [] } });
  });
  await p7.click('nav.tabs a[data-tab="/docs"]');
  await p7.waitForSelector("#dsave", { timeout: 8000 });
  await p7.fill("#dref", "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz01234");
  await p7.click("#dsave");
  await p7.waitForSelector("#dsplit .gutter", { timeout: 8000 });
  ok("서류 탭에도 경계선이 있다", (await p7.locator("#dsplit .gutter").count()) === 1);
  ok("서류 탭 경계선도 끌리는 모양이다",
     (await p7.locator("#dsplit .gutter").evaluate((e) => getComputedStyle(e).cursor))
     === "col-resize");
  await ctx6.close();
}

console.log("\n[13] PDF — 한 장씩 그림으로 그려 아래로 이어 붙이는지");
{
  // pdf.js 는 CDN 에서 받는다. 이 컨테이너의 크로미움은 바깥으로 TLS 를 못 맺으므로
  // 미리 받아 둔 같은 파일을 물려서 **진짜 pdf.js 로** 그려 본다.
  // (없으면 이 묶음은 건너뛴다 — 검사가 통신에 매달리면 안 된다)
  // 두 장짜리 PDF 는 저장소에 넣어 뒀다(844바이트). pdf.js 는 없으면 한 번 받아
  // 옆에 둔다 — 그다음부터는 통신 없이 돈다.
  const PDF = process.env.TEST_PDF || join(WEB, "verify", "fixtures", "two.pdf");
  const CDN = process.env.PDFJS_DIR || join(WEB, "verify", ".pdfjs");
  if (!existsSync(join(CDN, "pdf.min.mjs"))) {
    try {
      mkdirSync(CDN, { recursive: true });
      for (const f of ["pdf.min.mjs", "pdf.worker.min.mjs"]) {
        execFileSync("curl", ["-sS", "-f", "-o", join(CDN, f),
          `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/${f}`]);
      }
    } catch (e) { /* 통신이 안 되면 아래에서 건너뛴다 */ }
  }
  if (!existsSync(join(CDN, "pdf.min.mjs")) || !existsSync(PDF)) {
    console.log("  (건너뜀) pdf.js 를 받지 못했다 — 통신이 되는 곳에서 다시 돌려 주세요");
  } else {
    const F = "application/vnd.google-apps.folder";
    const ctx7 = await browser.newContext({ viewport: { width: 412, height: 900 } });
    await ctx7.addInitScript(() => {
      sessionStorage.setItem("planner.tok", JSON.stringify({
        token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
    });
    const p8 = await page(ctx7);
    await ctx7.route("**/accounts.google.com/**", (r) => r.abort());
  await ctx7.route("**/upload/drive/v3/**", (r) => r.fulfill({ json: { id: "W" } }));
    await ctx7.route("**/cdnjs.cloudflare.com/**", (r) => {
      const f = r.request().url().split("/").pop();
      const file = join(CDN, f);
      if (!existsSync(file)) return r.abort();
      return r.fulfill({ body: readFileSync(file),
                         contentType: "text/javascript; charset=utf-8" });
    });
    await ctx7.route("**/www.googleapis.com/drive/v3/**", (r) => {
      const u = decodeURIComponent(r.request().url());
      if (u.includes("alt=media")) {
        return r.fulfill({ body: readFileSync(PDF), contentType: "application/pdf" });
      }
      if (u.includes("files/PDFROOT0000000000000000000000?")) {
        return r.fulfill({ json: { id: "PDFROOT0000000000000000000000", mimeType: F } });
      }
      if (u.includes("in parents")) {
        return r.fulfill({ json: { files: [
          { id: "pp", name: "계약서.pdf", mimeType: "application/pdf", size: "844" }] } });
      }
      return r.fulfill({ json: { files: [] } });
    });
    await ctx7.route("**/sheets.googleapis.com/**", (r) => r.fulfill({ json: { values: [] } }));

    await p8.goto(s.url + "#/docs", { waitUntil: "networkidle" });
    await p8.waitForSelector("#dsave", { timeout: 8000 });
    await p8.fill("#dref",
      "https://drive.google.com/drive/folders/PDFROOT0000000000000000000000");
    await p8.click("#dsave");
    await p8.waitForSelector("#dlist button.row", { timeout: 8000 });
    await p8.locator('#dlist button.row', { hasText: "계약서" }).click();

    // ⚠️ 여기가 핵심이다. 예전엔 <iframe> 에 맡겼는데 안드로이드에서는 내장 뷰어가
    //    있기도 없기도 해서 빈 칸이 나왔다. 이제 장마다 <img> 로 그린다.
    await p8.waitForSelector(".vpage", { timeout: 30000 });
    await p8.waitForFunction(() => document.querySelectorAll(".vpage").length >= 2,
                             null, { timeout: 30000 });
    const n = await p8.locator(".vpage").count();
    ok("두 장짜리 PDF 가 두 장으로 그려진다", n === 2, n + "장");
    ok("iframe 을 쓰지 않는다", (await p8.locator("iframe").count()) === 0);
    ok("장마다 그림이다", (await p8.locator(".vpage").first().getAttribute("src")).startsWith("blob:"));

    // 아래로 이어 붙었는지 — 둘째 장이 첫 장 아래에 있어야 한다
    const ys = await p8.locator(".vpage").evaluateAll(
      (els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
    ok("장이 아래로 이어 붙는다", ys[1] > ys[0], ys.join(" → "));
    const w = await p8.locator(".vpage").first().evaluate((e) => e.getBoundingClientRect().width);
    ok("장이 화면 폭에 맞는다", w > 300 && w <= 412, Math.round(w) + "px");

    // 그림과 똑같이 확대·스크롤된다 — 조작이 하나여야 한다
    await p8.locator("#vin").click();
    ok("PDF 도 확대된다", (await p8.locator(".vpct").textContent()) === "150%");
    ok("PDF 칸도 스크롤을 막지 않는다",
       (await p8.locator(".vscroll").evaluate((e) => getComputedStyle(e).touchAction)) === "auto");
    await ctx7.close();
  }
}

console.log("\n[14] 일정 / 할일");
{
  // ⚠️ 한국 시간으로 돌린다. 이 컨테이너는 UTC 라 그냥 두면 14:30(+09:00) 이
  //    05:30 으로 보이고, 종일 일정이 전날로 밀리는지도 확인할 수 없다.
  const ctx8 = await browser.newContext({
    viewport: { width: 412, height: 900 },
    timezoneId: "Asia/Seoul", locale: "ko-KR" });
  await ctx8.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const p9 = await page(ctx8);
  const d = (n) => { const x = new Date(); x.setDate(x.getDate() + n);
    return `${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,"0")}-${String(x.getDate()).padStart(2,"0")}`; };
  const patched = [];
  await ctx8.route("**/accounts.google.com/**", (r) => r.abort());
  await ctx8.route("**/sheets.googleapis.com/**", (r) => r.fulfill({ json: { values: [] } }));
  await ctx8.route("**/www.googleapis.com/calendar/v3/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    if (u.includes("calendarList")) return r.fulfill({ json: { items: [
      { id: "primary", summary: "내 캘린더", primary: true },
      { id: "bad@g", summary: "탈난 캘린더", selected: true }] } });
    if (u.includes("calendars/bad%40g") || u.includes("calendars/bad@g")) {
      return r.fulfill({ status: 500, json: { error: { message: "boom" } } });
    }
    return r.fulfill({ json: { items: [
      // 종일 일정 — UTC 로 읽으면 한국에서 전날로 밀린다
      { id: "e1", start: { date: d(0) }, summary: "오늘 종일건" },
      { id: "e2", start: { dateTime: d(1) + "T14:30:00+09:00" }, summary: "내일 출고" },
      { id: "e3", start: { dateTime: d(5) + "T09:00:00+09:00" }, summary: "다음주 계약" },
    ] } });
  });
  await ctx8.route("**/tasks.googleapis.com/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    if (r.request().method() === "PATCH") { patched.push(u); return r.fulfill({ json: {} }); }
    if (u.includes("users/@me/lists")) return r.fulfill({ json: { items: [
      { id: "L1", title: "업무" }] } });
    return r.fulfill({ json: { items: [
      { id: "t1", title: "심사서류 받기", notes: "김상현", due: d(1) + "T00:00:00.000Z" },
      { id: "t2", title: "기한없는 할일" },
    ] } });
  });
  await ctx8.route("**/www.googleapis.com/drive/v3/**", (r) => r.fulfill({ json: { files: [] } }));

  await p9.goto(s.url + "#/agenda", { waitUntil: "networkidle" });
  await p9.waitForSelector("#agevents .evrow", { timeout: 10000 });
  const evs = await p9.locator("#agevents .evrow .t").allTextContents();
  ok("일정이 날짜순으로 나온다",
     JSON.stringify(evs) === '["오늘 종일건","내일 출고","다음주 계약"]', evs.join(", "));
  ok("종일 일정은 '종일' 로 나온다",
     (await p9.locator("#agevents .evtime").first().textContent()) === "종일");
  ok("시각이 있는 일정은 시각이 나온다",
     (await p9.locator("#agevents .evtime").nth(1).textContent()) === "14:30");

  // ⚠️ 종일 일정을 new Date("2026-08-14") 로 읽으면 UTC 자정이라 한국에서 전날이 된다
  const seps = await p9.locator("#agevents .daysep").allTextContents();
  ok("종일 일정이 전날로 밀리지 않는다", seps[0].startsWith("오늘"), seps.join(" | "));
  ok("오늘·내일을 말로 알려 준다",
     seps[0].startsWith("오늘") && seps[1].startsWith("내일"), seps.join(" | "));

  // 캘린더 하나가 탈났으면 조용히 넘어가면 안 된다
  ok("못 불러온 캘린더가 있으면 알려 준다",
     (await p9.locator("#agwarn .notice").textContent()).includes("탈난 캘린더"));

  const tks = await p9.locator("#agtasks .taskbody .t").allTextContents();
  ok("할일이 나온다 (기한 있는 것 먼저)",
     JSON.stringify(tks) === '["심사서류 받기","기한없는 할일"]', tks.join(", "));
  ok("기한을 '내일' 로 알려 준다",
     (await p9.locator("#agtasks .tag").first().textContent()).startsWith("내일"));

  // 체크 — 밖에서 엄지로 누르는 게 이 화면의 쓸모다
  const h = await p9.locator(".tickbtn").first().evaluate((e) => e.getBoundingClientRect().height);
  ok("체크 단추가 엄지로 누를 만큼 크다", h >= 40, Math.round(h) + "px");
  await p9.locator(".tickbtn").first().click();
  await p9.waitForTimeout(500);
  ok("체크하면 목록에서 바로 빠진다",
     (await p9.locator("#agtasks .taskbody .t").allTextContents()).length === 1);
  ok("구글에 '했다' 고 보낸다", patched.length === 1, patched.length + "건");

  // 껐다 켜도 캐시로 뜬다
  await ctx8.route("**/www.googleapis.com/calendar/v3/**", (r) => r.abort());
  await ctx8.route("**/tasks.googleapis.com/**", (r) => r.abort());
  const p10 = await page(ctx8);
  await p10.goto(s.url + "#/agenda");
  await p10.waitForSelector("#agevents .evrow", { timeout: 10000 });
  ok("구글이 안 되어도 캐시로 일정이 뜬다",
     (await p10.locator("#agevents .evrow").count()) === 3);
  await ctx8.close();
}

console.log("\n[15] 수당계산기");
{
  const ctx9 = await browser.newContext({
    viewport: { width: 412, height: 900 },
    timezoneId: "Asia/Seoul", locale: "ko-KR" });
  await ctx9.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const p11 = await page(ctx9);
  await ctx9.route("**/accounts.google.com/**", (r) => r.abort());
  await ctx9.route("**/www.googleapis.com/**", (r) => r.fulfill({ json: { files: [] } }));
  await ctx9.route("**/tasks.googleapis.com/**", (r) => r.fulfill({ json: { items: [] } }));
  await ctx9.route("**/sheets.googleapis.com/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    if (u.includes("수당율")) return r.fulfill({ json: { values: [
      ["브랜드", "차종", "수당율(%)", "화물차"],
      ["현대", "쏘나타 / HEV", "6.0", "FALSE"],
      ["현대", "GV80", "4.1", "FALSE"],
      ["현대", "포터", "7.0", "TRUE"],
      ["기아", "카니발", "6.0", "FALSE"],
    ] } });
    return r.fulfill({ json: { values: [] } });
  });

  await p11.goto(s.url + "#/calc", { waitUntil: "networkidle" });
  await p11.waitForSelector("#ccars button.carrow", { timeout: 10000 });
  ok("현대 차종이 나온다", (await p11.locator("#ccars .t").count()) === 3);

  await p11.click('#cbrand button[data-b="kia"]');
  await p11.waitForTimeout(200);
  ok("기아로 바꾸면 기아 차종만 나온다",
     JSON.stringify(await p11.locator("#ccars .t").allTextContents()) === '["카니발"]');
  await p11.click('#cbrand button[data-b="hyundai"]');
  await p11.waitForTimeout(200);

  await p11.fill("#ccar", "ㅅㄴㅌ");
  await p11.waitForTimeout(200);
  ok("차종을 초성으로 찾는다",
     JSON.stringify(await p11.locator("#ccars .t").allTextContents()) === '["쏘나타 / HEV"]');
  await p11.fill("#ccar", "");
  await p11.waitForTimeout(200);

  // 차량가는 치는 동안 1,000 단위가 붙어야 한다
  await p11.locator("#cprice").pressSequentially("57035000", { delay: 8 });
  ok("차량가에 1,000 단위가 붙는다",
     (await p11.locator("#cprice").inputValue()) === "57,035,000",
     await p11.locator("#cprice").inputValue());

  await p11.locator('#ccars button.carrow', { hasText: "GV80" }).click();
  await p11.waitForTimeout(150);
  // 파이썬 정답: calc(57035000, 4.1, False, 70, False) = 1,367,859
  ok("PC 앱과 같은 금액이 나온다",
     (await p11.locator("#cres").textContent()) === "₩ 1,367,859",
     await p11.locator("#cres").textContent());
  ok("적용한 수당율을 보여 준다",
     (await p11.locator("#crate").textContent()).includes("4.1%"));

  await p11.check("#cfree");
  await p11.waitForTimeout(150);
  // calc(57035000, 4.1, False, 70, True) = 1,298,641
  ok("면세를 켜면 금액이 바뀐다",
     (await p11.locator("#cres").textContent()) === "₩ 1,298,641",
     await p11.locator("#cres").textContent());
  await p11.uncheck("#cfree");

  await p11.fill("#cpay", "100");
  await p11.waitForTimeout(150);
  const want100 = (57035000 / 1.1572) * 0.041 * 1.0 * 0.967;
  ok("지급율을 바꾸면 반영된다",
     (await p11.locator("#cres").textContent())
     === "₩ " + Math.trunc(want100).toLocaleString("ko-KR"),
     await p11.locator("#cres").textContent());

  // 시트에 '수당율' 탭이 없어도 앱에 든 기본 표로 계산돼야 한다 —
  // PC 앱이 그렇게 동작한다. 폰만 못 쓰면 안 된다.
  ok("어느 표로 계산하는지 알려 준다",
     (await p11.locator("#csrc").textContent()).includes("공용 시트"),
     await p11.locator("#csrc").textContent());

  await p11.click("#creset");
  await p11.waitForTimeout(200);
  ok("초기화하면 0 으로 돌아온다", (await p11.locator("#cres").textContent()) === "₩ 0");
  ok("초기화하면 지급율이 70 으로 돌아온다",
     (await p11.locator("#cpay").inputValue()) === "70");
  await ctx9.close();
}

console.log("\n[16] 수당율 탭이 없을 때 — 앱에 든 기본 표로 계산되나");
{
  const ctxA = await browser.newContext({
    viewport: { width: 412, height: 900 }, timezoneId: "Asia/Seoul", locale: "ko-KR" });
  await ctxA.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const pA = await page(ctxA);
  await ctxA.route("**/accounts.google.com/**", (r) => r.abort());
  await ctxA.route("**/www.googleapis.com/**", (r) => r.fulfill({ json: { files: [] } }));
  await ctxA.route("**/tasks.googleapis.com/**", (r) => r.fulfill({ json: { items: [] } }));
  await ctxA.route("**/sheets.googleapis.com/**", (r) => r.fulfill({ status: 400, json: {
    error: { code: 400, message: "Unable to parse range: '수당율'!A1:D" } } }));

  await pA.goto(s.url + "#/calc", { waitUntil: "networkidle" });
  await pA.waitForSelector("#ccars button.carrow", { timeout: 10000 });
  const n = await pA.locator("#ccars .t").count();
  ok("탭이 없어도 차종이 나온다", n === 42, n + "종");
  ok("기본 표를 쓰고 있다고 알려 준다",
     (await pA.locator("#csrc").textContent()).includes("기본"),
     await pA.locator("#csrc").textContent());
  ok("PC 앱에서 저장하라고 일러 준다",
     (await pA.locator("#cerr").textContent()).includes("PC 앱"));

  await pA.locator("#cprice").pressSequentially("57035000", { delay: 5 });
  await pA.locator('#ccars button.carrow', { hasText: "GV80" }).first().click();
  await pA.waitForTimeout(150);
  ok("기본 표로도 PC 와 같은 금액이 나온다",
     (await pA.locator("#cres").textContent()) === "₩ 1,367,859",
     await pA.locator("#cres").textContent());
  await ctxA.close();
}

console.log("\n[17] 시트 주소를 안 정했을 때 · 계정이 바뀌었을 때");
{
  // (가) 기본 주소를 없앴으므로, 아무것도 안 정한 상태면 넣으라고 해야 한다.
  //      예전엔 여기에 특정인의 시트 주소가 박혀 있어서, 다른 직원이 자기
  //      계정으로 로그인해도 남의 고객 목록이 그대로 열렸다.
  const ctxB = await browser.newContext({ viewport: { width: 412, height: 900 } });
  await ctxB.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const pB = await page(ctxB);
  const asked = [];
  await ctxB.route("**/accounts.google.com/**", (r) => r.abort());
  await ctxB.route("**/oauth2/v3/userinfo", (r) => r.fulfill({ json: { email: "me@example.com" } }));
  await ctxB.route("**/sheets.googleapis.com/**", (r) => {
    asked.push(decodeURIComponent(r.request().url()));
    return r.fulfill({ json: { values: [] } });
  });
  await ctxB.route("**/www.googleapis.com/**", (r) => r.fulfill({ json: { files: [] } }));
  await ctxB.route("**/tasks.googleapis.com/**", (r) => r.fulfill({ json: { items: [] } }));

  await pB.goto(s.url + "#/customers", { waitUntil: "networkidle" });
  await pB.waitForTimeout(1200);
  const msg = await pB.locator("#clist .empty").textContent();
  ok("시트를 안 정했으면 정하라고 한다", msg.includes("시트 설정"), msg.slice(0, 40));
  // ⚠️ 남의 시트 주소가 박혀 있으면 안 된다 — 안 정했는데 조회를 시도하면 그 뜻이다
  ok("정하지 않았으면 고객 시트를 아예 조회하지 않는다",
     !asked.some((u) => u.includes("미출고차량")), asked.join(" "));
  ok("로그인한 계정을 화면에 보여 준다",
     (await pB.locator("#whochip").textContent()) === "me@example.com");
  await ctxB.close();

  // (나) 계정이 바뀌면 앞사람 자료가 남으면 안 된다.
  const ctxC = await browser.newContext({ viewport: { width: 412, height: 900 } });
  await seed(ctxC, {
    account: "앞사람@example.com",
    sheet: { id: "SECRETSHEET", tab: "미출고차량" },
    driveFolder: "앞사람 서류함",
    "split:kb": 300,
  });
  await ctxC.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "" }));
  });
  const pC = await page(ctxC);
  const touched = [];
  await ctxC.route("**/accounts.google.com/**", (r) => r.abort());
  await ctxC.route("**/oauth2/v3/userinfo", (r) =>
    r.fulfill({ json: { email: "새사람@example.com" } }));
  await ctxC.route("**/sheets.googleapis.com/**", (r) => {
    touched.push(decodeURIComponent(r.request().url()));
    return r.fulfill({ json: { values: [] } });
  });
  await ctxC.route("**/www.googleapis.com/drive/v3/**", (r) => {
    touched.push(decodeURIComponent(r.request().url()));
    return r.fulfill({ json: { files: [] } });
  });
  await ctxC.route("**/tasks.googleapis.com/**", (r) => r.fulfill({ json: { items: [] } }));
  await ctxC.route("**/www.googleapis.com/calendar/v3/**", (r) => r.fulfill({ json: { items: [] } }));

  await pC.goto(s.url + "#/customers", { waitUntil: "networkidle" });
  await pC.waitForTimeout(2000);
  const left = await pC.evaluate(() => new Promise((res) => {
    const q = indexedDB.open("planner", 1);
    q.onsuccess = () => {
      const t = q.result.transaction("meta", "readonly").objectStore("meta");
      const a = t.getAllKeys();
      a.onsuccess = () => {
        const g = q.result.transaction("meta", "readonly").objectStore("meta").get("account");
        g.onsuccess = () => res({ keys: a.result, account: g.result });
      };
    };
  }));
  ok("계정이 바뀌면 앞사람 계정을 새 계정으로 바꾼다",
     left.account === "새사람@example.com", String(left.account));
  ok("앞사람의 시트 주소를 지운다", !left.keys.includes("sheet"), left.keys.join(","));
  ok("앞사람의 서류 폴더도 지운다", !left.keys.includes("driveFolder"), left.keys.join(","));
  ok("화면 설정(목록 너비)은 남긴다", left.keys.includes("split:kb"), left.keys.join(","));
  ok("앞사람 시트를 조회하지 않는다",
     !touched.some((u) => u.includes("SECRETSHEET")),
     touched.filter((u) => u.includes("SECRET")).join(" "));
  const m2 = await pC.locator("#clist .empty").textContent();
  ok("새 계정에는 시트를 다시 정하라고 한다", m2.includes("시트 설정"), m2.slice(0, 40));
  await ctxC.close();
}

console.log("\n[18] 넓은 화면에서 서류가 지나치게 커지지 않는다");
{
  const ctxD = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  await seed(ctxD, { account: "me@example.com", driveFolder: "1AbCdEfGhIjKlMnOpQrStUvWxYz01234" });
  await ctxD.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const F = "application/vnd.google-apps.folder";
  const PNG2 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    "base64");
  const pD = await page(ctxD);
  await ctxD.route("**/accounts.google.com/**", (r) => r.abort());
  await ctxD.route("**/upload/drive/v3/**", (r) => r.fulfill({ json: { id: "W" } }));
  await ctxD.route("**/sheets.googleapis.com/**", (r) => r.fulfill({ json: { values: [] } }));
  await ctxD.route("**/tasks.googleapis.com/**", (r) => r.fulfill({ json: { items: [] } }));
  await ctxD.route("**/www.googleapis.com/calendar/v3/**", (r) => r.fulfill({ json: { items: [] } }));
  await ctxD.route("**/www.googleapis.com/drive/v3/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    if (u.includes("alt=media")) return r.fulfill({ body: PNG2, contentType: "image/png" });
    if (u.includes("files/1AbCdEfGhIjKlMnOpQrStUvWxYz01234?")) {
      return r.fulfill({ json: { id: "1AbCdEfGhIjKlMnOpQrStUvWxYz01234", mimeType: F } });
    }
    if (u.includes("in parents")) return r.fulfill({ json: { files: [
      { id: "z1", name: "계약서.jpg", mimeType: "image/jpeg", size: "1000" }] } });
    return r.fulfill({ json: { files: [] } });
  });

  await pD.goto(s.url + "#/docs", { waitUntil: "networkidle" });
  await pD.waitForSelector("#dlist button.row", { timeout: 10000 });
  await pD.locator("#dlist button.row").first().click();
  await pD.waitForSelector(".vimg", { timeout: 10000 });
  const box = await pD.evaluate(() => {
    const i = document.querySelector(".vimg").getBoundingClientRect();
    const v = document.querySelector(".vscroll").getBoundingClientRect();
    return { img: Math.round(i.width), imgX: Math.round(i.x),
             pane: Math.round(v.width), paneX: Math.round(v.x) };
  });
  // ⚠️ PC 처럼 넓은 화면에서 width:100% 만 두면 서류 한 장이 화면 전체로 늘어나
  //    오히려 읽기 어렵다. 종이가 편히 읽히는 폭까지만 키운다.
  ok("넓은 화면에서 서류가 화면 전체로 늘어나지 않는다",
     box.img <= 820, box.img + "px (칸 " + box.pane + "px)");
  ok("서류가 가운데에 온다",
     Math.abs((box.imgX - box.paneX) - (box.pane - box.img) / 2) < 3,
     `img x=${box.imgX} pane x=${box.paneX}`);
  await ctxD.close();
}

console.log("\n[19] 설정이 계정을 따라다니는지 (드라이브 앱 전용 폴더)");
{
  // 이 기기에는 아무것도 없다. 그런데 PC 앱이 올려 둔 설정이 계정에 있다.
  // → 폰에서 아무것도 입력하지 않아도 그대로 쓸 수 있어야 한다.
  const ctxE = await browser.newContext({ viewport: { width: 412, height: 900 } });
  await ctxE.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const pE = await page(ctxE);
  const PCCFG = JSON.stringify({ sheetId: "PCSHEET123", sheetName: "미출고차량(PC)",
                                 filesDriveFolder: "PC 서류함" });
  const wrote = [];
  await ctxE.route("**/accounts.google.com/**", (r) => r.abort());
  await ctxE.route("**/tasks.googleapis.com/**", (r) => r.fulfill({ json: { items: [] } }));
  await ctxE.route("**/www.googleapis.com/calendar/v3/**", (r) => r.fulfill({ json: { items: [] } }));
  await ctxE.route("**/upload/drive/v3/**", async (r) => {
    wrote.push(r.request().postData() || "");
    return r.fulfill({ json: { id: "W1" } });
  });
  await ctxE.route("**/www.googleapis.com/drive/v3/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    if (u.includes("appDataFolder") && u.includes("planner_web.json")) {
      return r.fulfill({ json: { files: [] } });          // 웹앱 파일은 아직 없다
    }
    if (u.includes("appDataFolder") && u.includes("planner_sync.json")) {
      return r.fulfill({ json: { files: [{ id: "SYNC1", name: "planner_sync.json" }] } });
    }
    if (u.includes("files/SYNC1") && u.includes("alt=media")) {
      return r.fulfill({ body: JSON.stringify({ files: { "plan_cfg.json": PCCFG } }),
                         contentType: "application/json" });
    }
    return r.fulfill({ json: { files: [] } });
  });
  const asked = [];
  await ctxE.route("**/sheets.googleapis.com/**", (r) => {
    asked.push(decodeURIComponent(r.request().url()));
    return r.fulfill({ json: { values: [] } });
  });

  await pE.goto(s.url + "#/customers", { waitUntil: "networkidle" });
  await pE.waitForTimeout(2000);
  // ⚠️ 이게 핵심이다. 폰에서 시트 주소를 한 번도 넣지 않았는데, PC 에 넣어 둔
  //    값을 계정에서 물려받아 바로 조회해야 한다.
  ok("PC 에 넣어 둔 시트를 그대로 물려받는다",
     asked.some((u) => u.includes("PCSHEET123")),
     asked.filter((u) => u.includes("spreadsheets/")).map((u) => u.slice(46, 60)).join(" "));
  ok("탭 이름도 물려받는다",
     asked.some((u) => u.includes("미출고차량(PC)")),
     asked.filter((u) => u.includes("!A1:Q")).map((u) => u.slice(-60)).join(" "));

  await pE.click('nav.tabs a[data-tab="/docs"]');
  await pE.waitForTimeout(800);
  ok("서류 폴더도 물려받아 설정 화면이 안 뜬다",
     (await pE.locator("#dsave").count()) === 0);

  // 폰에서 바꾸면 계정에도 올라가야 한다 — 다음에 PC 나 다른 기기에서 쓰게
  await pE.click('nav.tabs a[data-tab="/customers"]');
  await pE.waitForSelector("#cconf", { timeout: 8000 });
  await pE.click("#cconf");
  await pE.waitForSelector("#sid");
  await pE.fill("#sid", "PHONESHEET9");
  await ctxE.route("**/sheets.googleapis.com/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    asked.push(u);
    if (u.includes("fields=properties.title")) return r.fulfill({ json: {
      properties: { title: "폰에서 바꾼 시트" }, sheets: [{ properties: { title: "미출고차량" } }] } });
    return r.fulfill({ json: { values: [] } });
  });
  await pE.click("#sload");
  await pE.waitForTimeout(900);
  ok("폰에서 바꾼 설정을 계정에 올린다",
     wrote.some((b) => b.includes("PHONESHEET9")), wrote.join(" | ").slice(0, 120));
  await ctxE.close();
}

console.log("\n[20] 주간 요약 — 폰에서");
{
  const ctxF = await browser.newContext({
    viewport: { width: 412, height: 900 }, timezoneId: "Asia/Seoul", locale: "ko-KR" });
  await seed(ctxF, { account: "me@example.com",
                     sheet: { id: "WKSHEET", tab: "미출고차량" } });
  await ctxF.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const pF = await page(ctxF);
  // 오늘을 기준으로 이번 주 안의 날짜를 만든다(실행하는 날에 따라 안 흔들리게)
  const now = new Date();
  const wd = (now.getDay() + 6) % 7;
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - wd);
  const fmt = (d) => `${d.getFullYear()}. ${d.getMonth() + 1}. ${d.getDate()}`;
  const plus = (n) => { const x = new Date(monday); x.setDate(x.getDate() + n); return x; };
  const HDR = ["순번", "고객명/사업자", "금융사", "차종", "차량가격", "금융수수료",
               "대리점 수당", "합계", "특판/대리점", "계약일(발주)", "출고일", "진행현황",
               "계약조건", "내용", "출고유형", "고객센터 번호", "사고접수연락처"];
  const SHEET = [
    HDR,
    ["1", "김상현", "우리금융캐피탈", "쏘나타", "", "", "", "500,000", "",
     fmt(plus(0)), fmt(plus(2)), "출고완료", "60개월", "", "", "", ""],
    ["2", "박영희", "KB캐피탈", "아이오닉5", "", "", "", "300,000", "",
     fmt(plus(1)), "", "심사중", "48개월", "", "", "", ""],
    ["3", "한지민", "IM캐피탈", "G70", "", "", "", "900,000", "",
     fmt(plus(1)), fmt(plus(3)), "취소", "60개월", "", "", "", ""],
  ];
  await ctxF.route("**/accounts.google.com/**", (r) => r.abort());
  await ctxF.route("**/www.googleapis.com/**", (r) => r.fulfill({ json: { files: [] } }));
  await ctxF.route("**/tasks.googleapis.com/**", (r) => r.fulfill({ json: { items: [] } }));
  await ctxF.route("**/sheets.googleapis.com/**", (r) => {
    const u = decodeURIComponent(r.request().url());
    if (u.includes("batchGet")) {
      return r.fulfill({ json: { valueRanges: [
        { values: SHEET.map((x) => x.slice(0, 17)) }, { values: SHEET.map(() => []) }] } });
    }
    return r.fulfill({ json: { values: [] } });
  });

  await pF.goto(s.url + "#/customers", { waitUntil: "networkidle" });
  await pF.waitForSelector("#clist button.row", { timeout: 10000 });
  await pF.click("#cweek");
  await pF.waitForSelector(".wksec", { timeout: 8000 });

  const heads = await pF.locator(".wkhead").allTextContents();
  ok("이번 주 출고·계약 칸이 있다",
     heads.some((h) => h.includes("이번 주 출고")) && heads.some((h) => h.includes("이번 주 계약")),
     heads.join(" | "));
  const body = await pF.locator("#body").innerText();
  const names = await pF.locator(".wkitem .t").allTextContents();
  ok("이번 주 출고에 그 고객이 뜬다", names.includes("김상현"), names.join(", "));
  // ⚠️ 취소 건은 실적에도 예정에도 들어가면 안 된다
  ok("취소된 계약은 안 들어간다", !names.includes("한지민"), names.join(", "));
  ok("수수료 합계를 적는다",
     (await pF.locator(".wknote").first().textContent()).includes("수수료 합계"),
     await pF.locator(".wknote").first().textContent());
  ok("몇 명으로 계산했는지 알려 준다", body.includes("명으로 계산"));

  // 고객을 누르면 그 고객 상세로
  await pF.locator(".wkitem").first().click();
  await pF.waitForTimeout(600);
  ok("고객을 누르면 상세로 간다",
     (await pF.locator("#cdetail h2").count()) === 1
     || (await pF.locator("#cment").count()) === 1,
     await pF.evaluate(() => location.hash));

  await pF.goBack();
  await pF.waitForTimeout(400);
  ok("뒤로 오면 주간 요약이 그대로", (await pF.locator(".wksec").count()) > 0);
  await ctxF.close();
}

console.log("\n[21] 폰에서 고객 고치기 — 시트를 망가뜨리지 않는지");
{
  const ctxG = await browser.newContext({
    viewport: { width: 412, height: 900 }, timezoneId: "Asia/Seoul", locale: "ko-KR" });
  await seed(ctxG, { account: "me@example.com",
                     sheet: { id: "EDSHEET", tab: "미출고차량" } });
  await ctxG.addInitScript(() => {
    sessionStorage.setItem("planner.tok", JSON.stringify({
      token: "test-token-ascii-only", expiresAt: Date.now() + 3600e3, email: "me@example.com" }));
  });
  const pG = await page(ctxG);
  const HDR = ["순번", "고객명/사업자", "금융사", "차종", "차량가격", "금융수수료",
               "대리점 수당", "합계", "특판/대리점", "계약일(발주)", "출고일", "진행현황",
               "계약조건", "내용", "출고유형", "고객센터 번호", "사고접수연락처"];
  // 머리글이 1행 → 김상현은 **2행**이다 (parseRows 의 row = i+1)
  let SHEET = [
    HDR,
    ["1", "김상현", "우리금융캐피탈", "쏘나타", "35,000,000", "300,000", "200,000",
     "500,000", "대리점", "2026. 8. 1", "2026. 8. 20", "심사중", "60/2만", "메모",
     "신차", "1588-1111", "1588-2222"],
  ];
  const writes = [];
  let rowNow = () => SHEET[1];
  await ctxG.route("**/accounts.google.com/**", (r) => r.abort());
  await ctxG.route("**/www.googleapis.com/**", (r) => r.fulfill({ json: { files: [] } }));
  await ctxG.route("**/tasks.googleapis.com/**", (r) => r.fulfill({ json: { items: [] } }));
  await ctxG.route("**/sheets.googleapis.com/**", async (r) => {
    const u = decodeURIComponent(r.request().url());
    if (r.request().method() === "POST" && u.includes("values:batchUpdate")) {
      writes.push(JSON.parse(r.request().postData() || "{}"));
      return r.fulfill({ json: { totalUpdatedCells: 1 } });
    }
    if (u.includes("batchGet")) {
      // 한 줄만 묻는 경우(저장 직전 확인)와 전체 목록을 갈라 준다
      const one = /!A\d+:Q\d+/.test(u);
      const rows = one ? [rowNow()] : SHEET;
      return r.fulfill({ json: { valueRanges: [
        { values: rows.map((x) => x.slice(0, 17)) }, { values: rows.map(() => []) }] } });
    }
    if (/!S\d+:S\d+/.test(u)) return r.fulfill({ json: { values: [[""]] } });
    return r.fulfill({ json: { values: [] } });
  });

  await pG.goto(s.url + "#/customers", { waitUntil: "networkidle" });
  await pG.waitForSelector("#clist button.row", { timeout: 10000 });
  await pG.locator("#clist button.row").first().click();
  await pG.waitForSelector("#cedit", { timeout: 8000 });
  await pG.click("#cedit");
  await pG.waitForSelector("#esave", { timeout: 8000 });

  ok("견적서 칸은 아예 없다", (await pG.locator("#e_doc").count()) === 0);
  ok("고칠 수 있는 칸이 다 있다",
     (await pG.locator("#e_customer").count()) === 1
     && (await pG.locator("#e_status").count()) === 1
     && (await pG.locator("#e_price").count()) === 1
     && (await pG.locator("#e_contract_date").count()) === 1);
  ok("금융사 후보를 시트 값에서 뽑는다",
     (await pG.locator("#dl_finance option").first().getAttribute("value")) === "우리금융캐피탈");

  // 안 고치고 저장 → 아무것도 안 보낸다
  await pG.click("#esave");
  await pG.waitForTimeout(400);
  ok("바뀐 게 없으면 시트를 안 건드린다", writes.length === 0,
     JSON.stringify(writes).slice(0, 80));
  ok("바뀐 게 없다고 말해 준다",
     (await pG.locator("#emsg").textContent()).includes("바뀐 것이 없"));

  // 진행현황·금액·출고일을 고친다
  await pG.fill("#e_status", "출고완료");
  await pG.fill("#e_price", "36500000");
  await pG.fill("#e_deliver_date", "2026-09-05");
  await pG.click("#esave");
  await pG.waitForTimeout(900);

  ok("저장을 한 번 보낸다", writes.length === 1, writes.length);
  const body = writes[0] || {};
  const data = body.data || [];
  const ranges = data.map((d) => d.range);
  const val = (r) => (data.find((d) => d.range.endsWith("!" + r)) || {}).values?.[0]?.[0];

  ok("USER_ENTERED 로 보낸다", body.valueInputOption === "USER_ENTERED",
     body.valueInputOption);

  // ⚠️ 이 검사가 이 판에서 제일 중요하다. 수식 칸이 값으로 덮이면 시트가 망가진다.
  const FORMULA = ["A2", "H2", "P2", "Q2", "R2", "T2"];
  const hit = FORMULA.filter((c) => ranges.some((r) => r.endsWith("!" + c)));
  ok("수식 칸(A·H·P·Q·R·T)을 하나도 안 건드린다", hit.length === 0, hit.join(","));
  ok("견적서(S열)도 안 건드린다", !ranges.some((r) => /!S\d+$/.test(r)), ranges.join(" "));

  ok("고친 칸만 보낸다", data.length === 3, ranges.join(" "));
  ok("진행현황은 L열", val("L2") === "출고완료", val("L2"));
  // 금액은 콤마를 떼고 숫자로 — 안 그러면 시트 통화 서식이 깨진다
  ok("금액에 콤마가 없다", val("E2") === "36500000", val("E2"));
  // 날짜는 시트 서식으로, 0 을 안 채운다
  ok("날짜가 시트 서식이다", val("K2") === "2026. 9. 5", val("K2"));

  ok("저장하면 상세로 돌아간다",
     (await pG.evaluate(() => location.hash)) === "#/customers/2",
     await pG.evaluate(() => location.hash));
  await pG.waitForTimeout(400);
  ok("화면에도 바로 반영된다",
     (await pG.locator("#cdetail").innerText()).includes("출고완료"));

  // 미정으로 되돌리면 빈 문자열
  writes.length = 0;
  await pG.click("#cedit");
  await pG.waitForSelector("#esave");
  await pG.check("#u_deliver_date");
  await pG.click("#esave");
  await pG.waitForTimeout(800);
  const d2 = (writes[0] || {}).data || [];
  ok("'미정' 은 빈 문자열로 보낸다",
     d2.length === 1 && d2[0].range.endsWith("!K2") && d2[0].values[0][0] === "",
     JSON.stringify(d2));

  // 그 사이 누가 고쳤으면 묻는다
  writes.length = 0;
  SHEET[1][11] = "다른곳에서바꿈";        // 시트 쪽 진행현황이 바뀌었다
  rowNow = () => SHEET[1];
  pG.once("dialog", (d) => d.dismiss());   // [취소] 를 누른다
  await pG.click("#cedit");
  await pG.waitForSelector("#esave");
  await pG.fill("#e_status", "내가바꾼값");
  await pG.click("#esave");
  await pG.waitForTimeout(900);
  ok("그 사이 바뀌었으면 묻고, 취소하면 안 쓴다", writes.length === 0, writes.length);
  ok("왜 안 썼는지 말해 준다",
     (await pG.locator("#emsg").textContent()).includes("저장하지 않았"),
     await pG.locator("#emsg").textContent());
  await ctxG.close();
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
// 펼치면 격자로 바뀐다 — 왼쪽 한 줄은 탭 레일이 통째로 쓰고,
// 오른쪽은 위에 머리말, 아래에 본문이다.
// (예전엔 flex row 로 눕혔는데, 그러면 머리말까지 오른쪽에 세로 띠로 섰다 —
//  제목 '일정관리기' 가 화면 절반을 먹던 그 버그다. 자세한 건 [12] 에서 본다)
const wide = await p.evaluate(() => {
  const cs = getComputedStyle(document.querySelector("#app"));
  const g = (sel) => { const r = document.querySelector(sel).getBoundingClientRect();
                       return { x: r.x, y: r.y, w: r.width, h: r.height }; };
  return { display: cs.display, head: g("header"), body: g("#body"), tabs: g("nav.tabs") };
});
ok("넓으면 격자로 바뀐다", wide.display === "grid", wide.display);
ok("머리말은 가로로 눕고 본문 위에 있다",
   wide.head.w > 600 && wide.head.h < 120 && wide.head.y < wide.body.y,
   `머리말 ${Math.round(wide.head.w)}x${Math.round(wide.head.h)}`);
const rail = { w: wide.tabs.w, x: wide.tabs.x, bodyX: wide.body.x };
ok("레일이 세로로 선다", rail.w < 200, Math.round(rail.w) + "px");
// 세로로 서 있기만 보면 #app 이 안 눕는 버그를 놓친다(실제로 놓쳤다).
// 레일이 본문 **왼쪽**에 있는지까지 봐야 잡힌다.
ok("레일이 본문 왼쪽에 붙는다", rail.x < rail.bodyX,
   `rail=${Math.round(rail.x)} body=${Math.round(rail.bodyX)}`);

await browser.close();
await s2.close();
console.log("\n" + (fails ? `${fails}건 실패` : "전부 통과"));
process.exit(fails ? 1 : 0);
