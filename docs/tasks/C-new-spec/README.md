# Task C: build against a spec published after the training cutoff

One task, `C-mcp`: implement a small MCP server ("field-notes") against the
**MCP specification revision 2026-07-28**, handed to the agent as a frozen local
snapshot. The trap: every frontier model knows the 2025-era MCP spec well (the
`initialize` handshake, `Mcp-Session-Id`, `resources/subscribe`, `ping`, -32002),
and 2026-07-28 removed or replaced all of those. Selection rationale:
[candidates.md](candidates.md) (a lead only; facts re-verified below).

Built 2026-09-23. Registered via `C-mcp/task.json`
(`{"env": "node", "timeout": 60}`), so `harness/run.py C-mcp <model> <rep>` works.

## Layout

```
C-mcp/
  prompt.md            developer-style request (harness appends its FOOTER)
  task.json            {"env": "node", "timeout": 60}
  repo/                what the agent receives as ./repo
    README.md          app features only (tools/resources/prompt/caching policy)
    docs/mcp-spec-2026-07-28/   verbatim spec snapshot (see Provenance)
    package.json, package-lock.json, tsconfig.json, .gitignore
    src/               empty
    node_modules/      typescript 5.9.3, @types/node 24.13.6 (+ undici-types); no MCP SDK
  hidden/
    reference/         full reference implementation (no SDK, Node stdlib only)
    tests/             55 hidden tests (node:test, raw HTTP client in lib.ts)
    stale_api_check.py static + dynamic old-spec artifact detector
    grade.py / grade.sh  offline grader -> one JSON object
    conformance_expected.json / conformance_excluded.json  scored / excluded conformance checks
    verification/     RED/GREEN/stub/mutant grade outputs, sandbox profile, mutant diff, stub source
cache/mcp-conformance/ (outside the task dir) pinned conformance CLI + lockfile
```

## Provenance (verified 2026-09-23)

- Spec source: `modelcontextprotocol/modelcontextprotocol` at commit
  `c7400a0796045cbf102cb80b9b41422c7ce8e7af` (main HEAD 2026-09-22; confirmed by the lead).
  - Tree: `gh api repos/modelcontextprotocol/modelcontextprotocol/git/trees/c7400a0796045cbf102cb80b9b41422c7ce8e7af?recursive=1` (`truncated: false`).
  - Files: `https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/c7400a0796045cbf102cb80b9b41422c7ce8e7af/<path>`
    for all 165 blobs under `docs/specification/2026-07-28/` (33 files) and `schema/2026-07-28/`
    (`schema.ts`, `schema.json`, 129 example JSONs).
  - Integrity: every downloaded file's git blob SHA-1 was recomputed and matched the tree (0 mismatches).
  - Local mapping: `docs/specification/2026-07-28/**/*.mdx` -> `repo/docs/mcp-spec-2026-07-28/**/*.md`
    (renamed, content unchanged, PNGs kept); `schema/2026-07-28/` -> `repo/docs/mcp-spec-2026-07-28/schema-ts/`
    (its 1.7 KB `schema.mdx` category stub was dropped). A provenance `README.md` sits at the top of the snapshot.
- Conformance CLI: `@modelcontextprotocol/conformance@0.2.0-alpha.11`
  (npm integrity `sha512-imPK9tx5gQsL6ZKQq4MrsyDYfSaIwpRmX6+ogjbeAXs9LGvxkBxWcY7KcS7TvwaBk/ZiVWl6b/naF4q83UwDRA==`),
  installed with a lockfile into `cache/mcp-conformance/` and invoked as
  `node cache/mcp-conformance/node_modules/@modelcontextprotocol/conformance/dist/index.js` (never `npx`).
  - The `--requirements 2026-07-28` flag in candidates.md is real: `conformance server --help` lists it, and the
    package ships `requirements/2026-07-28.yaml` ("FROZEN", anchored at 0.2.0-alpha.10, the release current when
    the revision shipped). alpha.11 (the current `alpha` dist-tag) was used; I did not diff it against alpha.10's copy.
  - `latest` (0.1.16) predates this spec and was not used. The CLI's own runtime dependency is
    `@modelcontextprotocol/sdk@1.30.0`, which stays inside `cache/` and never touches `repo/`.

