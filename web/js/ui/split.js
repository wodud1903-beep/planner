// 목록과 내용 사이의 경계선을 끌어서 넓힌다. 세 탭(서류·고객·자료)이 같이 쓴다.
//
// 정한 너비는 탭마다 따로 기억한다 — 자료검색은 제목이 짧아 좁아도 되고,
// 고객관리는 '주식회사 …' 같은 긴 이름이라 넓어야 편하다.
//
// ⚠️ 마우스 이벤트가 아니라 포인터 이벤트를 쓴다. 폴드는 손가락으로 끈다.
//    setPointerCapture 를 걸어야 빨리 끌었을 때 포인터가 경계선을 앞질러도
//    계속 따라온다.
import * as store from "../store.js";

const MIN = 220;          // 목록이 이보다 좁으면 이름이 잘려 쓸모가 없다
const MIN_RIGHT = 260;    // 내용 쪽도 최소한은 남겨 둔다
const DEF = 340;

export async function widthOf(key) {
  const w = await store.get("meta", "split:" + key);
  return Number(w) > 0 ? Number(w) : DEF;
}

/** .split 안에 경계선을 끼우고 끌 수 있게 만든다.
 *  splitEl 은 `<div class="split"><div class="left">…</div><div class="right">…</div></div>` */
export async function attach(splitEl, key) {
  if (!splitEl) return;
  const left = splitEl.querySelector(":scope > .left");
  const right = splitEl.querySelector(":scope > .right");
  if (!left || !right) return;
  if (splitEl.querySelector(":scope > .gutter")) return;   // 두 번 붙이지 않는다

  const g = document.createElement("div");
  g.className = "gutter";
  g.setAttribute("role", "separator");
  g.setAttribute("aria-orientation", "vertical");
  g.setAttribute("aria-label", "목록 너비 조절");
  g.tabIndex = 0;
  splitEl.insertBefore(g, right);

  let w = await widthOf(key);
  const apply = (px) => {
    const max = Math.max(MIN, splitEl.clientWidth - MIN_RIGHT);
    w = Math.round(Math.min(max, Math.max(MIN, px)));
    left.style.width = w + "px";
    g.setAttribute("aria-valuenow", String(w));
  };
  apply(w);

  // 접었다 펴면 전체 너비가 확 바뀐다. 그때 목록이 화면 밖으로 나가지 않게 다시 잰다.
  // ⚠️ window.resize 가 아니라 ResizeObserver 다 — 접고 펴도 resize 가 안 올 수 있다.
  new ResizeObserver(() => apply(w)).observe(splitEl);

  let startX = 0, startW = 0;
  const move = (e) => apply(startW + (e.clientX - startX));
  const up = (e) => {
    g.classList.remove("dragging");
    g.releasePointerCapture(e.pointerId);
    g.removeEventListener("pointermove", move);
    g.removeEventListener("pointerup", up);
    g.removeEventListener("pointercancel", up);
    store.put("meta", "split:" + key, w);
  };
  g.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    startX = e.clientX;
    startW = left.getBoundingClientRect().width;
    g.classList.add("dragging");
    g.setPointerCapture(e.pointerId);
    g.addEventListener("pointermove", move);
    g.addEventListener("pointerup", up);
    g.addEventListener("pointercancel", up);
  });
  // 손가락이 안 닿는 상황(블루투스 키보드 등)에서도 조절할 수 있게
  g.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 48 : 16;
    if (e.key === "ArrowLeft") { apply(w - step); store.put("meta", "split:" + key, w); }
    else if (e.key === "ArrowRight") { apply(w + step); store.put("meta", "split:" + key, w); }
    else return;
    e.preventDefault();
  });
  // 두 번 누르면 기본 너비로 되돌린다
  g.addEventListener("dblclick", () => { apply(DEF); store.put("meta", "split:" + key, w); });
}

export const _test = { MIN, MIN_RIGHT, DEF };
