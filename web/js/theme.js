// 테마 — 정보 탭에서 고른다. 이 기기에만 저장한다(폰마다 달라도 된다).
//
//   "" (자동)  폰 설정(밝게/어둡게)을 따른다 — <html> 에 data-theme 를 두지 않는다
//   light      기본
//   warm       따뜻한
//   dark       다크
//
// ⚠️ 화면이 뜨기 전에 index.html 의 작은 스크립트가 같은 키로 먼저 넣는다.
//    키 이름을 바꾸면 거기도 같이 바꾼다.
export const KEY = "planner.theme";

export const THEMES = [
  ["", "자동(폰 설정)"],
  ["light", "기본"],
  ["warm", "따뜻한"],
  ["dark", "다크"],
];

export function current() {
  try { return localStorage.getItem(KEY) || ""; } catch (e) { return ""; }
}

export function apply(name) {
  name = THEMES.some(([k]) => k === name) ? name : "";
  try {
    if (name) localStorage.setItem(KEY, name); else localStorage.removeItem(KEY);
  } catch (e) { /* 저장을 막은 브라우저 — 이번 화면에만 적용 */ }
  const root = document.documentElement;
  if (name) root.dataset.theme = name; else delete root.dataset.theme;
  paintBar();
}

// 브라우저 위 막대 색을 지금 화면 바탕과 맞춘다.
export function paintBar() {
  const m = document.querySelector('meta[name="theme-color"]');
  if (!m) return;
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--card").trim();
  if (bg) m.setAttribute("content", bg);
}