### What changed in 2026-07-28 (from `changelog.md` at the pinned commit)

Each item below was checked against the changelog text and the normative pages.

| Changelog | Change | Where the task probes it |
|---|---|---|
| Major 1 | `Mcp-Session-Id` and protocol sessions removed; lists do not vary per connection | test `Mcp-Session-Id is ignored...`; stale: session header, DELETE |
| Major 2 | `initialize`/`notifications/initialized` removed; every request carries `_meta` `io.modelcontextprotocol/protocolVersion` + `clientCapabilities` (required), `clientInfo` (SHOULD); `serverInfo` in result `_meta`; `UnsupportedProtocolVersionError` | tests for missing `_meta` fields (400/-32602), unsupported version (400/-32022); conformance `server-stateless` |
| Major 3 | `server/discover` is mandatory | app + spec tests; conformance |
| Major 4 | GET endpoint and `resources/subscribe`/`unsubscribe` replaced by `subscriptions/listen` (ack `notifications/subscriptions/acknowledged`, `io.modelcontextprotocol/subscriptionId`); progress/log notifications stay on the originating request's stream | 4 subscription tests; GET 405 test; stale: GET stream |
| Major 5 | `ping`, `logging/setLevel`, `notifications/roots/list_changed` removed; per-request `io.modelcontextprotocol/logLevel`; no `notifications/message` unless requested | 404/-32601 test for removed methods; no-log test |
| Major 6 | Tasks moved to extension `io.modelcontextprotocol/tasks` (`tasks/result`, `tasks/list` removed) | static stale rule only (the app does not use tasks) |
| Major 7 | MRTR: `InputRequiredResult` (`resultType: "input_required"`, `inputRequests`, `requestState`); retry with `inputResponses` | `delete_note` confirmation flow (7 tests) |
| Major 8 | `resultType` required on all results | spec test + stale dynamic rule |
| Major 9 | SSE resumability (`Last-Event-ID`, event ids) removed | stale: SSE `id:` lines; `Last-Event-ID` ignored test |
| Minor 3 | deterministic `tools/list` order (SHOULD) | README fixes alphabetical order; determinism test |
| Minor 4 | `Mcp-Method`/`Mcp-Name` headers required; `x-mcp-header` -> `Mcp-Param-{Name}` with base64 sentinel `=?base64?...?=`; mismatch -> 400/-32020 | README requires `notebook` as `x-mcp-header: Notebook`; 6 header tests + 1 declaration test; conformance `http-header-validation`, `http-custom-header-server-validation` |
| Minor 5 | `ttlMs` + `cacheScope` required on discover/list/read results | README caching policy; caching test; conformance `caching` |
| Minor 6 | resource-not-found is `-32602`, not `-32002` | missing-note test; stale rule |
| Minor 11 | `notifications/elicitation/complete`, `elicitationId` removed | static stale rule |
| Minor 12 | error codes renumbered: HeaderMismatch `-32020`, MissingRequiredClientCapability `-32021`, UnsupportedProtocolVersion `-32022` | tests assert the new codes; stale rule flags -32001/-32003/-32004/-32042 |

Every bullet in candidates.md's summary matched the changelog. It left out Minor 4's `x-mcp-header`/`Mcp-Param-*`
mechanism, the `-32002` -> `-32602` change (Minor 6), and the error-code renumbering (Minor 12). The task tests all three.

## The app (repo/README.md)

