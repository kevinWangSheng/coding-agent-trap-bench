// Field Notes application: method handlers for tools, resources, prompts,
// discovery and subscriptions.

import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import {
  INVALID_PARAMS,
  META_CLIENT_CAPABILITIES,
  META_SUBSCRIPTION_ID,
  MISSING_REQUIRED_CLIENT_CAPABILITY,
  RpcError,
  SUPPORTED_VERSIONS,
  decodeHeaderValue,
  HEADER_MISMATCH,
  isObject,
  type JsonObject,
  type RequestId,
} from "./protocol.js";
import { INDEX_URI, NoteStore, noteUri, renderNote, type Note } from "./notes.js";

/** What a handler can do besides returning a result. */
export interface Ctx {
  id: RequestId;
  params: JsonObject;
  headers: Record<string, string | string[] | undefined>;
  /** Aborted when the client disconnects (cancellation on Streamable HTTP). */
  signal: AbortSignal;
  /** Switches the response to an SSE stream and sends a notification on it. */
  notify(message: JsonObject): void;
  /** Resolves when the server is shutting down. */
  shutdown: Promise<void>;
}

/** Returned by a handler that ended without a response (client went away). */
export const NO_RESPONSE = Symbol("no-response");
export type HandlerResult = JsonObject | typeof NO_RESPONSE;
type Handler = (ctx: Ctx) => Promise<HandlerResult>;

const LIST_CACHE = { ttlMs: 300_000, cacheScope: "public" as const };
const NOTE_CACHE = { ttlMs: 0, cacheScope: "private" as const };
const NOTEBOOK_RE = /^[A-Za-z0-9_-]{1,64}$/;
const INSTRUCTIONS =
  "Field Notes stores short notes grouped into notebooks. Use add_note to save a note, read notes://index to see what exists.";

const store = new NoteStore();
const stateKey = randomBytes(32);
const STATE_TTL_MS = 10 * 60_000;

// ---------- tools ----------

const TOOLS = [
  {
    name: "add_note",
    title: "Add note",
    description: "Create a note in a notebook.",
    inputSchema: {
      type: "object",
      properties: {
        notebook: {
          type: "string",
          description: "Notebook name (1-64 chars of A-Z a-z 0-9 _ -)",
          pattern: "^[A-Za-z0-9_-]{1,64}$",
          "x-mcp-header": "Notebook",
        },
        title: { type: "string", minLength: 1, maxLength: 200 },
        body: { type: "string" },
      },
      required: ["notebook", "title", "body"],
      additionalProperties: false,
    },
    outputSchema: {
      type: "object",
      properties: {
        id: { type: "string" },
        uri: { type: "string" },
        notebook: { type: "string" },
        wordCount: { type: "integer", minimum: 0 },
      },
      required: ["id", "uri", "notebook", "wordCount"],
      additionalProperties: false,
    },
  },
  {
    name: "delete_note",
    title: "Delete note",
    description: "Delete a note after the user confirms.",
    inputSchema: {
      type: "object",
      properties: { id: { type: "string" } },
      required: ["id"],
      additionalProperties: false,
    },
    annotations: { destructiveHint: true, idempotentHint: true },
  },
  {
    name: "reindex",
    title: "Rebuild search index",
    description: "Rebuild the search index. Slow; reports progress.",
    inputSchema: {
      type: "object",
      properties: {
        steps: { type: "integer", minimum: 1, maximum: 20, default: 5 },
        delayMs: { type: "integer", minimum: 0, maximum: 1000, default: 200 },
      },
      additionalProperties: false,
    },
  },
];

const text = (t: string) => ({ type: "text", text: t });
const toolError = (message: string) => ({ content: [text(message)], isError: true });

