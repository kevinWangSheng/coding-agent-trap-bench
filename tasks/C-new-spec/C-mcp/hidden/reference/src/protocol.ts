// Protocol constants and helpers for MCP 2026-07-28 (see docs/mcp-spec-2026-07-28).

export const PROTOCOL_VERSION = "2026-07-28";
export const SUPPORTED_VERSIONS = [PROTOCOL_VERSION];
export const SERVER_INFO = { name: "field-notes", version: "1.0.0" };

export const META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion";
export const META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities";
export const META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo";
export const META_LOG_LEVEL = "io.modelcontextprotocol/logLevel";
export const META_SERVER_INFO = "io.modelcontextprotocol/serverInfo";
export const META_SUBSCRIPTION_ID = "io.modelcontextprotocol/subscriptionId";

export const PARSE_ERROR = -32700;
export const INVALID_REQUEST = -32600;
export const METHOD_NOT_FOUND = -32601;
export const INVALID_PARAMS = -32602;
export const INTERNAL_ERROR = -32603;
export const HEADER_MISMATCH = -32020;
export const MISSING_REQUIRED_CLIENT_CAPABILITY = -32021;
export const UNSUPPORTED_PROTOCOL_VERSION = -32022;

export const LOG_LEVELS = ["debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"];

export type RequestId = string | number;
export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };
export type JsonObject = { [k: string]: unknown };

/** A JSON-RPC error raised while handling a request, with the HTTP status to use. */
export class RpcError extends Error {
  constructor(
    public code: number,
    message: string,
    public data?: unknown,
    public httpStatus = 200,
  ) {
    super(message);
  }
}

export function isObject(v: unknown): v is JsonObject {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Every result carries resultType and identifies the server in _meta. */
export function finishResult(result: JsonObject): JsonObject {
  const meta = isObject(result._meta) ? result._meta : {};
  return { resultType: "complete", ...result, _meta: { ...meta, [META_SERVER_INFO]: SERVER_INFO } };
}

export function errorBody(id: RequestId | undefined, code: number, message: string, data?: unknown): JsonObject {
  const error: JsonObject = { code, message };
  if (data !== undefined) error.data = data;
  return id === undefined ? { jsonrpc: "2.0", error } : { jsonrpc: "2.0", id, error };
}

const SENTINEL = /^=\?base64\?([A-Za-z0-9+/]*={0,2})\?=$/;

/**
 * Decodes a header value that may use the Base64 sentinel encoding
 * (basic/transports/streamable-http.md, "Value Encoding"). Returns undefined
 * when the sentinel is present but malformed.
 */
export function decodeHeaderValue(raw: string): string | undefined {
  if (raw.startsWith("=?base64?") && raw.endsWith("?=")) {
    const m = SENTINEL.exec(raw);
    if (!m || m[1]!.length % 4 !== 0) return undefined;
    return Buffer.from(m[1]!, "base64").toString("utf8");
  }
  return raw;
}
