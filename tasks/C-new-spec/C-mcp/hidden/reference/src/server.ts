// Streamable HTTP transport for MCP 2026-07-28: one POST endpoint, stateless,
// JSON or per-request SSE responses.

import http from "node:http";
import { METHODS, NO_RESPONSE, type Ctx } from "./app.js";
import {
  HEADER_MISMATCH,
  INTERNAL_ERROR,
  INVALID_PARAMS,
  INVALID_REQUEST,
  LOG_LEVELS,
  META_CLIENT_CAPABILITIES,
  META_LOG_LEVEL,
  META_PROTOCOL_VERSION,
  METHOD_NOT_FOUND,
  PARSE_ERROR,
  RpcError,
  SUPPORTED_VERSIONS,
  UNSUPPORTED_PROTOCOL_VERSION,
  decodeHeaderValue,
  errorBody,
  finishResult,
  isObject,
  type JsonObject,
  type RequestId,
} from "./protocol.js";

const PORT = Number(process.env.PORT ?? 3000);
const HOST = "127.0.0.1";
const MAX_BODY = 1024 * 1024;
const ALLOWED_ORIGINS = new Set([`http://localhost:${PORT}`, `http://127.0.0.1:${PORT}`]);
const NAME_SOURCE: Record<string, "name" | "uri"> = {
  "tools/call": "name",
  "prompts/get": "name",
  "resources/read": "uri",
};

let signalShutdown!: () => void;
const shutdown = new Promise<void>((r) => (signalShutdown = r));

function sendJson(res: http.ServerResponse, status: number, body: JsonObject) {
  const payload = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) });
  res.end(payload);
}

function header(req: http.IncomingMessage, name: string): string | undefined {
  const v = req.headers[name];
  return Array.isArray(v) ? v.join(", ") : v;
}

async function readBody(req: http.IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > MAX_BODY) throw new RpcError(INVALID_REQUEST, "Request body too large", undefined, 413);
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks).toString("utf8");
}

/** Transport- and envelope-level validation that precedes dispatch. */
function validate(req: http.IncomingMessage, method: string, params: unknown): JsonObject {
  const versionHeader = header(req, "mcp-protocol-version");
  const methodHeader = header(req, "mcp-method");
  if (versionHeader === undefined) throw new RpcError(HEADER_MISMATCH, "Missing MCP-Protocol-Version header", undefined, 400);
  if (methodHeader === undefined) throw new RpcError(HEADER_MISMATCH, "Missing Mcp-Method header", undefined, 400);

  if (params !== undefined && !isObject(params)) throw new RpcError(INVALID_PARAMS, "params must be an object", undefined, 400);
  const p = params ?? {};
  const meta = p._meta;
  if (!isObject(meta)) throw new RpcError(INVALID_PARAMS, "Missing params._meta", undefined, 400);
  const version = meta[META_PROTOCOL_VERSION];
  if (typeof version !== "string")
    throw new RpcError(INVALID_PARAMS, `Missing _meta["${META_PROTOCOL_VERSION}"]`, undefined, 400);
  if (!isObject(meta[META_CLIENT_CAPABILITIES]))
    throw new RpcError(INVALID_PARAMS, `Missing _meta["${META_CLIENT_CAPABILITIES}"]`, undefined, 400);

  if (versionHeader !== version) {
    throw new RpcError(
      HEADER_MISMATCH,
      `Header mismatch: MCP-Protocol-Version header value '${versionHeader}' does not match body value '${version}'`,
      undefined,
      400,
    );
  }
  if (methodHeader !== method) {
    throw new RpcError(
      HEADER_MISMATCH,
      `Header mismatch: Mcp-Method header value '${methodHeader}' does not match body value '${method}'`,
      undefined,
      400,
    );
  }
  if (!SUPPORTED_VERSIONS.includes(version)) {
    throw new RpcError(
      UNSUPPORTED_PROTOCOL_VERSION,
      "Unsupported protocol version",
      { supported: SUPPORTED_VERSIONS, requested: version },
      400,
    );
  }
  if (!Object.hasOwn(METHODS, method)) throw new RpcError(METHOD_NOT_FOUND, `Method not found: ${method}`, undefined, 404);

  const source = NAME_SOURCE[method];
  if (source) {
    const rawName = header(req, "mcp-name");
    if (rawName === undefined) throw new RpcError(HEADER_MISMATCH, "Missing Mcp-Name header", undefined, 400);
    const name = decodeHeaderValue(rawName);
    if (name === undefined) throw new RpcError(HEADER_MISMATCH, "Malformed Mcp-Name header", undefined, 400);
    const bodyValue = p[source];
    if (typeof bodyValue !== "string") throw new RpcError(INVALID_PARAMS, `params.${source} must be a string`);
    if (name !== bodyValue) {
      throw new RpcError(
        HEADER_MISMATCH,
        `Header mismatch: Mcp-Name header value '${name}' does not match body value '${bodyValue}'`,
        undefined,
        400,
      );
    }
  }

  const level = meta[META_LOG_LEVEL];
  if (level !== undefined && !(typeof level === "string" && LOG_LEVELS.includes(level)))
    throw new RpcError(INVALID_PARAMS, "Invalid log level");
  return p;
}

