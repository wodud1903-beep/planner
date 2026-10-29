// 함수 공통 — JSON 응답.
//   cache : 브라우저가 보는 Cache-Control
//   edge  : Vercel 끝(CDN)만 보는 묶어 두기(Vercel-CDN-Cache-Control). 브라우저에는 가지 않는다 —
//           브라우저가 stale-while-revalidate 를 따르면 '한 번 늦은' 자료를 보여 주기 때문이다.
export function send(res, status, body, cache = "no-store", edge = "") {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", cache);
  if (edge) res.setHeader("Vercel-CDN-Cache-Control", edge);
  res.end(JSON.stringify(body));
}
