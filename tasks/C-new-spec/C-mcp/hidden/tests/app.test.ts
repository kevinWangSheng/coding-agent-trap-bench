// Application features described in repo/README.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  Stream,
  addNote,
  callTool,
  confirmDelete,
  readResource,
  result,
  rpc,
  sleep,
  textOf,
  type Msg,
} from "./lib.ts";

const T = { timeout: 20_000 };
const uniq = (p: string) => `${p}${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
const SEEDS = [
  { id: "n1", notebook: "work", title: "Standup", body: "Discussed the release schedule and blockers." },
  { id: "n2", notebook: "work", title: "Retro actions", body: "Automate the changelog. Rotate the on-call." },
  { id: "n3", notebook: "personal", title: "Groceries", body: "Eggs, flour, coffee." },
];

// Compare only the fields the README specifies; extra optional fields (e.g. _meta, annotations) are allowed.
const pickContents = (c: Msg) => ({ uri: c.uri, mimeType: c.mimeType, text: c.text });
function pickMessage(m: Msg): Msg {
  const c = m.content ?? {};
  if (c.type === "text") return { role: m.role, content: { type: "text", text: c.text } };
  if (c.type === "resource") return { role: m.role, content: { type: "resource", resource: pickContents(c.resource ?? {}) } };
  return { role: m.role, content: { type: c.type } };
}

async function indexNotes(): Promise<Msg[]> {
  const res = await result("resources/read", { uri: "notes://index" });
  return JSON.parse(res.contents[0].text);
}

test("app: discover identifies field-notes 1.0.0 with instructions and capabilities", T, async () => {
  const r = await result("server/discover");
  assert.ok(Array.isArray(r.supportedVersions) && r.supportedVersions.includes("2026-07-28"));
  assert.deepEqual(r._meta?.["io.modelcontextprotocol/serverInfo"]?.name, "field-notes");
  assert.deepEqual(r._meta?.["io.modelcontextprotocol/serverInfo"]?.version, "1.0.0");
  assert.equal(
    r.instructions,
    "Field Notes stores short notes grouped into notebooks. Use add_note to save a note, read notes://index to see what exists.",
  );
  assert.ok(r.capabilities?.tools, "tools capability");
  assert.ok(r.capabilities?.prompts, "prompts capability");
  assert.equal(r.capabilities?.resources?.subscribe, true, "resources.subscribe");
});

test("app: tools/list returns the three tools alphabetically with schemas", T, async () => {
  const r = await result("tools/list");
  assert.deepEqual(r.tools.map((t: Msg) => t.name), ["add_note", "delete_note", "reindex"]);
  const add = r.tools[0];
  assert.equal(add.inputSchema?.type, "object");
  assert.deepEqual([...(add.inputSchema?.required ?? [])].sort(), ["body", "notebook", "title"]);
  assert.equal(add.outputSchema?.type, "object", "add_note declares an output schema");
  for (const k of ["id", "uri", "notebook", "wordCount"]) assert.ok(add.outputSchema.properties?.[k], `outputSchema.${k}`);
  const del = r.tools[1];
  assert.deepEqual(del.inputSchema?.required, ["id"]);
  const re = r.tools[2];
  assert.ok(re.inputSchema?.properties?.steps && re.inputSchema?.properties?.delayMs);
});

test("app: add_note exposes notebook via x-mcp-header Notebook", T, async () => {
  const r = await result("tools/list");
  const add = r.tools.find((t: Msg) => t.name === "add_note");
  assert.equal(add.inputSchema.properties.notebook["x-mcp-header"], "Notebook");
  for (const [k, v] of Object.entries(add.inputSchema.properties as Record<string, Msg>)) {
    if (k !== "notebook") assert.equal(v["x-mcp-header"], undefined, `${k} must not be a header`);
  }
});

test("app: add_note returns structured output matching its schema plus JSON text", T, async () => {
  const nb = uniq("s");
  const r = await result("tools/call", { name: "add_note", arguments: { notebook: nb, title: "Words", body: " one two\tthree\nfour  " } });
  assert.equal(r.resultType, "complete");
  assert.ok(!r.isError);
  const sc = r.structuredContent;
  assert.match(sc.id, /^n\d+$/);
  assert.deepEqual(sc, { id: sc.id, uri: `notes://notes/${sc.id}`, notebook: nb, wordCount: 4 });
  const textBlock = r.content.find((c: Msg) => c.type === "text");
  assert.ok(textBlock, "text content block present");
  assert.deepEqual(JSON.parse(textBlock.text), sc);
  const empty = await result("tools/call", { name: "add_note", arguments: { notebook: nb, title: "Empty", body: "" } });
  assert.equal(empty.structuredContent.wordCount, 0);
});

