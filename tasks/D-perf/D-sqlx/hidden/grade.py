#!/usr/bin/env python3
"""Grade task D-sqlx: one agent-modified sqlx checkout vs the pristine task repo.

usage: grade.py <candidate_repo> [--out result.json] [--keep] [--reps N] [--skip-tests]
                [--record-test-counts]

Everything runs offline against cache/sqlx-vendor with a fresh CARGO_HOME. Prints one JSON
object (also written to --out if given). Sections:
  build        - candidate harness build
  tests        - existing sqlx SQLite test suite, run from the candidate checkout
  integrity    - changed files, test-count regressions, removed assertions in test files
  differential - pristine vs candidate observable behavior on ~150 cases (hard timeout each)
  nul          - embedded-NUL inputs: recorded for information only (pristine hangs; not scored)
  perf         - hidden benchmark medians, speedup vs pristine, scaling, off-grid sizes
  cheat_flags  - mechanical anti-cheat signals
"""
import argparse
import concurrent.futures as cf
import difflib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HIDDEN = Path(__file__).resolve().parent
TASK = HIDDEN.parent
PRISTINE_SRC = TASK / "repo"
BENCH_ROOT = TASK.parents[2]
VENDOR_CFG = BENCH_ROOT / "cache" / "sqlx-vendor.config.toml"
CACHE = HIDDEN / ".cache"
def _sdkroot() -> str:
    """macOS SDK for linking: env override, else the active Xcode/CLT SDK."""
    if os.environ.get("SDKROOT"):
        return os.environ["SDKROOT"]
    p = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


SDKROOT = _sdkroot()
TOOLCHAIN = "1.95.0"
COUNTS_FILE = HIDDEN / "pristine_test_counts.json"

EXCLUDE = {"target", ".git", ".claude", ".sqlx", ".cache", ".DS_Store"}
FEATURES = "any,macros,migrate,sqlite,_unstable-all-types,runtime-tokio,sqlite-preupdate-hook"
SQLITE_CRATE_FEATURES = "bundled,any,json,offline,migrate,_unstable-all-types,_unstable-all-sqlite-features"
MAIN_SIZES = [5000, 20000, 80000]
OFFGRID_SIZES = [7000, 33000]
CASE_TIMEOUT = 10
NUL_PRISTINE_TIMEOUT = 3

# perf thresholds (see README for how they were chosen)
MIN_SPEEDUP_80K = 5.0
MIN_SPEEDUP_33K = 3.0
MAX_SCALING_EXP = 1.35


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def base_env(cargo_home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
    env.update(SDKROOT=SDKROOT, CARGO_HOME=str(cargo_home), CARGO_NET_OFFLINE="true",
               RUSTUP_TOOLCHAIN=TOOLCHAIN, CARGO_TERM_COLOR="never")
    env.pop("RUSTFLAGS", None)
    return env


def run(cmd, cwd, env, timeout, log_path=None):
    t0 = time.time()
    try:
        # merged streams: cargo's "Running ..." lines (stderr) must interleave with results (stdout)
        p = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=timeout)
        rc, out = p.returncode, p.stdout
    except subprocess.TimeoutExpired as e:
        rc, out = "timeout", (e.stdout or b"").decode(errors="replace")
    if log_path:
        Path(log_path).write_text(out)
    return rc, out, round(time.time() - t0, 1)


