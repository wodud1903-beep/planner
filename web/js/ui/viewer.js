// 서류 보기 — 그림과 PDF.
//
// PDF 는 <iframe> 에 맡기지 않는다. 안드로이드에서는 브라우저마다 내장 뷰어가
// 있기도 없기도 해서 빈 칸이 나오는 일이 잦았다. 대신 pdf.js 로 **한 장씩
// 그림으로 그려 아래로 이어 붙인다** — 그림과 똑같이 다루면 되니 조작도 하나다.
//
// ⚠️ pdf.js 는 미리 받아 두지 않는다(1MB 가 넘는다). PDF 를 처음 열 때만
//    내려받는다. 그림만 보는 날은 한 바이트도 쓰지 않는다.
import { html, raw, esc, render, $, $$ } from "./dom.js";

const PDFJS_VER = "4.10.38";
const PDFJS = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VER}/pdf.min.mjs`;
const PDFJS_WORKER =
  `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VER}/pdf.worker.min.mjs`;

// 화면 배율. 한 번 누를 때마다 한 칸씩 움직인다.
const STEPS = [1, 1.5, 2, 3, 4];
const MAX_PAGES = 60;          // 이보다 긴 PDF 는 앞에서부터 이만큼만 그린다

let _pdfjs = null;
async function pdfjs() {
  if (_pdfjs) return _pdfjs;
  const m = await import(/* @vite-ignore */ PDFJS);
  m.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
  _pdfjs = m;
  return m;
}

/** 한 파일을 그려 넣는다. 되돌리는 함수를 돌려준다(blob 주소 정리용).
 *
 *  nav = { pos, count, go(j) } 를 주면 같은 자료의 다른 첨부로 **닫지 않고** 넘긴다
 *  (자료검색 첨부 — PC 일정관리기 v1.25.1 · 업무자료검색과 같게):
 *    · ◀ ▶ 단추, 키보드 ← → (글 칸에 치는 중이면 건드리지 않는다), Esc 는 닫기
 *    · 폰은 옆으로 밀어서 — 확대해 둔 동안은 그림을 옮기는 손짓이라 넘기지 않는다
 *  blob 이 없으면 pending 일 때 '받는 중', 아니면 '받지 못함' 을 띄운다.
 */
export function mount(box, { blob, name, isPdf, driveUrl, nav, pending }) {
  const urls = [];
  const make = (b) => { const u = URL.createObjectURL(b); urls.push(u); return u; };
  let scale = 1;
  const many = !!(nav && nav.count > 1);

  render(box, html`
    <div class="vhead">
      <div class="vtitle"><b>${name}</b><button class="chip" id="vclose">닫기</button></div>
      ${raw(many ? html`<span class="vnav">
        <button class="chip" id="vprev" title="앞 첨부 (←)" aria-label="앞 첨부"
          ${raw(nav.pos > 0 ? "" : "disabled")}>◀</button>
        <span class="vpos" id="vpos">${nav.pos + 1} / ${nav.count}</span>
        <button class="chip" id="vnext" title="다음 첨부 (→)" aria-label="다음 첨부"
          ${raw(nav.pos < nav.count - 1 ? "" : "disabled")}>▶</button></span>` : "")}
      <button class="chip" id="vout" title="축소">−</button>
      <span class="vpct" id="vpct">100%</span>
      <button class="chip" id="vin" title="확대">＋</button>
      <a class="chip" href="${driveUrl}" target="_blank" rel="noopener">드라이브</a>
    </div>
    <div class="vscroll" id="vscroll"><div class="vpages" id="vpages"></div></div>`);

  const scroll = $("#vscroll", box);
  const pages = $("#vpages", box);
  const pct = $("#vpct", box);

  // ---- 옆 첨부로 넘기기 ----
  const go = (d) => {
    const j = nav.pos + d;
    if (j >= 0 && j < nav.count) nav.go(j);
  };
  let onKey = null;
  if (many) {
    $("#vprev", box).onclick = () => go(-1);
    $("#vnext", box).onclick = () => go(1);
    onKey = (e) => {
      if (!box.isConnected) { document.removeEventListener("keydown", onKey); return; }
      if (e.altKey || e.ctrlKey || e.metaKey || e.defaultPrevented) return;
      const t = e.target;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ""))) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        go(e.key === "ArrowLeft" ? -1 : 1);
      } else if (e.key === "Escape") {
        const c = $("#vclose", box);
        if (c) c.click();
      }
    };
    document.addEventListener("keydown", onKey);
    let sx = null, sy = 0;
    scroll.addEventListener("touchstart", (e) => {
      sx = e.touches.length === 1 && scale === 1 ? e.touches[0].clientX : null;
      sy = e.touches.length === 1 ? e.touches[0].clientY : 0;
    }, { passive: true });
    scroll.addEventListener("touchend", (e) => {
      if (sx === null || scale !== 1 || !e.changedTouches.length) { sx = null; return; }
      const t = e.changedTouches[0];
      const dx = t.clientX - sx, dy = t.clientY - sy;
      sx = null;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) go(dx < 0 ? 1 : -1);
    }, { passive: true });
  }

  const applyScale = (next, anchor) => {
    const prev = scale;
    scale = Math.min(STEPS[STEPS.length - 1], Math.max(STEPS[0], next));
    pct.textContent = Math.round(scale * 100) + "%";
    pages.style.width = (scale * 100) + "%";
    // 보고 있던 자리를 지킨다 — 확대했더니 엉뚱한 데로 튀면 못 쓴다
    if (anchor && prev !== scale) {
      const r = scroll.getBoundingClientRect();
      const cx = anchor.x - r.left + scroll.scrollLeft;
      const cy = anchor.y - r.top + scroll.scrollTop;
      const k = scale / prev;
      scroll.scrollLeft = cx * k - (anchor.x - r.left);
      scroll.scrollTop = cy * k - (anchor.y - r.top);
    }
  };
  const step = (dir, anchor) => {
    const i = STEPS.findIndex((v) => v > scale + 0.001);
    const j = [...STEPS].reverse().find((v) => v < scale - 0.001);
    applyScale(dir > 0 ? (i >= 0 ? STEPS[i] : scale) : (j !== undefined ? j : scale), anchor);
  };

  $("#vin", box).onclick = () => step(1);
  $("#vout", box).onclick = () => step(-1);

  // ⚠️ 눌러서 확대하지 않는다. 서류를 읽으려고 짚거나 스크롤하려고 손을 대면
  //    그때마다 확대돼서 오히려 방해가 됐다. 확대는 ＋ − 단추와
  //    두 손가락(핀치)으로만 한다 — 하려고 할 때만 된다.

  // ⚠️ 그냥 굴리면 **위아래로 넘어간다**. 확대는 Ctrl(또는 두 손가락)일 때만.
  //    예전엔 그림 위에서 굴려도 아무 일도 안 났는데, touch-action 이 한 손가락
  //    움직임을 막고 있었기 때문이다. 이제 막지 않는다.
  scroll.addEventListener("wheel", (e) => {
    if (!e.ctrlKey) return;                 // 평범한 스크롤은 건드리지 않는다
    e.preventDefault();
    step(e.deltaY < 0 ? 1 : -1, { x: e.clientX, y: e.clientY });
  }, { passive: false });

  if (!blob) {
    // 옆 첨부로 넘겼는데 아직 안 받았다(받는 중) / 받지 못했다
    render(pages, pending
      ? html`<p class="empty" id="vmsg">첨부를 받는 중입니다…</p>`
      : html`<p class="empty">이 첨부를 받지 못했습니다.</p>
        <p style="text-align:center"><a class="bigcopy" href="${driveUrl}"
           target="_blank" rel="noopener">드라이브에서 열기</a></p>`);
  } else if (!isPdf) {
    render(pages, html`<img class="vimg" src="${make(blob)}" alt="${name}">`);
  } else {
    render(pages, html`<p class="empty" id="vmsg">PDF 를 여는 중입니다…</p>`);
    drawPdf(blob, pages, make).catch((e) => {
      render(pages, html`<p class="empty">PDF 를 그리지 못했습니다.<br>${e.message || ""}</p>
        <p style="text-align:center"><a class="bigcopy" href="${driveUrl}"
           target="_blank" rel="noopener">드라이브 앱에서 열기</a></p>`);
    });
  }

  return {
    close() {
      if (onKey) document.removeEventListener("keydown", onKey);
      for (const u of urls) URL.revokeObjectURL(u);
    },
    onClose(fn) { $("#vclose", box).onclick = fn; },
  };
}

async function drawPdf(blob, pages, make) {
  const pdf = await pdfjs();
  const data = new Uint8Array(await blob.arrayBuffer());
  const doc = await pdf.getDocument({ data }).promise;
  const n = Math.min(doc.numPages, MAX_PAGES);
  const msg = $("#vmsg", pages);
  if (msg) msg.textContent = `${doc.numPages}장 — 그리는 중…`;

  for (let i = 1; i <= n; i++) {
    const page = await doc.getPage(i);
    // 폰 화면 폭에 맞춰 그린다. 너무 크게 그리면 메모리가 터지고,
    // 너무 작게 그리면 확대했을 때 글씨가 뭉갠다. 2배까지만 올린다.
    const base = page.getViewport({ scale: 1 });
    const want = Math.min(1600, Math.max(900, pages.clientWidth || 900));
    const vp = page.getViewport({ scale: Math.min(2.5, want / base.width) });
    const cv = document.createElement("canvas");
    cv.width = Math.round(vp.width);
    cv.height = Math.round(vp.height);
    await page.render({ canvasContext: cv.getContext("2d"), viewport: vp }).promise;
    const b = await new Promise((res) => cv.toBlob(res, "image/jpeg", 0.85));
    // 캔버스를 그대로 두면 장마다 화면 크기 비트맵이 메모리에 남는다 → 그림으로 바꾼다
    cv.width = cv.height = 0;
    const img = document.createElement("img");
    img.className = "vimg vpage";
    img.src = make(b);
    img.alt = `${i}쪽`;
    if (i === 1 && msg) msg.remove();
    pages.appendChild(img);
    page.cleanup();
  }
  if (doc.numPages > n) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = `앞 ${n}장만 보여 드립니다. 나머지는 드라이브 앱에서 봐 주세요.`;
    pages.appendChild(p);
  }
}
