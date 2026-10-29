// 업무자료검색 웹 검사 — 함수(api/*)를 Vercel 처럼 돌리고, 진짜 브라우저로 화면을 눌러 본다.
//   cd kbsearch/web && npm install && node verify/verify_web.mjs
// 시트는 진짜 공개 주소를 읽는다(로그인 없이 받는지가 핵심이다). 스위치 저장소는 가짜를 끼운다.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

process.env.KB_ADMIN_PASSWORD = "test-pass-1234";
const state = await import("../lib/state.js");
const sheet = await import("../lib/sheet.js");

let FAIL = [];
const ok = (name, cond, extra = "") => {
  console.log((cond ? "  OK  " : "  ** FAIL ** ") + name + (extra ? "  " + extra : ""));
  if (!cond) FAIL.push(name);
};

// ---- 가짜 Blob 저장소 ----
let blob = null, puts = 0, failGet = false;
state._setStore({
  async get(p, o) {
    if (failGet) throw new Error("store down");
    if (o.access !== "private") throw new Error("wrong access");
    return blob == null ? null : { stream: new Response(blob).body };
  },
  async put(p, body, o) {
    if (o.access !== "private" || !o.allowOverwrite || o.addRandomSuffix) throw new Error("bad put");
    blob = body; puts++;
  },
});

