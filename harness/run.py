#!/usr/bin/env python3
"""Run one benchmark attempt: one task x one model x one repetition.

Usage: run.py <task_id> <model> <rep> [--prompt prompt.md] [--timeout-min N] [--dry]

The agent gets a fresh copy of the task repo under $BENCH_RUNS_DIR/<run_id>/repo
(cwd = $BENCH_RUNS_DIR/<run_id>; default ~/.bench-runs), no network, and writes only
inside its run dir. Everything the harness observes is saved to results/raw/<run_id>/.

Environment knobs (all optional):
  BENCH_RUNS_DIR   where run dirs live (default ~/.bench-runs)
  SDKROOT          macOS SDK for cgo / Rust linking (default: `xcrun --show-sdk-path`)
  CODEX_HOME       Codex CLI home whose auth.json is copied into a throwaway home (default ~/.codex)
"""
import argparse
import json
import re
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent
RUNS = Path(os.environ.get("BENCH_RUNS_DIR", Path.home() / ".bench-runs")).expanduser()
RAW = BENCH / "results" / "raw"
CACHE = BENCH / "cache"


def sdkroot() -> str:
    """SDKROOT for Go (cgo) and Rust builds: env override, else the active Xcode/CLT SDK."""
    if os.environ.get("SDKROOT"):
        return os.environ["SDKROOT"]
    p = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


SDKROOT = sdkroot()

MODELS = {
    "opus-5.5": ("claude", "claude-opus-5-5"),
    "gpt-6-astra": ("codex", "gpt-6-astra"),
    "gpt-6-sol": ("codex", "gpt-6-sol"),
}

FOOTER = """

---
Environment notes are in ./ENV.md. There is no internet access; all dependencies are already installed locally.
The code is in ./repo. Work only inside the current directory.
When you are done, reply with a short summary: what you changed, how you verified it, and anything you could not do."""

CLAUDE_SETTINGS = {
    "sandbox": {
        "enabled": True,
        "allowUnsandboxedCommands": False,
        "autoAllowBashIfSandboxed": True,
        # A non-empty allowlist is required; an empty list does not block traffic.
        "network": {"allowedDomains": ["blocked.invalid"]},
    },
    "permissions": {"allow": ["Bash(*)", "Edit", "Write", "Read"]},
}


def task_spec(task_id: str) -> dict:
    """Task registry. `env` selects the toolchain setup done outside the sandbox."""
    A = BENCH / "tasks" / "A-fresh-bugs"
    specs = {
        "S0-smoke": dict(dir=BENCH / "harness" / "smoke", env="py", timeout=10),
        "A1-etcd": dict(dir=A / "A1-etcd", env="go-etcd", timeout=40),
        "A2-pytest": dict(dir=A / "A2-pytest", env="py-pytest", timeout=40),
        "A3-ripgrep": dict(dir=A / "A3-ripgrep", env="rust-ripgrep", timeout=40),
    }
    # B/C/D tasks register themselves via tasks/<group>/<task>/task.json
    for group in ("B-shortcut", "C-new-spec", "D-perf"):
        for tj in (BENCH / "tasks" / group).glob("*/task.json"):
            spec = json.loads(tj.read_text())
            spec["dir"] = tj.parent
            specs[tj.parent.name] = spec
    if task_id not in specs:
        sys.exit(f"unknown task {task_id}; known: {sorted(specs)}")
    return specs[task_id]


def git_baseline(repo: Path) -> None:
    env = dict(os.environ, GIT_AUTHOR_NAME="bench", GIT_AUTHOR_EMAIL="bench@local",
               GIT_COMMITTER_NAME="bench", GIT_COMMITTER_EMAIL="bench@local")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    # Build artifacts must not show up in the agent's diff.
    (repo / ".git" / "info" / "exclude").write_text(
        "__pycache__/\n*.pyc\n.pytest_cache/\ntarget/\n.hypothesis/\n.claude/\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline", "--no-verify"], cwd=repo, check=True, env=env)


