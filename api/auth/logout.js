// 로그아웃 — 이 기기의 로그인(쿠키)을 지운다. 계정 바꾸기 전에도 부른다.
// 구글 쪽 권한은 그대로 둔다(PC 앱·다른 기기는 계속 쓴다).
const s = require("../_session.js");

module.exports = (req, res) => {
  if (!s.guard(req, res, { needConfig: false })) return;
  s.setCookies(res, [s.clearSession()]);
  s.send(res, 200, { ok: true });
};
