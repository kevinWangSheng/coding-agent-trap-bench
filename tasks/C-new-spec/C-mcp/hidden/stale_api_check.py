#!/usr/bin/env python3
"""Detect pre-2026-07-28 MCP artifacts ("stale API") in an implementation.

Usage: stale_api_check.py --src <repo>/src [--url http://127.0.0.1:PORT/mcp]

Two parts, both reported as a count plus a list of hits:

* static  - scans source files (comments stripped) for identifiers that the
            2026-07-28 changelog removed or renumbered. Mentions are not
            automatically wrong (e.g. code that explicitly rejects `initialize`
            is fine), so static hits are reported, not scored.
* dynamic - probes the live server and inspects raw HTTP responses for old-spec
            behavior (sessions, handshake, removed RPCs, GET stream, SSE event
            ids, old error codes, missing resultType, server-initiated requests).
            Dynamic hits are the scored signal; a conformant server has 0.

Every rule cites the changelog item (docs/mcp-spec-2026-07-28/changelog.md at
modelcontextprotocol/modelcontextprotocol@c7400a0796045cbf102cb80b9b41422c7ce8e7af).
Only the standard library is used; no network beyond the given local URL.
"""
import argparse
import http.client
import json
import os
import re
import socket
import sys
import time
import urllib.parse

PV = "2026-07-28"
SRC_EXT = {".ts", ".mts", ".cts", ".js", ".mjs", ".cjs"}

# (rule id, regex applied to comment-stripped source, changelog reference, note)
STATIC_RULES = [
    ("session-header", re.compile(r"mcp-session-id", re.I), "Major 1", "protocol-level sessions and Mcp-Session-Id removed"),
    ("initialize-handshake", re.compile(r"""["'`](initialize|notifications/initialized)["'`]|(?<![\w.$])initialize\s*[:(]"""), "Major 2", "initialize/notifications/initialized handshake removed"),
    ("ping", re.compile(r"""["'`]ping["'`]|(?<![\w.$])ping\s*:"""), "Major 5", "ping removed"),
    ("logging-setLevel", re.compile(r"logging/setLevel"), "Major 5", "logging/setLevel removed; log level is per-request _meta"),
    ("roots-list-changed", re.compile(r"notifications/roots/list_changed"), "Major 5", "notifications/roots/list_changed removed"),
    ("resources-subscribe", re.compile(r"resources/(un)?subscribe"), "Major 4", "replaced by subscriptions/listen"),
    ("last-event-id", re.compile(r"last-event-id", re.I), "Major 9", "SSE resumability removed"),
    ("tasks-core-methods", re.compile(r"tasks/(result|list)\b"), "Major 6", "tasks/result and tasks/list removed (tasks moved to an extension)"),
    ("elicitation-complete", re.compile(r"notifications/elicitation/complete|\belicitationId\b"), "Minor 11", "URL-elicitation completion notification removed"),
    ("resource-not-found-32002", re.compile(r"(?<![\d.])-?32002\b"), "Minor 6", "resource-not-found is -32602 now"),
    ("draft-error-codes", re.compile(r"(?<![\d.])-?320(01|03|04|42)\b"), "Minor 12 / basic#error-codes", "renumbered to -32020/-32021/-32022; -32042 must not be emitted"),
    ("legacy-protocol-version", re.compile(r"""["'`](2025-11-25|2025-06-18|2025-03-26|2024-11-05)["'`]"""), "versioning", "legacy protocol version string"),
]


