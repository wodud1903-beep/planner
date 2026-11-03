// 금요일 주간 보고 알림 — Vercel 예약 작업이 부른다(vercel.json crons, v1.26).
// 금요일 16:50 뒤 첫 예약 작업에 폰마다 그 주에 한 번. 하는 일은 cron.js 와 같다.
const cron = require("./cron.js");

module.exports = (req, res) => cron.run(req, res, "weekly");
