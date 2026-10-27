// GET /api/kb — 회사 공통 업무자료(읽기 전용). 서버가 꺼져 있으면 503 과 안내만 준다.
import { readState } from "../lib/state.js";
import { readKb, NotPublic } from "../lib/sheet.js";
import { send } from "../lib/http.js";

export default async function handler(req, res) {
  const s = await readState();
  if (!s.on) return send(res, 503, { off: true, message: s.message }, "public, s-maxage=30");
  try {
    const items = await readKb();
    send(res, 200, { items, at: new Date().toISOString() },
         "public, max-age=0, s-maxage=120, stale-while-revalidate=600");
  } catch (e) {
    send(res, 502, { error: e instanceof NotPublic ? e.message : "자료를 받지 못했습니다" });
  }
}
