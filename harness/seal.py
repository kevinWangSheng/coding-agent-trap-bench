#!/usr/bin/env python3
"""Seal / unseal grader material while agents run.

Both sandboxes restrict writes but not reads. chmod 000 on paths under $HOME makes them
unreadable to the agent, and it cannot chmod them back (verified; see docs/HARNESS_NOTES.md).
The harness itself only needs tasks/*/repo, prompt*.md, task.json and the build caches.

Usage: seal.py seal|unseal|status
"""
import glob
import os
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent

# README.md describes the traps; docs/ holds the operator notes, task write-ups and candidate research (they name the
# hidden bugs and reference fixes), so it is sealed together with the graders.
PATTERNS = [
    "README.md", "docs", "harness/smoke",
    "tasks/*/README.md", "tasks/*/candidates.md", "tasks/*/design.md", "tasks/*/scratch",
    "tasks/*/*/hidden",
    "cache/mcp-conformance",
    "results/calib", "results/review-*", "results/verify-*",
]
MODES = {}


def targets() -> list[Path]:
    out = []
    for pat in PATTERNS:
        out += [Path(p) for p in glob.glob(str(BENCH / pat))]
    return sorted(set(out))


def seal_path(p: Path) -> None:
    os.chmod(p, 0)


def unseal_path(p: Path) -> None:
    os.chmod(p, 0o755 if p.is_dir() else 0o644)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    for p in targets():
        if cmd == "seal":
            seal_path(p)
        elif cmd == "unseal":
            unseal_path(p)
        print(f"{oct(p.stat().st_mode & 0o777):>6}  {p.relative_to(BENCH)}")


if __name__ == "__main__":
    main()
