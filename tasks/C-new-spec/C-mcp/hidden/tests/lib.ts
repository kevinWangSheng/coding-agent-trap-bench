// Minimal raw MCP 2026-07-28 Streamable HTTP client for the hidden tests.
// Deliberately independent of the implementation under test.

export const URL_ = process.env.MCP_URL ?? "http://127.0.0.1:3000/mcp";
export const PV = "2026-07-28";
export const PORT = new URL(URL_).port;

let nextId = 1000;
export const newId = () => nextId++;

export type Msg = Record<string, any>;

export interface Reply {
  status: number;
  headers: Headers;
  contentType: string;
  /** Every JSON-RPC message received (SSE events or the single JSON body). */
  messages: Msg[];
  /** The JSON-RPC response (result or error) matching the request id, if any. */
  response: Msg | undefined;
  /** Raw body text. */
  raw: string;
}

export function baseMeta(caps: Record<string, unknown> = {}): Msg {
  return {
    "io.modelcontextprotocol/protocolVersion": PV,
    "io.modelcontextprotocol/clientInfo": { name: "hidden-tests", version: "1.0.0" },
    "io.modelcontextprotocol/clientCapabilities": caps,
  };
}

const SAFE = /^[\x21-\x7e]([\x20-\x7e]*[\x21-\x7e])?$/;
export function encodeHeader(v: string): string {
  if (SAFE.test(v) && !(v.startsWith("=?base64?") && v.endsWith("?="))) return v;
  return `=?base64?${Buffer.from(v, "utf8").toString("base64")}?=`;
}

export interface RpcOpts {
  id?: string | number;
  /** Extra/override headers; a value of undefined removes the header. */
  headers?: Record<string, string | undefined>;
  caps?: Record<string, unknown>;
  /** Replace the whole params._meta (undefined = omit _meta entirely when set via noMeta). */
  meta?: Msg;
  noMeta?: boolean;
  signal?: AbortSignal;
  httpMethod?: string;
}

export function buildRequest(method: string, params: Msg = {}, opts: RpcOpts = {}) {
  const id = opts.id ?? newId();
  const p: Msg = { ...params };
  if (!opts.noMeta) p._meta = { ...(opts.meta ?? baseMeta(opts.caps)), ...(params._meta ?? {}) };
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
    "MCP-Protocol-Version": PV,
    "Mcp-Method": method,
  };
  if (method === "tools/call" || method === "prompts/get") {
    if (typeof p.name === "string") headers["Mcp-Name"] = encodeHeader(p.name);
  }
  if (method === "resources/read" && typeof p.uri === "string") headers["Mcp-Name"] = encodeHeader(p.uri);
  if (method === "tools/call" && p.name === "add_note") {
    const nb = p.arguments?.notebook;
    if (nb !== undefined && nb !== null) headers["Mcp-Param-Notebook"] = encodeHeader(String(nb));
  }
  for (const [k, v] of Object.entries(opts.headers ?? {})) {
    const existing = Object.keys(headers).find((h) => h.toLowerCase() === k.toLowerCase());
    if (existing) delete headers[existing];
    if (v !== undefined) headers[k] = v;
  }
  return { id, headers, body: JSON.stringify({ jsonrpc: "2.0", id, method, params: p }) };
}

export function parseSse(text: string): Msg[] {
  const out: Msg[] = [];
  for (const block of text.split(/\r?\n\r?\n/)) {
    const data = block
      .split(/\r?\n/)
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).replace(/^ /, ""));
    if (!data.length) continue;
    try {
      out.push(JSON.parse(data.join("\n")));
    } catch {
      /* ignore non-JSON events */
    }
  }
  return out;
}

export async function post(headers: Record<string, string>, body: string, signal?: AbortSignal, httpMethod = "POST"): Promise<Reply> {
  const res = await fetch(URL_, { method: httpMethod, headers, body: httpMethod === "GET" ? undefined : body, signal });
  const raw = await res.text();
  const contentType = res.headers.get("content-type") ?? "";
  let messages: Msg[] = [];
  if (contentType.includes("text/event-stream")) messages = parseSse(raw);
  else if (raw.trim()) {
    try {
      messages = [JSON.parse(raw)];
    } catch {
      messages = [];
    }
  }
  return { status: res.status, headers: res.headers, contentType, messages, response: undefined, raw };
}

