// 아침 브리핑 폰 알림 — 브라우저 쪽. 서버는 api/push/*.
//
// 켜기: 알림 허락 → 서비스워커로 구독 → 서버에 알림 주소를 맡긴다(로그인과 묶인다).
// 켜 둔 폰은 앱을 열 때 하루 한 번 서버에 다시 알려, 로그인을 새로 했으면 그것으로 바꾼다.
import * as auth from "./auth.js";

const API = "./api/push/";
const TOUCH = "planner.push.touched";       // 마지막으로 서버에 다시 알린 날

const post = (name, body) => fetch(API + name, {
  method: "POST", credentials: "same-origin", cache: "no-store",
  headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
});

/** 이 브라우저에서 알림을 쓸 수 있나. 못 쓰면 이유(사람 말). */
export function support() {
  try {
    if (!("serviceWorker" in navigator) || !navigator.serviceWorker) return "이 브라우저는 알림을 받을 수 없어요.";
    if (!("PushManager" in window) || !("Notification" in window)) {
      const ios = /iPhone|iPad|iPod/i.test(navigator.userAgent || "");
      return ios ? "아이폰은 '홈 화면에 추가' 한 앱에서만 알림을 받을 수 있어요."
                 : "이 브라우저는 알림을 받을 수 없어요. 크롬·삼성 인터넷에서 열어 주세요.";
    }
  } catch (e) { return "이 브라우저는 알림을 받을 수 없어요."; }
  return "";
}

async function reg() {
  return navigator.serviceWorker.ready;
}

/** 지금 이 폰의 구독(없으면 null). */
export async function current() {
  if (support()) return null;
  try { return await (await reg()).pushManager.getSubscription(); } catch (e) { return null; }
}

function keyBytes(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

/** [알림 켜기] — 결과: "" 성공 | 사람 말로 된 이유. */
export async function enable() {
  const why = support();
  if (why) return why;
  if (auth.mode() !== "server") return "먼저 로그인해 주세요(로그인 서버를 쓰는 새 주소에서).";
  const perm = await Notification.requestPermission();
  if (perm !== "granted") {
    return perm === "denied"
      ? "알림이 막혀 있어요. 브라우저 주소창의 자물쇠 → 권한 → 알림을 '허용' 으로 바꿔 주세요."
      : "알림을 허락해야 받을 수 있어요.";
  }
  const kr = await fetch(API + "key", { cache: "no-store" });
  if (!kr.ok) {
    let e = "";
    try { e = (await kr.json()).error || ""; } catch (x) {}
    return e === "no_store"
      ? "알림 저장소를 아직 연결하지 않았어요(Vercel → Storage 에서 한 번 만들면 됩니다)."
      : "알림 서버가 아직 준비되지 않았어요.";
  }
  const { publicKey } = await kr.json();
  const r = await reg();
  let sub = await r.pushManager.getSubscription();
  if (!sub) {
    sub = await r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) });
  }
  const res = await post("subscribe", { subscription: sub.toJSON() });
  if (res.status === 401) return "로그인이 필요해요. 위 [로그인] 을 먼저 눌러 주세요.";
  if (!res.ok) return "알림을 켜지 못했어요. 잠시 뒤 다시 해 주세요.";
  try { localStorage.setItem(TOUCH, new Date().toDateString()); } catch (e) {}
  return "";
}

/** [알림 끄기] */
export async function disable() {
  const sub = await current();
  if (!sub) return;
  const ep = sub.endpoint;
  try { await sub.unsubscribe(); } catch (e) { /* 이미 없다 */ }
  try { await post("unsubscribe", { endpoint: ep }); } catch (e) { /* 다음에 서버가 지운다(410) */ }
}

/** [지금 한 번 받아 보기] — 결과 {ok, title, body} | {error} */
export async function test() {
  const sub = await current();
  if (!sub) return { error: "알림이 꺼져 있어요." };
  const r = await post("test", { endpoint: sub.endpoint });
  if (r.ok) return r.json();
  return { error: r.status === 401 ? "로그인이 필요해요."
    : r.status === 410 ? "이 폰의 알림 주소가 바뀌었어요. 알림을 껐다 다시 켜 주세요."
    : "보내지 못했어요. 잠시 뒤 다시 해 주세요." };
}

/** 켜 둔 폰이면 하루 한 번 서버에 다시 알린다(새로 로그인했으면 그 로그인으로). */
export async function touch() {
  try {
    if (auth.mode() !== "server") return;
    const today = new Date().toDateString();
    if (localStorage.getItem(TOUCH) === today) return;
    const sub = await current();
    if (!sub) return;
    const r = await post("subscribe", { subscription: sub.toJSON() });
    if (r.ok) localStorage.setItem(TOUCH, today);
  } catch (e) { /* 다음에 다시 */ }
}
