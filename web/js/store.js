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