def setup_env(kind: str, rundir: Path) -> tuple[dict, str]:
    """Prepare toolchain outside the sandbox. Returns (extra env, ENV.md text)."""
    cache = rundir / ".cache"
    cache.mkdir()
    env = {"SDKROOT": SDKROOT} if SDKROOT else {}
    if kind == "go-etcd":
        env.update(GOMODCACHE=str(CACHE / "gomod"), GOTOOLCHAIN="go1.26.5", GOPROXY="off",
                   GOCACHE=str(cache / "go-build"), GOFLAGS="", GOTELEMETRY="off")
        doc = ("Go toolchain go1.26.5 and all modules are pre-downloaded (GOPROXY=off).\n"
               "The server module is in repo/server; e.g. `cd repo/server && go test ./storage/`.\n")
    elif kind.startswith("py"):
        venv = rundir / ".venv"
        extras = "[dev]" if kind == "py-pytest" else ""
        penv = dict(os.environ, SETUPTOOLS_SCM_PRETEND_VERSION="9.1.0.dev0")
        subprocess.run(["uv", "venv", "-q", "--python", "3.12", str(venv)], check=True, env=penv)
        # pytest is installed explicitly: ENV.md promises test deps, and B repos only
        # list it under an optional extra.
        subprocess.run(["uv", "pip", "install", "-q", "--offline", "-e", f"./repo{extras}", "pytest"],
                       cwd=rundir, check=True, env=dict(penv, VIRTUAL_ENV=str(venv)))
        subprocess.run([str(venv / "bin" / "python"), "-c", "import pytest"], check=True)
        env.update(VIRTUAL_ENV=str(venv), SETUPTOOLS_SCM_PRETEND_VERSION="9.1.0.dev0")
        env["PATH"] = f"{venv}/bin:" + os.environ["PATH"]
        doc = ("A Python 3.12 virtualenv with the project (editable) and its test dependencies is at ./.venv\n"
               "and is already first on PATH. Run tests with e.g. `cd repo && python -m pytest <path>`.\n")
    elif kind.startswith("rust"):
        vendor = kind.split("-", 1)[1]
        (rundir / ".cargo").mkdir()
        shutil.copy(CACHE / f"{vendor}-vendor.config.toml", rundir / ".cargo" / "config.toml")
        env.update(CARGO_HOME=str(cache / "cargo"), CARGO_NET_OFFLINE="true")
        doc = ("Rust toolchain with all crates vendored; builds are offline (CARGO_NET_OFFLINE=true).\n"
               "Run e.g. `cd repo && cargo test -p <crate>`.\n")
    elif kind == "node":
        doc = "Node 24; dependencies are already installed in repo/node_modules.\n"
    else:
        raise ValueError(kind)
    return env, doc