test("app: add_note ids are sequential and never reused", T, async () => {
  const nb = uniq("seq");
  const a = await addNote(nb, "a", "x");
  const b = await addNote(nb, "b", "x");
  const na = Number(a.id.slice(1));
  const nbb = Number(b.id.slice(1));
  assert.ok(nbb > na, "later note gets a larger id");
  await confirmDelete(b.id);
  const c = await addNote(nb, "c", "x");
  assert.ok(Number(c.id.slice(1)) > nbb, "deleted ids are not reused");
});

test("app: add_note invalid arguments are tool execution errors", T, async () => {
  const cases: Msg[] = [
    { notebook: "work", title: "", body: "x" },
    { notebook: "work", body: "x" },
    { notebook: "bad name!", title: "t", body: "x" },
    { notebook: "work", title: "x".repeat(201), body: "x" },
    { notebook: "work", title: "t", body: 42 },
  ];
  for (const args of cases) {
    const r = await callTool("add_note", args);
    assert.ok(r.response && "result" in r.response, `result (not protocol error) for ${JSON.stringify(args).slice(0, 80)}: ${r.raw.slice(0, 200)}`);
    assert.equal(r.response.result.isError, true, `isError for ${JSON.stringify(args).slice(0, 80)}`);
    assert.ok(textOf(r.response.result).length > 0, "has an explanatory message");
  }
  const ok = await callTool("add_note", { notebook: "work", title: "x".repeat(200), body: "" });
  assert.notEqual(ok.response?.result?.isError, true, "200-char title is allowed");
});

test("app: unknown tool is a protocol error -32602", T, async () => {
  const r = await callTool("no_such_tool", {});
  assert.equal(r.response?.error?.code, -32602);
});

test("app: reindex reports progress on the request's stream", T, async () => {
  const r = await rpc("tools/call", { name: "reindex", arguments: { steps: 4, delayMs: 20 }, _meta: { progressToken: "tok-1" } });
  assert.ok(r.contentType.includes("text/event-stream"), `progress needs an SSE response, got ${r.contentType}`);
  const progress = r.messages.filter((m) => m.method === "notifications/progress");
  assert.equal(progress.length, 4);
  progress.forEach((m, i) => {
    assert.equal(m.params.progressToken, "tok-1");
    assert.equal(m.params.progress, i + 1);
    assert.equal(m.params.total, 4);
    assert.equal(m.params.message, `Indexed ${i + 1}/4`);
    assert.equal(m.id, undefined, "notification has no id");
  });
  const respIdx = r.messages.findIndex((m) => m === r.response);
  assert.ok(respIdx > r.messages.indexOf(progress[3]!), "final response comes after progress");
  assert.equal(r.response?.result?.resultType, "complete");
  assert.equal(textOf(r.response!.result), "Reindex complete: 4 steps");
});

test("app: reindex numeric progress token and defaults", T, async () => {
  const r = await rpc("tools/call", { name: "reindex", arguments: { delayMs: 0 }, _meta: { progressToken: 77 } });
  const progress = r.messages.filter((m) => m.method === "notifications/progress");
  assert.equal(progress.length, 5, "default steps is 5");
  assert.ok(progress.every((m) => m.params.progressToken === 77 && m.params.total === 5));
  assert.equal(textOf(r.response!.result), "Reindex complete: 5 steps");
});

