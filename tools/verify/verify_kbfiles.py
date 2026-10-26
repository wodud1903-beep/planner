"""자료검색 첨부(그림·PDF) — 저장 모양, 시트 G열, 드라이브 올리기·받기, 카톡으로 복사.

구글 드라이브·시트를 가짜로 끼워 실제 요청 모양 그대로 시험한다(네트워크 없음).
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import json
import os
import tempfile
import time
import urllib.parse

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from planner import config, kb, kb_files, sheets  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])


def pump(n=20):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


def png_bytes(color="#2563EB", w=40, h=30):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(color))
    ba = QByteArray()
    b = QBuffer(ba)
    b.open(QIODevice.WriteOnly)
    img.save(b, "PNG")
    return bytes(ba)


class Resp:
    def __init__(self, code=200, body=None, content=b"", headers=None):
        self.status_code = code
        self._body = body
        self.content = content
        self.headers = headers or {}
        self.text = json.dumps(body, ensure_ascii=False) if body is not None else ""

    def json(self):
        return self._body if self._body is not None else {}


class Fake:
    """드라이브·시트 흉내. 부른 요청을 calls 에 모은다."""

    def __init__(self):
        self.calls = []
        self.files = {}            # id → bytes (드라이브에 있는 것)
        self.public = set()
        self.api_ok = True          # 내 로그인으로 받기가 되나
        self.kb_rows = []           # A:F
        self.kb_g = None            # G 열 (None 이면 400)
        self.cols = 26
        self.put_values = None
        self.perm_fail = False
        self._n = 0

    def get(self, url, headers=None, timeout=None, params=None):
        self.calls.append(("GET", url, params))
        if url.startswith(config.DRIVE_FILES_URL + "/") and (params or {}).get("alt") == "media":
            fid = url.rsplit("/", 1)[1]
            if self.api_ok and fid in self.files:
                return Resp(200, content=self.files[fid])
            return Resp(404, {"error": {"message": "File not found"}})
        if url.startswith("https://drive.google.com/uc"):
            fid = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["id"][0]
            if fid in self.public:
                return Resp(200, content=self.files[fid], headers={"Content-Type": "image/png"})
            return Resp(200, content=b"<html>login</html>",
                        headers={"Content-Type": "text/html; charset=utf-8"})
        if url == config.DRIVE_FILES_URL:        # 폴더 찾기
            return Resp(200, {"files": [{"id": "FOLDER", "name": "업무자료"}]})
        if "/values/" in url:
            rng = urllib.parse.unquote(url.split("/values/", 1)[1])
            if rng.endswith("!G1:G"):
                if self.kb_g is None:
                    return Resp(400, {"error": {"message": "exceeds grid limits"}})
                return Resp(200, {"values": [[v] if v else [] for v in self.kb_g]})
            return Resp(200, {"values": self.kb_rows})
        if "fields" in (params or {}):
            return Resp(200, {"sheets": [{"properties": {
                "sheetId": 5, "title": "업무자료",
                "gridProperties": {"columnCount": self.cols}}}]})
        return Resp(404, {})

    def post(self, url, headers=None, timeout=None, params=None, json=None, data=None):
        self.calls.append(("POST", url, json if json is not None else params))
        if url == config.DRIVE_UPLOAD_URL and (params or {}).get("uploadType") == "resumable":
            self._n += 1
            return Resp(200, {}, headers={"Location": f"https://upload/session/{self._n}"})
        if url.endswith("/permissions"):
            if self.perm_fail:
                return Resp(403, {"error": {"message": "no"}})
            self.public.add(url.split("/")[-2])
            return Resp(200, {})
        if url.endswith(":batchUpdate"):
            return Resp(200, {})
        if url.endswith(":clear"):
            return Resp(200, {})
        return Resp(200, {})

    def put(self, url, headers=None, timeout=None, params=None, json=None, data=None):
        self.calls.append(("PUT", url, None))
        if url.startswith("https://upload/session/"):
            fid = "F" + url.rsplit("/", 1)[1]
            self.files[fid] = data
            return Resp(200, {"id": fid})
        self.put_values = json
        return Resp(200, {})

    def patch(self, url, headers=None, timeout=None, json=None):
        self.calls.append(("PATCH", url, json))
        return Resp(200, {})


F = Fake()
kb_files._http = lambda: F
sheets._http = lambda: F


class Auth:
    def __init__(self, on=True):
        self.on = on

    def is_connected(self):
        return self.on

    def _headers(self):
        return {"Authorization": "Bearer t"}

    def valid_token(self):
        return "t"


A = Auth()

print("[1] 저장 모양 — 첨부를 지키고, 이름으로도 찾는다")
it = kb._clean({"title": "신한 전자약정", "files": [
    {"id": "a", "name": "위임장.pdf", "mime": "application/pdf", "size": "1200"},
    {"id": "", "name": "안올린것.png"},            # 아직 안 올린 것은 버린다
    {"name": "번호없음.png"}, "엉뚱한값"]})
ok("올린 첨부만 남는다", it["files"] == [
    {"id": "a", "name": "위임장.pdf", "mime": "application/pdf", "size": 1200}], it.get("files"))
ok("첨부 없는 자료는 예전 모양 그대로(files 없음)", "files" not in kb._clean({"title": "x"}))
ok("첨부 이름으로 찾는다", kb.search([it], "위임장") == [it])
ok("편집 창 안의 것(그림 바이트)은 저장 안 함",
   kb.clean_files([{"id": "b", "name": "a.png", "_data": b"x", "_err": "e"}])
   == [{"id": "b", "name": "a.png", "mime": "", "size": 0}])

print("\n[2] 공용 시트 G열 — 따로 읽고, 제목이 맞을 때만 붙인다")
F.kb_rows = [["카테고리", "금융사", "제목", "태그", "본문", "체크리스트(줄바꿈)"],
             ["전자약정", "", "신한 전자약정", "", "본문", ""],
             ["심사서류", "", "개인 심사서류", "", "", "신분증"]]
F.kb_g = None
got = sheets.read_kb(A, "SID")
ok("G 가 격자 밖(400)이어도 목록은 산다", got and len(got) == 2 and "files" not in got[0])
F.kb_g = ["첨부(앱 전용 · 지우지 마세요)",
          json.dumps({"title": "신한 전자약정",
                      "files": [{"id": "x1", "name": "링크.png", "mime": "image/png"}]}),
          json.dumps({"title": "다른 자료", "files": [{"id": "x2", "name": "남의것.png"}]})]
got = sheets.read_kb(A, "SID")
ok("제목이 맞는 줄에 첨부가 붙는다", got[0].get("files", [{}])[0].get("id") == "x1", got[0])
ok("제목이 다르면(줄이 밀림) 안 붙인다", "files" not in got[1])

F.cols = 6
F.calls.clear()
sheets.write_kb(A, "SID", [it, {"title": "개인 심사서류", "checklist": ["신분증"]}])
dims = [c for c in F.calls if c[0] == "POST" and c[1].endswith(":batchUpdate")
        and "appendDimension" in json.dumps(c[2])]
ok("열이 6개뿐이면 7개로 늘린다", dims and dims[0][2]["requests"][0]["appendDimension"]["length"] == 1)
clr = [c for c in F.calls if c[1].endswith(":clear")]
ok("G 까지 비우고 새로 쓴다", clr and "A1%3AG10000" in clr[0][1], clr[0][1] if clr else "")
vals = F.put_values["values"]
ok("머리글에 첨부 열", len(vals[0]) == 7 and "첨부" in vals[0][6])
g1 = json.loads(vals[1][6])
ok("G 에 제목+첨부를 적는다", g1["title"] == "신한 전자약정" and g1["files"][0]["id"] == "a")
ok("첨부 없는 자료는 G 가 빈칸", vals[2][6] == "")

print("\n[3] 올리기 — 공통은 링크 공개, 내 메모는 비공개")
data = png_bytes()
F.calls.clear()
att = kb_files.upload(A, data, "링크 화면.png", public=True)
ok("드라이브 번호를 받는다", att["id"].startswith("F") and att["mime"] == "image/png"
   and att["size"] == len(data))
start = [c for c in F.calls if c[0] == "POST" and c[1] == config.DRIVE_UPLOAD_URL]
ok("이어올리기(resumable) 로 업무자료 폴더에", start and start[0][2].get("uploadType") == "resumable")
ok("공통은 링크 공개", att["id"] in F.public)
ok("올린 파일은 캐시에도 둔다(다시 받지 않게)", kb_files.cached(att) is not None)
att2 = kb_files.upload(A, data, "내 메모 그림.png", public=False)
ok("내 메모는 공개하지 않는다", att2["id"] not in F.public)
for bad, why in (("문서.hwp", "종류"), ("빈.png", "빈 파일")):
    try:
        kb_files.upload(A, b"" if why == "빈 파일" else b"x", bad, public=False)
        ok(f"{why} 거절", False)
    except kb_files.KbFileError:
        ok(f"{why} 거절", True)
F.perm_fail = True
n_files = len(F.files)
try:
    kb_files.upload(A, data, "공개실패.png", public=True)
    ok("공개 설정이 실패하면 알린다", False)
except kb_files.KbFileError:
    trashed = [c for c in F.calls if c[0] == "PATCH" and c[2] == {"trashed": True}]
    ok("공개 설정이 실패하면 알리고 그 파일은 휴지통으로", trashed and len(F.files) == n_files + 1)
F.perm_fail = False

print("\n[4] 받기 — 내 로그인 → 안 되면 공개 주소, 안내 화면(HTML)은 실패")
F.files["P1"] = data
F.public.add("P1")
F.api_ok = False
p = kb_files.fetch(A, {"id": "P1", "name": "관리자가 올린 것.png"})
ok("API 가 안 되면 공개 주소로 받는다", p.read_bytes() == data and p.name == "관리자가 올린 것.png")
n = len(F.calls)
kb_files.fetch(A, {"id": "P1", "name": "관리자가 올린 것.png"})
ok("받아 둔 것은 다시 묻지 않는다", len(F.calls) == n)
F.files["H1"] = b"secret"
try:
    kb_files.fetch(A, {"id": "H1", "name": "비공개.png"})
    ok("공개가 아니면(HTML 안내 화면) 받았다고 하지 않는다", False)
except kb_files.KbFileError:
    ok("공개가 아니면(HTML 안내 화면) 받았다고 하지 않는다",
       kb_files.cached({"id": "H1", "name": "비공개.png"}) is None)
F.api_ok = True
p = kb_files.fetch(A, {"id": "H1", "name": "비공개.png"})
ok("내 파일은 내 로그인으로 받는다", p.read_bytes() == b"secret")
ok("캐시 이름은 원래 이름(카톡에 그 이름으로 간다)", p.name == "비공개.png")
ok("이상한 글자는 바꿔 둔다", kb_files.cache_path({"id": "a/b", "name": 'x:y?.png'}).name == "x_y_.png")

print("\n[5] 붙여넣기·끌어다 놓기 → 첨부")
md = QMimeData()
img = QImage(10, 10, QImage.Format_RGB32)
img.fill(QColor("red"))
md.setImageData(img)
got, bad = kb_files.from_mime(md)
ok("복사한 그림 → PNG 첨부", len(got) == 1 and got[0][0].endswith(".png")
   and got[0][1][:8] == b"\x89PNG\r\n\x1a\n", got[0][0] if got else "")
tmp = tempfile.mkdtemp()
pdf = os.path.join(tmp, "안내.pdf")
open(pdf, "wb").write(b"%PDF-1.4 test")
txt = os.path.join(tmp, "메모.txt")
open(txt, "w").write("x")
md2 = QMimeData()
md2.setUrls([QUrl.fromLocalFile(pdf), QUrl.fromLocalFile(txt), QUrl.fromLocalFile(tmp)])
got, bad = kb_files.from_mime(md2)
ok("PDF 는 받는다", [g[0] for g in got] == ["안내.pdf"])
ok("그 밖의 파일·폴더는 이유와 함께 거절", len(bad) == 2, bad)

print("\n[6] 본문 칸에서 Ctrl+V — 그림이면 첨부로, 글이면 글로")
from planner.kb_tab import KbEditDialog, KbTab, KbView, _BodyEdit  # noqa: E402

seen = []
be = _BodyEdit(lambda m: seen.append(m))
be.insertFromMimeData(md)
ok("그림만 있으면 첨부로", len(seen) == 1 and be.toPlainText() == "")
mt = QMimeData()
mt.setText("엑셀에서 복사한 글")
mt.setImageData(img)                       # 엑셀은 글과 함께 그 모양 그림도 싣는다
be.insertFromMimeData(mt)
ok("글이 같이 있으면 글이 먼저", be.toPlainText() == "엑셀에서 복사한 글" and len(seen) == 1)
be.insertFromMimeData(md2)
ok("탐색기에서 복사한 파일은 첨부로", len(seen) == 2)
ok("서식 있는 글은 안 받는다(보이지 않는 글자가 섞이지 않게)", not be.acceptRichText())

print("\n[7] 보기 화면 — Ctrl+C 로 카톡에, 아직 안 받은 것은 받는 대로")
shared = [{"category": "전자약정", "title": "신한 전자약정", "body": "본문",
           "files": [att, {"id": "P1", "name": "관리자가 올린 것.png", "mime": "image/png"},
                     {"id": "Z9", "name": "아직.png", "mime": "image/png"}]}]
kb.save_shared(shared)
F.files["Z9"] = png_bytes("#15803D")
F.public.add("Z9")
view = KbView()
view.set_auth(A)
view.show()
view.lst.setCurrentRow(0)
pump(40)
ok("첨부 칸에 셋", view.lst_att.count() == 3 and view.lst_att.isVisible())
ok("보자마자 받아 둔다", kb_files.cached({"id": "Z9", "name": "아직.png"}) is not None)
view.lst_att.clearSelection()
view.lst_att.item(0).setSelected(True)
view.copy_attachments()
cb = QGuiApplication.clipboard().mimeData()
urls = [u.toLocalFile() for u in cb.urls()]
ok("고른 첨부를 파일로 올린다", len(urls) == 1 and urls[0].endswith("링크 화면.png"), urls)
ok("그림 하나면 그림으로도(그림만 받는 곳)", cb.hasImage())
view.lst_att.clearSelection()
view.copy_attachments()
ok("안 고르면 전부", len(QGuiApplication.clipboard().mimeData().urls()) == 3)
ok("끌기에 실을 경로", len(view.attach_paths(view.lst_att.atts())) == 3)
# 아직 안 받은 첨부를 Ctrl+C → 받는 대로 복사
F.files["Q1"] = png_bytes("#A35F0D")
F.public.add("Q1")
late = {"id": "Q1", "name": "늦게.png", "mime": "image/png"}
view.copy_attachments([late])
for _ in range(100):
    pump(2)
    if any(u.toLocalFile().endswith("늦게.png") for u in QGuiApplication.clipboard().mimeData().urls()):
        break
ok("받기가 끝나면 그때 복사한다",
   any(u.toLocalFile().endswith("늦게.png") for u in QGuiApplication.clipboard().mimeData().urls()))
# 끝내 못 받는 첨부 → 멈추고 알린다(끝없이 다시 받지 않는다)
gone = {"id": "NOPE", "name": "없는것.png", "mime": "image/png"}
view.copy_attachments([gone])
pump(60)
n = len([c for c in F.calls if "NOPE" in c[1]])
pump(60)
ok("못 받으면 멈추고 알린다", "받지 못" in view.lbl_status.text()
   and len([c for c in F.calls if "NOPE" in c[1]]) == n, view.lbl_status.text())

print("\n[8] 편집 창 — 붙여 넣고, [저장] 때 올리고, 실패하면 닫지 않는다")
config.is_rates_admin = lambda e: True
kb.save_mine([{"title": "내 자료", "body": "", "files": [att2]}])
d = KbEditDialog("admin@x", None, auth=A)
d.show()
d.lst.setCurrentRow(0)                       # 회사 공통 '신한 전자약정'(첨부 셋)
pump()
n0 = d.lst_att.count()
d.drop_attachments(md)
ok("붙여 넣은 그림이 첨부 줄에(아직 안 올림)",
   d.lst_att.count() == n0 + 1 and not d.lst_att.atts()[-1]["id"], (n0, d.lst_att.count()))
d.drop_attachments(md)                       # 같은 것을 또 붙이면
ok("같은 것은 두 번 안 붙는다", d.lst_att.count() == n0 + 1)
d.lst_att.clearSelection()
d.lst_att.item(0).setSelected(True)
d.remove_attachments()
ok("[빼기]", d.lst_att.count() == n0 and d.lst_att.atts()[0]["name"] != att["name"])
calls = []
real_upload = kb_files.upload


def flaky(auth, data, name, public):
    calls.append((name, public))
    if len(calls) == 1:
        raise kb_files.KbFileError(f"'{name}' — 올리지 못했습니다 (HTTP 500).")
    return real_upload(auth, data, name, public)


kb_files.upload = flaky
from PySide6.QtWidgets import QMessageBox  # noqa: E402
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
d._ok()
ok("올리기가 실패하면 창을 닫지 않는다", d.result() == 0 and d.isVisible())
ok("공통 자료 첨부는 공개로 올린다", calls and calls[0][1] is True)
d._ok()
ok("다시 누르면 남은 것만 올리고 닫힌다", len(calls) == 2 and d.result() == 1)
saved = [x for x in d.shared if x["title"] == "신한 전자약정"][0]
ok("올라간 첨부는 번호가 붙어 저장된다", all(f.get("id") for f in saved["files"]))
kb_files.upload = real_upload

print("\n[9] 자료에서 뺀 첨부는 드라이브 휴지통으로")
tab = KbTab()
tab.set_account("admin@x")
tab.set_auth(A)
trashed = []
kb_files.trash = lambda auth, ids: trashed.extend(ids)
KbEditDialog.run = classmethod(lambda cls, account="", parent=None, auth=None: (
    [{"title": "신한 전자약정", "files": [att]}],           # P1·Z9 를 뺐다
    [{"title": "내 자료", "files": []}]))                   # att2 를 뺐다
tab._edit()
pump(20)
ok("뺀 것만 휴지통으로", sorted(trashed) == sorted(["P1", "Z9", att2["id"]]), trashed)
ok("남긴 첨부는 그대로", att["id"] not in trashed)

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
