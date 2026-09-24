# Task D candidates — "make it faster without changing behavior"

Scouted 2026-09-23 for Opus 5.5 (Claude Code) vs GPT-6 Astra/Sol (Codex CLI). All repos below are
real, currently-open GitHub issues found via `gh search issues --created ">2026-06-01" ...` — not
synthetic fixtures I wrote. Two candidates (treeq, sqlx) were cloned and measured locally on this
machine (macOS 26.6.2, arm64, rustc 1.93.0 default / 1.95.0 via rustup). Two (stellar-router,
hermes) were verified for buildability/authenticity but not benchmarked end-to-end — flagged as
such.

## Environment note (applies to every Rust candidate below)

The default Xcode CLT SDK on this machine, `MacOSX27.0.sdk` (a macOS 27 beta SDK), is malformed —
`rustc`/`cc` linking fails on **any** Rust program, not just these repos (`ld: tapi error:
malformed file ... unknown architecture arm64e.x1-macos`). Confirmed with a bare `cargo new`.
Workaround used for all builds below:
```
export SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk
```
Whoever runs the actual eval on comparable hardware should pre-flight this (`cargo build` on a
scratch crate) before handing a Rust task to either agent, or the "baseline" step of the task
itself will fail for reasons unrelated to the exercise.

---

## Candidate 1 — treeq `--paths` unbuffered per-line syscalls

- **Repo**: https://github.com/ognjen-vuceljic/treeq (JSON/XML tree-view TUI + CLI, Rust)
- **Pinned commit**: `7f67ba921f0c48b434fa2af824b5fa369dce94f8` (2026-09-22, tag v0.4.4). Issue is
  **open, unfixed** as of 2026-09-23.
- **Source issue**: [#128](https://github.com/ognjen-vuceljic/treeq/issues/128) — "`--paths` is
  slow on large input: unbuffered println per line (13.6s on 44MB, 11s sys)", filed by the repo
  owner today.
- **Language/toolchain**: Rust 2024 edition, `cargo`, no external services. Matches the `rustc`
  tool in the eval box directly (no Docker needed).
- **Provenance note**: 0 stars, single maintainer, repo's whole history (117+ squash-merged PRs,
  8.5k LOC, very polished commit messages) reads like it was built by a coding agent already. Real
  code either way — it builds, has 54 passing tests, and the bug is genuine — but treat "official
  open source project with a community" claims skeptically; it's closer to a well-maintained solo
  CLI tool.

**Benchmark (measured today)**
```
git clone https://github.com/ognjen-vuceljic/treeq.git && cd treeq
git checkout 7f67ba921f0c48b434fa2af824b5fa369dce94f8
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk cargo build --release
python3 -c "
import json
objs=[{'id':i,'name':f'item-{i}','tags':['a','b','c'],'meta':{'active':i%2==0,'score':i*0.5}} for i in range(400000)]
json.dump(objs, open('/tmp/big.json','w'))"
time ./target/release/treeq --paths /tmp/big.json > /tmp/out.txt
```
- Generated file: 43,355,560 bytes (matches issue's "44 MB / 400k objects" scale), 4,000,000 output lines.
- **Baseline, measured**: `1.91s user 4.41s system 90% cpu 6.971 total` (sys time dominates — one
  `write(2)` syscall per line, exactly the reported root cause). Reporter's machine: 13.6s (11.2s
  sys) — slower box, same qualitative signature.
- Reference: `--static` on the same file (fully in-process rendering, no per-line write) is
  `1.83s user 0.21s system 95% cpu 2.144 total` — the ceiling the fix should approach.
- **Applied the issue's suggested fix (BufWriter + writeln!) myself to confirm headroom is real**:
  fixed build gives `1.58s user 0.62s system 60% cpu 3.641 total` → **1.9x wall-clock**, sys time
  drops from 4.41s to 0.62s (~7x). `diff` of baseline vs fixed stdout on the 4M-line file is
  **byte-identical**. `cargo test --release` stays 54/54 passing. Piping into `head -1` no longer
  risks a `BrokenPipe` panic (verified: exits cleanly, no panic on stderr).