def strip_comments(src: str) -> str:
    """Removes // and /* */ comments while keeping string/template literals (and line numbers)."""
    out = []
    i, n = 0, len(src)
    quote = None
    while i < n:
        c = src[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"`":
            quote = c
            out.append(c)
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            chunk = src[i : (n if j < 0 else j + 2)]
            out.append("\n" * chunk.count("\n"))
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def static_scan(src_dir: str):
    hits = []
    if not os.path.isdir(src_dir):
        return {"src": src_dir, "files_scanned": 0, "hits": [], "count": 0, "note": "src directory missing"}
    files = 0
    for root, dirs, names in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", ".git")]
        for name in sorted(names):
            if os.path.splitext(name)[1] not in SRC_EXT:
                continue
            path = os.path.join(root, name)
            files += 1
            try:
                text = strip_comments(open(path, encoding="utf-8", errors="replace").read())
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for rule, rx, ref, note in STATIC_RULES:
                    if rx.search(line):
                        hits.append({"rule": rule, "file": os.path.relpath(path, src_dir), "line": lineno,
                                     "code": line.strip()[:160], "changelog": ref, "why": note})
    return {"src": src_dir, "files_scanned": files, "count": len(hits), "hits": hits}


# ---------------- dynamic ----------------

def meta(caps=None, version=PV):
    return {"io.modelcontextprotocol/protocolVersion": version,
            "io.modelcontextprotocol/clientInfo": {"name": "stale-check", "version": "1"},
            "io.modelcontextprotocol/clientCapabilities": caps or {}}


class Probe:
    def __init__(self, url: str):
        u = urllib.parse.urlparse(url)
        self.host, self.port, self.path = u.hostname, u.port or 80, u.path or "/"
        self.log = []

    def request(self, http_method, body=None, headers=None, read_timeout=5.0, max_events=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=read_timeout)
        try:
            data = json.dumps(body).encode() if body is not None else None
            conn.request(http_method, self.path, body=data, headers=headers or {})
            resp = conn.getresponse()
            ctype = resp.getheader("content-type") or ""
            raw = b""
            if "text/event-stream" in ctype and max_events is not None:
                # Read a bounded number of events from a long-lived stream, then drop it.
                deadline = time.time() + read_timeout
                while raw.count(b"\n\n") < max_events and time.time() < deadline:
                    try:
                        chunk = resp.read1(4096)
                    except (socket.timeout, TimeoutError):
                        break
                    if not chunk:
                        break
                    raw += chunk
            else:
                try:
                    raw = resp.read()
                except (socket.timeout, TimeoutError, http.client.IncompleteRead) as e:
                    raw = getattr(e, "partial", b"") or raw
            rec = {"method": http_method, "req": body, "status": resp.status,
                   "headers": {k.lower(): v for k, v in resp.getheaders()}, "ctype": ctype,
                   "raw": raw.decode("utf-8", "replace")}
        except Exception as e:  # noqa: BLE001 - any transport failure is recorded
            rec = {"method": http_method, "req": body, "error": repr(e)}
        finally:
            conn.close()
        rec["messages"] = parse_messages(rec)
        self.log.append(rec)
        return rec

    def rpc(self, method, params=None, *, rid=None, headers=None, with_meta=True, caps=None, **kw):
        params = dict(params or {})
        if with_meta:
            params["_meta"] = {**meta(caps), **params.get("_meta", {})}
        body = {"jsonrpc": "2.0", "id": rid if rid is not None else f"stale-{len(self.log)}", "method": method, "params": params}
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
             "MCP-Protocol-Version": PV, "Mcp-Method": method}
        if method in ("tools/call", "prompts/get") and "name" in params:
            h["Mcp-Name"] = params["name"]
        if method == "resources/read" and "uri" in params:
            h["Mcp-Name"] = params["uri"]
        if method == "tools/call" and params.get("name") == "add_note":
            h["Mcp-Param-Notebook"] = str(params.get("arguments", {}).get("notebook", ""))
        for k, v in (headers or {}).items():
            for existing in [x for x in h if x.lower() == k.lower()]:
                del h[existing]
            if v is not None:
                h[k] = v
        return self.request("POST", body, h, **kw)


def parse_messages(rec):
    raw, ctype = rec.get("raw", ""), rec.get("ctype", "")
    if not raw.strip():
        return []
    if "text/event-stream" in ctype:
        out = []
        for block in re.split(r"\r?\n\r?\n", raw):
            data = [l[5:].lstrip(" ") for l in block.splitlines() if l.startswith("data:")]
            if data:
                try:
                    out.append(json.loads("\n".join(data)))
                except ValueError:
                    pass
        return out
    try:
        return [json.loads(raw)]
    except ValueError:
        return []


