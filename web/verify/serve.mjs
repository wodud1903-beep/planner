// web/ 을 **/planner/ 하위에** 붙여 띄운다 — GitHub Pages 와 같은 조건을 만든다.
// 절대경로를 쓴 곳이 있으면 여기서 404 로 드러난다(Pages PWA 최대 실패 원인).
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { join, extname, resolve } from "node:path";
import { existsSync } from "node:fs";

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".png": "image/png", ".md": "text/markdown; charset=utf-8",
};

export function serve(root, { port = 8123, base = "/planner/", build = "dev" } = {}) {
  root = resolve(root);
  const hits = [];
  const srv = createServer(async (req, res) => {
    let p = decodeURIComponent(req.url.split("?")[0]);
    hits.push(p);
    if (!p.startsWith(base)) { res.writeHead(404).end("밖"); return; }
    let rel = p.slice(base.length) || "index.html";
    if (rel.endsWith("/")) rel += "index.html";
    // CHANGELOG.md 는 저장소 뿌리에 원본 하나만 둔다(배포 때 CI 가 복사한다).
    // web/ 에 같이 두면 두 벌이 되어 조용히 어긋난다.
    const file = rel === "CHANGELOG.md" && !existsSync(join(root, rel))
      ? join(root, "..", "CHANGELOG.md")
      : join(root, rel);
    try {
      const st = await stat(file);
      if (st.isDirectory()) { res.writeHead(404).end("dir"); return; }
      let buf = await readFile(file);
      if (rel === "sw.js" || rel === "version.json") {
        buf = Buffer.from(String(buf).replaceAll("__BUILD_ID__", build)
                                     .replaceAll("__APP_VERSION__", "test"));
      }
      res.writeHead(200, {
        "Content-Type": TYPES[extname(rel)] || "application/octet-stream",
        "Cache-Control": "no-store",
      });
      res.end(buf);
    } catch (e) { res.writeHead(404).end("없음: " + rel); }
  });
  return new Promise((ok) => srv.listen(port, () => ok({
    srv, port, base, hits,
    url: `http://localhost:${port}${base}`,
    close: () => new Promise((r) => srv.close(r)),
  })));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const s = await serve(new URL("..", import.meta.url).pathname);
  console.log("띄움:", s.url);
}