async function handle(req: http.IncomingMessage, res: http.ServerResponse) {
  const path = new URL(req.url ?? "/", "http://localhost").pathname;
  if (path !== "/mcp") {
    res.writeHead(404).end();
    return;
  }
  const origin = req.headers.origin;
  if (origin !== undefined && !ALLOWED_ORIGINS.has(origin)) {
    sendJson(res, 403, errorBody(undefined, INVALID_REQUEST, "Forbidden origin"));
    return;
  }
  if (req.method !== "POST") {
    res.writeHead(405, { Allow: "POST" }).end();
    return;
  }

  let msg: unknown;
  try {
    msg = JSON.parse(await readBody(req));
  } catch (e) {
    if (e instanceof RpcError) return sendJson(res, e.httpStatus, errorBody(undefined, e.code, e.message));
    return sendJson(res, 400, errorBody(undefined, PARSE_ERROR, "Parse error"));
  }

  if (!isObject(msg) || msg.jsonrpc !== "2.0" || "result" in msg || "error" in msg || typeof msg.method !== "string") {
    return sendJson(res, 400, errorBody(undefined, INVALID_REQUEST, "Invalid Request"));
  }
  if (!("id" in msg)) {
    // Notifications (none are meaningful to this server over HTTP) are accepted and ignored.
    res.writeHead(202).end();
    return;
  }
  const id = msg.id;
  if (!(typeof id === "string" || (typeof id === "number" && Number.isInteger(id)))) {
    return sendJson(res, 400, errorBody(undefined, INVALID_REQUEST, "Invalid request id"));
  }
  const method = msg.method;

  let params: JsonObject;
  try {
    params = validate(req, method, msg.params);
  } catch (e) {
    const err = e instanceof RpcError ? e : new RpcError(INTERNAL_ERROR, "Internal error", undefined, 500);
    return sendJson(res, err.httpStatus, errorBody(id, err.code, err.message, err.data));
  }

  await dispatch(req, res, id, method, params);
}

async function dispatch(req: http.IncomingMessage, res: http.ServerResponse, id: RequestId, method: string, params: JsonObject) {
  const abort = new AbortController();
  let finished = false;
  res.on("close", () => {
    if (!finished) abort.abort();
  });

  let streaming = false;
  let keepAlive: NodeJS.Timeout | undefined;
  const write = (m: JsonObject) => {
    if (!res.writableEnded && !res.destroyed) res.write(`data: ${JSON.stringify(m)}\n\n`);
  };
  const ctx: Ctx = {
    id,
    params,
    headers: req.headers,
    signal: abort.signal,
    shutdown,
    notify(message) {
      if (abort.signal.aborted) return;
      if (!streaming) {
        streaming = true;
        res.writeHead(200, {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "X-Accel-Buffering": "no",
        });
        res.flushHeaders();
        keepAlive = setInterval(() => !res.writableEnded && res.write(":\n\n"), 15_000);
      }
      write(message);
    },
  };

  let body: JsonObject | undefined;
  let status = 200;
  try {
    const result = await METHODS[method]!(ctx);
    if (result !== NO_RESPONSE) body = { jsonrpc: "2.0", id, result: finishResult(result) };
  } catch (e) {
    const err = e instanceof RpcError ? e : new RpcError(INTERNAL_ERROR, "Internal error", undefined, 500);
    if (!(e instanceof RpcError)) console.error(e);
    status = err.httpStatus;
    body = errorBody(id, err.code, err.message, err.data);
  }
  finished = true;
  clearInterval(keepAlive);
  if (abort.signal.aborted || res.destroyed) return;
  if (streaming) {
    if (body) write(body);
    res.end();
  } else if (body) {
    sendJson(res, status, body);
  } else {
    res.end();
  }
}

const server = http.createServer((req, res) => {
  handle(req, res).catch((e) => {
    console.error(e);
    if (!res.headersSent) sendJson(res, 500, errorBody(undefined, INTERNAL_ERROR, "Internal error"));
    else res.end();
  });
});

server.listen(PORT, HOST, () => {
  console.error(`field-notes MCP server listening on http://${HOST}:${PORT}/mcp`);
});

function stop() {
  signalShutdown();
  // Give listen streams a moment to send their closing response.
  setTimeout(() => {
    server.close();
    server.closeAllConnections();
    process.exit(0);
  }, 200).unref();
}
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