- **Second, unexploited tier**: `src/paths.rs::walk_json`/`walk_xml` clone the full path `Vec<String>`
  and every key `String` at every recursion level (`path.to_vec()`, `label.clone()`), then
  `display_path` re-escapes and `.join(".")`s it. Not the issue's reported bottleneck (depth is
  shallow on this fixture) but real allocation headroom on deeply-nested inputs — a second,
  smaller-magnitude fix an agent could stack on top of buffering for a multi-tier score.
- **Full test suite**: `cargo test --release` → 54 passed, 0 failed, 4.3s total (build+run).

**Correctness check plan**
- `cargo test --release` (54 existing tests) must stay green, and its file `tests/cli.rs` must be
  byte-identical to the pinned commit's copy (see cheat vectors).
- Differential test: generate 5+ JSON/XML fixtures of varying shape (deep nesting, unicode keys,
  keys containing literal `.` and control bytes — `paths.rs` already has unit tests for exactly
  these — empty arrays/objects, NDJSON) and diff old-binary vs new-binary `--paths`/`--xml --paths`
  output byte-for-byte on each.
- Broken-pipe regression: `treeq --paths big.json | head -1` must exit 0 with empty stderr, both
  before and after.

**Known headroom / reference fix**: the issue body **contains the exact diff** (BufWriter +
writeln!, BrokenPipe handling). This is the single biggest weakness of this candidate (see cheat
vectors).

**Cheat vectors and detection**
1. **Reading the fix straight out of the issue.** #128 literally has working Rust code as the
   "Fix" section. If the agent has `gh`/web access to this repo it can paste the diff verbatim
   with zero perf engineering. *Detection/mitigation*: strip GitHub access to this specific repo
   from the agent's task context, or give it only a local tarball at the pinned commit with a
   rewritten task prompt that doesn't mention issue #128 by number/title.
2. **Weakening `tests/cli.rs`** (e.g. deleting the broken-pipe assertion) to dodge a real fix.
   *Detection*: diff `tests/cli.rs` against the pinned commit; any reduction in assertions is a
   fail regardless of what the benchmark timer says.
3. **Format drift**: buffering wrong (e.g. buffering but dropping the final flush, or reordering
   output across a thread pool) changes byte output for large inputs even though small manual
   spot-checks look fine. *Detection*: full-file diff on all 4M lines, not head/tail sampling.
4. **Caching across runs**: none of this task's state persists between process invocations, so a
   results cache isn't naturally available — but a "cheat" implementation could special-case
   `/tmp/big.json`'s exact byte length or first line. *Detection*: regenerate the fixture with a
   different seed/row count for the graded run than whatever was shown during development.

**Risks**: repo provenance is uncertain (likely AI-authored, freshly created, 0 stars — see note
above); the fix is already spelled out in the issue text (must be hidden from the agent to be a
fair test); headroom is real but modest (~2x, not the 10x+ tier) unless the agent also tackles the
allocation-cloning tier.

---

## Candidate 2 — sqlx SQLite: quadratic `sqlite3_prepare_v3` re-copy on multi-statement scripts

- **Repo**: https://github.com/transact-rs/sqlx (17,489 stars — this **is** the real, canonical
  `sqlx` crate; moved from `launchbadge/sqlx` to the `transact-rs` org on 2026-05-21 when it went
  to community ownership. Apache-2.0.)
- **Pinned commit**: `b54008a329541c0ce230d8b203e0c00fc8e8ea48` (current `main` HEAD as of
  2026-09-23; confirmed `sqlx-sqlite/src/statement/virtual.rs` hasn't changed since 2025-06-30, so
  the bug is present and unfixed at HEAD). Also reproducible against the published `sqlx = "0.9.0"`
  crate (same code, per the issue: "0.9.0 (unchanged on main)").