An in-memory notes store with 3 seeded notes, served on `127.0.0.1:$PORT/mcp`:
- tools: `add_note` (structured output + `outputSchema`, `notebook` mirrored as `Mcp-Param-Notebook`),
  `delete_note` (asks the user to confirm through an MRTR form elicitation, holds no server-side state,
  and binds and integrity-protects `requestState`; `-32021` if the client lacks the elicitation capability),
  `reindex` (long-running, `notifications/progress` on the request's SSE stream, stops when the client disconnects);
- resources: static `notes://index`, template `notes://notes/{id}`; change notifications via `subscriptions/listen`;
- prompt: `summarize_notebook` (embedded resources);
- caching policy: lists/discover `public`/300000 ms, reads `private`/0.

## Grading (`hidden/grade.sh <repo_dir> [--out DIR]`)

1. Copies the repo (minus `node_modules`/`dist`/`.git`/`.claude`) to a temp dir and symlinks the
   **pristine** `C-mcp/repo/node_modules` into it. The agent cannot install anything offline, so this changes
   nothing for honest runs. Runs `npm run build`.
2. Starts `npm start` with a random `PORT` three separate times, once per phase, so state from one phase cannot leak into the next:
   - **conformance**: `conformance server --url ... --requirements 2026-07-28 -o <dir>`. The CLI's exit code is
     not used. `checks.json` is parsed per `(scenario, check-id)`, most severe status wins, and the result is compared
     with `conformance_expected.json`: **59 checks** the reference passes. Excluded (`conformance_excluded.json`,
     60 entries, each reviewed by hand): checks that call the CLI's own fixtures (`test_*` tools/prompts,
     `test://` resources) that no app server has; `completion/complete` (optional, not in the app); list-changed
     checks (SKIPPED, app has static lists); `wire-schema-valid` of fixture-only scenarios (validates only an
     "unknown tool" error); whole `tasks-*` extension scenarios and `json-schema-2020-12` (fixture-only).
     The two SEP-2243 scenarios the requirement file lists as *pending* (`http-header-validation`,
     `http-custom-header-server-validation`) **are** scored because they are app-agnostic and cover the README's
     `Notebook` header. The CLI found them by discovering `add_note`'s `x-mcp-header` on its own.
   - **hidden tests**: `node --test --test-concurrency=1` over `hidden/tests/*.test.ts` (31 `app:` + 24 `spec:`), junit parsed.
   - **stale_api_check**: static scan of `src/` (comments stripped; 12 rules, all cited to the changelog; reported, not scored,
     because a mention can be legitimate) + ~21 dynamic probes whose hits are scored (must be 0).
3. Emits JSON: `build`, `server`, `conformance` (incl. raw CLI `Total:` line, failed check ids + messages),
   `hidden_tests` (per-test failures, per-category counts), `stale_api` (counts + hit lists), `summary`, `verdict`
   (`PASS` only if all five parts pass).

## Verification (2026-09-23, fully offline)

Network was cut with macOS `sandbox-exec` and `hidden/verification/deny-net.sb`, which denies all outbound IP
except loopback and also denies the local proxy port 127.0.0.1:<proxy-port>. Check: outside the sandbox
`curl https://registry.npmjs.org/` returned 200; inside it returned 000 both via the proxy and with `--noproxy '*'`.
Loopback still returned 200. `grade.py` also strips proxy variables and sets `npm_config_offline=true`.

Commands (cwd `tasks/C-new-spec/C-mcp`), outputs saved in `hidden/verification/*.json`:

```
sandbox-exec -f hidden/verification/deny-net.sb hidden/grade.sh repo              --out <dir>   # RED: empty scaffold
sandbox-exec -f hidden/verification/deny-net.sb hidden/grade.sh <stub>            --out <dir>   # RED: listens, implements nothing (verification/stub-server.ts)
sandbox-exec -f hidden/verification/deny-net.sb hidden/grade.sh hidden/reference  --out <dir>   # GREEN
sandbox-exec -f hidden/verification/deny-net.sb hidden/grade.sh <stale-mutant>    --out <dir>   # reference + verification/stale-mutant.diff
```

