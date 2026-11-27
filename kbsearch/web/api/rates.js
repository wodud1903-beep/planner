// GET /api/rates — 수당계산기의 수당율 표(읽기 전용). 서버가 꺼져 있으면 503 과 안내만 준다.
// /api/kb 와 같은 방식: 끝(edge)에 받아 둔 것을 바로 주고 5분이 지났으면 뒤에서 새로 받는다.
import { readState } from "../lib/state.js";
import { readRates, NotPublic } from "../lib/sheet.js";
import { send } from "../lib/http.js";

export default async function handler(req, res) {
  const [s, got] = await Promise.all([
    readState(),
    readRates().then((rows) => ({ rows }), (e) => ({ e })),
  ]);
  if (!s.on) return send(res, 503, { off: true, message: s.message }, "no-cache", "max-age=30");
  if (got.e) {
    return send(res, 502, { error: got.e instanceof NotPublic ? got.e.message : "수당율을 받지 못했습니다" });
  }
  send(res, 200, { rows: got.rows, at: new Date().toISOString() },
       "no-cache", "max-age=300, stale-while-revalidate=86400");
}