/** Validates Mcp-Param-* headers for x-mcp-header annotated parameters. */
function checkParamHeaders(tool: (typeof TOOLS)[number], args: JsonObject, headers: Ctx["headers"]) {
  const props = tool.inputSchema.properties as unknown as Record<string, JsonObject>;
  for (const [prop, schema] of Object.entries(props)) {
    const name = schema["x-mcp-header"];
    if (typeof name !== "string") continue;
    const headerName = `mcp-param-${name.toLowerCase()}`;
    const raw = headers[headerName];
    const value = args[prop];
    const present = value !== undefined && value !== null;
    if (raw === undefined) {
      if (present) throw new RpcError(HEADER_MISMATCH, `Missing Mcp-Param-${name} header`, undefined, 400);
      continue;
    }
    const decoded = decodeHeaderValue(Array.isArray(raw) ? raw.join(", ") : raw);
    if (decoded === undefined) throw new RpcError(HEADER_MISMATCH, `Malformed Mcp-Param-${name} header`, undefined, 400);
    if (!present) throw new RpcError(HEADER_MISMATCH, `Mcp-Param-${name} header present but argument absent`, undefined, 400);
    const expected = typeof value === "string" ? value : JSON.stringify(value);
    const matches =
      typeof value === "number" ? Number(decoded) === value && decoded.trim() !== "" : decoded === expected;
    if (!matches) {
      throw new RpcError(
        HEADER_MISMATCH,
        `Header mismatch: Mcp-Param-${name} header value '${decoded}' does not match body value '${expected}'`,
        undefined,
        400,
      );
    }
  }
}

function addNote(args: JsonObject) {
  const { notebook, title, body } = args;
  const extra = Object.keys(args).filter((k) => !["notebook", "title", "body"].includes(k));
  if (typeof notebook !== "string" || !NOTEBOOK_RE.test(notebook))
    return toolError("notebook must be 1-64 characters from [A-Za-z0-9_-]");
  if (typeof title !== "string" || title.length === 0) return toolError("title must be a non-empty string");
  if (title.length > 200) return toolError("title must be at most 200 characters");
  if (typeof body !== "string") return toolError("body must be a string");
  if (extra.length) return toolError(`unexpected argument(s): ${extra.join(", ")}`);
  const note = store.add(notebook, title, body);
  const out = { id: note.id, uri: noteUri(note.id), notebook, wordCount: body.split(/\s+/).filter(Boolean).length };
  return { content: [text(JSON.stringify(out))], structuredContent: out };
}

// requestState: base64url(payload).base64url(hmac). Binds the confirmation to one note.
function signState(payload: JsonObject): string {
  const p = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const mac = createHmac("sha256", stateKey).update(p).digest("base64url");
  return `${p}.${mac}`;
}

function verifyState(state: string): JsonObject | undefined {
  const [p, mac, ...rest] = state.split(".");
  if (!p || !mac || rest.length) return undefined;
  const expected = createHmac("sha256", stateKey).update(p).digest();
  const given = Buffer.from(mac, "base64url");
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return undefined;
  try {
    const payload = JSON.parse(Buffer.from(p, "base64url").toString("utf8"));
    return isObject(payload) ? payload : undefined;
  } catch {
    return undefined;
  }
}

function deleteNote(ctx: Ctx, args: JsonObject) {
  const id = args.id;
  if (typeof id !== "string" || id.length === 0) return toolError("id must be a non-empty string");
  const note = store.get(id);
  if (!note) return toolError(`Note ${id} not found`);

  const caps = ctx.params._meta && isObject(ctx.params._meta) ? ctx.params._meta[META_CLIENT_CAPABILITIES] : undefined;
  const elicitation = isObject(caps) ? caps.elicitation : undefined;
  const formOk = isObject(elicitation) && (Object.keys(elicitation).length === 0 || "form" in elicitation);
  if (!formOk) {
    throw new RpcError(
      MISSING_REQUIRED_CLIENT_CAPABILITY,
      "delete_note requires the elicitation (form) capability",
      { requiredCapabilities: { elicitation: { form: {} } } },
      400,
    );
  }

  const { requestState, inputResponses } = ctx.params;
  if (requestState !== undefined) {
    const payload = typeof requestState === "string" ? verifyState(requestState) : undefined;
    if (
      !payload ||
      payload.tool !== "delete_note" ||
      payload.noteId !== id ||
      typeof payload.exp !== "number" ||
      payload.exp < Date.now()
    ) {
      throw new RpcError(INVALID_PARAMS, "Invalid or expired requestState");
    }
    const answer = isObject(inputResponses) ? inputResponses.confirm : undefined;
    if (isObject(answer)) {
      const confirmed = answer.action === "accept" && isObject(answer.content) && answer.content.confirm === true;
      if (!confirmed) return { content: [text("Deletion cancelled")] };
      store.delete(id);
      return { content: [text(`Deleted note ${id}`)] };
    }
    // Missing answer: ask again below.
  }
  return confirmationRequest(note);
}