// ---- Vercel 처럼 돌리는 작은 서버 ----
const handlers = {};
for (const n of ["status", "kb", "switch"]) handlers[n] = (await import(`../api/${n}.js`)).default;
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };
let KB_DELAY = 0;                   // /api/kb 를 일부러 늦춰 '받는 동안' 화면을 본다
let JS_DELAY = 0;                   // app.js 를 늦춰도 자료 받기가 그것을 기다리지 않는지 본다
const LOG = [];                     // 들어온 요청 차례
const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, "http://x");
  LOG.push(u.pathname);
  const m = u.pathname.match(/^\/api\/(\w+)$/);
  if (m && handlers[m[1]]) {
    if (m[1] === "kb" && KB_DELAY) await new Promise((r) => setTimeout(r, KB_DELAY));
    let raw = "";
    try { for await (const c of req) raw += c; } catch (e) { return; }   // 브라우저가 끊음(새로 고침)
    if (res.destroyed) return;
    try { req.body = raw ? JSON.parse(raw) : {}; } catch (e) { req.body = raw; }
    return handlers[m[1]](req, res);
  }
  const f = path.join(ROOT, "public", u.pathname === "/" ? "index.html" : u.pathname);
  if (!f.startsWith(path.join(ROOT, "public")) || !fs.existsSync(f)) { res.statusCode = 404; return res.end(); }
  if (u.pathname === "/app.js" && JS_DELAY) await new Promise((r) => setTimeout(r, JS_DELAY));
  res.setHeader("Content-Type", MIME[path.extname(f)] || "application/octet-stream");
  fs.createReadStream(f).pipe(res);
  res.on("finish", () => LOG.push("done:" + u.pathname));
});
await new Promise((r) => server.listen(0, r));
const BASE = `http://127.0.0.1:${server.address().port}`;
const api = async (p, body) => {
  const r = await fetch(BASE + p, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  return [r.status, await r.json().catch(() => ({})), r.headers];
};

console.log("[1] CSV · 시트");
const rows = sheet.parseCsv('a,"b\n""c""",d\r\n1,2,3');
ok("여러 줄·따옴표 칸", JSON.stringify(rows) === JSON.stringify([["a", 'b\n"c"', "d"], ["1", "2", "3"]]));
const its = sheet.itemsFromRows([["캐피탈", "", "가", "", "본문", "", '{"title":"가","files":[{"id":"F1","name":"a.png"},{"id":"local-1","name":"b.png"}]}'],
                                 ["", "", "", "", "", "", ""], ["카테고리", "금융사", "제목"]]);
ok("빈 줄·머리글 건너뜀 · 이 PC 첨부(local-) 뺌", its.length === 1 && its[0].files.length === 1 && its[0].files[0].id === "F1");
const fakeResp = (status, type, text) => async () => new Response(text, { status, headers: { "content-type": type } });
for (const [why, f] of [["잠긴 시트(HTML)", fakeResp(200, "text/html", "<html>")],
                        ["첫 탭(수당율)이 옴", fakeResp(200, "text/csv", "구분,수당율\n1,2")]]) {
  let hit = false;
  try { await sheet.readKb(f); } catch (e) { hit = e instanceof sheet.NotPublic; }
  ok(`${why} → 받지 않음`, hit);
}

console.log("[2] 함수");
delete process.env.BLOB_READ_WRITE_TOKEN;
let [st, j] = await api("/api/status");
ok("저장소가 없으면 켜짐으로", st === 200 && j.on === true && j.store === false);
[st, j] = await api("/api/kb");
ok("로그인 없이 회사 공통 자료를 받는다", st === 200 && j.items.length > 5, `${j.items && j.items.length}건`);
const live = j.items || [];
[st, j] = await api("/api/switch", { password: "x" });
ok("틀린 비밀번호 → 401", st === 401);
[st, j] = await api("/api/switch", { password: "test-pass-1234", on: false });
ok("저장소가 없으면 끄지 못한다고 알린다", st === 503 && /저장소/.test(j.error));
process.env.BLOB_READ_WRITE_TOKEN = "vercel_blob_rw_fake";
[st, j] = await api("/api/switch", { password: "test-pass-1234" });
ok("비밀번호 확인 → 지금 상태", st === 200 && j.ok && j.on === true && j.store === true);
[st, j] = await api("/api/switch", { password: "test-pass-1234", on: false, message: "점검 중입니다" });
ok("끄기", st === 200 && j.on === false && JSON.parse(blob).on === false);
[st, j, ] = await api("/api/status");
ok("상태가 꺼짐 · 안내", j.on === false && j.message === "점검 중입니다");
[st, j] = await api("/api/kb");
ok("꺼지면 자료를 주지 않는다(503)", st === 503 && j.off === true);
failGet = true;
[st, j] = await api("/api/status");
ok("저장소를 못 읽으면 켜짐으로(fail-open)", j.on === true);
failGet = false;
[st, j] = await api("/api/switch", { password: "test-pass-1234", on: true });
ok("켜기", st === 200 && j.on === true);
[st, j] = await api("/api/switch", { password: "test-pass-1234", on: "yes" });
ok("on 이 참/거짓이 아니면 바꾸지 않는다", st === 200 && JSON.parse(blob).on === true);
ok("GET 으로는 못 바꾼다", (await api("/api/switch"))[0] === 405);

console.log("[3] 화면 (브라우저)");
const browser = await chromium.launch();
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  KB_DELAY = 2500;
  JS_DELAY = 800;
  LOG.length = 0;
  await page.goto(BASE + "/", { waitUntil: "commit" });
  await page.waitForTimeout(1200);
  ok("빠르게 — 자료 받기가 스크립트 파일을 기다리지 않는다",
     LOG.indexOf("/api/kb") >= 0 && LOG.indexOf("/api/kb") < LOG.indexOf("done:/app.js"), LOG.join(" "));
  JS_DELAY = 0;
  ok("빠르게 — 세 스크립트를 한꺼번에 받는다(차례로 기다리지 않는다)",
     ["/app.js", "/kb.js", "/hangul.js"].every((p) => LOG.includes(p)));
  ok("처음 — 받는 동안 목록 모양의 빈 자리", await page.locator("#list .sk").count() > 3);
  await page.waitForSelector("#list button.row", { timeout: 15000 });
  const t0 = Date.now();
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("#list button.row", { timeout: 2000 }).catch(() => {});
  const fast = Date.now() - t0;
  ok("다시 열면 — 받아 둔 자료가 기다리지 않고 바로 보인다", fast < 2000
     && await page.locator("#list button.row").count() === live.length, `${fast}ms`);
  const ft = await page.locator("#foot").innerText();
  ok("다시 열면 — '새로 받는 중' 을 알린다", /새로 받는 중/.test(ft), ft);
  await page.waitForFunction(() => /받음/.test(document.querySelector("#foot").innerText), null, { timeout: 15000 });
  ok("새 자료가 오면 '받음' 으로", true);
  KB_DELAY = 0;
  await page.keyboard.press("/");
  ok("'/' 를 누르면 검색칸", await page.evaluate(() => document.activeElement.id === "q"));
  const chip = await page.locator("#cats button").first().innerText();
  ok("분류마다 건수", chip.replace(/\s+/g, "") === "전체" + live.length, chip);
  ok("자료마다 분류 색 표시", await page.locator("#list .row .av").count() === live.length);
  await page.screenshot({ path: path.join(process.env.SHOT_DIR || "/tmp", "kbweb-hello.png") });
  await ctx.close();
}
for (const [label, vp] of [["넓은 화면", { width: 1280, height: 800 }], ["폰", { width: 390, height: 800 }]]) {
  const page = await browser.newPage({ viewport: vp });
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e)));
  await page.goto(BASE + "/");
  await page.waitForSelector("#list button.row");
  const n = await page.locator("#list button.row").count();
  ok(`${label} — 목록이 뜬다`, n === live.length, `${n}건`);
  await page.fill("#q", "ㄱㅇ ㅅㅅㅅㄹ");
  await page.waitForTimeout(400);
  const first = await page.locator("#list button.row .t").first().innerText();
  ok(`${label} — 초성으로 찾는다`, first === "개인 심사서류", first);
  await page.locator("#list button.row").first().click();
  ok(`${label} — 본문이 보인다`, (await page.locator("#detail .kbbody").innerText()).length > 10);
  ok(`${label} — 본문 복사 단추`, await page.locator("#copy").isEnabled());
  const ov = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  ok(`${label} — 가로로 넘치지 않는다`, !ov);
  if (label === "폰") {
    ok("폰 — 내용만 보인다", !(await page.locator(".left").isVisible()));
    await page.click("#back");
    await page.waitForTimeout(200);
    ok("폰 — [← 목록] 으로 돌아간다", await page.locator(".left").isVisible());
  }
  const withFile = live.find((it) => (it.files || []).length);
  if (withFile && label !== "폰") {
    await page.fill("#q", withFile.title);
    await page.waitForTimeout(400);
    await page.locator("#list button.row").first().click();
    ok("첨부가 보인다(드라이브 공개 주소)", await page.locator(".att").count() === withFile.files.length);
  }
  await page.screenshot({ path: path.join(process.env.SHOT_DIR || "/tmp", `kbweb-${vp.width}.png`) });
  ok(`${label} — 스크립트 오류 없음`, errs.length === 0, errs.join(" | "));
  await page.close();
}

