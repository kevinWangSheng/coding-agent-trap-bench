# Task C candidates — "build against a spec you've never seen"

Scouted 2026-09-23 for a Claude Opus 5.5 (Claude Code) vs GPT-6 Astra/Sol (Codex CLI)
head-to-head. Selection bar: published or substantially changed **after 2026-07-01**,
so neither Opus 5.5 (cutoff June 2026) nor GPT-6 (cutoff unknown but presumably
similar-era) can have seen it in training. Dates below are verified against primary
sources (RFC Editor, IETF datatracker, official changelogs/blogs, npm registry
metadata, GitHub releases API) via WebFetch/WebSearch/`gh api`/`curl` on 2026-09-23;
anything not independently confirmed is marked "unverified."

---

## 1. MCP specification 2026-07-28 (Model Context Protocol)

- **Primary sources:**
  - Spec + changelog: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx
  - Blog (final spec): https://blog.modelcontextprotocol.io/posts/2026-07-28/
  - Blog (release candidate): https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
  - Conformance tooling: https://www.npmjs.com/package/@modelcontextprotocol/conformance (repo: github.com/modelcontextprotocol/conformance)
- **Publication date:** 2026-07-28, verified (final spec date; previous version was 2025-11-25). Repo HEAD as of scout date is `c7400a0` (2026-09-22), i.e. docs are still being actively edited — **a benchmark run must pin a commit SHA**, not track `main`.
- **What changed (memory traps for a model that only knows the 2025-06-18/2025-11-25 spec):**
  - Protocol goes **stateless**: `Mcp-Session-Id` header and the `initialize`/`notifications/initialized` handshake are removed; every request now carries protocol version + capabilities in `_meta`. A model "remembering" MCP will reflexively implement the handshake and session header — that's now wrong.
  - New required `server/discover` RPC for capability/version advertisement.
  - `resources/subscribe`/`resources/unsubscribe` + SSE `GET` stream replaced by a single `subscriptions/listen` long-lived POST stream; SSE resumability (`Last-Event-ID`) removed entirely.
  - `ping`, `logging/setLevel`, `notifications/roots/list_changed` removed; log level now per-request via `_meta`.
  - All results require a new `resultType` field (`"complete"` | `"input_required"`), replacing blocking server-initiated request patterns with an `InputRequiredResult`.
  - Roots, Sampling, Logging deprecated; Tasks moved out of core into an extensions namespace; OAuth Dynamic Client Registration deprecated in favor of Client ID Metadata Documents.
  - New `extensions` capability field, cache metadata (`ttlMs`, `cacheScope`) on cacheable results, deterministic tool ordering for caching, standardized error-code allocation policy.
- **Proposed implementation task:** Implement a minimal MCP server (Python or TypeScript, Streamable HTTP transport) against the frozen 2026-07-28 docs only: `server/discover`, stateless `tools/list` (deterministic order, cache metadata) and `tools/call` (returns `resultType: "complete"`) for 1–2 real tools (e.g. `echo`, `add`), correct required headers (`Mcp-Method`, `Mcp-Name`), no session ID/handshake anywhere.
- **Grading:** Official conformance CLI exists and is actively tracking this exact spec version: `npx @modelcontextprotocol/conformance server --url <url> --requirements 2026-07-28`. npm registry shows version churn right around the spec date — `0.2.0-alpha.10` published 2026-07-27 (day before final spec), `0.2.0-alpha.11` published 2026-08-07 — so pin exactly one of those alpha builds for reproducible grading; the `0.1.x` line (latest `0.1.16`, 2026-03-30) predates and does not know this spec version. Supplement with a handful of hand-written hidden tests (e.g. assert no `Mcp-Session-Id` round-trips, assert `resultType` present) since the conformance package is still alpha and may not cover every new behavior.
- **Estimated effort:** 60–90 min (moderate surface area: several removed/renamed RPCs plus one new required RPC).
- **Risks:** Spec docs are a living Mintlify site still being edited daily — must snapshot a commit SHA and hand the agent that snapshot, not a live link, or the "hidden" grading target can drift under us. Conformance package is pre-1.0 alpha (`0.2.0-alpha.*`); its own coverage of the July spec could have gaps or bugs, so don't rely on it as the sole test oracle.

---

## 2. RFC 10008 — The HTTP QUERY Method (IETF, June 2026)

