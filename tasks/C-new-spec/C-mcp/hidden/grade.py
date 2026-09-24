#!/usr/bin/env python3
"""Grade one implementation of task C-mcp (MCP 2026-07-28 server), fully offline.

Usage: grade.py <repo_dir> [--out DIR] [--record-expected]

Steps (each on a fresh server process, so state from one phase cannot leak
into another):
  1. copy <repo_dir> (minus node_modules/dist/.git) to a work dir and link the
     task's pristine repo/node_modules into it; `npm run build`
  2. conformance: pinned @modelcontextprotocol/conformance CLI from
     cache/mcp-conformance, `server --requirements 2026-07-28`; scored against
     hidden/conformance_expected.json (the checks the reference passes; checks
     that depend on the CLI's own fixture tools/prompts are excluded - see
     hidden/conformance_excluded.json)
  3. hidden tests: node --test hidden/tests/*.test.ts against the server
  4. stale_api_check.py: static scan of src/ + dynamic probes of the server
Emits one JSON object on stdout. --record-expected (reference only) rewrites
the expected/excluded conformance files from this run.
"""
import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HIDDEN = Path(__file__).resolve().parent
TASK = HIDDEN.parent
BENCH = TASK.parent.parent.parent
PRISTINE_NODE_MODULES = TASK / "repo" / "node_modules"
CONFORMANCE_DIR = BENCH / "cache" / "mcp-conformance"
CONFORMANCE_BIN = CONFORMANCE_DIR / "node_modules" / "@modelcontextprotocol" / "conformance" / "dist" / "index.js"
EXPECTED = HIDDEN / "conformance_expected.json"
EXCLUDED = HIDDEN / "conformance_excluded.json"
# Scenarios never scored: optional extensions and a scenario that only probes the CLI's own fixture tool.
EXCLUDED_SCENARIOS_PREFIX = ("tasks-",)
EXCLUDED_SCENARIOS = {"json-schema-2020-12"}

PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


def offline_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
    env.update(npm_config_offline="true", npm_config_update_notifier="false", npm_config_fund="false",
               npm_config_audit="false", NO_UPDATE_NOTIFIER="1", NODE_NO_WARNINGS="1")
    env.update(extra)
    return env


def tail(s: str, n=3000) -> str:
    return s if len(s) <= n else "..." + s[-n:]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def prepare(repo: Path, work: Path):
    def ignore(d, names):
        return {n for n in names if n in ("node_modules", "dist", ".git", ".claude")} if Path(d) == repo else set()
    shutil.copytree(repo, work, symlinks=True, ignore=ignore)
    os.symlink(PRISTINE_NODE_MODULES, work / "node_modules")


def build(work: Path, logdir: Path):
    try:
        p = subprocess.run(["npm", "run", "build"], cwd=work, env=offline_env(), capture_output=True, text=True, timeout=300)
        out, rc = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        out, rc = f"timeout: {e}", -1
    (logdir / "build.log").write_text(out)
    return {"ok": rc == 0, "rc": rc, "log_tail": tail(out, 2000)}


