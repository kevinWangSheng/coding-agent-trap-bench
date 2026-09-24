// Protocol behaviors specific to MCP 2026-07-28, asserted directly.
import { test } from "node:test";
import assert from "node:assert/strict";
import { PORT, PV, URL_, baseMeta, buildRequest, encodeHeader, post, result, rpc, type Msg } from "./lib.ts";

const T = { timeout: 20_000 };

test("spec: every result carries resultType complete", T, async () => {
  const calls: Array<[string, Msg]> = [
    ["server/discover", {}],
    ["tools/list", {}],
    ["resources/list", {}],
    ["resources/templates/list", {}],
    ["resources/read", { uri: "notes://index" }],
    ["prompts/list", {}],
    ["prompts/get", { name: "summarize_notebook", arguments: { notebook: "work" } }],
    ["tools/call", { name: "reindex", arguments: { steps: 1, delayMs: 0 } }],
  ];
  for (const [m, p] of calls) {
    const r = await result(m, p);
    assert.equal(r.resultType, "complete", m);
  }
});

test("spec: discover identifies the server in _meta serverInfo", T, async () => {
  for (const m of ["server/discover"]) {
    const r = await result(m);
    assert.deepEqual(r._meta?.["io.modelcontextprotocol/serverInfo"], { name: "field-notes", version: "1.0.0" }, m);
  }
});

test("spec: discover has no legacy initialize-result fields", T, async () => {
  const r = await result("server/discover");
  assert.equal(r.protocolVersion, undefined, "top-level protocolVersion is the old InitializeResult shape");
  assert.equal(r.serverInfo, undefined, "top-level serverInfo is the old InitializeResult shape");
});

test("spec: cacheable results carry ttlMs/cacheScope per README policy", T, async () => {
  for (const m of ["server/discover", "tools/list", "prompts/list", "resources/list", "resources/templates/list"]) {
    const r = await result(m);
    assert.equal(r.ttlMs, 300000, `${m} ttlMs`);
    assert.equal(r.cacheScope, "public", `${m} cacheScope`);
  }
  for (const uri of ["notes://index", "notes://notes/n1"]) {
    const r = await result("resources/read", { uri });
    assert.equal(r.ttlMs, 0, `${uri} ttlMs`);
    assert.equal(r.cacheScope, "private", `${uri} cacheScope`);
  }
});

test("spec: tools/list order is deterministic", T, async () => {
  const a = await result("tools/list");
  const b = await result("tools/list");
  assert.deepEqual(a.tools, b.tools);
});

test("spec: missing required _meta fields -> 400 / -32602", T, async () => {
  const variants: Array<[string, RpcMeta]> = [
    ["no _meta", { noMeta: true }],
    ["no protocolVersion", { meta: { "io.modelcontextprotocol/clientCapabilities": {} } }],
    ["no clientCapabilities", { meta: { "io.modelcontextprotocol/protocolVersion": PV } }],
  ];
  for (const [label, opts] of variants) {
    const r = await rpc("tools/list", {}, opts);
    assert.equal(r.status, 400, label);
    assert.equal(r.response?.error?.code, -32602, label);
  }
});
type RpcMeta = { noMeta?: boolean; meta?: Msg };

test("spec: clientInfo is optional", T, async () => {
  const r = await rpc("tools/list", {}, { meta: { "io.modelcontextprotocol/protocolVersion": PV, "io.modelcontextprotocol/clientCapabilities": {} } });
  assert.equal(r.status, 200);
  assert.ok(r.response?.result);
});

test("spec: unsupported protocol version -> 400 / -32022 with supported list", T, async () => {
  for (const v of ["2025-11-25", "1900-01-01"]) {
    const r = await rpc("tools/list", {}, { meta: { ...baseMeta(), "io.modelcontextprotocol/protocolVersion": v }, headers: { "MCP-Protocol-Version": v } });
    assert.equal(r.status, 400, v);
    assert.equal(r.response?.error?.code, -32022, v);
    assert.ok(r.response?.error?.data?.supported?.includes(PV), v);
    assert.equal(r.response?.error?.data?.requested, v);
  }
});

