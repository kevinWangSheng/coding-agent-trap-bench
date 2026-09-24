import http from "node:http";
// Listens but implements no MCP methods.
http
  .createServer((_req, res) => {
    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ jsonrpc: "2.0", error: { code: -32601, message: "not implemented" } }));
  })
  .listen(Number(process.env.PORT ?? 3000), "127.0.0.1");
