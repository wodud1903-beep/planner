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
  const multi = live.find((it) => (it.files || []).filter((f) => !/\.pdf$/i.test(f.name)).length >= 2);
  if (multi) {
    await page.fill("#q", multi.title);
    await page.waitForTimeout(400);
    await page.locator("#list button.row").first().click();
    if (label === "폰") await page.waitForSelector("#detail .att");
    const n = multi.files.length;
    await page.locator(".att a.thumb").first().click();
    await page.waitForSelector("#viewer[open]");
    ok(`${label} — 첨부를 누르면 이 화면 안에서 크게(새 탭 아님)`, page.context().pages().length === 1
       && (await page.locator("#v-count").innerText()) === `1 / ${n}`);
    const src = await page.locator("#v-stage img, #v-stage iframe").first().getAttribute("src");
    ok(`${label} — 큰 그림(그림은 큰 크기 · PDF 는 미리보기)`,
       /\.pdf$/i.test(multi.files[0].name) ? /\/preview$/.test(src) : /sz=w2000/.test(src), src);
    ok(`${label} — 처음엔 [이전] 꺼짐`, await page.locator("#v-prev").isDisabled());
    await page.keyboard.press("ArrowRight");
    ok(`${label} — → 로 다음 첨부`, (await page.locator("#v-count").innerText()) === `2 / ${n}`
       && (await page.locator("#v-name").innerText()) === multi.files[1].name);
    await page.click("#v-prev");
    ok(`${label} — [◀] 단추로 앞 첨부`, (await page.locator("#v-count").innerText()) === `1 / ${n}`);
    for (let k = 0; k < n + 2; k++) await page.keyboard.press("ArrowRight");
    ok(`${label} — 끝에서 멈춘다 · [다음] 꺼짐`, (await page.locator("#v-count").innerText()) === `${n} / ${n}`
       && await page.locator("#v-next").isDisabled());
    await page.screenshot({ path: path.join(process.env.SHOT_DIR || "/tmp", `kbweb-viewer-${vp.width}.png`) });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);
    ok(`${label} — Esc 로 닫는다`, !(await page.locator("#viewer").evaluate((d) => d.open)));
  } else {
    ok("첨부가 여럿인 자료가 시트에 있다", false);
  }
  await page.screenshot({ path: path.join(process.env.SHOT_DIR || "/tmp", `kbweb-${vp.width}.png`) });
  ok(`${label} — 스크립트 오류 없음`, errs.length === 0, errs.join(" | "));
  await page.close();
}

