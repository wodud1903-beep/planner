// 알림 서명 공개키(VAPID) — 폰이 알림을 구독할 때 쓴다. 공개해도 되는 값이다.
const s = require("../_session.js");
const p = require("../_push.js");

module.exports = (req, res) => {
  const k = s.configured() ? p.vapid() : null;
  if (!k) { s.send(res, 503, { error: "not_configured" }); return; }
  if (!p.storeReady()) { s.send(res, 503, { error: "no_store" }); return; }
  s.send(res, 200, { publicKey: k.publicKey });
};
