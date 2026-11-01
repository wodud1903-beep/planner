// 아침 브리핑 보내기 — Vercel 예약 작업이 부른다(vercel.json crons).
//
// 무료 요금제의 예약 작업은 정한 '시' 안 아무 때나 돈다. 그래서 여러 번 걸어 두고
// 한국 시각 8:50 이 지난 첫 번째에 폰마다 하루 한 번 보낸다(같은 날 두 번 안 보낸다).
// 남이 이 주소를 불러도 할 수 있는 일은 '오늘 보낼 것을 조금 일찍(8:50 뒤) 보내기' 뿐이다.
const s = require("../_session.js");
const p = require("../_push.js");

function allowed(req) {
  const secret = process.env.CRON_SECRET || "";
  if (secret) return (req.headers.authorization || "") === `Bearer ${secret}`;
  return /vercel-cron/i.test(req.headers["user-agent"] || "");
}

module.exports = async (req, res) => {
  if (!allowed(req)) { s.send(res, 403, { error: "cron" }); return; }
  if (!s.configured() || !p.storeReady()) { s.send(res, 503, { error: "not_configured" }); return; }
  // ?check=1 — 저장소(비공개 Blob)에 실제로 닿는지만 본다(보내지 않는다). 설정 확인용.
  if (/[?&]check=1\b/.test(req.url || "")) {
    try {
      const n = (await p.store().list()).length;
      s.send(res, 200, { ok: true, store: "ok", subscriptions: n });
    } catch (e) {
      s.send(res, 500, { ok: false, store: "fail", error: String(e && e.message || e).slice(0, 200) });
    }
    return;
  }
  const now = p.now();
  if (!p.dueNow(now)) { s.send(res, 200, { ok: true, skipped: "time" }); return; }
  const today = p.kst(now).ymd;
  const st = p.store();
  const ids = await st.list();
  const out = { sent: 0, skipped: 0, removed: 0, failed: 0 };
  for (const id of ids) {
    let cur;
    try { cur = await st.get(id); } catch (e) { out.failed++; continue; }
    if (!cur || !cur.rec) { out.skipped++; continue; }
    const rec = cur.rec;
    if (rec.last === today) { out.skipped++; continue; }
    // 먼저 '오늘 보냄' 으로 표시한다 — 예약 작업 둘이 겹쳐 돌아도 한 번만 보내게(ETag)
    try { await st.put(id, { ...rec, last: today }, cur.etag); }
    catch (e) { out.skipped++; continue; }
    try {
      const token = await p.accessFrom(rec.rt);
      await p.send(rec.sub, await p.buildBrief(token, now));
      out.sent++;
    } catch (e) {
      if (e.revoked || e.statusCode === 404 || e.statusCode === 410) {
        // 구글에서 권한을 뺐거나 폰이 알림 주소를 버렸다 — 기록을 지운다
        await st.del(id).catch(() => {});
        out.removed++;
      } else {
        // 잠깐 탈났다 — 다음 예약 작업에서 다시 해 보게 표시를 되돌린다
        await st.put(id, { ...rec, last: rec.last || "" }).catch(() => {});
        out.failed++;
      }
    }
  }
  s.send(res, 200, { ok: true, ...out });
};