console.log("[4] 이 기기에서만 고치기 — 팩스번호 등(PC 의 '이 PC 에서 고침' 과 같다)");
{
  const target = live.find((it) => /0504-214-5287/.test(it.body || ""));
  ok("팩스번호가 든 공통 자료가 있다", !!target, target && target.title);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const pg = await ctx.newPage();
  const errs = [];
  pg.on("pageerror", (e) => errs.push(String(e)));
  pg.on("dialog", (d) => d.accept());
  const open = async (title) => {
    await pg.fill("#q", title);
    await pg.waitForTimeout(400);
    await pg.locator("#list button.row").first().click();
    await pg.waitForSelector("#detail #edit");
  };
  await pg.goto(BASE + "/");
  await pg.waitForSelector("#list button.row");
  await open(target.title);
  ok("[수정] 단추가 있다", await pg.locator("#edit").isVisible());
  await pg.click("#edit");
  const ta = pg.locator("#ed-body");
  ok("누르면 본문을 고치는 칸(지금 본문이 들어 있다)", await ta.isVisible() && /0504-214-5287/.test(await ta.inputValue()));
  ok("이 기기에서만 바뀐다는 안내", /이 기기/.test(await pg.locator(".editor .hint").innerText()));
  await ta.fill((await ta.inputValue()).replaceAll("0504-214-5287", "0504-000-1111"));
  await pg.click("#ed-save");
  await pg.waitForSelector("#detail .kbbody");
  const body = await pg.locator("#detail .kbbody").innerText();
  ok("저장하면 고친 본문이 보인다", /0504-000-1111/.test(body) && !/0504-214-5287/.test(body));
  ok("'공통 · 이 기기에서 고침' 표시 · [회사 자료로 되돌리기]", /이 기기에서 고침/.test(await pg.locator("#detail .tags").innerText())
     && await pg.locator("#revert").isVisible());
  ok("아래 줄에 고친 건수", /이 기기에서 고친 것 1건/.test(await pg.locator("#foot").innerText()));
  await pg.reload();
  await pg.waitForSelector("#list button.row");
  await open("0504-000-1111");
  ok("다시 열어도 남아 있고 고친 내용으로도 찾는다", (await pg.locator("#detail h2").innerText()) === target.title
     && /0504-000-1111/.test(await pg.locator("#detail .kbbody").innerText()));
  const other = await browser.newContext();
  const op = await other.newPage();
  await op.goto(BASE + "/");
  await op.waitForSelector("#list button.row");
  await op.fill("#q", target.title);
  await op.waitForTimeout(400);
  await op.locator("#list button.row").first().click();
  ok("다른 사람(다른 브라우저)에게는 회사 원본 그대로", /0504-214-5287/.test(await op.locator("#detail .kbbody").innerText()));
  await other.close();
  await pg.screenshot({ path: path.join(process.env.SHOT_DIR || "/tmp", "kbweb-edited.png") });
  await pg.click("#revert");
  await pg.waitForSelector("#detail .tags");
  ok("되돌리면 회사 원본", /0504-214-5287/.test(await pg.locator("#detail .kbbody").innerText())
     && !/이 기기에서 고침/.test(await pg.locator("#detail .tags").innerText()));
  await pg.click("#edit");
  await pg.click("#ed-save");                       // 그대로 저장 — 고친 것이 없다
  ok("원본과 같으면 따로 남기지 않는다", await pg.evaluate(() => JSON.parse(localStorage.getItem("kbsearch:local:v1") || "[]").length) === 0);
  await pg.click("#edit");
  await pg.keyboard.press("Escape");
  ok("Esc 로 고치기를 그만둔다", !(await pg.locator("#ed-body").count()));
  await pg.setViewportSize({ width: 390, height: 800 });
  await pg.click("#edit");
  ok("폰 — 고치는 칸이 가로로 넘치지 않는다", !(await pg.evaluate(() => document.documentElement.scrollWidth > innerWidth)));
  await pg.screenshot({ path: path.join(process.env.SHOT_DIR || "/tmp", "kbweb-edit-phone.png") });
  ok("고치기 — 스크립트 오류 없음", errs.length === 0, errs.join(" | "));
  await ctx.close();
}

