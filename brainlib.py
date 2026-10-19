#!/usr/bin/env python3
"""Run brainlib from this folder. Nothing to install: only Python 3.9 or newer is needed.

macOS / Linux:  python3 brainlib.py next
Windows:        py -3 brainlib.py next     (or: brainlib.cmd next)
"""

import os
import sys

if sys.version_info < (3, 9):
    sys.stderr.write(
        "ERROR: brainlib needs Python 3.9 or newer; this is Python %d.%d.\n"
        "FIX: install a newer Python (see step 1 of AGENTS.md), then try again.\n" % sys.version_info[:2]
    )
    sys.exit(2)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brainlib.cli import main  # noqa: E402

sys.exit(main())