class Server:
    def __init__(self, work: Path, logdir: Path, tag: str):
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        self.log = open(logdir / f"server-{tag}.log", "w")
        self.proc = subprocess.Popen(["npm", "start"], cwd=work, env=offline_env(PORT=str(self.port)),
                                     stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        self.started = self._wait()

    def _wait(self, timeout=20.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                return False
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(0.2)
        return False

    def stop(self):
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.proc.wait()
        self.log.close()


TS_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}T[\d-]+Z$")


def conformance(url: str, logdir: Path, record: bool):
    outdir = logdir / "conformance"
    cmd = ["node", str(CONFORMANCE_BIN), "server", "--url", url, "--requirements", "2026-07-28", "-o", str(outdir)]
    try:
        p = subprocess.run(cmd, env=offline_env(), capture_output=True, text=True, timeout=900)
        out, rc = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        out, rc = f"timeout: {e}", -1
    (logdir / "conformance.log").write_text(out)
    summary = [l for l in out.splitlines() if l.startswith("Total:")]

    # Collapse repeated check ids per scenario, most severe first.
    rank = {"FAILURE": 4, "SKIPPED": 3, "WARNING": 2, "SUCCESS": 1, "INFO": 0}
    verdict, messages = {}, {}
    for f in sorted(outdir.glob("server-*/checks.json")) if outdir.exists() else []:
        scenario = TS_SUFFIX.sub("", f.parent.name[len("server-"):])
        if scenario in EXCLUDED_SCENARIOS or scenario.startswith(EXCLUDED_SCENARIOS_PREFIX):
            continue
        for c in json.loads(f.read_text()):
            key = f"{scenario}:{c['id']}"
            st = c.get("status", "FAILURE")
            if st == "INFO":
                continue
            if rank.get(st, 4) >= rank.get(verdict.get(key, "INFO"), 0):
                verdict[key] = st
                messages[key] = (c.get("errorMessage") or "")[:300]

    if record:
        # wire-schema-valid in a scenario whose only substantive checks target the CLI's fixtures
        # validates nothing but an "unknown tool" error, so it is excluded as noise.
        substantive = {k.split(":", 1)[0] for k, v in verdict.items() if v == "SUCCESS" and not k.endswith(":wire-schema-valid")}
        noise = {k for k in verdict if k.endswith(":wire-schema-valid") and k.split(":", 1)[0] not in substantive}
        EXPECTED.write_text(json.dumps(sorted(k for k, v in verdict.items() if v == "SUCCESS" and k not in noise), indent=1) + "\n")
        EXCLUDED.write_text(json.dumps({k: {"status": v, "message": messages[k] if k not in noise else "wire-schema-valid of a fixture-only scenario"}
                                        for k, v in sorted(verdict.items()) if v != "SUCCESS" or k in noise}, indent=1) + "\n")

    expected = json.loads(EXPECTED.read_text()) if EXPECTED.exists() else []
    passed = [k for k in expected if verdict.get(k) in ("SUCCESS", "WARNING")]
    failed = {k: {"status": verdict.get(k, "MISSING"), "message": messages.get(k, "check not reached")} for k in expected if k not in passed}
    warnings = [k for k in expected if verdict.get(k) == "WARNING"]
    return {"cli": "@modelcontextprotocol/conformance@0.2.0-alpha.11", "args": "server --requirements 2026-07-28",
            "exit_code": rc, "raw_summary": summary[-1] if summary else None,
            "scored_total": len(expected), "passed": len(passed), "failed_count": len(failed), "failed": failed,
            "warnings": warnings, "ok": bool(expected) and not failed}


def hidden_tests(url: str, logdir: Path):
    tests = sorted(str(p) for p in (HIDDEN / "tests").glob("*.test.ts"))
    junit = logdir / "hidden-tests.xml"
    cmd = ["node", "--test", "--test-concurrency=1", "--test-timeout=30000", "--test-reporter=spec",
           "--test-reporter-destination=stdout", "--test-reporter=junit", f"--test-reporter-destination={junit}", *tests]
    try:
        p = subprocess.run(cmd, cwd=HIDDEN / "tests", env=offline_env(MCP_URL=url), capture_output=True, text=True, timeout=600)
        out = p.stdout + p.stderr
    except subprocess.TimeoutExpired as e:
        out = f"timeout: {e}"
    (logdir / "hidden-tests.log").write_text(out)
    cases = []
    if junit.exists():
        try:
            for tc in ET.parse(junit).getroot().iter("testcase"):
                bad = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
                cases.append({"name": tc.get("name"), "ok": bad is None and tc.find("skipped") is None,
                              "message": None if bad is None else (bad.get("message") or bad.text or "")[:400]})
        except ET.ParseError as e:
            out += f"\njunit parse error: {e}"
    by_cat = {}
    for c in cases:
        cat = c["name"].split(":", 1)[0] if ":" in c["name"] else "other"
        d = by_cat.setdefault(cat, {"total": 0, "passed": 0})
        d["total"] += 1
        d["passed"] += c["ok"]
    failed = [{"name": c["name"], "message": c["message"]} for c in cases if not c["ok"]]
    return {"total": len(cases), "passed": sum(c["ok"] for c in cases), "failed_count": len(failed),
            "by_category": by_cat, "failed": failed, "ok": bool(cases) and not failed}


def stale_check(src: Path, url: str | None, logdir: Path):
    cmd = [sys.executable, str(HIDDEN / "stale_api_check.py"), "--src", str(src)] + (["--url", url] if url else [])
    p = subprocess.run(cmd, env=offline_env(), capture_output=True, text=True, timeout=300)
    (logdir / "stale.json").write_text(p.stdout + p.stderr)
    try:
        d = json.loads(p.stdout)
    except ValueError:
        return {"ok": False, "error": tail(p.stdout + p.stderr, 1000)}
    dyn = d["dynamic"]
    return {"static_hits_count": d["static"]["count"], "static_hits": d["static"]["hits"],
            "dynamic_reachable": dyn.get("reachable"), "dynamic_hits_count": dyn.get("count"),
            "dynamic_hits": dyn.get("hits", []), "ok": dyn.get("reachable") is True and dyn.get("count") == 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--out")
    ap.add_argument("--record-expected", action="store_true")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    logdir = Path(a.out).resolve() if a.out else Path(tempfile.mkdtemp(prefix="grade-C-mcp-"))
    logdir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="grade-work-")) / "repo"
    t0 = time.time()
    res = {"task": "C-mcp", "repo": str(repo), "logs": str(logdir)}
    try:
        prepare(repo, work)
        res["build"] = build(work, logdir)
        phases = [("conformance", lambda url: conformance(url, logdir, a.record_expected)),
                  ("hidden_tests", lambda url: hidden_tests(url, logdir)),
                  ("stale_api", lambda url: stale_check(work / "src", url, logdir))]
        starts = {}
        for name, fn in phases:
            srv = Server(work, logdir, name)
            starts[name] = srv.started
            try:
                if srv.started:
                    res[name] = fn(srv.url)
                elif name == "stale_api":
                    res[name] = stale_check(work / "src", None, logdir)
                    res[name]["ok"] = False
                else:
                    res[name] = {"ok": False, "error": "server did not start (see server log)"}
            finally:
                srv.stop()
        res["server"] = {"started": all(starts.values()), "per_phase": starts}
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)
    checks = ["build", "conformance", "hidden_tests", "stale_api"]
    res["summary"] = {k: bool(res.get(k, {}).get("ok")) for k in checks}
    res["summary"]["server_started"] = res.get("server", {}).get("started", False)
    res["verdict"] = "PASS" if all(res["summary"].values()) else "FAIL"
    res["wall_s"] = round(time.time() - t0, 1)
    json.dump(res, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
