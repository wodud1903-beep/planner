// 서버 스위치 — 웹페이지와 PC 프로그램(업무자료검색)이 함께 본다.
//
// Vercel Blob 에 작은 JSON 하나로 둔다: { on, message, at }.
//   · 저장소가 아직 연결되지 않았거나 파일이 없으면 **켜짐**으로 본다.
//   · 읽다가 오류가 나도 켜짐으로 본다(fail-open) — 저장소 사고로 전 직원이 멈추면 안 된다.
//     끄는 것은 관리자가 [끄기] 를 눌러 '꺼짐' 이 확실히 적혔을 때뿐이다.
import { get, put } from "@vercel/blob";

// 검사(verify/verify_web.mjs)가 가짜 저장소를 끼운다
let store = { get, put };
export function _setStore(s) { store = s; }

const PATH = "kbsearch/switch.json";
export const DEFAULT_OFF_MESSAGE =
  "업무자료검색 서비스가 종료되었습니다.\n그동안 이용해 주셔서 감사합니다.";

export const storeReady = () => Boolean(process.env.BLOB_READ_WRITE_TOKEN);

// 저장소를 만들 때 '비공개/공개' 중 무엇을 골랐는지 모른다 — 둘 다 해 본다.
const ACCESS = ["private", "public"];

function clean(o) {
  const on = !(o && o.on === false);
  return {
    on,
    message: on ? "" : String((o && o.message) || DEFAULT_OFF_MESSAGE).slice(0, 300),
    at: String((o && o.at) || ""),
  };
}

export async function readState() {
  if (!storeReady()) return { ...clean(null), store: false };
  let lastErr = null;
  for (const access of ACCESS) {
    try {
      const r = await store.get(PATH, { access, useCache: false });
      if (!r) return { ...clean(null), store: true };          // 아직 한 번도 안 적음
      const text = await new Response(r.stream).text();
      return { ...clean(JSON.parse(text)), store: true };
    } catch (e) {
      lastErr = e;
    }
  }
  return { ...clean(null), store: true, error: String((lastErr && lastErr.message) || lastErr) };
}

export async function writeState(on, message) {
  const body = JSON.stringify({
    on: Boolean(on),
    message: on ? "" : String(message || DEFAULT_OFF_MESSAGE).slice(0, 300),
    at: new Date().toISOString(),
  });
  let lastErr = null;
  for (const access of ACCESS) {
    try {
      await store.put(PATH, body, {
        access, addRandomSuffix: false, allowOverwrite: true,
        contentType: "application/json", cacheControlMaxAge: 60,
      });
      return clean(JSON.parse(body));
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("저장하지 못했습니다");
}
