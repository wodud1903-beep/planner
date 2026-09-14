// 저장 — IndexedDB.
//
// ⚠️ localStorage 를 쓰면 안 된다. 그건 **동기**라 켤 때 수 MB 를 JSON.parse 하는
//    동안 화면이 멈춘다. 정확히 피하려던 그 버벅임이다. IndexedDB 는 비동기이고
//    구조화 복제라 parse 단계가 아예 없다.
//
// 데이터셋마다 **레코드 하나**로 통째 저장한다. 어차피 화면마다 전체를 훑어 검색하고,
// 시트를 읽는 것도 전부 아니면 전무라서 줄 단위로 나눠 봐야 득이 없다.

const DB_NAME = "planner";
const DB_VER = 1;
let _db = null;

function open() {
  if (_db) return Promise.resolve(_db);
  return new Promise((res, rej) => {
    const req = indexedDB.open(DB_NAME, DB_VER);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta");
      if (!db.objectStoreNames.contains("data")) db.createObjectStore("data");
      if (!db.objectStoreNames.contains("recent")) {
        db.createObjectStore("recent", { keyPath: "uid" });
      }
    };
    req.onsuccess = () => { _db = req.result; res(_db); };
    req.onerror = () => rej(req.error);
  });
}

function tx(store, mode, fn) {
  return open().then((db) => new Promise((res, rej) => {
    const t = db.transaction(store, mode);
    const s = t.objectStore(store);
    let out;
    const r = fn(s);
    if (r) r.onsuccess = () => { out = r.result; };
    t.oncomplete = () => res(out);
    t.onerror = () => rej(t.error);
    t.onabort = () => rej(t.error);
  }));
}

export const get = (store, key) => tx(store, "readonly", (s) => s.get(key));
export const put = (store, key, val) =>
  tx(store, "readwrite", (s) => (store === "recent" ? s.put(val) : s.put(val, key)));
export const all = (store) => tx(store, "readonly", (s) => s.getAll());
export const del = (store, key) => tx(store, "readwrite", (s) => s.delete(key));

// 화면 상태(마지막 탭·검색어 등) — 작아서 meta 에 같이 둔다
export async function ui(patch) {
  const cur = (await get("meta", "ui")) || {};
  if (!patch) return cur;
  const next = { ...cur, ...patch };
  await put("meta", "ui", next);
  return next;
}


// ---------------------------------------------------------------- 계정 갈이
//
// ⚠️ 저장한 것은 **브라우저(기기)에 딸린 것이지 계정에 딸린 것이 아니다.**
//    그래서 다른 계정으로 로그인해도 앞사람의 고객 목록·일정·서류 폴더·시트
//    주소가 그대로 남아 보였다. 실제로 그렇게 드러났다.
//    PC 앱은 계정마다 폴더를 따로 쓰는데(config.data_dir), 웹에는 그 장치가
//    없었다. 계정이 바뀌면 앞사람 것을 지운다.
//
// 지우지 않는 것: 목록 너비(split:*) 처럼 누구 것이라도 상관없는 화면 설정.
const KEEP_META = (k) => String(k).startsWith("split:");

/** 지금 로그인한 계정을 알린다. 앞사람과 다르면 남은 것을 지운다.
 *  돌려주는 값이 true 면 지웠다는 뜻 — 화면을 다시 그려야 한다. */
export async function useAccount(email) {
  const who = (email || "").trim().toLowerCase();
  if (!who) return false;                       // 아직 누군지 모른다 — 건드리지 않는다
  const had = ((await get("meta", "account")) || "").trim().toLowerCase();
  if (had === who) return false;
  if (had) await wipe();                        // 처음 로그인이면 지울 것이 없다
  await put("meta", "account", who);
  return !!had;
}

/** 계정에 딸린 것을 모두 지운다. */
export async function wipe() {
  await tx("data", "readwrite", (s) => s.clear());
  await tx("recent", "readwrite", (s) => s.clear());
  const keys = await tx("meta", "readonly", (s) => s.getAllKeys());
  for (const k of keys || []) {
    if (k === "account" || KEEP_META(k)) continue;
    await del("meta", k);                       // 시트 주소·서류 폴더·멘트·검색어까지
  }
}

export const account = () => get("meta", "account");
