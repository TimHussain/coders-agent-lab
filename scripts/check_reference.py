"""Facilitator-only check: execute the documented solutions in a temporary copy.

Run with the same Python environment as the installed lab. No participant files
are edited. The same test suite runs against the three exact code blocks in the guide.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    guide = (root / "FACILITATOR.md").read_text(encoding="utf-8")
    solutions = re.findall(r"<!-- solution: ([^ ]+) -->\n```python\n(.*?)\n```", guide, re.S)
    expected = {
        "src/agentlab/mcp_server/tools.py",
        "src/agentlab/harness/raw_loop.py",
        "src/agentlab/harness/lc_agent.py",
    }
    if {path for path, _ in solutions} != expected or len(solutions) != 3:
        raise RuntimeError(
            "The facilitator guide must contain exactly three complete solution files."
        )
    with tempfile.TemporaryDirectory(prefix="agentlab-reference-") as directory:
        target = Path(directory) / "lab"
        shutil.copytree(
            root,
            target,
            ignore=shutil.ignore_patterns(
                ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "traces", ".env"
            ),
        )
        for relative, source in solutions:
            (target / relative).write_text(source + "\n", encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(target / "src"), "AGENTLAB_LIVE_TEST": "0"}
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q"], cwd=target, env=env
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
