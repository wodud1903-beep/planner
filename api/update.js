// 업데이트 우회 길(v1.32) — 저장소를 비공개로 돌려도 PC 프로그램이 새 판을 받을 수 있게.
//
// 지금은 저장소가 공개라 PC 가 깃허브 릴리스를 바로 읽는다. 비공개로 돌리면 그 길이 404 가 된다.
// 그때 PC 는 여기로 온다 — 서버가 **읽기 전용 토큰**(환경변수 GITHUB_UPDATE_TOKEN)으로 대신 읽어 준다.
//
//   GET /api/update?app=planner|kb          → 200 {tag, name, notes, asset_url}
//   GET /api/update?app=…&dl=1[&tag=…]      → 302 (깃허브가 주는 잠깐 쓰는 내려받기 주소)
//                                              503 {error:"not_configured"}  토큰을 아직 안 넣었다
//
// 토큰은 응답에 싣지 않는다. 내려받기 주소는 깃허브가 서명한 몇 분짜리 주소다(릴리스 exe 는 지금도 공개다).
const REPO = "wodud1903-beep/planner";
const API = "https://api.github.com/repos/" + REPO;

function send(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(body));
}

const isKb = (tag) => /^kb-v/.test(tag || "");

async function gh(path, token, extra = {}) {
  return fetch(path.startsWith("http") ? path : API + path, {
    headers: { Authorization: "Bearer " + token, Accept: "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "jyplanner-update" },
    ...extra,
  });
}

// 그 프로그램의 가장 새 릴리스(초안·시험판 빼고). 일정관리기는 v…, 업무자료검색은 kb-v… 꼬리표다.
async function pick(app, token, tag) {
  const r = await gh("/releases?per_page=30", token);
  if (!r.ok) return { status: r.status };
  const list = (await r.json()).filter((x) => !x.draft && !x.prerelease
    && (app === "kb" ? isKb(x.tag_name) : !isKb(x.tag_name)));
  const rel = tag ? list.find((x) => x.tag_name === tag) : list[0];
  return { rel };
}

const exeOf = (rel) => (rel.assets || []).find((a) =>
  /\.exe$/i.test(a.name || "") || /\.exe$/i.test(a.label || ""));

module.exports = async (req, res) => {
  if (req.method !== "GET") { send(res, 405, { error: "method" }); return; }
  const token = (process.env.GITHUB_UPDATE_TOKEN || "").trim();
  if (!token) { send(res, 503, { error: "not_configured" }); return; }
  const q = new URL(req.url, "http://x").searchParams;
  const app = q.get("app") === "kb" ? "kb" : "planner";
  const tag = (q.get("tag") || "").slice(0, 40);
  let got;
  try { got = await pick(app, token, tag); } catch (e) { send(res, 502, { error: "github" }); return; }
  if (!got.rel) { send(res, got.status === 401 || got.status === 403 ? 502 : 404, { error: "no_release" }); return; }
  const asset = exeOf(got.rel);
  if (!asset) { send(res, 404, { error: "no_asset" }); return; }
  const self = `https://${req.headers.host}/api/update?app=${app}&dl=1&tag=${encodeURIComponent(got.rel.tag_name)}`;
  if (q.get("dl") !== "1") {
    send(res, 200, { tag: got.rel.tag_name, name: got.rel.name || got.rel.tag_name,
                     notes: got.rel.body || "", asset_url: self, size: asset.size || 0 });
    return;
  }
  let a;
  try {
    a = await gh(asset.url, token, { headers: { Authorization: "Bearer " + token, Accept: "application/octet-stream",
                                                "User-Agent": "jyplanner-update" }, redirect: "manual" });
  } catch (e) { send(res, 502, { error: "github" }); return; }
  const loc = a.headers.get("location");
  if (!loc) { send(res, 502, { error: "no_location" }); return; }
  res.statusCode = 302;
  res.setHeader("Location", loc);
  res.setHeader("Cache-Control", "no-store");
  res.end();
};
