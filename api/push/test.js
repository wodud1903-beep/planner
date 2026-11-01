// [지금 한 번 받아 보기] — 오늘 브리핑을 지금 이 폰으로 보낸다(켜 둔 폰만).
const s = require("../_session.js");
const p = require("../_push.js");

module.exports = async (req, res) => {
  if (!s.guard(req, res)) return;
  if (!p.storeReady()) { s.send(res, 503, { error: "no_store" }); return; }
  const sess = s.unseal(s.cookie(req, s.SESSION));
  if (!sess || !sess.rt) { s.send(res, 401, { error: "signin" }); return; }
  const body = await p.readBody(req);
  const cur = body.endpoint ? await p.store().get(p.subId(body.endpoint)).catch(() => null) : null;
  if (!cur) { s.send(res, 404, { error: "not_subscribed" }); return; }
  let token;
  try { token = await p.accessFrom(sess.rt); }
  catch (e) { s.send(res, e.revoked ? 401 : 502, { error: e.revoked ? "signin" : "google" }); return; }
  const brief = await p.buildBrief(token, p.now());
  try {
    await p.send(cur.rec.sub, { ...brief, tag: "brief-test" });
  } catch (e) {
    if (e.statusCode === 404 || e.statusCode === 410) {
      await p.store().del(p.subId(body.endpoint)).catch(() => {});
      s.send(res, 410, { error: "gone" });
      return;
    }
    s.send(res, 502, { error: "push" });
    return;
  }
  s.send(res, 200, { ok: true, title: brief.title, body: brief.body });
};
