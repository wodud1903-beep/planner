"""파일을 클립보드·끌기에 싣는 모양 — 카카오톡으로 보내는 길.

고객정보 탭과 자료검색 첨부가 같이 쓴다. 한 곳에 두어야 한쪽만 고쳐져
'여기선 카톡으로 붙는데 저기선 안 붙는' 일이 없다.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage


def file_mime(paths: list) -> QMimeData:
    """파일을 클립보드·드래그에 실을 형태로 담는다.

    - 파일 목록(urls)  : 카카오톡·탐색기가 '파일'로 받는다. 이게 본체다.
    - 글자(경로)        : 경로를 글자로 받는 곳이 있다.
    - 그림(그림 파일일 때): 파일을 못 받고 그림만 받는 곳(한글·워드 등)을 위해.
    """
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(p) for p in paths])
    md.setText("\n".join(paths))
    if len(paths) == 1:
        img = QImage(paths[0])
        if not img.isNull():
            md.setImageData(img)
    return md
