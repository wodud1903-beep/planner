// [알림 끄기] — 이 폰의 알림 기록을 지운다(로그인 토큰도 같이 지워진다).
const s = require("../_session.js");
const p = require("../_push.js");

module.exports = async (req, res) => {
  if (!s.guard(req, res, { needConfig: false })) return;
  const body = await p.readBody(req);
  const ep = String(body.endpoint || "");
  if (!ep) { s.send(res, 400, { error: "endpoint" }); return; }
  try { await p.store().del(p.subId(ep)); } catch (e) { /* 이미 없다 */ }
  s.send(res, 200, { ok: true });
};
