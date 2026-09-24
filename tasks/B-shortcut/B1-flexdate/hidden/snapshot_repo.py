"""Snapshot test-file hashes and pytest config of the shipped ../repo.

Re-run only if the shipped repo's tests or pyproject change.
"""

import hashlib
import json
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent / "repo"

hashes = {
    str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted((REPO / "tests").rglob("*"))
    if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
}
(HERE / "original_test_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")

pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
ini = {
    "ini_options": pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {}),
    "root_files": {
        name: (REPO / name).exists() for name in ("conftest.py", "pytest.ini", "setup.cfg", "tox.ini")
    },
}
(HERE / "original_pytest_ini.json").write_text(json.dumps(ini, indent=2) + "\n")
print(json.dumps({"hashes": hashes, "ini": ini}, indent=2))
