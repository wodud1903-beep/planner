"""구글 드라이브의 '내 드라이브 / 고객정보' 를 스스로 찾는가.

가짜 폴더를 만들어 놓고 찾게 한다 — 진짜 드라이브 문자를 두드리지 않는다.
화면도 통신도 필요 없다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import os
import tempfile

os.environ.setdefault("APPDATA", tempfile.mkdtemp())

from planner import customer_files, drive_path  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


TMP = _pl.Path(tempfile.mkdtemp())


def mk(*parts) -> str:
    p = TMP.joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def bases(*names):
    """_bases 를 가짜로 갈아 끼운다. 검사 내내 진짜 드라이브를 안 본다."""
    drive_path._bases = lambda: [str(TMP / n) for n in names]
    drive_path.invalidate()


class S:
    """설정 흉내."""
    drive_api_on = True
    files_drive_folder = ""

    def __init__(self, files_dir=""):
        self.files_dir = files_dir


# G: 흉내 — TMP/G/내 드라이브/고객정보
mk("G", "내 드라이브", "고객정보")
mk("G", "내 드라이브", "받은팩스")
# H: 흉내 — 영문 윈도
mk("H", "My Drive", "고객정보")
# J: 흉내 — 드라이브는 있는데 폴더 이름이 다르다 (사장님이 말한 그 경우)
mk("J", "내 드라이브", "고객서류")
# K: 흉내 — 드라이브가 아예 없다 (빈 폴더)
mk("K")

print("\n[A] 기본 — G:\\내 드라이브\\고객정보")
bases("G")
ok("찾는다", drive_path.find() == str(TMP / "G" / "내 드라이브" / "고객정보"),
   drive_path.find())
ok("이유 없이 깨끗하게 찾는다", drive_path.detect()[1] == "", drive_path.detect()[1])
ok("내 드라이브 자리도 알려 준다",
   drive_path.my_drive_roots() == [str(TMP / "G" / "내 드라이브")],
   drive_path.my_drive_roots())

print("\n[B] 드라이브 문자가 G: 가 아니어도 (영문 윈도 포함)")
bases("K", "H")
ok("My Drive 도 내 드라이브로 본다",
   drive_path.find() == str(TMP / "H" / "My Drive" / "고객정보"), drive_path.find())

print("\n[C] 앞에 있는 것이 이긴다 (G: 가 먼저)")
bases("G", "H")
ok("G: 를 먼저 쓴다", drive_path.find().startswith(str(TMP / "G")), drive_path.find())

print("\n[D] 폴더 이름이 다르면 — 바꿔 달라고 말한다")
bases("J")
p, why = drive_path.detect()
ok("경로를 못 준다", p == "", p)
# ⚠️ 이 문구는 사장님이 정한 그대로여야 한다. 말이 달라지면 무엇을 하라는
#    건지 한 번 더 생각해야 한다.
ok("'내 드라이브 → 고객정보 폴더로 폴더명을 변경해주세요.' 가 들어 있다",
   "내 드라이브 → 고객정보 폴더로 폴더명을 변경해주세요." in why, why)
ok("드라이브는 찾았다고 알려 준다", "구글 드라이브는 찾았지만" in why, why)
ok("어디를 봤는지 적어 준다", str(TMP / "J" / "내 드라이브") in why, why)

print("\n[E] 드라이브가 아예 없으면")
bases("K")
_real_exe = drive_path._exe_paths
drive_path._exe_paths = lambda: []          # 안 깔린 PC 흉내
p, why = drive_path.detect()
ok("경로를 못 준다", p == "")
# ⚠️ 안 깔린 사람에게 '켜 주세요' 라고 하면 안 된다. 할 말이 다르다.
ok("안 깔렸다고 말한다", "깔려 있지 않습니다" in why, why)
ok("받을 곳을 알려 준다", drive_path.INSTALL_HINT in why, why)
ok("같은 안내문이 붙는다", drive_path.FIX_HINT in why, why)

print("\n[E2] 깔려는 있는데 꺼 뒀으면")
drive_path._exe_paths = lambda: [str(TMP / "설치된척")]
mk("설치된척")
drive_path.invalidate()
p, why = drive_path.detect()
ok("켜 달라고 말한다", "실행되고 있지 않습니다" in why, why)
ok("받으라고 하지 않는다", drive_path.INSTALL_HINT not in why, why)
drive_path._exe_paths = _real_exe

print("\n[F] 손으로 지정한 폴더가 언제나 먼저다")
bases("G")
mine = mk("어딘가", "내서류")
path, auto, why = drive_path.resolve(S(mine))
ok("지정한 그 폴더를 쓴다", path == mine, path)
ok("자동으로 찾은 것이 아니라고 표시한다", auto is False)
# ⚠️ 여기가 핵심이다. 사람이 정한 것을 자동 찾기가 덮으면 안 된다.
ok("드라이브에 고객정보가 있어도 덮지 않는다",
   path != str(TMP / "G" / "내 드라이브" / "고객정보"))

print("\n[G] 다른 PC 에서 지정한 경로가 넘어왔을 때")
# 설정 파일은 PC 끼리 따라다닌다. H: 인 PC 가 적어 둔 경로는 이 PC 엔 없다.
path, auto, why = drive_path.resolve(S(r"H:\내 드라이브\고객정보"))
ok("이 PC 에서 찾은 것으로 대신한다",
   path == str(TMP / "G" / "내 드라이브" / "고객정보"), path)
ok("자동으로 찾았다고 표시한다", auto is True)

print("\n[H] 지정한 경로도 없고 드라이브도 없으면")
bases("K")
path, auto, why = drive_path.resolve(S(r"H:\내 드라이브\고객정보"))
ok("경로가 없다", path == "" and auto is False)
ok("지정해 둔 곳이 없다고 먼저 말한다", "이 PC 에는 없습니다" in why, why)
ok("그 뒤에 무엇을 하라는지 적는다", drive_path.FIX_HINT in why)

print("\n[I] 폴더째 마운트한 경우 (내 드라이브가 곧 그 폴더)")
mk("M", "고객정보")
bases("M")
ok("그것도 찾는다", drive_path.find() == str(TMP / "M" / "고객정보"), drive_path.find())
# 아무 폴더나 집어 오면 안 된다 — 고객정보가 없으면 인정하지 않는다
mk("N", "아무거나")
bases("N")
ok("고객정보가 없는 폴더는 내 드라이브로 치지 않는다",
   drive_path.my_drive_roots() == [] and drive_path.find() == "",
   drive_path.my_drive_roots())

print("\n[J] 자료 탭이 이걸 실제로 쓴다")
bases("G")


class FakeAuth:
    def is_connected(self):
        return False

    def has_scope(self, s):
        return False


src, why = customer_files.pick_source(S(""), FakeAuth())
ok("폴더를 지정하지 않아도 창고가 잡힌다", src is not None, why)
ok("그 창고가 드라이브의 고객정보다",
   src and src.root == str(TMP / "G" / "내 드라이브" / "고객정보"),
   src and src.root)
ok("자동으로 찾았다고 표시가 남는다", src and getattr(src, "auto", False))

bases("J")            # 폴더 이름이 다른 PC
src, why = customer_files.pick_source(S(""), FakeAuth())
ok("못 찾으면 창고가 없다", src is None)
# 예전엔 '폴더가 지정되지 않았습니다' 만 나왔다 — 무엇을 하라는 말이 없었다
ok("탭에도 같은 안내문이 간다", drive_path.FIX_HINT in why, why)

print("\n[K] 여러 번 불러도 같은 답 (그리고 버릴 수 있다)")
bases("G")
first = drive_path.find()
ok("두 번 불러도 같다", drive_path.find() == first)
bases("K")            # _bases 를 갈면서 invalidate 도 된다
ok("버리면 다시 찾는다", drive_path.find() == "", drive_path.find())

print("\n[J2] 드라이브가 없거나 꺼져 있어도 같은 폴더가 보인다")
# 드라이브 데스크톱이 안 깔렸거나 꺼져 있으면 PC 에 폴더가 없다.
# 그때는 인터넷으로 같은 폴더를 읽어 화면이 똑같이 나와야 한다.
bases("K")                     # 마운트가 없다 = 꺼져 있거나 안 깔렸다


class AuthOK:
    def is_connected(self):
        return True

    def has_scope(self, s):
        return True


src, why = customer_files.pick_source(S(""), AuthOK())
ok("인터넷으로 읽는 창고가 잡힌다", src is not None and src.kind == "drive", why)
ok("읽을 폴더는 고객정보", src and src.folder == drive_path.CUSTOMER_DIR,
   src and src.folder)


class SOff(S):
    drive_api_on = False


src, why = customer_files.pick_source(SOff(""), AuthOK())
ok("설정에서 끄면 안 쓴다", src is None)
ok("켜는 법을 알려 준다", "인터넷으로 같은 폴더를 읽기" in why, why)
# 드라이브가 켜져 있으면 굳이 인터넷으로 읽지 않는다 (그쪽이 빠르다)
bases("G")
src, why = customer_files.pick_source(S(""), AuthOK())
ok("드라이브가 켜져 있으면 PC 폴더를 먼저 쓴다",
   src is not None and src.kind == "local", src and src.kind)

print("\n[J3] 깔려 있나 / 돌고 있나")
bases("G")
ok("마운트가 보이면 돌고 있다", drive_path.running() is True)
ok("돌고 있으면 깔려 있는 것이다", drive_path.installed() is True)
bases("K")
ok("마운트가 없으면 안 돌고 있다", drive_path.running() is False)
st = drive_path.status()
ok("한 번에 형편을 알려 준다", set(st) == {"path", "installed", "running", "why"}, st)
ok("못 찾은 이유도 같이 온다", drive_path.FIX_HINT in st["why"])
# 안내문·주소는 사장님이 정한 그대로여야 한다
ok("설치 안내문이 그대로다",
   drive_path.INSTALL_HINT == "구글드라이브 설치 시 속도가 빠릅니다.",
   drive_path.INSTALL_HINT)
ok("설치 주소가 그대로다",
   drive_path.INSTALL_URL
   == "https://dl.google.com/drive-file-stream/GoogleDriveSetup.exe",
   drive_path.INSTALL_URL)

print("\n[L] 알려 주는 자리에 실제로 걸려 있나 (소스에서 확인)")
# ⚠️ 찾는 것만 맞고 **알리는 자리에 안 걸려 있으면** 아무 소용이 없다.
#    셋 다 걸어 뒀는지 여기서 본다. (창을 띄우는 검사는 verify_view 쪽 몫이다)
_pkg = _ROOT / "python" / "planner"
mw = (_pkg / "main_window.py").read_text(encoding="utf-8")
ok("시작 브리핑이 읽을 곳이 있는지 확인한다",
   "customer_files.pick_source(self.settings, self.gauth)[0] is None" in mw)
ok("드라이브가 없으면 설치 안내를 붙인다",
   "drive_path.installed()" in mw and "drive_path.INSTALL_HINT" in mw)
ok("팩스 배선이 사라졌다", "fax" not in mw.lower(),
   [l.strip()[:60] for l in mw.split("\n") if "fax" in l.lower()][:3])
ok("브리핑에 경고 절이 있다", "고객정보 폴더를 찾지 못했습니다" in mw)
ok("브리핑이 같은 안내문을 쓴다", "drive_path.FIX_HINT" in mw)
sd = (_pkg / "settings_dialog.py").read_text(encoding="utf-8")
ok("설정 창이 지금 상태를 적는다", "_refresh_files_auto" in sd)
ok("설정 창도 자동 찾기를 쓴다", "drive_path.detect()" in sd)
ok("설정 창에 설치 안내가 있다", "drive_path.INSTALL_URL" in sd
   and "drive_path.INSTALL_HINT" in sd)
ok("눌러서 바로 받게 해 뒀다", "setOpenExternalLinks(True)" in sd)
ok("받은팩스 설정은 사라졌다", "fax" not in sd.lower() and "팩스" not in sd)
cft = (_pkg / "customer_files_tab.py").read_text(encoding="utf-8")
ok("탭이 '자동으로 찾음' 이라고 밝힌다", "자동으로 찾음" in cft)
cf = (_pkg / "customer_files.py").read_text(encoding="utf-8")
ok("창고를 고를 때 자동 찾기를 쓴다", "drive_path.resolve(settings)" in cf)
# 설정 파일에 적어 두면 PC 끼리 엇갈린다 — 그러지 않았는지 본다
ok("찾은 경로를 설정에 저장하지 않는다",
   "files_dir =" not in cf and "settings.files_dir =" not in cf)

print("\n[M] 윈도 아닌 곳에서도 탈 없이 돈다")
ok("레지스트리를 못 읽어도 빈 목록", isinstance(drive_path._registry_mounts(), list))
ok("없는 경로를 물어도 안 죽는다", drive_path._isdir("") is False)

print("\n" + (f"{len(FAIL)}건 실패" if FAIL else "전부 통과"))
raise SystemExit(1 if FAIL else 0)
