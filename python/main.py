"""PyInstaller 엔트리 스크립트 (single-file exe 빌드용)."""

import sys

from planner.app import main

if __name__ == "__main__":
    sys.exit(main())