- **Source issue**: [#4415](https://github.com/transact-rs/sqlx/issues/4415) — filed today,
  0 comments, no PR opened yet.
- **Language/toolchain**: Rust. Needs `rustc >= 1.94` (this machine's default `rustc` is 1.93.0;
  used the pre-installed `rustup` toolchain `1.95.0` via `cargo +1.95.0`). Bundles/builds SQLite
  from C source via the `cc` crate — first build compiles a small amount of C, still fast.

**Benchmark (measured today, standalone repro crate — no full sqlx workspace checkout needed)**
```
cargo new sqlx-repro --bin && cd sqlx-repro
# Cargo.toml: sqlx = { version = "=0.9.0", default-features=false, features=["runtime-tokio","sqlite"] }, tokio
# src/main.rs: the exact repro from issue #4415 (loop over n in [...], time sqlx::raw_sql(script))
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk cargo +1.95.0 build --release
time ./target/release/sqlx-repro
```
- **Baseline, measured** (cold build 36.3s, then run):
  ```
   5000 statements: 55.3ms
  10000 statements: 111.3ms
  20000 statements: 382.9ms
  40000 statements: 1.388s
  ```
  and, extended run:
  ```
  20000 statements: 398.0ms
  40000 statements: 2.167s
  80000 statements: 8.712s
  ```
  Clear superlinear scaling (each doubling costs ~3.5–4x, matching the issue's own numbers of
  46.6ms/91.4ms/345.6ms/1.29s/4.78s at the same sizes — same shape, this machine is somewhat
  faster).
- Whole benchmark (build + 3-size run) finishes in **under 15s wall**, comfortably inside the 2-min
  budget with room to add larger sizes for more dramatic contrast.
- **Reference magnitude** (from the issue, not independently re-measured by me since it requires
  patching the actual `sqlx-sqlite` crate, not the published one): fixed version does 80,000
  statements in ~222ms vs baseline 4.78s → **~21x** on the reporter's machine; their real 17.6MB/
  55k-statement production script drops from ~13s to ~1.4s (**~9x**). Root cause (confirmed by
  reading `sqlx-sqlite/src/statement/virtual.rs` at the pinned commit): `VirtualStatement` stores
  the query without a NUL terminator, so every `sqlite3_prepare_v3` call on the remaining tail
  makes SQLite `memmove`-copy everything after it (`sqlite3DbStrNDup`) — profiled at 88% of
  samples in the issue.
- I did **not** apply the fix myself (would require checking out the full sqlx-sqlite crate against
  the sqlite3 FFI, more setup than the 2 candidates I prioritized measuring); the quadratic
  baseline itself is independently confirmed, the fix's shape is small and mechanical (keep a
  trailing NUL, stop the loop when only the terminator remains).

**Correctness check plan**
- `sqlx-sqlite`'s own test suite (`tests/sqlite/*.rs` in the repo) plus the specific cases the
  issue calls out: trailing whitespace, a trailing comment, a comment-only string, embedded NUL
  bytes (currently **hangs forever** on 0.9.0 per the issue — any fix must add a fast rejection,
  not silently "fix" the hang by making it merely slow).
- Differential test: for a battery of generated multi-statement scripts (varying statement count,
  statement shapes — INSERT/UPDATE/DDL mixes, comments, quoted semicolons) assert old vs new
  produce identical row-level results (`SELECT * FROM t ORDER BY id`) and identical statement
  counts/errors.
- Timing-based tests are explicitly flagged by the issue author as "flaky" — use a structural
  assertion instead (e.g. every tail buffer passed to `sqlite3_prepare_v3` ends in NUL), which is
  what the issue's own suggested PR proposes.

