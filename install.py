#!/usr/bin/env python3
"""Install Agent-Army: python3 install.py [--claude] [--codex] [--uninstall [--purge]] [--dry-run]"""

import sys

if sys.version_info < (3, 11):
    print("Agent-Army needs Python ≥ 3.11 (found %d.%d). Run install.py with a newer python3." % sys.version_info[:2])
    sys.exit(1)

from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from army.install import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
