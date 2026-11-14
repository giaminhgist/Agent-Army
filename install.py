#!/usr/bin/env python3
"""Install Agent-Army: python3 install.py [--claude] [--codex] [--uninstall [--purge]] [--dry-run]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from army.install import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
