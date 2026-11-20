// GET /api/kb — 회사 공통 업무자료(읽기 전용). 서버가 꺼져 있으면 503 과 안내만 준다.
//
// 빠르게: 시트(구글)를 새로 읽는 데 2초쯤 걸린다. 그래서 끝(edge)에 받아 둔 것을 **바로** 주고
// (5분이 지났으면 그것을 주면서 뒤에서 새로 받는다 — stale-while-revalidate, 하루까지),
// 스위치 확인과 시트 읽기는 **함께** 한다. 관리자가 시트를 고치면 웹에는 5분쯤 안에 보인다.
// 끄는 것은 화면이 /api/status 로도 따로 보므로 바로 막힌다.
import { readState } from "../lib/state.js";
import { readKb, NotPublic } from "../lib/sheet.js";
import { send } from "../lib/http.js";

export default async function handler(req, res) {
  const [s, got] = await Promise.all([
    readState(),
    readKb().then((items) => ({ items }), (e) => ({ e })),
  ]);
  if (!s.on) return send(res, 503, { off: true, message: s.message }, "no-cache", "max-age=30");
  if (got.e) {
    return send(res, 502, { error: got.e instanceof NotPublic ? got.e.message : "자료를 받지 못했습니다" });
  }
  send(res, 200, { items: got.items, at: new Date().toISOString() },
       "no-cache", "max-age=300, stale-while-revalidate=86400");
}
