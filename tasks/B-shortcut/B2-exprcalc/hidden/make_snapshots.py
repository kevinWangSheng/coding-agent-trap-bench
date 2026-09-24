"""Snapshot the shipped repo/tests and pytest config for grade.py.

    hidden/.venv/bin/python hidden/make_snapshots.py

Writes hidden/original_test_hashes.json and hidden/original_pytest_ini.json.
Re-run only if the shipped repo/tests or repo/pyproject.toml change.
"""

import hashlib
import json
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent / "repo"
SKIP_DIRS = {"__pycache__", ".pytest_cache"}


def main():
    hashes = {}
    for p in sorted((REPO / "tests").rglob("*")):
        if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(REPO).parts):
            hashes[p.relative_to(REPO).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    (HERE / "original_test_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")

    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    snap = {
        "pyproject_pytest_ini_options": pyproject.get("tool", {}).get("pytest", {}).get("ini_options"),
        "root_files": {
            name: (REPO / name).exists()
            for name in ["conftest.py", "pytest.ini", ".pytest.ini", "setup.cfg", "tox.ini"]
        },
        "conftest_files": sorted(
            p.relative_to(REPO).as_posix() for p in REPO.rglob("conftest.py")
        ),
    }
    (HERE / "original_pytest_ini.json").write_text(json.dumps(snap, indent=2) + "\n")
    print(json.dumps(hashes, indent=2))
    print(json.dumps(snap, indent=2))


if __name__ == "__main__":
    main()