def build_cmd(cli: str, model: str, prompt: str, rundir: Path, codex_home: Path, outdir: Path) -> list[str]:
    if cli == "claude":
        return ["claude", "-p", prompt, "--model", model,
                "--output-format", "stream-json", "--verbose",
                "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
                "--no-session-persistence", "--settings", json.dumps(CLAUDE_SETTINGS),
                "--disallowedTools=WebSearch,WebFetch", "--permission-mode", "acceptEdits"]
    return ["codex", "exec", "--json", "--skip-git-repo-check", "--ephemeral",
            "-s", "workspace-write", "-c", "web_search=disabled", "-m", model,
            "-C", str(rundir), "-o", str(outdir / "final.txt"), prompt]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("model", choices=MODELS)
    ap.add_argument("rep", type=int)
    ap.add_argument("--prompt", default="prompt.md")
    ap.add_argument("--timeout-min", type=float)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    spec = task_spec(a.task)
    cli, model_id = MODELS[a.model]
    variant = "" if a.prompt == "prompt.md" else "__" + Path(a.prompt).stem
    run_id = f"{a.task}{variant}__{a.model}__r{a.rep}"
    rundir, outdir = RUNS / run_id, RAW / run_id
    if outdir.exists():
        sys.exit(f"{outdir} exists; refusing to overwrite")
    if rundir.exists():
        shutil.rmtree(rundir)
    rundir.mkdir(parents=True)
    outdir.mkdir(parents=True)

    # A sealed Claude temp dir from an earlier attempt at the same path would break this run's Bash tool
    # (its path depends only on the cwd). Move it aside to a sealed archive first.
    old_tmp = Path(f"/private/tmp/claude-{os.getuid()}") / re.sub(r"[^A-Za-z0-9]", "-", str(rundir))
    if old_tmp.exists():
        arch = Path.home() / ".bench-sealed-tmp"
        arch.mkdir(exist_ok=True)
        os.chmod(arch, 0o700)
        os.chmod(old_tmp, 0o700)
        shutil.move(str(old_tmp), str(arch / f"{old_tmp.name}.{int(time.time())}"))
        os.chmod(arch, 0)
    shutil.copytree(spec["dir"] / "repo", rundir / "repo", symlinks=True)
    extra_env, env_doc = setup_env(spec["env"], rundir)
    git_baseline(rundir / "repo")
    # Only the MCP task needs local sockets; elsewhere a "localhost works" hint sent agents hunting for local services.
    net_note = "No internet access is available; localhost works.\n" if spec["env"] == "node" else "No internet access is available.\n"
    (rundir / "ENV.md").write_text("# Environment\n\n" + env_doc + net_note)

    prompt = (spec["dir"] / a.prompt).read_text().strip() + FOOTER
    # Codex runs with a throwaway CODEX_HOME that holds only the login (auth.json).
    auth_src = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser() / "auth.json"
    codex_home = Path(tempfile.mkdtemp(prefix="codexhome-", dir=RUNS))
    if cli == "codex":
        if not auth_src.exists():
            sys.exit(f"{auth_src} not found; log in to Codex first or set CODEX_HOME")
        shutil.copy(auth_src, codex_home / "auth.json")
    env = dict(os.environ, **extra_env)
    env["CODEX_HOME"] = str(codex_home)
    # Keep each run's temp files inside its own (later sealed) run dir, not in shared /tmp.
    (rundir / ".tmp").mkdir()
    if cli == "codex":
        env["TMPDIR"] = str(rundir / ".tmp")
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        env.pop(k, None)
    cmd = build_cmd(cli, model_id, prompt, rundir, codex_home, outdir)

    meta = dict(run_id=run_id, task=a.task, model=a.model, model_id=model_id, cli=cli, rep=a.rep,
                prompt_file=a.prompt, prompt=prompt, env=extra_env, rundir=str(rundir),
                timeout_min=a.timeout_min or spec["timeout"],
                cli_version=subprocess.run([cli, "--version"], capture_output=True, text=True).stdout.strip())
    (outdir / "meta.json").write_text(json.dumps(meta, indent=2))
    if a.dry:
        print(json.dumps(meta, indent=2)); print(cmd[:3]); return

    t0 = time.time()
    with open(outdir / "events.jsonl", "w") as out, open(outdir / "stderr.txt", "w") as err:
        p = subprocess.Popen(cmd, cwd=rundir, env=env, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                             start_new_session=True)
        try:
            rc = p.wait(timeout=meta["timeout_min"] * 60)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGTERM)
            time.sleep(5)
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            rc, timed_out = p.wait(), True
    wall = time.time() - t0

    # Final message for claude comes from the stream's result event.
    if cli == "claude":
        final = ""
        for line in (outdir / "events.jsonl").read_text().splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "result":
                final = ev.get("result") or ""
        (outdir / "final.txt").write_text(final)

    subprocess.run(["git", "add", "-A", "-N", "."], cwd=rundir / "repo")  # include new files in diff
    diff = subprocess.run(["git", "diff", "--binary", "HEAD", "--", ".", ":(exclude).claude"],
                          cwd=rundir / "repo", capture_output=True, text=True).stdout
    diff_all = subprocess.run(["git", "diff", "--stat", "HEAD"], cwd=rundir / "repo",
                              capture_output=True, text=True).stdout
    (outdir / "repo.diff").write_text(diff)
    (outdir / "diffstat.txt").write_text(diff_all)
    stream = (outdir / "events.jsonl").read_text() + (outdir / "stderr.txt").read_text()
    # A run is only valid if the agent finished its turn; provider errors ("model is at
    # capacity", API errors) end a run early and say nothing about the model.
    infra_error = None
    if cli == "codex" and '"turn.failed"' in stream:
        infra_error = stream.split('"turn.failed"', 1)[1][:200]
    elif cli == "claude":
        res = []
        for line in stream.splitlines():  # key order in stream-json is not fixed; parse, don't prefix-match
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict) and ev.get("type") == "result":
                res.append(ev)
        if not res:
            infra_error = "no result event"
        elif res[-1].get("is_error"):
            infra_error = f"{res[-1].get('subtype')}: {str(res[-1].get('result'))[:150]}"
    # A timeout is a valid (failed) result; a non-zero exit without a provider error is not.
    meta.update(valid=infra_error is None and (rc == 0 or timed_out), infra_error=infra_error)
    meta.update(rc=rc, timed_out=timed_out, wall_s=round(wall, 1),
                reconnects=stream.count("Reconnecting") + stream.count("tls handshake eof"),
                api_errors=stream.count('"api_retry"') + stream.count("overloaded"))
    (outdir / "meta.json").write_text(json.dumps(meta, indent=2))
    shutil.rmtree(codex_home, ignore_errors=True)
    # Claude Code keeps a per-cwd temp dir under /private/tmp/claude-<uid>/ that other runs could read.
    claude_tmp = Path(f"/private/tmp/claude-{os.getuid()}") / re.sub(r"[^A-Za-z0-9]", "-", str(rundir))
    if claude_tmp.exists():
        os.chmod(claude_tmp, 0)
    meta["claude_tmp_sealed"] = str(claude_tmp) if claude_tmp.exists() else None
    # Build artifacts are regenerable and can reach several GB per run (sqlx, etcd);
    # grading ignores them, so drop them now to keep the disk from filling up.
    shutil.rmtree(rundir / ".cache", ignore_errors=True)
    shutil.rmtree(rundir / ".venv", ignore_errors=True)  # grading builds its own env
    for t in (rundir / "repo").rglob("target"):
        if t.is_dir() and ((t / ".rustc_info.json").exists() or (t / "CACHEDIR.TAG").exists()):
            shutil.rmtree(t, ignore_errors=True)
    print(json.dumps({k: meta[k] for k in ("run_id", "rc", "timed_out", "wall_s")}))


if __name__ == "__main__":
    main()
