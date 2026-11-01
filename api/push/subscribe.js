// [알림 켜기] — 이 폰의 알림 주소를 로그인(쿠키의 갱신 토큰)과 묶어 둔다.
// 켜 둔 폰은 앱을 열 때마다 다시 불러, 로그인을 새로 했으면 그 토큰으로 바꿔 둔다.
//
//   POST /api/push/subscribe {subscription}  →  200 {ok, id}
//                                                401 로그인 전 · 400 이상한 주소
const s = require("../_session.js");
const p = require("../_push.js");

module.exports = async (req, res) => {
  if (!s.guard(req, res)) return;
  if (!p.storeReady()) { s.send(res, 503, { error: "no_store" }); return; }
  const sess = s.unseal(s.cookie(req, s.SESSION));
  if (!sess || !sess.rt) { s.send(res, 401, { error: "signin" }); return; }
  const body = await p.readBody(req);
  const sub = body.subscription;
  if (!p.validSub(sub)) { s.send(res, 400, { error: "subscription" }); return; }
  const id = p.subId(sub.endpoint);
  let last = "";
  try { const cur = await p.store().get(id); last = (cur && cur.rec && cur.rec.last) || ""; }
  catch (e) { /* 처음 */ }
  await p.store().put(id, {
    sub: { endpoint: sub.endpoint, keys: { p256dh: sub.keys.p256dh, auth: sub.keys.auth } },
    rt: sess.rt, email: sess.email || "", at: Date.now(), last,
  });
  s.send(res, 200, { ok: true, id });
};