test("spec: MCP-Protocol-Version header missing or mismatched -> 400 / -32020", T, async () => {
  const missing = await rpc("tools/list", {}, { headers: { "MCP-Protocol-Version": undefined } });
  assert.equal(missing.status, 400);
  assert.equal(missing.response?.error?.code, -32020);
  const mismatch = await rpc("tools/list", {}, { headers: { "MCP-Protocol-Version": "2025-11-25" } });
  assert.equal(mismatch.status, 400);
  assert.equal(mismatch.response?.error?.code, -32020);
});

test("spec: Mcp-Method header missing or mismatched -> 400 / -32020", T, async () => {
  const missing = await rpc("tools/list", {}, { headers: { "Mcp-Method": undefined } });
  assert.equal(missing.status, 400);
  assert.equal(missing.response?.error?.code, -32020);
  const mismatch = await rpc("tools/list", {}, { headers: { "Mcp-Method": "prompts/list" } });
  assert.equal(mismatch.status, 400);
  assert.equal(mismatch.response?.error?.code, -32020);
});

test("spec: Mcp-Name required and validated for tools/call, prompts/get, resources/read", T, async () => {
  const cases: Array<[string, Msg, string]> = [
    ["tools/call", { name: "reindex", arguments: { steps: 1, delayMs: 0 } }, "add_note"],
    ["prompts/get", { name: "summarize_notebook", arguments: { notebook: "work" } }, "other"],
    ["resources/read", { uri: "notes://index" }, "notes://notes/n1"],
  ];
  for (const [m, p, wrong] of cases) {
    const missing = await rpc(m, p, { headers: { "Mcp-Name": undefined } });
    assert.equal(missing.status, 400, `${m} missing`);
    assert.equal(missing.response?.error?.code, -32020, `${m} missing`);
    const mism = await rpc(m, p, { headers: { "Mcp-Name": wrong } });
    assert.equal(mism.status, 400, `${m} mismatch`);
    assert.equal(mism.response?.error?.code, -32020, `${m} mismatch`);
  }
});

test("spec: base64-encoded Mcp-Name is decoded before comparison", T, async () => {
  const b64 = `=?base64?${Buffer.from("reindex").toString("base64")}?=`;
  const r = await rpc("tools/call", { name: "reindex", arguments: { steps: 1, delayMs: 0 } }, { headers: { "Mcp-Name": b64 } });
  assert.equal(r.status, 200, r.raw.slice(0, 200));
  assert.equal(r.response?.result?.resultType, "complete");
});

test("spec: Mcp-Param-Notebook must be present and match the body", T, async () => {
  const args = { notebook: "hdr", title: "t", body: "b" };
  const missing = await rpc("tools/call", { name: "add_note", arguments: args }, { headers: { "Mcp-Param-Notebook": undefined } });
  assert.equal(missing.status, 400);
  assert.equal(missing.response?.error?.code, -32020);
  const mism = await rpc("tools/call", { name: "add_note", arguments: args }, { headers: { "Mcp-Param-Notebook": "other" } });
  assert.equal(mism.status, 400);
  assert.equal(mism.response?.error?.code, -32020);
  const lower = await rpc("tools/call", { name: "add_note", arguments: args }, { headers: { "Mcp-Param-Notebook": undefined, "mcp-param-notebook": "hdr" } });
  assert.equal(lower.status, 200, "header names are case-insensitive");
  assert.ok(lower.response?.result && !lower.response.result.isError);
});

test("spec: Mcp-Param-Notebook base64 values are decoded before comparison", T, async () => {
  const ok = await rpc(
    "tools/call",
    { name: "add_note", arguments: { notebook: "b64nb", title: "t", body: "b" } },
    { headers: { "Mcp-Param-Notebook": `=?base64?${Buffer.from("b64nb").toString("base64")}?=` } },
  );
  assert.equal(ok.status, 200, ok.raw.slice(0, 200));
  assert.ok(ok.response?.result && !ok.response.result.isError);
  // Non-ASCII value must travel base64-encoded; header matches, then app validation rejects the name.
  const cafe = await rpc("tools/call", { name: "add_note", arguments: { notebook: "Café", title: "t", body: "b" } });
  assert.equal(cafe.status, 200, cafe.raw.slice(0, 200));
  assert.equal(cafe.response?.result?.isError, true);
  const wrong = await rpc(
    "tools/call",
    { name: "add_note", arguments: { notebook: "Café", title: "t", body: "b" } },
    { headers: { "Mcp-Param-Notebook": encodeHeader("Cafe") } },
  );
  assert.equal(wrong.status, 400);
  assert.equal(wrong.response?.error?.code, -32020);
});