- **Primary source:** https://www.rfc-editor.org/rfc/rfc10008.txt (confirmed via direct fetch); info page https://www.rfc-editor.org/info/rfc10008/
- **Publication date:** June 2026, verified from the RFC document header itself ("Request for Comments: 10008 ... June 2026"; Standards Track; authors J. Reschke (greenbytes), J.M. Snell (Cloudflare), M. Bishop (Akamai)).
- **What changed / memory trap:** This is HTTP's **first new standard method since PATCH (RFC 5789, 2010)**. A model that "knows HTTP" will reach for its well-worn workarounds — `POST` for a body-bearing safe query, or an invalid `GET`-with-body — both of which are exactly what QUERY was designed to replace. Key precise, testable semantics: QUERY is **safe and idempotent** (unlike POST) and encloses request content describing how to process the target resource; servers advertise support via a new `Accept-Query` response header; caches must fold request content into the cache key (unlike GET, where the cache key is normally URI-only).
- **Proposed implementation task:** Build a small HTTP server (Go `net/http` with a custom method matcher, or Python with a raw ASGI/WSGI app — most frameworks don't route arbitrary methods out of the box, which is itself part of the challenge) exposing a resource collection. Implement: `QUERY` accepting a JSON filter body and returning matching records; `OPTIONS`/`Accept-Query` advertisement; correct status/semantics differences vs `POST` (e.g. safe/idempotent framing, no `Location` header on success); a cache layer whose key incorporates the QUERY body.
- **Grading:** No official conformance suite found. Write hidden tests directly from RFC section text (it's short and precise — normative "MUST/SHOULD" language throughout), e.g.: server rejects QUERY without `Content-Type`, advertises `Accept-Query` correctly, two QUERY requests with different bodies against the same URI get different cache entries, method is retried automatically by an RFC-aware client without side effects.
- **Estimated effort:** 30–50 min (smallest, most self-contained candidate — one RFC, no ecosystem churn to track).
- **Risks:** Because it's brand new, most HTTP libraries/frameworks (Flask, Express, stdlib `http.server`) don't special-case QUERY, so the agent must hand-roll method dispatch — good for signal, but means grading must not assume a particular framework's routing sugar exists yet. No official test suite means our hidden tests carry all the correctness weight; keep them tightly scoped to RFC-quoted MUST clauses to avoid grading contested interpretation.

---

## 3. WASI 0.3 (Component Model native async)

- **Primary sources:** https://wasi.dev/releases/wasi-p3 ; roadmap: https://github.com/bytecodealliance/wasi.dev/blob/main/docs/roadmap.md
- **Publication date:** 2026-06-11 (WASI 0.3.0), per WASI.dev release page — **unverified by direct fetch** (WebFetch to wasi.dev was not independently re-confirmed after the initial WebSearch summary; recommend a direct fetch of wasi.dev/releases/wasi-p3 before locking this in).
- **What changed / memory trap:** WASI 0.2 (Preview 2), which models know well, does async I/O via the `wasi:io` package (pollables, streams as a bolt-on). WASI 0.3 **removes `wasi:io` entirely** and moves async natively into the Component Model itself via `async func`, `stream<T>`, `future<T>` in the Canonical ABI — code written the "0.2 way" (poll-based `wasi:io/poll`) will reference an interface that no longer exists. Host runtime requirement: Wasmtime 43+.
- **Proposed implementation task:** Write a small Rust WASI component (via `wit-bindgen`/`cargo component`, target `wasm32-wasip2`) exporting one `async func` that returns a `stream<T>`, and a tiny host (Rust + Wasmtime 43+) that instantiates it and consumes the stream using native async, not the old `wasi:io/poll` pattern.
- **Grading:** No official conformance suite located; would need hand-written host-side tests asserting the stream yields the expected sequence/backpressure behavior, and a static check that no `wasi:io` import is present in the compiled component.
- **Estimated effort:** 60–90 min, with meaningful variance — **toolchain risk is the main issue**: needs `wasm32-wasip2` Rust target, a `wit-bindgen`/`cargo-component` version matched to WASI 0.3, and Wasmtime 43+ all present and compiling cleanly on macOS arm64. Should be pre-verified in the actual benchmark sandbox before committing to this pick; first-time `cargo component` builds can be slow.
- **Risks:** Highest environment-setup risk of the set; also the weakest evidence chain here (release date not independently re-fetched). Treat as a stretch/backup pick pending a toolchain smoke test.

---

## 4. OpenTelemetry GenAI Semantic Conventions (post-migration, June–July 2026)

- **Primary sources:** https://opentelemetry.io/blog/2026/genai-observability/ ; new repo: github.com/open-telemetry/semantic-conventions-genai ; background: https://john-hodge.com/blog/opentelemetry-genai-semantic-conventions/ (secondary, dated July 2026)
- **Publication date:** 2026-06-12, semantic-conventions core `v1.42.0` — the point at which all `gen_ai.*` attributes/spans/metrics/events were deprecated in the core repo and moved to the new dedicated `semantic-conventions-genai` repo — **unverified by direct primary-source fetch**; corroborated only via WebSearch summaries of secondary blog posts, not by fetching the actual registry YAML or CHANGELOG. Should confirm directly against `github.com/open-telemetry/semantic-conventions-genai` before use.
- **What changed / memory trap:** A model that knows the older, stabler `gen_ai.*` attribute set (from the core semconv repo, pre-migration) will emit attributes/namespaces from the old registry location and old names; the new repo has continued to iterate independently since the June 2026 split.
- **Proposed implementation task:** Instrument a mock LLM chat-completion call (Python or TS, OpenTelemetry SDK) to emit a span with attributes conforming to the post-migration `gen_ai.*` registry pinned to a specific commit after 2026-07-01.
- **Grading:** Registry is YAML-defined and machine-checkable in principle, so hidden tests could diff emitted span attributes against the pinned registry YAML — but no official conformance/validator tool was found, and this is compounded by the next point.
- **Estimated effort:** 45–75 min.
- **Risks:** As of mid-July 2026 every `gen_ai.*` item is still marked **stability: Development** (i.e., "experimental," no 1.0, names can still change between versions) per the search summary — this is the one candidate where "the old version is well known" is true but "the new version is precisely/stably specified" is shakier, since it's explicitly still moving. Weakest of the four on criterion (2) from the brief. Also weakest evidence chain (no direct primary fetch performed).

---

## 5. uv 0.12.0 (Python packaging tool, Astral)

- **Primary source:** https://github.com/astral-sh/uv/releases/tag/0.12.0 (fetched directly)
- **Publication date:** 2026-07-28, verified via direct fetch of the GitHub release page (same calendar day as the MCP 2026-07-28 spec, coincidentally).
- **What changed / memory trap:** 13 breaking changes bundled in one release — most relevant for a "memory trap": `uv init` now defaults to a packaged `uv_build` layout (`src/` + `[project.scripts]`) instead of the old flat/unpackaged default; pre-release resolution mode default flips from `if-necessary-or-explicit` to `if-necessary`; `pylock.toml` (lockfile) validation now **requires** a `packages` array and rejects files missing it; hash-checking mode now rejects MD5-only hashes; sdists must be `.tar.gz` (legacy `.tar.bz2`/`.tar.xz` rejected); invalid `SSL_CERT_FILE`/`SSL_CERT_DIR` now hard-fail instead of silently falling back.
- **Proposed implementation task:** Write a small Python tool (stdlib `tomllib`, no uv invocation needed) that validates/generates a `pylock.toml` file against uv 0.12's tightened rules (required `packages` array, filename constraints, declared-size verification), using only the release notes as spec text.
- **Grading:** Straightforward to hand-write hidden tests (valid/invalid lockfile fixtures) since the rules are itemized and concrete in the release notes; no official conformance suite, but uv itself (installed locally per the benchmark's stated environment) can serve as an oracle by running `uv lock --locked`/`uv sync` against agent-produced fixtures and checking accept/reject matches uv's real behavior.
- **Estimated effort:** 30–60 min — narrowest, most mechanical of the six.
- **Risks:** This is more "correctly parse a tightened file-format/CLI-behavior spec" than "implement a protocol" — thinner signal than the others, and picking only 2–3 of the 13 changes to scope the task risks feeling arbitrary. Best used as a quick supplementary/backup task rather than the headline pick.

---

## Ranked top 3

1. **MCP specification 2026-07-28** — best combination of (a) an old version every frontier model has memorized cold (MCP is ubiquitous in agent tooling), (b) large, sharply-defined breaking changes described in an official changelog, (c) an actively-maintained official conformance CLI we can pin to a specific alpha build for reproducible hidden-test grading, and (d) trivial local setup (Python/TS, no exotic toolchain). Main operational risk (docs still being edited) is fully mitigated by freezing a commit SHA.
2. **RFC 10008 (HTTP QUERY method)** — cleanest, smallest, most unambiguous "this literally did not exist before" trap; precise normative RFC text makes hidden-test authorship low-risk even without an official suite; forces the agent to hand-roll method routing, which surfaces stale-API usage (POST/GET-with-body substitutions) clearly.
3. **WASI 0.3 native async** — strong memory trap (`wasi:io` removal is a hard break from the well-known 0.2 model) and a real "build against a spec" task, but held to #3 because of unverified release-date sourcing and real toolchain-setup risk on the benchmark sandbox; promote to #1/#2 only after (a) re-confirming the 2026-06-11 date against wasi.dev directly and (b) smoke-testing `cargo component` + `wasm32-wasip2` + Wasmtime 43+ on the actual macOS arm64 runner.

(OpenTelemetry GenAI semconv and uv 0.12.0 are kept as candidates 4–5 for breadth/backup — see notes above on why each ranks below the top 3.)

---

## Draft task statement — #1 pick (MCP 2026-07-28)

> You are given the Model Context Protocol specification, frozen at commit `<PIN_SHA>` of
> `modelcontextprotocol/modelcontextprotocol` (docs/specification/2026-07-28/**), plus the
> spec changelog at the same commit. You do **not** have network access to the live docs
> site or GitHub during implementation — only the local copies provided.
>
> Implement an MCP server, in Python or TypeScript, exposed over the Streamable HTTP
> transport on `localhost:<port>`, that is conformant with this exact spec revision. It
> must expose at least two tools (`echo` and `add`) and satisfy, at minimum:
> - `server/discover` returns supported protocol version(s), capabilities, and identity —
>   no `initialize`/`notifications/initialized` handshake anywhere.
> - No `Mcp-Session-Id` header is set, read, or required at any point in any transport.
> - `tools/list` returns results in a stable, deterministic order across repeated calls
>   with no active connection state, and includes cache metadata (`ttlMs`, `cacheScope`)
>   per the spec's caching section.
> - `tools/call` results include the required `resultType` field (`"complete"` for both
>   tools in this task).
> - Required Streamable HTTP headers (`Mcp-Method`, `Mcp-Name`) are present on POST
>   requests.
> - `ping`, `logging/setLevel`, and `resources/subscribe`/`unsubscribe` are **not**
>   implemented (they were removed in this revision) — implementing them is not a bonus,
>   it's a spec violation to flag.
>
> Grading: run against `npx @modelcontextprotocol/[email protected]` (or the exact
> alpha we pin) with `--requirements 2026-07-28`, plus a small hidden suite asserting the
> removed/renamed RPCs above are genuinely absent and that no session-based behavior
> leaks into the implementation.

---

## Verification notes / provenance

- Dates independently confirmed by direct primary-source fetch: RFC 10008 (rfc-editor.org
  raw text), MCP 2026-07-28 changelog (GitHub, via WebFetch), uv 0.12.0 (GitHub release
  page, via WebFetch), MCP conformance package version timestamps (npm registry API via
  `curl`), MCP repo HEAD commit (`gh api`).
- Dates taken from WebSearch summaries only, **not yet independently re-fetched from a
  primary source** — flagged inline above, re-verify before locking in: WASI 0.3 release
  date (wasi.dev), OpenTelemetry GenAI semconv migration date (`v1.42.0`, 2026-06-12).
- Rejected as too-early / already inside model training windows (published before
  2026-07-01, or clearly pre-dating both models' stated cutoffs): OpenAPI 3.2 (2025-09-19),
  Kubernetes 1.34 (2025-08-27), Go 1.25 (2025-08-12), TOML 1.1.0 (2025-12-24), Next.js 16
  GA (2025-10-21), Zod v4 (stable since ~2025). OAuth 2.1 rejected for now because it is
  still an IETF Internet-Draft (`draft-ietf-oauth-v2-1-15`, dated 2026-03-02), not a
  published RFC — no stable, citable spec text to freeze. Pydantic v3 rejected: not yet
  released as of 2026-09-23 (only V2.x releases confirmed; pydantic-core repo was archived
  2026-04-11, suggesting restructuring, but no V3 changelog found).