test("app: reindex without a progress token sends no progress", T, async () => {
  const r = await rpc("tools/call", { name: "reindex", arguments: { steps: 2, delayMs: 0 } });
  assert.equal(r.messages.filter((m) => m.method === "notifications/progress").length, 0);
  assert.equal(textOf(r.response!.result), "Reindex complete: 2 steps");
});

test("app: reindex out-of-range arguments are tool execution errors", T, async () => {
  for (const args of [{ steps: 0 }, { steps: 21 }, { steps: 2.5 }, { delayMs: 1001 }, { delayMs: -1 }]) {
    const r = await callTool("reindex", { ...args, ...(args.delayMs === undefined ? { delayMs: 0 } : {}) });
    assert.equal(r.response?.result?.isError, true, JSON.stringify(args));
  }
});

test("app: resources/list returns only notes://index", T, async () => {
  const r = await result("resources/list");
  assert.equal(r.resources.length, 1);
  const [res] = r.resources;
  assert.equal(res.uri, "notes://index");
  assert.equal(res.name, "index");
  assert.equal(res.title, "All notes");
  assert.equal(res.mimeType, "application/json");
});

test("app: resources/templates/list returns the note template", T, async () => {
  const r = await result("resources/templates/list");
  assert.equal(r.resourceTemplates.length, 1);
  const [t] = r.resourceTemplates;
  assert.equal(t.uriTemplate, "notes://notes/{id}");
  assert.equal(t.name, "note");
  assert.equal(t.title, "A single note");
  assert.equal(t.mimeType, "text/markdown");
});

test("app: notes://index lists notes by numeric id with seeds", T, async () => {
  const nb = uniq("idx");
  // Make sure ids reach two digits so numeric vs lexical order matters.
  for (let i = 0; i < 10; i++) await addNote(nb, `t${i}`, "b");
  const res = await result("resources/read", { uri: "notes://index" });
  assert.equal(res.contents.length, 1);
  assert.equal(res.contents[0].uri, "notes://index");
  assert.equal(res.contents[0].mimeType, "application/json");
  const notes: Msg[] = JSON.parse(res.contents[0].text);
  for (const s of SEEDS) {
    const found = notes.find((n) => n.id === s.id);
    if (found) assert.deepEqual(found, { id: s.id, notebook: s.notebook, title: s.title });
  }
  assert.deepEqual(notes.slice(0, 1), [{ id: "n1", notebook: "work", title: "Standup" }]);
  const nums = notes.map((n) => Number(String(n.id).slice(1)));
  assert.deepEqual(nums, [...nums].sort((a, b) => a - b), "numeric id order");
  for (const n of notes) assert.deepEqual(Object.keys(n).sort(), ["id", "notebook", "title"]);
});

test("app: reading a note returns markdown", T, async () => {
  const res = await result("resources/read", { uri: "notes://notes/n1" });
  assert.deepEqual(res.contents.map(pickContents), [
    { uri: "notes://notes/n1", mimeType: "text/markdown", text: "# Standup\n\nDiscussed the release schedule and blockers.\n" },
  ]);
  const nb = uniq("md");
  const n = await addNote(nb, "Multi", "line one\nline two");
  const r2 = await result("resources/read", { uri: n.uri });
  assert.equal(r2.contents[0].text, "# Multi\n\nline one\nline two\n");
});

test("app: reading a missing note is -32602 (not the old -32002)", T, async () => {
  for (const uri of ["notes://notes/n999999", "notes://nope", "file:///etc/passwd"]) {
    const r = await readResource(uri);
    assert.equal(r.response?.error?.code, -32602, `${uri}: ${r.raw.slice(0, 200)}`);
  }
});

test("app: prompts/list describes summarize_notebook", T, async () => {
  const r = await result("prompts/list");
  assert.equal(r.prompts.length, 1);
  const [p] = r.prompts;
  assert.equal(p.name, "summarize_notebook");
  const nb = p.arguments.find((a: Msg) => a.name === "notebook");
  const st = p.arguments.find((a: Msg) => a.name === "style");
  assert.equal(nb?.required, true);
  assert.ok(st && st.required !== true);
});

