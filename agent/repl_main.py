#!/usr/bin/env python3
"""REPL launcher — thin wrapper that execs agent/repl.py."""
from __future__ import annotations
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPL = HERE / "repl.py"

if not REPL.exists():
    print(f"ERROR: repl.py not found at {REPL}", file=sys.stderr)
    sys.exit(1)

# Re-execute under the venv python with repl.py as __main__
os.execv(sys.executable, [sys.executable, str(REPL)] + sys.argv[1:])