function confirmationRequest(note: Note) {
  return {
    resultType: "input_required",
    inputRequests: {
      confirm: {
        method: "elicitation/create",
        params: {
          mode: "form",
          message: `Delete note "${note.title}"?`,
          requestedSchema: {
            type: "object",
            properties: { confirm: { type: "boolean", title: "Delete this note" } },
            required: ["confirm"],
          },
        },
      },
    },
    requestState: signState({ tool: "delete_note", noteId: note.id, exp: Date.now() + STATE_TTL_MS }),
  };
}

function intArg(v: unknown, def: number, min: number, max: number): number | undefined {
  if (v === undefined) return def;
  if (typeof v !== "number" || !Number.isInteger(v) || v < min || v > max) return undefined;
  return v;
}

async function reindex(ctx: Ctx, args: JsonObject): Promise<HandlerResult> {
  const steps = intArg(args.steps, 5, 1, 20);
  if (steps === undefined) return toolError("steps must be an integer between 1 and 20");
  const delayMs = intArg(args.delayMs, 200, 0, 1000);
  if (delayMs === undefined) return toolError("delayMs must be an integer between 0 and 1000");
  const meta = isObject(ctx.params._meta) ? ctx.params._meta : {};
  const token = meta.progressToken;
  const wantsProgress = typeof token === "string" || (typeof token === "number" && Number.isInteger(token));

  for (let k = 1; k <= steps; k++) {
    await sleep(delayMs, ctx.signal);
    if (ctx.signal.aborted) return NO_RESPONSE;
    if (wantsProgress) {
      ctx.notify({
        jsonrpc: "2.0",
        method: "notifications/progress",
        params: { progressToken: token, progress: k, total: steps, message: `Indexed ${k}/${steps}` },
      });
    }
  }
  return { content: [text(`Reindex complete: ${steps} steps`)] };
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const t = setTimeout(done, ms);
    signal.addEventListener("abort", done, { once: true });
    function done() {
      clearTimeout(t);
      signal.removeEventListener("abort", done);
      resolve();
    }
  });
}

// ---------- method table ----------

function noCursor(params: JsonObject) {
  if (params.cursor !== undefined) throw new RpcError(INVALID_PARAMS, "Invalid cursor");
}