test("app: summarize_notebook embeds the notebook's notes", T, async () => {
  const nb = uniq("p");
  const a = await addNote(nb, "Alpha", "first body");
  const b = await addNote(nb, "Beta", "second body");
  await addNote(uniq("other"), "Other", "not included");
  const r = await result("prompts/get", { name: "summarize_notebook", arguments: { notebook: nb } });
  assert.equal(r.resultType, "complete");
  assert.deepEqual(r.messages.map(pickMessage), [
    { role: "user", content: { type: "text", text: `Summarize the notes in the "${nb}" notebook in two sentences.` } },
    { role: "user", content: { type: "resource", resource: { uri: a.uri, mimeType: "text/markdown", text: "# Alpha\n\nfirst body\n" } } },
    { role: "user", content: { type: "resource", resource: { uri: b.uri, mimeType: "text/markdown", text: "# Beta\n\nsecond body\n" } } },
  ]);
});

test("app: summarize_notebook detailed style and empty notebook", T, async () => {
  const r = await result("prompts/get", { name: "summarize_notebook", arguments: { notebook: "personal", style: "detailed" } });
  assert.deepEqual(pickMessage(r.messages[0]), {
    role: "user",
    content: { type: "text", text: 'Summarize the notes in the "personal" notebook in detail, one paragraph per note.' },
  });
  assert.equal(r.messages[1]?.content?.resource?.uri, "notes://notes/n3");
  const empty = await result("prompts/get", { name: "summarize_notebook", arguments: { notebook: uniq("empty") } });
  assert.equal(empty.messages.length, 1);
});

test("app: summarize_notebook invalid arguments are -32602", T, async () => {
  const bad = await rpc("prompts/get", { name: "summarize_notebook", arguments: { notebook: "work", style: "haiku" } });
  assert.equal(bad.response?.error?.code, -32602);
  const missing = await rpc("prompts/get", { name: "summarize_notebook", arguments: {} });
  assert.equal(missing.response?.error?.code, -32602);
  const unknown = await rpc("prompts/get", { name: "nope", arguments: {} });
  assert.equal(unknown.response?.error?.code, -32602);
});

// ---------- delete_note: multi round-trip confirmation ----------

test("app: delete_note asks for confirmation with an input_required result", T, async () => {
  const n = await addNote(uniq("del"), "Doomed", "bye");
  const r = await result("tools/call", { name: "delete_note", arguments: { id: n.id } }, { caps: { elicitation: {} } });
  assert.equal(r.resultType, "input_required");
  const keys = Object.keys(r.inputRequests ?? {});
  assert.equal(keys.length, 1, "exactly one input request");
  const req = r.inputRequests[keys[0]!];
  assert.equal(req.method, "elicitation/create");
  assert.ok(req.params.mode === undefined || req.params.mode === "form");
  assert.equal(req.params.message, 'Delete note "Doomed"?');
  const schema = req.params.requestedSchema;
  assert.equal(schema.type, "object");
  assert.equal(schema.properties?.confirm?.type, "boolean");
  assert.ok(schema.required?.includes("confirm"));
  assert.equal(typeof r.requestState, "string", "server keeps no per-request state, so it must hand back requestState");
  assert.equal(r.ttlMs, undefined, "interim results carry no caching hints");
  // Nothing was deleted yet.
  assert.equal((await readResource(n.uri)).response?.result?.contents?.[0]?.text, "# Doomed\n\nbye\n");
});

test("app: delete_note deletes after the user accepts", T, async () => {
  const n = await addNote(uniq("del"), "Gone", "bye");
  const r = await confirmDelete(n.id);
  assert.equal(r.resultType, "complete");
  assert.notEqual(r.isError, true);
  assert.equal(textOf(r), `Deleted note ${n.id}`);
  assert.equal((await readResource(n.uri)).response?.error?.code, -32602);
  assert.ok(!(await indexNotes()).some((x) => x.id === n.id));
});

