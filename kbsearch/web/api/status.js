// GET /api/status — 서버 스위치 상태. PC 프로그램도 이것을 본다(config.SWITCH_URL).
//   { on: true|false, message, at }
// 끝(edge)에서 30초 묶어 둔다 — 직원 PC 가 많아도 저장소를 그만큼 덜 읽는다.
import { readState } from "../lib/state.js";
import { send } from "../lib/http.js";

export default async function handler(req, res) {
  const s = await readState();
  send(res, 200, { on: s.on, message: s.message, at: s.at, store: s.store },
       "public, max-age=0, s-maxage=30, stale-while-revalidate=30");
}
