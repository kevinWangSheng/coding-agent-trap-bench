#!/usr/bin/env python3
"""Run the full plan: tasks x models x reps, sealed, with bounded concurrency.

Usage: orchestrate.py [--reps 3] [--workers 3] [--only A1-etcd,B2-exprcalc] [--models ...] [--dry]

Rules:
- grader material is sealed for the whole batch (seal.py);
- two runs of the same task never overlap, so no run can read another model's work in progress;
- each finished run dir and its raw output dir are chmod 000 until grading;
- job order interleaves models within each rep, so time-of-day / network drift is spread evenly.
Progress is appended to results/orchestrate.log; re-running skips jobs whose output exists.
Run dirs live in $BENCH_RUNS_DIR (default ~/.bench-runs).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
BENCH = HARNESS.parent
RAW = BENCH / "results" / "raw"
RUNS = Path(os.environ.get("BENCH_RUNS_DIR", Path.home() / ".bench-runs")).expanduser()
LOG = BENCH / "results" / "orchestrate.log"
MAX_ATTEMPTS = 4
MIN_FREE = 8 << 30  # bytes; one sqlx build alone can take ~3 GB

TASKS = [
    ("A1-etcd", "prompt.md"), ("A2-pytest", "prompt.md"), ("A3-ripgrep", "prompt.md"),
    ("B1-flexdate", "prompt.md"), ("B2-exprcalc", "prompt.md"), ("B3-paylink", "prompt.md"),
    ("B1-flexdate", "prompt_noconstraint.md"), ("B2-exprcalc", "prompt_noconstraint.md"),
    ("B3-paylink", "prompt_noconstraint.md"),
    ("C-mcp", "prompt.md"), ("D-sqlx", "prompt.md"),
]
MODELS = ["opus-5.5", "gpt-6-astra", "gpt-6-sol"]


def run_id(task, prompt, model, rep):
    variant = "" if prompt == "prompt.md" else "__" + Path(prompt).stem
    return f"{task}{variant}__{model}__r{rep}"


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only")
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    # Only one orchestrator may run, and the lock is taken before anything else: planning
    # opens sealed result dirs, which must never happen while another batch is running.
    import fcntl
    (BENCH / "results").mkdir(exist_ok=True)
    lockf = open(BENCH / "results" / ".orchestrate.lock", "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("another orchestrator is running; refusing to start")
    models = a.models.split(",")
    only = set(a.only.split(",")) if a.only else None

    # Finished runs are sealed (chmod 000); open them just long enough to read meta.json,
    # otherwise a completed run would look unfinished and be deleted and re-run.
    def finished(rid):
        d = RAW / rid
        if not d.exists():
            return False
        mode = d.stat().st_mode & 0o777
        os.chmod(d, 0o755)
        try:
            m = json.loads((d / "meta.json").read_text())
            return "wall_s" in m and m.get("valid", True) is not False
        except (FileNotFoundError, json.JSONDecodeError):
            return False
        finally:
            os.chmod(d, mode)

    jobs = []
    for rep in range(1, a.reps + 1):
        for i, (task, prompt) in enumerate(TASKS):
            if only and task not in only:
                continue
            # rotate model order per task and rep
            k = (i + rep) % len(models)
            for m in models[k:] + models[:k]:
                rid = run_id(task, prompt, m, rep)
                if not finished(rid):
                    jobs.append((task, prompt, m, rep, rid))
    log(f"plan: {len(jobs)} jobs, workers={a.workers}")
    if a.dry:
        for j in jobs:
            print(j[-1])
        return

    subprocess.run([sys.executable, HARNESS / "seal.py", "seal"], check=True, capture_output=True)
    lock = threading.Lock()
    running_tasks = set()
    pending = list(jobs)

    def take():
        with lock:
            for j in pending:
                if j[0] not in running_tasks:
                    pending.remove(j)
                    running_tasks.add(j[0])
                    return j
            return None if not pending else "wait"

    def disk_ok():
        return shutil.disk_usage(Path.home()).free > MIN_FREE

    def worker():
        while True:
            while not disk_ok():
                log(f"low disk ({shutil.disk_usage(Path.home()).free >> 30} GB free); waiting")
                time.sleep(120)
            j = take()
            if j is None:
                return
            if j == "wait":
                time.sleep(10)
                continue
            task, prompt, model, rep, rid = j
            # a half-finished earlier attempt leaves a raw dir without wall_s; clear it
            for stale in (RAW / rid, RUNS / rid):
                if stale.exists():
                    subprocess.run(["chmod", "-R", "u+rwx", stale])
                    subprocess.run(["rm", "-rf", stale])
            for attempt in range(1, MAX_ATTEMPTS + 1):
                for stale in (RAW / rid, RUNS / rid):
                    if stale.exists():
                        subprocess.run(["chmod", "-R", "u+rwx", stale])
                        if stale == RAW / rid and attempt > 1:
                            # keep the failed attempt's logs for the record
                            dst = BENCH / "results" / "raw_invalid" / f"{rid}__attempt{attempt - 1}"
                            dst.parent.mkdir(exist_ok=True)
                            subprocess.run(["rm", "-rf", dst])
                            subprocess.run(["mv", stale, dst])
                        else:
                            subprocess.run(["rm", "-rf", stale])
                log(f"start {rid} attempt={attempt}")
                p = subprocess.run([sys.executable, HARNESS / "run.py", task, model, str(rep), "--prompt", prompt],
                                   capture_output=True, text=True)
                log(f"done  {rid} rc={p.returncode} {p.stdout.strip()[-200:]} {p.stderr.strip()[-300:]}")
                try:
                    m = json.loads((RAW / rid / "meta.json").read_text())
                except (FileNotFoundError, json.JSONDecodeError):
                    m = {}
                if p.returncode == 0 and m.get("valid"):
                    break
                log(f"invalid {rid} attempt={attempt}: {m.get('infra_error') or p.stderr.strip()[-200:]}")
                time.sleep(120 * attempt)
            for d in (RUNS / rid, RAW / rid):
                if d.exists():
                    os.chmod(d, 0)
            with lock:
                running_tasks.discard(task)

    threads = [threading.Thread(target=worker) for _ in range(a.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log("batch finished; grader material stays sealed until grade_all.py unseals it")


if __name__ == "__main__":
    main()