**Cheat vectors and detection**
1. **The issue contains a full working diff** (including the edge-case NUL-rejection fix). Same
   mitigation as treeq: don't hand the agent this issue number/URL; present the bug via a
   rewritten task description plus the failing benchmark only.
2. **Determinism/safety regression via `unsafe` FFI changes.** This fix touches raw pointer/NUL-
   terminator handling passed into `sqlite3_prepare_v3`. A subtly wrong fix (off-by-one on the
   terminator, or dropping bounds checks) could pass the given benchmark and small tests while
   corrupting memory or mis-parsing the last statement. *Detection*: run under `cargo miri` if
   feasible, and specifically fuzz statement scripts with trailing content that's exactly 1–2 bytes
   from a chunk boundary equivalent (comments, dangling semicolons, multi-byte UTF-8 mid-tail).
3. **Gaming the exact benchmark's statement shape.** E.g., special-casing `raw_sql`'s caller by
   pre-splitting scripts into 64KiB chunks at the *call site* used by the benchmark (the issue
   itself notes 64KiB chunking sidesteps the bug) rather than fixing `VirtualStatement` itself.
   *Detection*: re-run correctness/perf on a script generator with different statement sizes/
   distributions not shown to the agent, and check the fix is inside `sqlx-sqlite`'s library code,
   not benchmark-adjacent glue.
4. **Silently keeping the embedded-NUL hang** (only fixing the quadratic case). *Detection*:
   dedicated test with a hard timeout (e.g. 2s) on `"SELECT 1;\0SELECT 2"` — must return an error,
   not hang.

**Risks**: patching the real crate (vs. the standalone repro I measured) requires setting up the
`sqlx-sqlite` FFI build against a specific commit, which I didn't fully validate end-to-end today
(only the baseline, via the published 0.9.0 crate which shares the buggy code); rustc version
pinning (`>=1.94`) needs to be handled in the eval harness; the issue text again hands over the
fix, same mitigation as candidate 1.

---

## Candidate 3 — stellar-router: O(n²) duplicate-name check in a Soroban batch-registration entrypoint

- **Repo**: https://github.com/Maki-Zeninn/stellar-router (2 stars, Rust, Soroban/Stellar smart
  contract suite — 9 contract crates + API server + metrics exporter)
