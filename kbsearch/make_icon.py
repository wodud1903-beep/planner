"""kbsearch.ico 를 만든다 — icon.draw 그림을 여러 크기로 담는다.

    python make_icon.py          (kbsearch/ 에서)

윈도 ICO 는 크기별 그림을 한 파일에 담는다. 각 크기를 PNG 로 넣는다(윈도 Vista 이상).
그림을 바꿨을 때만 다시 돌리면 된다 — 만든 파일은 저장소에 들어 있다.
"""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kbsearch.icon import ICO_NAME, draw  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def png(size: int) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    draw(size).save(buf, "PNG")
    buf.close()
    return bytes(ba)


def main() -> int:
    _app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 — 그리는 동안 살아 있어야 한다
    images = [(s, png(s)) for s in SIZES]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for s, data in images:
        dim = 0 if s >= 256 else s          # 256 은 0 으로 적는다(ICO 규칙)
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    (HERE / ICO_NAME).write_bytes(head + entries + blobs)
    print(f"{ICO_NAME} 만듦 ({len(images)}가지 크기)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
