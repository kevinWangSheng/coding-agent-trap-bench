Please implement the MCP server described in ./repo/README.md.

The protocol behavior must follow the Model Context Protocol specification, revision 2026-07-28, which is checked in at repo/docs/mcp-spec-2026-07-28/. Treat that copy as the source of truth for the protocol. Don't use an MCP SDK; implement it in TypeScript under repo/src on Node's standard library.

`npm run build` and `npm start` (in repo/) must build and start the server as the README describes. Add tests that exercise the running server over HTTP, make `npm test` run them, and run them before you finish.