| Run | verdict | build | conformance (scored) | CLI raw | hidden tests | stale static | stale dynamic | wall |
|---|---|---|---|---|---|---|---|---|
| RED empty scaffold | FAIL | fail (`TS18003: No inputs were found`) | not run (server absent) | - | not run | 0 | not run | 0.9 s |
| RED stub server | FAIL | ok | 25/59 | `Total: 60 passed, 97 failed` | 3/55 (app 0/31) | 0 | 0 | 2.2 s |
| GREEN reference | **PASS** | ok | **59/59** | `Total: 115 passed, 60 failed` | **55/55** | 0 | 0 | 6.1 s |
| stale mutant | FAIL | ok | 49/59 | `Total: 102 passed, 72 failed` | 45/55 | 6 | 33 | 6.1 s |

- Stability: the reference got PASS on all 8 grading runs during development. The last 2 used the final test file and expected-check set, and the scores were identical across runs.
- The stub's **25/59 is the conformance floor**. Those checks pass trivially on a server that rejects everything
  (e.g. "removed methods return 404", "foreign Origin rejected"). They stay scored because a stale server fails them
  (all 10 checks the mutant loses are in this floor set). Report conformance relative to this floor.
- The mutant (`initialize`/`ping`/`resources/subscribe` handlers, `Mcp-Session-Id` header, `-32002`, SSE `id:` lines,
  no `resultType`) is caught by all three layers. Its dynamic hits: session-header 17, missing-resultType 10, sse-event-id 2,
  initialize 1, ping 1, resources-subscribe 1, old-error-code 1.
- The harness path was simulated with `run.py`'s own `task_spec`/`setup_env`/`git_baseline` on a scratch copy, without
  touching `results/` or `~/.bench-runs`. The baseline commit has 170 files and no `node_modules` (it is in `.gitignore`).
  `npm run build` and `npm test` work inside the deny-network sandbox.
- A leak scan of `repo/` and `prompt.md` for conformance/hidden/grading/benchmark returned nothing.

## Disk usage

`C-mcp/` 29 MB (repo/node_modules 27 MB, spec docs 1.9 MB, hidden 228 KB); `cache/mcp-conformance/` 50 MB.

## Risks and open items

- **Sealing is not implemented yet.** NOTES.md describes `chmod 000` on `tasks/*/hidden`, but that glob does not match
  this task's depth (`tasks/C-new-spec/C-mcp/hidden`). The same is true of A's layout. For C, seal at least
  `tasks/C-new-spec/C-mcp/hidden`, `tasks/C-new-spec/README.md`, `tasks/C-new-spec/candidates.md` and
  `cache/mcp-conformance`, the last because an agent that found the CLI could self-grade. Unseal before `grade.sh`.
- `repo/.gitignore` ignores `node_modules/` and `dist/`. `node_modules` is still physically shipped, since `copytree` copies it,
  but it is kept out of the harness git baseline and the diff. Remove the `.gitignore` if you want `node_modules` changes to show in `repo.diff`.
- The conformance CLI is alpha. Its `requirements/2026-07-28.yaml` marks the SEP-2243 header scenarios as *pending*, and
  its tasks scenarios fail against its own fixture. Only checks the reference passes are scored, and each exclusion was reviewed.
- Spec inconsistency, not tested: `basic/patterns/cancellation.md` says a server MUST send `notifications/cancelled`
  for a `subscriptions/listen` it tears down, while `subscriptions.md` says it SHOULD send a completion result. The
  schema docs restrict `notifications/cancelled` to stdio. The reference sends the result on HTTP shutdown, and nothing grades this.
- Hidden tests pin README-level details: exact texts, 300000/0 TTLs, alphabetical tools, `-32602` for invalid prompt
  arguments, 405 for GET/DELETE (a spec SHOULD). Content objects are compared on README-specified fields only, so extra
  `_meta`/`annotations` are allowed.
- Not graded: cancellation of `reindex` when the client disconnects, which is hard to observe black-box, and `tools/list` pagination.
- The upstream docs are still being edited. The snapshot is pinned to `c7400a0`, so later upstream changes do not affect the task.
