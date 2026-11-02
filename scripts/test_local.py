#!/usr/bin/env python3
"""Run ROM-free tests with the checkout import path inherited by child scripts.

Use the project's dependency-enabled Python. Additional arguments go to pytest;
no package installation, gameplay, registry regeneration or publication occurs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    source = str(root / "src")
    previous = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = source + (os.pathsep + previous if previous else "")
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        environment[name] = "1"
    return subprocess.call(
        [sys.executable, "-m", "pytest", "-m", "not integration", *sys.argv[1:]],
        cwd=root,
        env=environment,
    )


if __name__ == "__main__":
    raise SystemExit(main())