export async function rpc(method: string, params: Msg = {}, opts: RpcOpts = {}): Promise<Reply> {
  const { id, headers, body } = buildRequest(method, params, opts);
  const r = await post(headers, body, opts.signal);
  r.response = r.messages.find((m) => m.id === id && ("result" in m || "error" in m)) ?? r.messages.find((m) => "error" in m && m.id === undefined);
  return r;
}

/** Calls and returns the result object, failing if the response is not a result. */
export async function result(method: string, params: Msg = {}, opts: RpcOpts = {}): Promise<Msg> {
  const r = await rpc(method, params, opts);
  if (!r.response || !("result" in r.response)) {
    throw new Error(`${method}: expected a result, got HTTP ${r.status}: ${r.raw.slice(0, 400)}`);
  }
  return r.response.result;
}

export const callTool = (name: string, args: Msg = {}, opts: RpcOpts = {}, extra: Msg = {}) =>
  rpc("tools/call", { name, arguments: args, ...extra }, opts);

export async function addNote(notebook: string, title: string, body: string): Promise<Msg> {
  const res = await result("tools/call", { name: "add_note", arguments: { notebook, title, body } });
  if (res.isError) throw new Error(`add_note failed: ${JSON.stringify(res)}`);
  return res.structuredContent;
}

export async function readResource(uri: string): Promise<Reply> {
  return rpc("resources/read", { uri });
}

/** Deletes a note through the confirmation round trip. */
export async function confirmDelete(id: string, answer: Msg = { action: "accept", content: { confirm: true } }): Promise<Msg> {
  const caps = { elicitation: {} };
  const first = await result("tools/call", { name: "delete_note", arguments: { id } }, { caps });
  if (first.resultType !== "input_required") throw new Error(`expected input_required, got ${JSON.stringify(first)}`);
  const key = Object.keys(first.inputRequests ?? {})[0]!;
  const extra: Msg = { inputResponses: { [key]: answer } };
  if (first.requestState !== undefined) extra.requestState = first.requestState;
  return result("tools/call", { name: "delete_note", arguments: { id }, ...extra }, { caps });
}

/** A long-lived SSE stream (e.g. subscriptions/listen). */
export class Stream {
  messages: Msg[] = [];
  status = 0;
  contentType = "";
  private waiters: Array<() => void> = [];
  private ctrl = new AbortController();
  done: Promise<void>;
  ended = false;

  constructor(method: string, params: Msg, opts: RpcOpts = {}) {
    const { headers, body } = buildRequest(method, params, opts);
    this.done = this.run(headers, body);
  }

  private async run(headers: Record<string, string>, body: string) {
    try {
      const res = await fetch(URL_, { method: "POST", headers, body, signal: this.ctrl.signal });
      this.status = res.status;
      this.contentType = res.headers.get("content-type") ?? "";
      if (!res.body) return;
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx: number;
        while ((idx = buf.search(/\r?\n\r?\n/)) >= 0) {
          const block = buf.slice(0, idx);
          buf = buf.slice(idx).replace(/^\r?\n\r?\n/, "");
          const parsed = this.contentType.includes("text/event-stream") ? parseSse(block + "\n\n") : [];
          for (const m of parsed) this.messages.push(m);
          this.wake();
        }
      }
      if (buf.trim()) {
        const tail = this.contentType.includes("text/event-stream") ? parseSse(buf) : safeJson(buf);
        this.messages.push(...tail);
      }
    } catch {
      /* aborted */
    } finally {
      this.ended = true;
      this.wake();
    }
  }

  private wake() {
    const w = this.waiters;
    this.waiters = [];
    for (const f of w) f();
  }

  /** Waits until pred holds for the collected messages, or times out. */
  async waitFor(pred: (msgs: Msg[]) => boolean, timeoutMs = 3000): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (!pred(this.messages)) {
      if (this.ended) return pred(this.messages);
      const left = deadline - Date.now();
      if (left <= 0) return false;
      await new Promise<void>((r) => {
        const t = setTimeout(r, left);
        this.waiters.push(() => {
          clearTimeout(t);
          r();
        });
      });
    }
    return true;
  }

  close() {
    this.ctrl.abort();
  }
}

function safeJson(s: string): Msg[] {
  try {
    return [JSON.parse(s)];
  } catch {
    return [];
  }
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
export const textOf = (res: Msg) => (res.content ?? []).filter((c: Msg) => c.type === "text").map((c: Msg) => c.text).join("");
