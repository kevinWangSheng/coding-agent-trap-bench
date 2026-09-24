# field-notes-mcp

An MCP server that exposes a small in-memory notes store to AI assistants.

The server speaks the Model Context Protocol, revision **2026-07-28**, over the
Streamable HTTP transport. The full protocol specification for that revision is
in [`docs/mcp-spec-2026-07-28/`](docs/mcp-spec-2026-07-28/README.md) and is the
reference for all protocol behavior. This README only describes what the
application does. Do not use an MCP SDK; implement the protocol directly on
Node's standard library.

## Running

```sh
npm run build   # compiles src/ to dist/
npm start       # node dist/server.js
```

- Listens on `127.0.0.1`, port from the `PORT` environment variable (default `3000`).
- The MCP endpoint is `/mcp`.
- Server identity: name `field-notes`, version `1.0.0`.
- Only protocol version `2026-07-28` is supported. Clients from earlier protocol
  revisions are not supported.
- Browser-originated requests are only allowed from `http://localhost:<PORT>` and
  `http://127.0.0.1:<PORT>`.
- Instructions for the model (returned wherever the protocol carries server
  instructions): `Field Notes stores short notes grouped into notebooks. Use add_note to save a note, read notes://index to see what exists.`

## Data model

A note has:

| Field      | Type   | Notes                                                        |
| ---------- | ------ | ------------------------------------------------------------ |
| `id`       | string | `n1`, `n2`, ... assigned in creation order, never reused      |
| `notebook` | string | 1-64 characters from `[A-Za-z0-9_-]`                          |
| `title`    | string | non-empty, at most 200 characters                             |
| `body`     | string | may be empty                                                  |

Notes live in memory only. The server starts with these three notes:

| id   | notebook   | title             | body                                              |
| ---- | ---------- | ----------------- | ------------------------------------------------- |
| `n1` | `work`     | `Standup`         | `Discussed the release schedule and blockers.`    |
| `n2` | `work`     | `Retro actions`   | `Automate the changelog. Rotate the on-call.`     |
| `n3` | `personal` | `Groceries`       | `Eggs, flour, coffee.`                            |

## Tools

Tools are listed in alphabetical order by name.

### `add_note`

Creates a note.

- Arguments: `notebook` (string, required), `title` (string, required),
  `body` (string, required).
- The `notebook` argument is routing-relevant: our gateway routes and
  rate-limits by notebook without parsing request bodies. Use the spec's
  mechanism for exposing a tool parameter as an HTTP header, with header name
  part `Notebook`, so clients send the notebook in a header. The server must
  enforce the consistency rules the spec defines for that header.
- Returns structured output, and declares an output schema for it:

  ```json
  { "id": "n4", "uri": "notes://notes/n4", "notebook": "work", "wordCount": 3 }
  ```

  `wordCount` is the number of whitespace-separated words in `body`.
  Also return the same object serialized as JSON in a text content block.
- Invalid arguments (missing/empty title, bad notebook name, wrong types, title
  too long) are reported as a tool execution error (not a protocol error) with a
  message explaining what is wrong, so the model can correct itself.

### `delete_note`

Deletes a note, but only after the user explicitly confirms.

- Arguments: `id` (string, required).
- If the note does not exist: tool execution error `Note <id> not found`.
- Otherwise the server asks the user for confirmation through the client using
  a form-mode elicitation with message `Delete note "<title>"?` and a single
  required boolean field `confirm`. Use the spec's mechanism for a server that
  needs client input to complete a request. The server must not keep any
  per-request state in memory while waiting for the answer.
- When the user accepts with `confirm: true`, the note is deleted and the tool
  returns text `Deleted note <id>`. If the user declines, cancels, or answers
  `confirm: false`, nothing is deleted and the tool returns text
  `Deletion cancelled` (not an error).
- A confirmation that was issued for one note must not be usable to delete a
  different note, and must not be forgeable or modifiable by the client.
- Clients that cannot show a form to the user cannot use this tool; respond
  as the spec requires when a request needs a client capability that was not
  declared.

### `reindex`

Rebuilds the (simulated) search index. This is slow, so it reports progress.

- Arguments: `steps` (integer 1-20, default 5), `delayMs` (integer 0-1000,
  default 200) - the time spent on each step.
- When the client asked for progress, report progress after each step:
  `progress` = steps completed so far, `total` = `steps`, `message` =
  `Indexed <k>/<steps>`.
- Result: text `Reindex complete: <steps> steps`.
- If the client goes away before it finishes, stop working on it.
- Out-of-range arguments are tool execution errors.

## Resources

### `notes://index` (static resource)

- Name `index`, title `All notes`, MIME type `application/json`.
- Content: JSON array of `{ "id", "notebook", "title" }` for every note, ordered
  by numeric id (`n1`, `n2`, ..., `n10`, ...).
- It is the only entry returned by the resource list.

### `notes://notes/{id}` (resource template)

- Name `note`, title `A single note`, MIME type `text/markdown`.
- Content of `notes://notes/n1`: `# <title>\n\n<body>\n` (a heading line, a blank
  line, the body, and a trailing newline).
- Reading a note that does not exist is an error, reported the way the spec
  says a missing resource must be reported.

### Change notifications

Clients can watch `notes://index` and any `notes://notes/{id}` URI for changes
using the spec's subscription mechanism:

- Adding a note updates `notes://index`.
- Deleting a note updates `notes://index` and `notes://notes/<id>`.
- Only watchers of a URI are told about changes to it.

The lists of tools, prompts, resources and resource templates never change at
runtime, so the server offers no list-change notifications.

## Prompts

### `summarize_notebook`

- Arguments: `notebook` (required), `style` (optional, `brief` or `detailed`,
  default `brief`).
- Messages, all with role `user`:
  1. Text: `Summarize the notes in the "<notebook>" notebook in two sentences.`
     for `brief`, or `Summarize the notes in the "<notebook>" notebook in detail, one paragraph per note.`
     for `detailed`.
  2. One message per note in that notebook (in id order), each an embedded
     resource with the note's URI, MIME type `text/markdown`, and the same text
     as reading that note's resource.
- An unknown `style` or a missing `notebook` is an invalid-params error. A
  notebook with no notes just produces the first message.

## Caching

- Discovery and every list result may be cached by anyone for 5 minutes.
- Note contents (both resources) are user data: they must not be shared
  between users and must not be considered fresh at all.

## Development

- TypeScript sources go in `src/`; the entry point compiles to `dist/server.js`.
- `npm test` runs `node --test` (Node 24 runs `.ts` test files directly).
- Only the packages already in `node_modules` are available.