test("app: delete_note decline, cancel or confirm:false keeps the note", T, async () => {
  for (const answer of [
    { action: "decline" },
    { action: "cancel" },
    { action: "accept", content: { confirm: false } },
  ]) {
    const n = await addNote(uniq("keep"), "Kept", "still here");
    const r = await confirmDelete(n.id, answer);
    assert.equal(r.resultType, "complete");
    assert.notEqual(r.isError, true, JSON.stringify(answer));
    assert.equal(textOf(r), "Deletion cancelled", JSON.stringify(answer));
    assert.ok((await readResource(n.uri)).response?.result, `note survives ${JSON.stringify(answer)}`);
  }
});

test("app: delete_note on a missing note is a tool execution error", T, async () => {
  const r = await callTool("delete_note", { id: "n999999" }, { caps: { elicitation: {} } });
  assert.equal(r.response?.result?.isError, true);
  assert.equal(textOf(r.response!.result), "Note n999999 not found");
});

test("app: delete_note without elicitation capability is -32021 (HTTP 400)", T, async () => {
  const n = await addNote(uniq("cap"), "NoCap", "x");
  const r = await callTool("delete_note", { id: n.id }, { caps: {} });
  assert.equal(r.status, 400);
  assert.equal(r.response?.error?.code, -32021);
  const req = r.response?.error?.data?.requiredCapabilities;
  assert.ok(req && typeof req === "object" && !Array.isArray(req) && "elicitation" in req, JSON.stringify(req));
  assert.ok((await readResource(n.uri)).response?.result, "note not deleted");
});

test("app: a confirmation for one note cannot delete another", T, async () => {
  const caps = { elicitation: {} };
  const a = await addNote(uniq("bind"), "A", "a");
  const b = await addNote(uniq("bind"), "B", "b");
  const first = await result("tools/call", { name: "delete_note", arguments: { id: a.id } }, { caps });
  const key = Object.keys(first.inputRequests)[0]!;
  const r = await rpc(
    "tools/call",
    { name: "delete_note", arguments: { id: b.id }, inputResponses: { [key]: { action: "accept", content: { confirm: true } } }, requestState: first.requestState },
    { caps },
  );
  assert.ok(!(r.response?.result && textOf(r.response.result).startsWith("Deleted")), r.raw.slice(0, 300));
  assert.ok((await readResource(a.uri)).response?.result, "A survives");
  assert.ok((await readResource(b.uri)).response?.result, "B survives");
});

test("app: a tampered or forged requestState is rejected", T, async () => {
  const caps = { elicitation: {} };
  const n = await addNote(uniq("tamper"), "T", "t");
  const first = await result("tools/call", { name: "delete_note", arguments: { id: n.id } }, { caps });
  const key = Object.keys(first.inputRequests)[0]!;
  const s: string = first.requestState;
  const mid = Math.floor(s.length / 2);
  const tampered = s.slice(0, mid) + (s[mid] === "A" ? "B" : "A") + s.slice(mid + 1);
  for (const state of [tampered, "forged", Buffer.from(JSON.stringify({ id: n.id, noteId: n.id, confirmed: true })).toString("base64")]) {
    const r = await rpc(
      "tools/call",
      { name: "delete_note", arguments: { id: n.id }, inputResponses: { [key]: { action: "accept", content: { confirm: true } } }, requestState: state },
      { caps },
    );
    assert.ok(!(r.response?.result && textOf(r.response.result).startsWith("Deleted")), `state ${state.slice(0, 20)}: ${r.raw.slice(0, 200)}`);
  }
  assert.ok((await readResource(n.uri)).response?.result, "note survives");
});

// ---------- subscriptions ----------