console.log("[5] 구글 동기화 — 심사서류 3종을 같은 계정의 PC 와 맞추기");
{
  const S = await import("../public/sync.js");
  // ---- 합치기 규칙(PC kbsearch/sync.py 와 같다)
  const T1 = "개인 심사서류", T2 = "개인사업자 심사서류", T3 = "법인 심사서류";
  const rec = (t, body, at) => ({ key: [t, 0], base: { title: t, body: "원본" }, item: { title: t, body }, at });
  let m = S.mergeEdits([rec(T1, "웹", "2026-11-07T01:00:00Z"), rec("캐피탈A", "내것", "")], {},
                       { [T1]: { item: { title: T1, body: "PC" }, base: null, at: "2026-11-07T02:00:00Z" } }, "2026-11-07T03:00:00Z");
  ok("나중에 고친 쪽이 이긴다(PC 가 나중)", m.recs.find((r) => r.key[0] === T1).item.body === "PC"
     && m.changedTitles.join() === T1 && !m.pushNeeded);
  ok("세 자료 말고 고친 것은 이 기기에만(드라이브에 안 감)", m.recs.some((r) => r.key[0] === "캐피탈A") && !("캐피탈A" in m.edits));
  m = S.mergeEdits([rec(T1, "웹", "2026-11-07T05:00:00Z")], {},
                   { [T1]: { item: { title: T1, body: "PC" }, base: null, at: "2026-11-07T02:00:00Z" } });
  ok("이 기기가 나중이면 올린다", m.pushNeeded && m.edits[T1].item.body === "웹" && !m.changedTitles.length);
  m = S.mergeEdits([], { [T2]: "2026-11-07T05:00:00Z" },
                   { [T2]: { item: { title: T2, body: "PC" }, base: null, at: "2026-11-07T02:00:00Z" } });
  ok("되돌린 것도 전한다(item=null)", m.pushNeeded && m.edits[T2].item === null && m.dead[T2]);
  m = S.mergeEdits([rec(T3, "웹", "2026-11-07T01:00:00Z")], {},
                   { [T3]: { item: null, base: null, at: "2026-11-07T02:00:00Z" } });
  ok("다른 곳에서 나중에 되돌렸으면 이 기기도 되돌린다", !m.recs.length && m.dead[T3] && m.changedTitles.join() === T3);
  m = S.mergeEdits([rec(T1, "옛날 것", "")], {},
                   { [T1]: { item: { title: T1, body: "PC" }, base: null, at: "2026-11-01T00:00:00Z" } });
  ok("동기화 전에 고친 것(시각 없음)은 드라이브 것에 진다", m.recs[0].item.body === "PC");
  m = S.mergeEdits([rec(T1, "옛날 것", "")], {}, {}, "2026-11-07T09:00:00Z");
  ok("드라이브가 비었으면 올린다(지금 시각으로)", m.pushNeeded && m.edits[T1].at === "2026-11-07T09:00:00Z");
  m = S.mergeEdits([], {}, { 다른자료: { item: { body: "x" }, at: "1" } });
  ok("모르는 칸은 그대로 둔다", !m.pushNeeded && m.edits.다른자료);

  // ---- 로그인 함수(api/auth/*) — jyplanner 가 대신 받은 쪽지를 쿠키에
  const A = await import("../lib/auth.js");
  const fres = () => { const r = { statusCode: 200, headers: {}, body: "" };
    r.setHeader = (k, v) => { r.headers[k.toLowerCase()] = v; }; r.end = (b) => { r.body = b || ""; };
    r.cookies = () => [].concat(r.headers["set-cookie"] || []); return r; };
  const login = (await import("../api/auth/login.js")).default;
  const accept = (await import("../api/auth/accept.js")).default;
  const tokenFn = (await import("../api/auth/token.js")).default;
  let r = fres();
  login({ url: "/api/auth/login?hint=me%40x.com", headers: {} }, r);
  const L = new URL(r.headers.location);
  const nonce = L.searchParams.get("n");
  ok("로그인은 jyplanner 로그인 길로(app=kb · 계정 힌트)", L.origin === "https://jyplanner.vercel.app"
     && L.pathname === "/api/auth/start" && L.searchParams.get("app") === "kb" && L.searchParams.get("hint") === "me@x.com");
  const stc = r.cookies().find((c) => c.startsWith(A.STATE + "="));
  ok("시작 값 쿠키 — HttpOnly · Secure · SameSite=None(POST 로 돌아올 때도 오게)",
     stc && stc.includes(nonce) && /HttpOnly/.test(stc) && /Secure/.test(stc) && /SameSite=None/.test(stc));
  const H = "sealed_" + "x".repeat(60);
  r = fres();
  await accept({ method: "POST", headers: { cookie: `${A.STATE}=${nonce}` }, body: { h: H, n: nonce, f: "ok" } }, r);
  const sc = r.cookies().find((c) => c.startsWith(A.SESSION + "="));
  ok("시작 값이 맞으면 쪽지를 쿠키에(HttpOnly · 400일) → /?auth=ok", r.statusCode === 303 && r.headers.location === "/?auth=ok"
     && sc && sc.includes(H) && /HttpOnly/.test(sc) && /Max-Age=34560000/.test(sc));
  r = fres();
  await accept({ method: "POST", headers: { cookie: `${A.STATE}=${nonce}` }, body: { h: H, n: "other-nonce-123456789", f: "ok" } }, r);
  ok("시작 값이 다르면(남이 밀어 넣은 로그인) 거절", r.headers.location === "/?auth=expired"
     && !r.cookies().some((c) => c.startsWith(A.SESSION + "=s")));
  r = fres();
  await accept({ method: "POST", headers: { cookie: `${A.STATE}=${nonce}` }, body: `h=${H}&n=${nonce}&f=partial` }, r);
  ok("폼 글자 그대로 와도 읽는다 · partial 전달", r.headers.location === "/?auth=partial");
  const realFetch = globalThis.fetch;
  let brokerReply = { status: 200, json: { access_token: "AT", expires_in: 3600, email: "me@x.com", missing: [] } }, brokerGot = null;
  globalThis.fetch = async (url, init) => {
    if (String(url).startsWith("https://jyplanner.vercel.app/")) {
      brokerGot = { url: String(url), body: JSON.parse(init.body) };
      return new Response(JSON.stringify(brokerReply.json), { status: brokerReply.status });
    }
    return realFetch(url, init);
  };
  const treq = (o = {}) => ({ method: "POST", headers: { origin: "https://kbsearch.vercel.app", host: "kbsearch.vercel.app",
                                                        cookie: `${A.SESSION}=${H}`, ...o } });
  r = fres();
  await tokenFn(treq(), r);
  ok("쓸 토큰 — 쪽지를 jyplanner 에 내밀어 받아 온다", r.statusCode === 200 && JSON.parse(r.body).access_token === "AT"
     && brokerGot.url.endsWith("/api/auth/kb-token") && brokerGot.body.h === H);
  r = fres();
  await tokenFn(treq({ origin: "https://evil.example" }), r);
  ok("다른 사이트에서 온 요청은 403", r.statusCode === 403);
  r = fres();
  await tokenFn(treq({ cookie: "" }), r);
  ok("로그인 전이면 401", r.statusCode === 401);
  brokerReply = { status: 401, json: { error: "signin", reason: "revoked" } };
  r = fres();
  await tokenFn(treq(), r);
  ok("권한을 뺐으면 401 + 쿠키 지움", r.statusCode === 401 && r.cookies().some((c) => c.startsWith(A.SESSION + "=;")));
  brokerReply = { status: 502, json: { error: "google" } };
  r = fres();
  await tokenFn(treq(), r);
  ok("잠깐 탈났으면 502(로그인은 그대로)", r.statusCode === 502 && !r.cookies().length);
  globalThis.fetch = realFetch;

  // ---- 화면 — 가짜 구글 드라이브(앱 전용 공간)로 PC 와 주고받기
  const pick = (t) => live.find((it) => it.title === t);
  ok("세 심사서류가 회사 자료에 있다", [T1, T2, T3].every(pick));
  const drive = { file: null, writes: 0 };     // 앱 전용 공간의 kb_edits.json
  const pcEdit = (t, body, at) => {
    const o = drive.file ? JSON.parse(drive.file) : { v: 1, edits: {} };
    o.edits[t] = { item: { ...pick(t), body }, base: { ...pick(t) }, at };
    drive.file = JSON.stringify(o);
  };
  const remote = () => (drive.file ? JSON.parse(drive.file).edits : {});
  let tokenStatus = 200;
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await ctx.route("**/api/auth/token", (rt) => rt.fulfill(tokenStatus === 200
    ? { json: { access_token: "AT", expires_in: 3600, email: "me@x.com", missing: [] } }
    : { status: 401, json: { error: "signin" } }));
  await ctx.route("**/api/auth/logout", (rt) => rt.fulfill({ json: { ok: true } }));
  await ctx.route("https://www.googleapis.com/**", async (rt) => {
    const rq = rt.request(), u = new URL(rq.url());
    if (rq.headers().authorization !== "Bearer AT" || tokenStatus !== 200) return rt.fulfill({ status: 401, body: "{}" });
    if (u.pathname === "/drive/v3/files" && rq.method() === "GET") {
      ok("드라이브는 앱 전용 공간만 본다", u.searchParams.get("spaces") === "appDataFolder");
      return rt.fulfill({ json: { files: drive.file ? [{ id: "F1" }] : [] } });
    }
    if (u.pathname === "/drive/v3/files/F1" && u.searchParams.get("alt") === "media") return rt.fulfill({ body: drive.file || "" });
    if (u.pathname === "/upload/drive/v3/files/F1" && rq.method() === "PATCH") {
      drive.file = rq.postData(); drive.writes++; return rt.fulfill({ json: { id: "F1" } });
    }
    if (u.pathname === "/upload/drive/v3/files" && rq.method() === "POST") {
      const parts = rq.postData().split(/--kbsearch\w+/);
      const meta = JSON.parse(parts[1].split("\r\n\r\n")[1]);
      ok("새 파일은 앱 전용 공간에 kb_edits.json 으로", meta.name === "kb_edits.json" && meta.parents[0] === "appDataFolder");
      drive.file = parts[2].split("\r\n\r\n").slice(1).join("\r\n\r\n").replace(/\r\n$/, ""); drive.writes++;
      return rt.fulfill({ json: { id: "F1" } });
    }
    return rt.fulfill({ status: 404, body: "{}" });
  });
  const pg = await ctx.newPage();
  const errs = [];
  pg.on("pageerror", (e) => errs.push(String(e)));
  pg.on("dialog", (d) => d.accept());
  const open = async (title) => {
    if (await pg.locator("#syncdlg[open]").count()) await pg.click("#sync-close");
    await pg.fill("#q", title);
    await pg.waitForTimeout(400);
    await pg.locator("#list button.row", { hasText: title }).first().click();
    await pg.waitForSelector("#detail #edit");
  };
  const bodyNow = () => pg.locator("#detail .kbbody").innerText();
  const until = async (fn, ms = 5000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await fn()) return true; await pg.waitForTimeout(100); } return false; };

  await pg.goto(BASE + "/");
  await pg.waitForSelector("#list button.row");
  ok("[구글 동기화] 단추가 위에 있다", await pg.locator("#btn-sync").isVisible());
  await pg.click("#btn-sync");
  ok("로그인 전 — 설명과 [구글 로그인]", await pg.locator("#syncdlg[open]").count() === 1
     && await pg.locator("#sync-login").isVisible() && /개인 · 개인사업자 · 법인 심사서류/.test(await pg.locator("#syncdlg .sub").innerText()));
  const [navReq] = await Promise.all([pg.waitForRequest((q) => q.url().includes("/api/auth/login")), pg.click("#sync-login")]);
  ok("[구글 로그인] 은 로그인 길로 간다", !!navReq);

  // PC 에서 개인 심사서류의 팩스번호를 고치고 [동기화] 해 둔 상태
  pcEdit(T1, pick(T1).body.replaceAll("0504-214-5287", "0504-777-8888"), "2026-11-07T00:00:00Z");
  await pg.goto(BASE + "/?auth=ok");
  await pg.waitForSelector("#list button.row");
  ok("로그인에서 돌아오면 바로 맞춘다 · 주소의 ?auth= 는 지운다", await until(async () =>
     /받았습니다/.test(await pg.locator("#sync-err").innerText())) && !(await pg.evaluate(() => location.search)).includes("auth"));
  ok("계정이 보인다 · 단추에 초록 점", /me@x\.com/.test(await pg.locator("#sync-state").innerText())
     && await pg.locator("#btn-sync.on").count() === 1);
  await pg.screenshot({ path: path.join(process.env.SHOT_DIR || "/tmp", "kbweb-sync.png") });
  await open(T1);
  ok("PC 에서 고친 팩스번호가 웹에 보인다", /0504-777-8888/.test(await bodyNow()));
  ok("'공통 · 내 계정에서 고침' 표시", /내 계정에서 고침/.test(await pg.locator("#detail .tags").innerText()));

  // 웹에서 개인사업자 심사서류를 고치면 드라이브(→ PC)로 간다
  await open(T2);
  await pg.click("#edit");
  ok("고치는 칸 안내 — PC 에도 반영된다", /PC 업무자료검색에도 반영/.test(await pg.locator(".editor .hint").innerText()));
  await pg.fill("#ed-body", (await pg.locator("#ed-body").inputValue()) + "\n웹에서 덧붙임 0504-123-4567");
  await pg.click("#ed-save");
  ok("저장하면 곧 드라이브에 올라간다", await until(() => /0504-123-4567/.test((remote()[T2] || {}).item?.body || "")));
  ok("올린 것에 고친 시각", /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(remote()[T2].at));
  // 세 자료 말고는 가지 않는다
  const nonSync = live.find((it) => ![T1, T2, T3].includes(it.title) && (it.body || "").trim());
  await open(nonSync.title);
  await pg.click("#edit");
  await pg.fill("#ed-body", "나만 쓰는 메모");
  const w0 = drive.writes;
  await pg.click("#ed-save");
  await pg.waitForTimeout(1200);
  ok("다른 자료를 고친 것은 드라이브에 가지 않는다", drive.writes === w0 && !(nonSync.title in remote()));
  // 되돌리면 되돌림도 전한다
  await open(T1);
  await pg.click("#revert");
  ok("되돌리면 PC 에도 되돌림을 전한다(item=null)", await until(() => remote()[T1] && remote()[T1].item === null));
  ok("웹은 회사 원본", /0504-214-5287/.test(await bodyNow()));

  // 그사이 PC 에서 법인 심사서류를 고침 → 다시 열면 저절로 받는다
  pcEdit(T3, pick(T3).body + "\nPC 에서 고친 줄", "2099-01-01T00:00:00Z");
  await pg.reload();
  await pg.waitForSelector("#list button.row");
  await until(async () => (await pg.evaluate(() => localStorage.getItem("kbsearch:local:v1") || "")).includes("PC 에서 고친 줄"));
  await open(T3);
  ok("다시 열면 로그인 그대로 · 저절로 받는다", /PC 에서 고친 줄/.test(await bodyNow()));
  await pg.setViewportSize({ width: 390, height: 800 });
  ok("폰 — 위 단추들이 가로로 넘치지 않는다", !(await pg.evaluate(() => document.documentElement.scrollWidth > innerWidth)));
  await pg.screenshot({ path: path.join(process.env.SHOT_DIR || "/tmp", "kbweb-sync-phone.png") });
  await pg.setViewportSize({ width: 1280, height: 800 });
  // 구글에서 권한을 뺐거나 로그인이 끝났다
  tokenStatus = 401;
  await pg.click("#btn-sync");
  ok("로그인이 끝났으면 다시 로그인하라고 · 초록 점 꺼짐", await until(async () =>
     /다시 눌러/.test(await pg.locator("#sync-err").innerText())) && await pg.locator("#btn-sync.on").count() === 0
     && await pg.locator("#sync-login").isVisible());
  await pg.goto(BASE + "/?auth=partial");
  await pg.waitForSelector("#syncdlg[open]");
  ok("동의 화면에서 덜 체크했으면 안내", /체크/.test(await pg.locator("#sync-err").innerText()));
  ok("동기화 — 스크립트 오류 없음", errs.length === 0, errs.join(" | "));
  await ctx.close();
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