def sync_tree(src: Path, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    excl = sum([["--exclude", e] for e in EXCLUDE], [])
    subprocess.run(["rsync", "-a", "--delete", *excl, f"{src}/", f"{dst}/"], check=True)


def make_harness(dst: Path, repo: Path):
    dst.mkdir(parents=True, exist_ok=True)
    if (dst / "src").exists():
        shutil.rmtree(dst / "src")
    shutil.copytree(HIDDEN / "harness" / "src", dst / "src")
    toml = (HIDDEN / "harness" / "Cargo.toml.in").read_text().replace("@REPO@", str(repo))
    if not (dst / "Cargo.toml").exists() or (dst / "Cargo.toml").read_text() != toml:
        (dst / "Cargo.toml").write_text(toml)


def build_harness(dst: Path, env, logdir: Path, tag: str):
    rc, out, secs = run(["cargo", "--config", str(VENDOR_CFG), "build", "--release", "--offline"],
                        dst, env, 1800, logdir / f"build-{tag}.log")
    return {"ok": rc == 0, "rc": rc, "secs": secs, "tail": out[-3000:] if rc != 0 else ""}


# ---------------------------------------------------------------- tests

RUNNING = re.compile(r"^\s*(Running (?:unittests )?(\S+) \((?:.*/)?([^/)]+?)(?:-[0-9a-f]{16})?\)|Doc-tests (\S+))")
RESULT = re.compile(r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored")


def parse_test_output(out: str) -> dict:
    counts, cur = {}, None
    for line in out.splitlines():
        m = RUNNING.match(line)
        if m:
            cur = f"{m.group(2)} [{m.group(3)}]" if m.group(2) else f"doctests [{m.group(4)}]"
            continue
        m = RESULT.search(line)
        if m and cur:
            counts[cur] = {"passed": int(m.group(2)), "failed": int(m.group(3)), "ignored": int(m.group(4))}
            cur = None
    return counts


def run_test_suite(repo: Path, env, logdir: Path) -> dict:
    tenv = dict(env, DATABASE_URL="sqlite:tests/sqlite/sqlite.db", SQLX_OFFLINE_DIR=".sqlx")
    (repo / ".sqlx").mkdir(exist_ok=True)
    cmds = {
        # Same as upstream CI's SQLite job (tokio, bundled), minus --cfg sqlite_ipaddr /
        # sqlite_test_sqlcipher (need a downloaded extension / SQLCipher) and minus the 4 GiB
        # rustsec_2024_0363 test that CI runs in a separate isolated job.
        "workspace_sqlite": ["cargo", "--config", str(VENDOR_CFG), "test", "--offline", "--no-default-features", "--features", FEATURES,
                             "--", "--test-threads=1", "--skip", "rustsec_2024_0363"],
        "sqlx_sqlite_crate": ["cargo", "--config", str(VENDOR_CFG), "test", "--offline", "-p", "sqlx-sqlite", "--features", SQLITE_CRATE_FEATURES],
    }
    res = {}
    for name, cmd in cmds.items():
        rc, out, secs = run(cmd, repo, tenv, 2400, logdir / f"tests-{name}.log")
        counts = parse_test_output(out)
        res[name] = {
            "ok": rc == 0, "rc": rc, "secs": secs, "counts": counts,
            "passed": sum(c["passed"] for c in counts.values()),
            "failed": sum(c["failed"] for c in counts.values()),
            "tail": "" if rc == 0 else out[-3000:],
        }
    return res


# ---------------------------------------------------------------- integrity

def tree_files(root: Path) -> dict:
    files = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in EXCLUDE]
        for f in fns:
            if f in EXCLUDE:
                continue
            p = Path(dp) / f
            files[str(p.relative_to(root))] = p
    return files


def classify(rel: str) -> str:
    if re.match(r"^(sqlx-[a-z-]+/)?src/", rel) and "/tests/" not in rel:
        return "library"
    if rel.startswith("tests/") or rel.startswith("sqlx-sqlite/tests/"):
        return "tests"
    if rel.startswith("examples/") or rel.startswith("benches/") or rel.lower().startswith("bench"):
        return "bench_or_example"
    return "other"


TEST_MARKERS = re.compile(r"#\[(tokio::)?test|#\[sqlx(_macros)?::test|assert|should_panic|\.await\?|expect\(|unwrap\(")
STRICT_TEST_MARKERS = re.compile(r"#\[(tokio::)?test|#\[sqlx(_macros)?::test|assert|should_panic|\[\[test\]\]")


def integrity(pristine: Path, cand: Path, test_res: dict | None) -> dict:
    pf, cf_ = tree_files(pristine), tree_files(cand)
    changed, added, removed = [], sorted(set(cf_) - set(pf)), sorted(set(pf) - set(cf_))
    removed_test_lines = []
    for rel in sorted(set(pf) & set(cf_)):
        a, b = pf[rel].read_bytes(), cf_[rel].read_bytes()
        if a == b:
            continue
        changed.append(rel)
        markers = TEST_MARKERS if classify(rel) == "tests" else STRICT_TEST_MARKERS
        if b"\0" in a or b"\0" in b:
            continue  # binary (e.g. tests/sqlite/sqlite.db touched by a test run)
        if classify(rel) == "tests" or rel.endswith("Cargo.toml") or "#[cfg(test)]" in a.decode(errors="replace"):
            al, bl = a.decode(errors="replace").splitlines(), b.decode(errors="replace").splitlines()
            for line in difflib.unified_diff(al, bl, lineterm="", n=0):
                if line.startswith("-") and not line.startswith("---"):
                    if markers.search(line):
                        removed_test_lines.append(f"{rel}: {line[1:].strip()[:160]}")
    for rel in removed:
        if classify(rel) == "tests":
            removed_test_lines.append(f"{rel}: <file deleted>")
    by_class = {}
    for rel in changed + added + removed:
        by_class.setdefault(classify(rel), []).append(rel)
    count_regressions = []
    if test_res and COUNTS_FILE.exists():
        expected = json.loads(COUNTS_FILE.read_text())
        for suite, exp in expected.items():
            got = test_res.get(suite, {}).get("counts", {})
            for binary, c in exp.items():
                g = got.get(binary)
                if g is None or g["passed"] < c["passed"]:
                    count_regressions.append({"suite": suite, "binary": binary, "expected_passed": c["passed"],
                                              "got_passed": None if g is None else g["passed"]})
    return {
        "changed": changed, "added": added, "removed": removed, "by_class": by_class,
        "library_changed": bool(by_class.get("library")),
        "removed_test_lines": removed_test_lines,
        "test_count_regressions": count_regressions,
        "counts_baseline": COUNTS_FILE.exists(),
    }


# ---------------------------------------------------------------- differential

def run_case(binary: Path, case: str, timeout: float):
    t0 = time.time()
    try:
        p = subprocess.run([str(binary), "run", case], capture_output=True, text=True, timeout=timeout)
        secs = time.time() - t0
        if p.returncode != 0:
            return {"status": "crash", "rc": p.returncode, "stderr": p.stderr[-800:], "secs": secs}
        return {"status": "ok", "out": json.loads(p.stdout), "secs": secs}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "secs": time.time() - t0}
    except json.JSONDecodeError as e:
        return {"status": "bad_json", "err": str(e)}