test("app: subscriptions deliver resource updates for watched URIs", T, async () => {
  const nb = uniq("sub");
  const victim = await addNote(nb, "Victim", "v");
  const s = new Stream(
    "subscriptions/listen",
    { notifications: { resourceSubscriptions: ["notes://index", victim.uri] } },
    { id: "sub-a" },
  );
  try {
    assert.ok(await s.waitFor((m) => m.length >= 1), "ack arrives");
    assert.equal(s.status, 200);
    assert.ok(s.contentType.includes("text/event-stream"));
    const ack = s.messages[0]!;
    assert.equal(ack.method, "notifications/subscriptions/acknowledged");
    assert.equal(ack.params?._meta?.["io.modelcontextprotocol/subscriptionId"], "sub-a");
    assert.deepEqual([...(ack.params?.notifications?.resourceSubscriptions ?? [])].sort(), ["notes://index", victim.uri].sort());

    const added = await addNote(nb, "New", "n");
    const upd = (uri: string) => (m: Msg[]) =>
      m.some((x) => x.method === "notifications/resources/updated" && x.params?.uri === uri);
    assert.ok(await s.waitFor(upd("notes://index")), "index update after add");
    assert.ok(!s.messages.some((x) => x.params?.uri === added.uri), "unwatched new note URI not notified");

    await confirmDelete(victim.id);
    assert.ok(await s.waitFor(upd(victim.uri)), "note update after delete");
    for (const m of s.messages.slice(1)) {
      assert.equal(m.method, "notifications/resources/updated", `unexpected ${m.method}`);
      assert.equal(m.params?._meta?.["io.modelcontextprotocol/subscriptionId"], "sub-a", "tagged with subscriptionId");
      assert.equal(m.id, undefined);
    }
  } finally {
    s.close();
  }
});

test("app: subscriptions only notify watchers of the changed URI", T, async () => {
  const nb = uniq("filt");
  const a = await addNote(nb, "A", "a");
  const b = await addNote(nb, "B", "b");
  const sa = new Stream("subscriptions/listen", { notifications: { resourceSubscriptions: [a.uri] } }, { id: 4242 });
  const sb = new Stream("subscriptions/listen", { notifications: { resourceSubscriptions: [b.uri] } }, { id: "sub-b" });
  try {
    assert.ok(await sa.waitFor((m) => m.length >= 1));
    assert.ok(await sb.waitFor((m) => m.length >= 1));
    assert.equal(sa.messages[0]!.params?._meta?.["io.modelcontextprotocol/subscriptionId"], 4242, "numeric id preserved");
    await addNote(nb, "C", "c"); // changes only the index
    await confirmDelete(b.id);
    assert.ok(
      await sb.waitFor((m) => m.some((x) => x.method === "notifications/resources/updated" && x.params?.uri === b.uri)),
      "B watcher told about B",
    );
    await sleep(300);
    assert.equal(sa.messages.length, 1, `A watcher got nothing beyond ack: ${JSON.stringify(sa.messages.slice(1))}`);
    assert.ok(sb.messages.slice(1).every((x) => x.params?.uri === b.uri), "B watcher only gets B");
  } finally {
    sa.close();
    sb.close();
  }
});

test("app: acknowledgment omits list-change types the server does not offer", T, async () => {
  const s = new Stream(
    "subscriptions/listen",
    { notifications: { toolsListChanged: true, promptsListChanged: true, resourcesListChanged: true, resourceSubscriptions: ["notes://index"] } },
    { id: "sub-lists" },
  );
  try {
    assert.ok(await s.waitFor((m) => m.length >= 1));
    const n = s.messages[0]!.params?.notifications ?? {};
    assert.notEqual(n.toolsListChanged, true);
    assert.notEqual(n.promptsListChanged, true);
    assert.notEqual(n.resourcesListChanged, true);
    assert.deepEqual(n.resourceSubscriptions, ["notes://index"]);
  } finally {
    s.close();
  }
});

test("app: request-scoped progress never appears on a listen stream", T, async () => {
  const s = new Stream("subscriptions/listen", { notifications: { resourceSubscriptions: ["notes://index"] } }, { id: "sub-progress" });
  try {
    assert.ok(await s.waitFor((m) => m.length >= 1));
    const r = await rpc("tools/call", { name: "reindex", arguments: { steps: 3, delayMs: 10 }, _meta: { progressToken: "iso" } });
    assert.equal(r.messages.filter((m) => m.method === "notifications/progress").length, 3);
    await sleep(200);
    assert.ok(!s.messages.some((m) => m.method === "notifications/progress"), "no progress on listen stream");
  } finally {
    s.close();
  }
});