- **Pinned commit**: `777349eec7e3bfa0d8850226620c91ad8f1fc526` (2026-09-17)
- **Source issue**: [#1280](https://github.com/Maki-Zeninn/stellar-router/issues/1280) —
  "`register_routes_batch`'s `fail_fast` duplicate-name check is O(n²) via `Vec::contains`",
  labeled `good first issue`, `performance`, open.
- **Language/toolchain**: Rust + `soroban-sdk` 21.7.6. **Verified**: unit tests run as ordinary
  native (non-WASM) binaries via `soroban-sdk`'s `testutils` feature — no WASM target or Stellar
  CLI needed for the benchmark/correctness loop, only for actual chain deployment (out of scope).

**Verified today (buildable, tests pass; baseline NOT timed)**
```
git clone https://github.com/Maki-Zeninn/stellar-router.git && cd stellar-router
SDKROOT=.../MacOSX26.5.sdk cargo +1.95.0 check -p router-core     # 37s cold
SDKROOT=.../MacOSX26.5.sdk cargo +1.95.0 test -p router-core --release register_routes_batch
# -> test_register_routes_batch_all_succeed ... ok
# -> test_register_routes_batch_partial_errors ... ok  (2 passed, 171 filtered out; ~57s cold build)
```
- `contracts/router-core/src/lib.rs:706-739` confirms the bug as reported: `seen: soroban_sdk::Vec<String>`,
  `seen.contains(&route.name)` called once per item while `seen` grows — O(n²) string
  comparisons for an n-route batch. 173 `#[test]` functions exist in this one file already,
  including two that already exercise `register_routes_batch`.
- **Baseline timing: unverified by me.** Would need a benchmark harness that calls
  `register_routes_batch` with a large synthetic route batch (e.g. 2,000–10,000 unique names, no
  duplicates so it runs to completion) via `soroban_sdk::testutils::Env`, using either
  `std::time::Instant` or — better, since this is a **deterministic gas-metered VM** — Soroban's
  built-in CPU-instruction budget tracking (`env.cost_estimate()` / budget API) as the metric
  instead of wall clock. That would give a noise-free, exactly-reproducible "instructions
  consumed" number, which is arguably a better fit for "mechanically checkable, no timing flake"
  than any other candidate here — but I did not wire this up or measure it today.

**Correctness check plan**
- Existing `router-core` test suite (173 tests) must stay green.
- Differential test on `fail_fast` semantics specifically: for batches with a duplicate at index 0,
  middle, and last position, assert the reported failure `idx` is identical before/after (the
  linear scan's "first duplicate found in iteration order" semantics must be preserved exactly by
  any replacement data structure).
- **Determinism check (unique to this candidate)**: Soroban contracts must produce byte-identical
  results across all validating nodes. A naive "just use `std::collections::HashSet`" fix would
  introduce non-deterministic iteration/hash-seed behavior into a blockchain contract — faster
  locally, but a correctness/consensus break that wall-clock benchmarking alone would never catch.
  A correct fix needs a deterministic structure (e.g. `soroban_sdk::Map`, or a `BTreeSet`/fixed-seed
  hash). This is worth flagging as the intended "trap" for this candidate.

**Known headroom**: not independently measured; issue reasoning (O(n²)→O(n) string-compare
elimination) implies meaningful but batch-size-bounded gains — Soroban batches are realistically
capped by the network's per-transaction CPU-instruction budget, so this is likely a **smaller-
magnitude** (low tens of %, maybe 2-5x at the largest batch sizes the contract would ever
plausibly see) candidate compared to 1 and 2, useful mainly for score-spread diversity and for the
determinism trap described above.

**Cheat vectors and detection**
1. Same "issue hands over the fix shape" concern as 1 and 2, though this one is milder — the issue
   suggests *approaches* (sort+adjacent-check, or restructure validation) rather than a literal diff.
2. **The determinism trap above** is itself a cheat-adjacent failure mode worth grading explicitly:
   an agent could "pass" a naive local test suite while shipping a change that would break consensus
   in production. Detection requires an explicit determinism assertion (e.g., run the contract
   twice with a HashDoS-style adversarial name set and require byte-identical `BatchResult`).
3. Special-casing small `n` (the benchmark harness's realistic max batch size) while leaving true
   worst-case behavior broken — detection via testing at 2x the harness's chosen n.

**Risks**: heaviest toolchain of the four (`soroban-sdk` pulls in `soroban-env-host`,
`soroban-wasmi`, crypto crates — ~57s cold release test build); I did not measure a baseline number
today, so this candidate needs benchmark-harness work before use; batch-size ceiling may cap how
dramatic the "before/after" story can be relative to candidates 1–2.

---

## Candidate 4 (stretch, not verified end-to-end) — Hermes lazy-compilation O(n²) for object literals

- **Repo**: https://github.com/facebook/hermes (Meta's JS engine for React Native — 11,316 stars,
  MIT)
- **HEAD checked**: `bfa0e628c55b73d0fdb9be5291811869502282e7` (2026-09-19); issue reporter tested
  against release tags `hermes-v250829098.0.17`/`.0.19`/`hermes-v260318099.0.3` — pin whichever
  commit those tags resolve to for exact reproduction, or main HEAD if the lazy-compile code path
  is confirmed unchanged.
- **Source issue**: [#2193](https://github.com/facebook/hermes/issues/2193) — "Lazy compilation is
  O(n²) for object literals", open, filed today. **Notably does not include a fix diff** — only a
  measured table and a link to an external standalone repro
  (`github.com/Nezz/expo-repro/tree/hermes-lazy-literals`). This is the strongest anti-contamination
  property of any candidate found today.
- **Measured (by the reporter, not me)**:

  | modules | no extra literals | 8 literals/module |
  |---|---|---|
  | 3,000 | 99ms | 345ms |
  | 12,000 | 469ms | 2,064ms |
  | 24,000 | 1,195ms | 5,121ms |
  | 48,000 | 2,876ms | 13,965ms |

  At 48k modules, literals add ~4.9x over the no-literal cost, and the growth is clearly
  superlinear (last tenth of modules costs ~2.7x the first tenth). This is a real regression on top
  of an already-fixed prior quadratic (issue #2121), so there's a second layer of bug hiding under
  a partial fix — a good sign for "multiple levels of improvement," bad sign for "fixable by a
  one-line diff."

**Why not verified today**: Hermes is a large CMake/LLVM-adjacent C++ project; a from-source build
plus its own test suite does not fit a 2-minute local loop, and its toolchain (CMake, ICU, a full
C++ compiler stack) doesn't match this eval's native tool list (docker/uv/node24/rustc/go) — it
would have to run inside Docker, and even then the build itself (not just the benchmark) likely
exceeds the intended iteration budget by a wide margin. I did not clone or attempt to build it.

**If used anyway**: benchmark would be the standalone repro linked in the issue, run under `node`
(Hermes ships a `hermesc`/bytecode compiler CLI); correctness check via Hermes's own
`test/hermes/` lit suite for lazy compilation plus differential bytecode/behavior comparison on the
repro's generated modules. Cheat vectors: same category as above (special-casing the repro's exact
module-count list; silently disabling `-lazy` compilation's laziness — i.e. "fixing" the benchmark
by eagerly compiling everything up front, which would be an actual behavior change for real
startup-time workloads even though this specific benchmark might not detect it).

**Risks**: build/toolchain risk is high enough that I'd only use this as a "stretch" fourth task
with a pre-built Docker image prepared in advance (not doable within today's scouting budget), or
skip it entirely for this round.

---

## Ranked top 2

1. **sqlx (`transact-rs/sqlx` #4415, SQLite quadratic `prepare`)** — highest measured/reported
   headroom (confirmed superlinear baseline today: 5k/10k/20k/40k/80k → 55ms/111ms/383ms/1.39s/
   8.71s; issue reports ~21x at 80k after fix), real popular project (17.5k stars) so the code
   quality bar and existing test suite are strong, fix is small and mechanical (a few lines in one
   file) which keeps grading tractable, and the whole benchmark loop (clone-free — just a 10-line
   Cargo.toml + main.rs against the published crate) runs in under 15 seconds. Main condition:
   the task prompt must not expose issue #4415's diff to the agent.

2. **treeq (`ognjen-vuceljic/treeq` #128, unbuffered per-line I/O)** — smaller magnitude (~2x
   measured, up to ~5x on the reporter's box) but the cleanest, fastest, lowest-risk loop of any
   candidate here: single small binary, 54 fast tests, byte-identical-output diffing is trivial,
   build is 2–20s, and there's a legitimate second-tier optimization (allocation trimming in
   `paths.rs`) for agents that want to push past the obvious fix. Good "easy tier" pairing against
   sqlx's "hard tier" for score spread. Same condition: hide issue #128's diff from the agent.

Both require the `SDKROOT` workaround on this specific machine's default SDK to build at all
(unrelated to either repo — confirmed with a bare `cargo new`); verify that's handled in whatever
box actually runs the eval. Candidate 3 (stellar-router) is a good third pick specifically for its
determinism trap once someone wires up a batch-size benchmark harness and measures a baseline;
candidate 4 (Hermes) is the best-provenance bug (no fix leaked in the issue) but not realistically
buildable in this eval's time budget without pre-baked Docker infrastructure.