function readResource(uri: string) {
  if (uri === INDEX_URI) {
    const index = store.list().map(({ id, notebook, title }) => ({ id, notebook, title }));
    return { uri, mimeType: "application/json", text: JSON.stringify(index, null, 2) };
  }
  const m = /^notes:\/\/notes\/([^/?#]+)$/.exec(uri);
  const note = m ? store.get(m[1]!) : undefined;
  if (!note) throw new RpcError(INVALID_PARAMS, "Resource not found", { uri });
  return { uri, mimeType: "text/markdown", text: renderNote(note) };
}

export const METHODS: Record<string, Handler> = {
  "server/discover": async () => ({
    supportedVersions: SUPPORTED_VERSIONS,
    capabilities: { tools: {}, resources: { subscribe: true }, prompts: {} },
    instructions: INSTRUCTIONS,
    ...LIST_CACHE,
  }),

  "tools/list": async ({ params }) => {
    noCursor(params);
    return { tools: TOOLS, ...LIST_CACHE };
  },

  "tools/call": async (ctx) => {
    const { name, arguments: rawArgs } = ctx.params;
    if (typeof name !== "string") throw new RpcError(INVALID_PARAMS, "params.name must be a string");
    const tool = TOOLS.find((t) => t.name === name);
    if (!tool) throw new RpcError(INVALID_PARAMS, `Unknown tool: ${name}`);
    if (rawArgs !== undefined && !isObject(rawArgs))
      throw new RpcError(INVALID_PARAMS, "params.arguments must be an object");
    const args = rawArgs ?? {};
    checkParamHeaders(tool, args, ctx.headers);
    switch (name) {
      case "add_note":
        return addNote(args);
      case "delete_note":
        return deleteNote(ctx, args);
      default:
        return reindex(ctx, args);
    }
  },

  "resources/list": async ({ params }) => {
    noCursor(params);
    return {
      resources: [{ uri: INDEX_URI, name: "index", title: "All notes", mimeType: "application/json" }],
      ...LIST_CACHE,
    };
  },

  "resources/templates/list": async ({ params }) => {
    noCursor(params);
    return {
      resourceTemplates: [
        { uriTemplate: "notes://notes/{id}", name: "note", title: "A single note", mimeType: "text/markdown" },
      ],
      ...LIST_CACHE,
    };
  },

  "resources/read": async ({ params }) => {
    if (typeof params.uri !== "string") throw new RpcError(INVALID_PARAMS, "params.uri must be a string");
    return { contents: [readResource(params.uri)], ...NOTE_CACHE };
  },

  "prompts/list": async ({ params }) => {
    noCursor(params);
    return {
      prompts: [
        {
          name: "summarize_notebook",
          title: "Summarize notebook",
          description: "Ask the model to summarize the notes in one notebook.",
          arguments: [
            { name: "notebook", description: "Notebook to summarize", required: true },
            { name: "style", description: "brief (default) or detailed", required: false },
          ],
        },
      ],
      ...LIST_CACHE,
    };
  },

  "prompts/get": async ({ params }) => {
    if (params.name !== "summarize_notebook") throw new RpcError(INVALID_PARAMS, `Unknown prompt: ${String(params.name)}`);
    const args = params.arguments === undefined ? {} : params.arguments;
    if (!isObject(args)) throw new RpcError(INVALID_PARAMS, "params.arguments must be an object");
    const { notebook, style = "brief" } = args;
    if (typeof notebook !== "string" || notebook === "")
      throw new RpcError(INVALID_PARAMS, "Missing required argument: notebook");
    if (style !== "brief" && style !== "detailed")
      throw new RpcError(INVALID_PARAMS, "style must be 'brief' or 'detailed'");
    const instruction =
      style === "brief"
        ? `Summarize the notes in the "${notebook}" notebook in two sentences.`
        : `Summarize the notes in the "${notebook}" notebook in detail, one paragraph per note.`;
    const messages = [
      { role: "user", content: text(instruction) },
      ...store
        .list()
        .filter((n) => n.notebook === notebook)
        .map((n) => ({
          role: "user",
          content: { type: "resource", resource: { uri: noteUri(n.id), mimeType: "text/markdown", text: renderNote(n) } },
        })),
    ];
    return { description: `Summarize notebook ${notebook}`, messages };
  },

  "subscriptions/listen": async (ctx) => {
    const filter = ctx.params.notifications;
    if (!isObject(filter)) throw new RpcError(INVALID_PARAMS, "params.notifications must be an object");
    const uris = filter.resourceSubscriptions;
    if (uris !== undefined && !(Array.isArray(uris) && uris.every((u) => typeof u === "string")))
      throw new RpcError(INVALID_PARAMS, "resourceSubscriptions must be an array of strings");
    // Lists are static, so only resource update subscriptions are honored.
    const acknowledged: JsonObject = {};
    if (uris !== undefined) acknowledged.resourceSubscriptions = uris;
    const subMeta = { [META_SUBSCRIPTION_ID]: ctx.id };
    ctx.notify({
      jsonrpc: "2.0",
      method: "notifications/subscriptions/acknowledged",
      params: { _meta: subMeta, notifications: acknowledged },
    });
    const watched = new Set((uris as string[] | undefined) ?? []);
    const off = store.onChange((uri) => {
      if (watched.has(uri)) {
        ctx.notify({ jsonrpc: "2.0", method: "notifications/resources/updated", params: { _meta: subMeta, uri } });
      }
    });
    const ended = await Promise.race([
      ctx.shutdown.then(() => "shutdown" as const),
      new Promise<"closed">((r) => ctx.signal.addEventListener("abort", () => r("closed"), { once: true })),
    ]);
    off();
    return ended === "shutdown" ? { _meta: subMeta } : NO_RESPONSE;
  },
};