test("spec: removed methods are unknown (404 / -32601)", T, async () => {
  const legacy: Array<[string, Msg]> = [
    ["initialize", { protocolVersion: "2025-11-25", capabilities: {}, clientInfo: { name: "old", version: "1" } }],
    ["ping", {}],
    ["logging/setLevel", { level: "info" }],
    ["resources/subscribe", { uri: "notes://index" }],
    ["resources/unsubscribe", { uri: "notes://index" }],
  ];
  for (const [m, p] of legacy) {
    const r = await rpc(m, p);
    assert.equal(r.status, 404, m);
    assert.equal(r.response?.error?.code, -32601, m);
  }
});

test("spec: errors preserve the request id", T, async () => {
  const r = await rpc("ping", {}, { id: "keep-me" });
  assert.equal(r.response?.id, "keep-me");
  const r2 = await rpc("tools/list", {}, { id: 31337, noMeta: true });
  assert.equal(r2.response?.id, 31337);
});

test("spec: no GET/DELETE endpoint (405)", T, async () => {
  for (const method of ["GET", "DELETE"]) {
    const res = await fetch(URL_, { method, headers: { Accept: "text/event-stream", "MCP-Protocol-Version": PV } });
    await res.text().catch(() => "");
    assert.equal(res.status, 405, method);
    assert.ok(!(res.headers.get("content-type") ?? "").includes("text/event-stream"), `${method} must not open a stream`);
  }
});

test("spec: Mcp-Session-Id is ignored and never issued", T, async () => {
  const r = await rpc("tools/list", {}, { headers: { "Mcp-Session-Id": "legacy-session-123" } });
  assert.equal(r.status, 200);
  assert.ok(r.response?.result);
  assert.equal(r.headers.get("mcp-session-id"), null);
  const d = await rpc("server/discover");
  assert.equal(d.headers.get("mcp-session-id"), null);
});

test("spec: Last-Event-ID is ignored", T, async () => {
  const r = await rpc("tools/list", {}, { headers: { "Last-Event-ID": "5" } });
  assert.equal(r.status, 200);
  assert.ok(r.response?.result);
});

test("spec: Origin validation (403 for foreign origins)", T, async () => {
  const evil = await rpc("tools/list", {}, { headers: { Origin: "http://evil.example.com" } });
  assert.equal(evil.status, 403);
  for (const origin of [`http://localhost:${PORT}`, `http://127.0.0.1:${PORT}`]) {
    const ok = await rpc("tools/list", {}, { headers: { Origin: origin } });
    assert.equal(ok.status, 200, origin);
  }
});

test("spec: client notifications are accepted with 202 and no body", T, async () => {
  const res = await fetch(URL_, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream", "MCP-Protocol-Version": PV, "Mcp-Method": "notifications/cancelled" },
    body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/cancelled", params: { requestId: 1, reason: "test" } }),
  });
  assert.equal(res.status, 202);
  assert.equal((await res.text()).trim(), "");
});

test("spec: no log notifications without a requested logLevel", T, async () => {
  const r = await rpc("tools/call", { name: "reindex", arguments: { steps: 2, delayMs: 0 }, _meta: { progressToken: "nolog" } });
  assert.ok(!r.messages.some((m) => m.method === "notifications/message"));
});

test("spec: server sends no JSON-RPC requests on response streams", T, async () => {
  const r = await rpc("tools/call", { name: "reindex", arguments: { steps: 2, delayMs: 0 }, _meta: { progressToken: "noreq" } });
  assert.ok(!r.messages.some((m) => "method" in m && "id" in m), JSON.stringify(r.messages).slice(0, 300));
});

test("spec: malformed JSON is a parse error", T, async () => {
  const { headers } = buildRequest("tools/list");
  const r = await post(headers, "{not json");
  assert.equal(r.messages[0]?.error?.code, -32700);
});
