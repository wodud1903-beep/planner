// 한글 초성 검색 — planner/hangul.py 를 그대로 옮긴 것.
//
// ⚠️ 파이썬 쪽과 결과가 한 글자라도 달라지면 안 된다. web/verify/vectors.json 에
//    파이썬이 낸 정답표가 들어 있고 verify_hangul.mjs 가 대조한다.
//
// ⚠️ CHOSUNG 은 '호환 자모'(U+3131…) 다. 계산으로 만들지 말고 이 글자열을 그대로 쓴다 —
//    한글 음절에서 뽑히는 초성과 키보드로 치는 자음이 같은 코드여야 검색이 걸린다.

const HANGUL_BASE = 0xAC00;
const HANGUL_LAST = 0xD7A3;

export const CHOSUNG = [
  "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
  "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
];

// 키보드에서 겹자음을 안 치고 홑자음만 치는 사람이 많다.
// "ㅅㄴㅌ" 로도 "쏘나타"(초성 ㅆㄴㅌ)가 걸리도록 홑↔겹을 같은 것으로 본다.
const LOOSE = { "ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ" };

export function chosung(text) {
  let out = "";
  for (const ch of text || "") {
    const code = ch.codePointAt(0);
    if (code >= HANGUL_BASE && code <= HANGUL_LAST) {
      out += CHOSUNG[Math.floor((code - HANGUL_BASE) / 588)];
    } else {
      out += ch.toLowerCase();
    }
  }
  return out;
}

function loose(s) {
  let out = "";
  for (const ch of s || "") out += (LOOSE[ch] || ch);
  return out;
}

// 공백을 없애고 소문자로 — '디 엣지' 와 '디엣지' 를 같게 본다.
function squash(s) {
  return (s || "").split(/\s+/).join("").toLowerCase();
}

function tokenHit(hay, hayCho, token) {
  const tok = squash(token);
  if (!tok) return true;
  if (hay.includes(tok)) return true;
  // 초성만 친 경우(ㄱㄴㄷ…) 또는 초성이 섞인 경우 — 초성 글자열에서 찾는다
  return hayCho.includes(loose(tok));
}

// 찾을 대상을 미리 다듬어 둔다 — [눌린글자, 초성].
// 검색창에 한 자 칠 때마다 이걸 다시 만들면 느리다(파이썬에서 2만 건에 147ms 였다).
export function prepare(item) {
  const hay = squash(item);
  return [hay, loose(squash(chosung(item)))];
}

export function matchesPrepared(prepared, query) {
  const q = (query || "").trim();
  if (!q) return true;
  const [hay, hayCho] = prepared;
  return q.split(/\s+/).every((t) => tokenHit(hay, hayCho, t));
}

export function matches(item, query) {
  const q = (query || "").trim();
  if (!q) return true;
  return matchesPrepared(prepare(item), q);
}

// 정렬용 점수 — 작을수록 먼저. 완전일치 → 앞에서 시작 → 포함 → 초성.
export function rank(item, query) {
  const q = squash(query);
  const hay = squash(item);
  if (!q) return 3;
  if (hay === q) return 0;
  if (hay.startsWith(q)) return 1;
  if (hay.includes(q)) return 2;
  return 4;
}