const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.on("dialog", (d) => d.accept());
await page.goto(BASE + "/");
await page.waitForSelector("#list button.row");
await page.click("#btn-admin");
await page.fill("#pw", "틀림");
await page.click("#admin-go");
await page.waitForSelector("#admin-err:text('맞지 않습니다')", { timeout: 5000 }).catch(() => {});
ok("관리 — 틀린 비밀번호", /맞지 않습니다/.test(await page.locator("#admin-err").innerText()));
await page.fill("#pw", "test-pass-1234");
await page.click("#admin-go");
await page.waitForSelector("#admin-panel:not([hidden])");
ok("관리 — 켜짐 상태 · [끄기] 만 눌린다", /켜져/.test(await page.locator("#admin-state").innerText())
   && await page.locator("#btn-off").isEnabled() && !(await page.locator("#btn-on").isEnabled()));
await page.fill("#offmsg", "오늘은 쉽니다");
await page.click("#btn-off");
await page.waitForSelector("#admin-state.off");
ok("관리 — 끄면 저장소에 꺼짐", JSON.parse(blob).on === false && JSON.parse(blob).message === "오늘은 쉽니다");
ok("관리 — 화면도 꺼짐 안내", await page.locator("#off").isVisible()
   && (await page.locator("#off-msg").innerText()) === "오늘은 쉽니다");
await page.screenshot({ path: path.join(process.env.SHOT_DIR || "/tmp", "kbweb-admin.png") });
const p2 = await browser.newPage();
await p2.goto(BASE + "/");
await p2.waitForSelector("#off:not([hidden])");
ok("다른 사람이 열어도 꺼짐 안내만", await p2.locator("#off").isVisible() && !(await p2.locator("#split").isVisible()));
await p2.screenshot({ path: path.join(process.env.SHOT_DIR || "/tmp", "kbweb-off.png") });
await page.click("#btn-on");
await page.waitForSelector("#admin-state.on");
await page.waitForSelector("#list button.row");
ok("관리 — 다시 켜면 자료가 돌아온다", JSON.parse(blob).on === true && await page.locator("#split").isVisible());
await browser.close();
server.close();

console.log();
console.log("실패:", FAIL.length ? FAIL : "없음");
process.exit(FAIL.length ? 1 : 0);
