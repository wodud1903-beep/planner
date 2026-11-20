"""PyInstaller 엔트리 스크립트 (단일 exe 빌드용)."""

import sys

from kbsearch.app import main

if __name__ == "__main__":
    sys.exit(main())