def dynamic_scan(url: str):
    p = Probe(url)
    hits = []

    def hit(rule, ref, why, rec):
        hits.append({"rule": rule, "changelog": ref, "why": why,
                     "request": (rec.get("req") or {}).get("method") if isinstance(rec.get("req"), dict) else rec.get("method"),
                     "status": rec.get("status"), "evidence": (rec.get("raw") or rec.get("error") or "")[:300]})

    # Reachability.
    first = p.rpc("server/discover")
    if "error" in first and "status" not in first:
        return {"url": url, "reachable": False, "count": None, "hits": [], "probes": 1, "note": first["error"]}

    # --- exercise the server (also used by the generic checks below) ---
    p.rpc("tools/list")
    p.rpc("resources/read", {"uri": "notes://index"})
    p.rpc("prompts/get", {"name": "summarize_notebook", "arguments": {"notebook": "work"}})
    p.rpc("tools/call", {"name": "reindex", "arguments": {"steps": 2, "delayMs": 0}, "_meta": {"progressToken": "stale-p"}})
    added = p.rpc("tools/call", {"name": "add_note", "arguments": {"notebook": "stale", "title": "s", "body": "b"}})
    note_id = None
    for m in added["messages"]:
        sc = (m.get("result") or {}).get("structuredContent") or {}
        note_id = sc.get("id") or note_id
    p.rpc("tools/call", {"name": "delete_note", "arguments": {"id": note_id or "n1"}}, caps={"elicitation": {}}, read_timeout=3.0)
    p.request("POST", {"jsonrpc": "2.0", "id": "stale-listen", "method": "subscriptions/listen",
                       "params": {"_meta": meta(), "notifications": {"resourceSubscriptions": ["notes://index"]}}},
              {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": PV, "Mcp-Method": "subscriptions/listen"}, read_timeout=1.5, max_events=1)

    # --- legacy probes ---
    legacy_init = {"jsonrpc": "2.0", "id": "stale-init", "method": "initialize",
                   "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "old", "version": "1"}}}
    rec = p.request("POST", legacy_init, {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    if any("result" in m for m in rec["messages"]):
        hit("initialize-handshake", "Major 2", "legacy initialize (no _meta, no version header) succeeded", rec)
    rec = p.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "old", "version": "1"}})
    if any("result" in m for m in rec["messages"]):
        hit("initialize-handshake", "Major 2", "initialize with modern _meta succeeded", rec)
    for method, params, ref in [("ping", {}, "Major 5"), ("logging/setLevel", {"level": "info"}, "Major 5"),
                                ("resources/subscribe", {"uri": "notes://index"}, "Major 4"),
                                ("resources/unsubscribe", {"uri": "notes://index"}, "Major 4")]:
        rec = p.rpc(method, params)
        if any("result" in m for m in rec["messages"]):
            hit(method.replace("/", "-"), ref, f"removed RPC {method} still answered with a result", rec)
    rec = p.request("GET", None, {"Accept": "text/event-stream", "MCP-Protocol-Version": PV}, read_timeout=1.5, max_events=1)
    if rec.get("status") == 200 or "text/event-stream" in rec.get("ctype", ""):
        hit("get-sse-endpoint", "Major 4", "HTTP GET on the MCP endpoint still opens/serves a stream", rec)
    rec = p.request("DELETE", None, {"Mcp-Session-Id": "stale-session", "MCP-Protocol-Version": PV})
    if 200 <= (rec.get("status") or 0) < 300:
        hit("session-delete", "Major 1", "HTTP DELETE (session termination) accepted", rec)
    p.rpc("tools/list", headers={"Mcp-Session-Id": "stale-session", "Last-Event-ID": "1"})
    rec = p.rpc("resources/read", {"uri": "notes://notes/does-not-exist"})
    # Error-code probes: header mismatch, missing capability, unsupported version.
    p.rpc("tools/list", headers={"Mcp-Method": "prompts/list"})
    p.rpc("tools/call", {"name": "delete_note", "arguments": {"id": "n1"}}, caps={})
    p.rpc("tools/list", {"_meta": {"io.modelcontextprotocol/protocolVersion": "1900-01-01"}}, headers={"MCP-Protocol-Version": "1900-01-01"})

    # --- generic checks over every recorded exchange ---
    for rec in p.log:
        if "mcp-session-id" in rec.get("headers", {}):
            hit("session-header", "Major 1", "response carries Mcp-Session-Id", rec)
        if "text/event-stream" in rec.get("ctype", "") and re.search(r"(?m)^id:", rec.get("raw", "")):
            hit("sse-event-id", "Major 9", "SSE events carry id: fields (resumability removed)", rec)
        for m in rec["messages"]:
            if not isinstance(m, dict):
                continue
            if "method" in m and "id" in m:
                hit("server-initiated-request", "Major 7", f"server sent JSON-RPC request {m.get('method')} on a stream (use MRTR input_required)", rec)
            err = m.get("error")
            if isinstance(err, dict) and err.get("code") in (-32002, -32001, -32003, -32004, -32042):
                hit("old-error-code", "Minor 6 / Minor 12", f"old error code {err.get('code')}", rec)
            res = m.get("result")
            if isinstance(res, dict):
                if "resultType" not in res:
                    hit("missing-resultType", "Major 8", "result without resultType", rec)
                req_method = (rec.get("req") or {}).get("method") if isinstance(rec.get("req"), dict) else None
                if req_method == "server/discover" and ("protocolVersion" in res or "serverInfo" in res):
                    hit("initialize-result-shape", "Major 2", "discover result uses InitializeResult fields (protocolVersion/serverInfo at top level)", rec)
    return {"url": url, "reachable": True, "probes": len(p.log), "count": len(hits), "hits": hits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--url")
    a = ap.parse_args()
    out = {"static": static_scan(a.src)}
    out["dynamic"] = dynamic_scan(a.url) if a.url else {"reachable": None, "count": None, "hits": [], "note": "no --url given"}
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