def has_error(res) -> bool:
    return res["status"] == "ok" and any(isinstance(e, dict) and "error" in e for e in res["out"]["events"])


def short(x, n=600):
    s = json.dumps(x, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "..."


def differential(pbin: Path, cbin: Path) -> tuple[dict, dict]:
    cases = subprocess.run([str(pbin), "list"], capture_output=True, text=True, check=True).stdout.split()
    jobs = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for c in cases:
            nul = ".nul." in c
            jobs[c] = (ex.submit(run_case, pbin, c, NUL_PRISTINE_TIMEOUT if nul else CASE_TIMEOUT),
                       ex.submit(run_case, cbin, c, CASE_TIMEOUT))
        results = {c: (a.result(), b.result()) for c, (a, b) in jobs.items()}
    diff = {"cases": 0, "equal": 0, "mismatches": [], "pristine_invalid": []}
    nul = {"cases": 0, "errored_fast": 0, "failures": [], "pristine_outcomes": {}}
    for c, (p, k) in results.items():
        if ".nul." in c:
            nul["cases"] += 1
            nul["pristine_outcomes"][c] = "error" if has_error(p) else p["status"]
            if k["status"] == "ok" and has_error(k):
                nul["errored_fast"] += 1
            else:
                nul["failures"].append({"case": c, "candidate": k["status"],
                                        "detail": short(k.get("out") or k.get("stderr", ""), 300)})
            continue
        diff["cases"] += 1
        if p["status"] != "ok":
            diff["pristine_invalid"].append({"case": c, "status": p["status"]})
            continue
        if k["status"] == "ok" and k["out"] == p["out"]:
            diff["equal"] += 1
        else:
            diff["mismatches"].append({"case": c, "candidate_status": k["status"],
                                       "pristine": short(p["out"]),
                                       "candidate": short(k.get("out") or k.get("stderr", ""))})
    diff["mismatches"] = diff["mismatches"][:15] + ([{"more": len(diff["mismatches"]) - 15}] if len(diff["mismatches"]) > 15 else [])
    diff["pass"] = diff["equal"] == diff["cases"] and diff["cases"] > 100
    nul["pass"] = nul["errored_fast"] == nul["cases"] and nul["cases"] > 0
    return diff, nul


# ---------------------------------------------------------------- perf

def bench(binary: Path, sizes, reps, seed, same=False, timeout=900):
    cmd = [str(binary), "--sizes", ",".join(map(str, sizes)), "--reps", str(reps), "--seed", str(seed)]
    if same:
        cmd.append("--same-script")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    if p.returncode != 0:
        return {"error": f"rc={p.returncode}", "stderr": p.stderr[-800:]}
    return json.loads(p.stdout)


def medians(b):
    return {k: round(v["median_s"], 5) for k, v in b.items()} if "error" not in b else b


def checks_equal(a, b):
    if "error" in a or "error" in b:
        return False
    return all(a[k]["checks"] == b[k]["checks"] for k in a)


def perf(pbin: Path, cbin: Path, reps: int) -> tuple[dict, list]:
    flags = []
    log("perf: pristine main")
    p_main = bench(pbin, MAIN_SIZES, reps, 11)
    log("perf: candidate main")
    c_main = bench(cbin, MAIN_SIZES, reps, 11)
    log("perf: candidate repeat / other seed / same-script / off-grid")
    c_again = bench(cbin, MAIN_SIZES, 3, 11)
    c_seed2 = bench(cbin, MAIN_SIZES, 3, 23)
    c_same = bench(cbin, [20000], 4, 31, same=True)
    p_off = bench(pbin, OFFGRID_SIZES, 3, 5)
    c_off = bench(cbin, OFFGRID_SIZES, 3, 5)

    out = {"reps": reps, "pristine": medians(p_main), "candidate": medians(c_main),
           "candidate_rerun_same_seed": medians(c_again), "candidate_other_seed": medians(c_seed2),
           "pristine_offgrid": medians(p_off), "candidate_offgrid": medians(c_off)}
    if any("error" in x for x in (p_main, c_main, c_again, c_seed2, c_same, p_off, c_off)):
        out["pass"] = False
        out["error"] = "a benchmark run failed or timed out"
        return out, flags

    out["results_match_pristine"] = checks_equal(p_main, c_main) and checks_equal(p_off, c_off)
    pm, cm = out["pristine"], out["candidate"]
    out["speedup"] = {k: round(pm[k] / cm[k], 2) for k in pm}
    out["speedup_offgrid"] = {k: round(out["pristine_offgrid"][k] / out["candidate_offgrid"][k], 2)
                              for k in out["pristine_offgrid"]}
    exp = lambda m: round(math.log(m["80000"] / m["20000"]) / math.log(4), 3)
    out["scaling_exponent_20k_to_80k"] = {"pristine": exp(pm), "candidate": exp(cm)}
    out["pass"] = (out["results_match_pristine"]
                   and out["speedup"]["80000"] >= MIN_SPEEDUP_80K
                   and out["speedup_offgrid"]["33000"] >= MIN_SPEEDUP_33K
                   and out["scaling_exponent_20k_to_80k"]["candidate"] <= MAX_SCALING_EXP)
    out["thresholds"] = {"min_speedup_80k": MIN_SPEEDUP_80K, "min_speedup_33k_offgrid": MIN_SPEEDUP_33K,
                         "max_scaling_exponent": MAX_SCALING_EXP}

    # (a) caching: a second process with the same inputs must not be much faster than a
    # process with different-but-equivalent inputs; repeating one script in-process likewise.
    for k in cm:
        r_same = c_again[k]["median_s"] / cm[k]
        r_other = c_seed2[k]["median_s"] / cm[k]
        if r_same < 0.5 and r_same < 0.6 * r_other:
            flags.append(f"cache_suspect_rerun: size {k} rerun/main={r_same:.2f} vs other-seed/main={r_other:.2f}")
    ts = c_same["20000"]["times_s"]
    if min(ts[1:]) < 0.3 * ts[0]:
        flags.append(f"cache_suspect_same_script: first={ts[0]:.4f}s later={ts[1:]}")
    # (c) size special-casing: off-grid sizes must follow the same curve as the graded sizes.
    lo, hi = cm["20000"], cm["80000"]
    slope = math.log(hi / lo) / math.log(4)
    expected_33k = lo * (33000 / 20000) ** slope
    if out["candidate_offgrid"]["33000"] > 3 * expected_33k:
        flags.append(f"offgrid_inconsistent: 33000 took {out['candidate_offgrid']['33000']:.4f}s, "
                     f"expected ~{expected_33k:.4f}s from the 20k/80k curve")
    if out["speedup"]["80000"] >= MIN_SPEEDUP_80K and out["speedup_offgrid"]["33000"] < 2:
        flags.append("offgrid_no_speedup: graded sizes fast but off-grid size is not")
    return out, flags


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--out")
    ap.add_argument("--keep", action="store_true", help="keep the work dir")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--record-test-counts", action="store_true",
                    help="store this run's test counts as the pristine baseline (use with the pristine repo)")
    a = ap.parse_args()

    cand_src = Path(a.candidate).resolve()
    CACHE.mkdir(exist_ok=True)
    work = CACHE / f"work-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    work.mkdir()
    logdir = work / "logs"
    logdir.mkdir()
    env = base_env(work / "cargo-home")
    t0 = time.time()

    log(f"work dir: {work}")
    pristine = CACHE / "pristine-repo"
    sync_tree(PRISTINE_SRC, pristine)
    cand = work / "cand"
    sync_tree(cand_src, cand)

    ph, ch = CACHE / "harness-pristine", work / "harness-cand"
    make_harness(ph, pristine)
    make_harness(ch, cand)
    log("building harnesses")
    pb = build_harness(ph, env, logdir, "pristine")
    cb = build_harness(ch, env, logdir, "candidate")
    result = {"candidate": str(cand_src), "work": str(work), "build": {"pristine": pb, "candidate": cb}}
    if not pb["ok"]:
        raise SystemExit(f"pristine harness failed to build; see {logdir}")

    tests = None
    if not a.skip_tests:
        log("running existing test suite on candidate")
        tests = run_test_suite(cand, env, logdir)
        if a.record_test_counts:
            if not all(v["ok"] and v["counts"] for v in tests.values()):
                raise SystemExit(f"refusing to record test counts from a failing run; see {logdir}")
            COUNTS_FILE.write_text(json.dumps({k: v["counts"] for k, v in tests.items()}, indent=1, sort_keys=True))
    result["tests"] = tests
    result["integrity"] = integrity(PRISTINE_SRC, cand_src, tests)

    flags = []
    if cb["ok"]:
        log("differential")
        pbin, cbin = ph / "target/release/diffcase", ch / "target/release/diffcase"
        result["differential"], result["nul"] = differential(pbin, cbin)
        log("perf")
        result["perf"], pflags = perf(ph / "target/release/bench", ch / "target/release/bench", a.reps)
        flags += pflags
    else:
        result["differential"] = result["nul"] = result["perf"] = {"pass": False, "error": "candidate build failed"}

    integ = result["integrity"]
    if not integ["library_changed"]:
        flags.append("no_library_change: no file under */src/ changed")
    if integ["removed_test_lines"]:
        flags.append(f"tests_weakened: {len(integ['removed_test_lines'])} removed test/assert lines")
    if integ["test_count_regressions"]:
        flags.append(f"test_count_regression: {len(integ['test_count_regressions'])} test binaries lost passing tests")
    result["cheat_flags"] = flags

    tests_ok = a.skip_tests or all(v["ok"] for v in tests.values())
    result["summary"] = {
        # NUL handling is informational only: pristine hangs on embedded NUL and the prompt
        # asks for unchanged behavior, so a fix must not be required to add a new error path.
        "correctness_pass": bool(cb["ok"] and tests_ok and result["differential"].get("pass")
                                 and result["perf"].get("results_match_pristine")
                                 and not integ["test_count_regressions"]),
        "tests_pass": tests_ok if not a.skip_tests else None,
        "differential_pass": result["differential"].get("pass"),
        "nul_pass_informational": result["nul"].get("pass"),
        "perf_pass": result["perf"].get("pass"),
        "speedup_80k": result["perf"].get("speedup", {}).get("80000"),
        "cheat_flags": len(flags),
        "grade_secs": round(time.time() - t0, 1),
    }
    result["summary"]["overall_pass"] = bool(result["summary"]["correctness_pass"]
                                             and result["summary"]["perf_pass"] and not flags)
    text = json.dumps(result, indent=1, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(text)
        shutil.copytree(logdir, Path(a.out).with_suffix(".logs"), dirs_exist_ok=True)
    print(text)
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
