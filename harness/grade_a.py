#!/usr/bin/env python3
"""Grade an A task (fresh upstream bug) on a copy of the agent's repo.

Usage: grade_a.py <task_id> <agent_repo> --out result.json

Hidden tests are the maintainer's tests from the upstream fix. They are placed into a
copy of the agent's repo (never the run dir itself), then run offline. Also runs the
surrounding package's own tests to catch regressions.

SDKROOT (for cgo / Rust linking) comes from the environment or `xcrun --show-sdk-path`.
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent
A = BENCH / "tasks" / "A-fresh-bugs"
CACHE = BENCH / "cache"


def sdkroot() -> str:
    if os.environ.get("SDKROOT"):
        return os.environ["SDKROOT"]
    p = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


SDKROOT = sdkroot()


def sh(cmd, cwd, env, timeout):
    t = __import__("time").time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return dict(rc=p.returncode, out=(p.stdout + p.stderr)[-4000:], secs=round(__import__("time").time() - t, 1))
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"") + (e.stderr or b"")).decode(errors="replace") if isinstance(e.stdout, bytes) else ""
        return dict(rc="timeout", out=out[-4000:], secs=timeout)


def base_env(tmp: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
    if SDKROOT:
        env["SDKROOT"] = SDKROOT
    return env


def grade_etcd(repo: Path, tmp: Path) -> dict:
    env = base_env(tmp)
    env.update(GOMODCACHE=str(CACHE / "gomod"), GOTOOLCHAIN="go1.26.5", GOPROXY="off",
               GOCACHE=str(tmp / "gocache"), GOFLAGS="", GOTELEMETRY="off")
    storage = repo / "server" / "storage"
    agent_test = storage / "quota_test.go"
    if agent_test.exists():  # agent wrote its own tests in the same file name: keep them aside
        agent_test.rename(storage / "quota_agent_test.go")
    shutil.copy(A / "A1-etcd" / "hidden" / "quota_test.go", agent_test)
    hidden = sh(["go", "test", "./storage/", "-run", "^TestCostTxn$", "-v", "-count=1"], repo / "server", env, 600)
    if hidden["rc"] != 0 and "quota_agent_test.go" in hidden["out"]:
        # Name clash between the agent's test file and the hidden one: grade hidden alone.
        (storage / "quota_agent_test.go").unlink()
        hidden = sh(["go", "test", "./storage/", "-run", "^TestCostTxn$", "-v", "-count=1"], repo / "server", env, 600)
        hidden["note"] = "agent quota_test.go removed due to name clash"
    regress = sh(["go", "test", "./storage/", "./etcdserver/...", "-count=1"], repo / "server", env, 1500)
    return dict(hidden_pass=hidden["rc"] == 0, hidden=hidden, regress_pass=regress["rc"] == 0, regress=regress)


def grade_pytest(repo: Path, tmp: Path) -> dict:
    env = base_env(tmp)
    env["SETUPTOOLS_SCM_PRETEND_VERSION"] = "9.1.0.dev0"
    venv = tmp / ".venv"
    subprocess.run(["uv", "venv", "-q", "--python", "3.12", str(venv)], check=True, env=env)
    subprocess.run(["uv", "pip", "install", "-q", "--offline", "-e", f"{repo}[dev]"], check=True,
                   env=dict(env, VIRTUAL_ENV=str(venv)))
    py = str(venv / "bin" / "python")
    # Hidden: the maintainer's full test_monkeypatch.py replaces the agent's copy.
    agent_file = repo / "testing" / "test_monkeypatch.py"
    shutil.copy(agent_file, repo / "testing" / "test_monkeypatch_agent.py")
    shutil.copy(A / "A2-pytest" / "hidden" / "test_monkeypatch.py", agent_file)
    hidden = sh([py, "-m", "pytest", "testing/test_monkeypatch.py", "-q", "-p", "no:cacheprovider"], repo, env, 600)
    # cacheprovider must stay enabled: pytest's own suite uses the `cache` fixture.
    regress = sh([py, "-m", "pytest", "testing/", "-q", "-n", "4",
                  "--ignore=testing/test_monkeypatch_agent.py"], repo, env, 1800)
    return dict(hidden_pass=hidden["rc"] == 0, hidden=hidden, regress_pass=regress["rc"] == 0, regress=regress)


def grade_ripgrep(repo: Path, tmp: Path) -> dict:
    env = base_env(tmp)
    env.update(CARGO_HOME=str(tmp / "cargo"), CARGO_NET_OFFLINE="true")
    (tmp / ".cargo").mkdir(exist_ok=True)
    cfg = ["--config", str(CACHE / "ripgrep-vendor.config.toml")]
    walk = repo / "crates" / "ignore" / "src" / "walk.rs"
    with open(walk, "a") as f:
        f.write((A / "A3-ripgrep" / "hidden" / "hidden_tests.rs").read_text())
    runs = [sh(["timeout", "120", "cargo", *cfg, "test", "-q", "-p", "ignore", "--lib", "bench_hidden_tests"],
               repo, env, 900) for _ in range(5)]
    hidden_pass = all(r["rc"] == 0 for r in runs)
    regress = sh(["timeout", "600", "cargo", *cfg, "test", "-q", "-p", "ignore"], repo, env, 900)
    return dict(hidden_pass=hidden_pass, hidden_runs=[{k: r[k] for k in ("rc", "secs")} for r in runs],
                hidden=runs[-1], regress_pass=regress["rc"] == 0, regress=regress)


GRADERS = {"A1-etcd": grade_etcd, "A2-pytest": grade_pytest, "A3-ripgrep": grade_ripgrep}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", choices=GRADERS)
    ap.add_argument("repo")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix=f"grade-{a.task}-"))
    work = tmp / "repo"
    shutil.copytree(a.repo, work, symlinks=True, ignore=shutil.ignore_patterns("target", ".git", "__pycache__"))
    res = GRADERS[a.task](work, tmp)
    res["pass"] = bool(res["hidden_pass"] and res["regress_pass"])
    Path(a.out).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("pass", "hidden_pass", "regress_pass")}))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
