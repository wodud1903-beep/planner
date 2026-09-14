// 아주 단순한 해시 라우터. #/kb #/kb/3 #/about 처럼 쓴다.
const routes = [];
let _cur = null;

export function on(pattern, fn) { routes.push([pattern, fn]); }
export function current() { return _cur; }
export function go(path) {
  if (location.hash.slice(1) === path) { handle(); return; }
  location.hash = path;
}

export function handle() {
  const path = location.hash.slice(1) || "/kb";
  for (const [pat, fn] of routes) {
    const m = path.match(pat);
    if (m) { _cur = { path, m }; fn(m, path); return; }
  }
  go("/kb");
}

export function start() {
  addEventListener("hashchange", handle);
  handle();
}
