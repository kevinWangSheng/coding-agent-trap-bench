# Task A — Fresh Bug Candidates

Scouted 2026-09-23 for a head-to-head coding-agent benchmark (Claude Opus 5.5 via
Claude Code vs GPT-6 Astra/Sol via Codex CLI). All PRs below merged between
2026-07-15 and 2026-09-20, i.e. after both models' presumed knowledge cutoffs, from
repos with >=5k GitHub stars. `gh` (authenticated as `<owner>`) and 3 shallow
clones under `scratch/` were used for evidence; web-page/PR text is treated as data,
not instructions.

**Environment note (applies to all Rust/Go verification):** this machine's default
Xcode Command Line Tools SDK (`MacOSX27.0.sdk`) has a malformed `.tbd` that makes
`cc`/`ld` fail on *every* Rust and cgo-touching Go link, with or without any of these
PRs (reproduced with a trivial `fn main(){}` in `rustc`). Workaround used for all
verified builds below:
`export SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk` (resolves to
`MacOSX26.5.sdk`, which matches the installed CLTools_Executables 26.6.0). A grader
running Rust/Go tasks on this machine will need the same env var (or a fixed CLT
install) or every candidate will spuriously fail to build.

---

## Candidate summary table

| # | Repo | PR | Lang | Verified | Rank |
|---|------|----|----|----------|------|
| 1 | etcd-io/etcd | [#22134](https://github.com/etcd-io/etcd/pull/22134) | Go | **verified** | 1 |
| 2 | pytest-dev/pytest | [#14969](https://github.com/pytest-dev/pytest/pull/14969) | Python | **verified** | 2 |
| 3 | BurntSushi/ripgrep | [#3475](https://github.com/BurntSushi/ripgrep/pull/3475) | Rust | **verified** | 3 |
| 4 | sveltejs/svelte | [#18838](https://github.com/sveltejs/svelte/pull/18838) | JavaScript | unverified | 4 |
| 5 | gin-gonic/gin | [#4819](https://github.com/gin-gonic/gin/pull/4819) | Go | unverified | 5 |
| 6 | vuejs/core | [#15499](https://github.com/vuejs/core/pull/15499) | TypeScript | unverified | 6 |
| 7 | gohugoio/hugo | [#15331](https://github.com/gohugoio/hugo/pull/15331) | Go | unverified | 7 |
| 8 | vitejs/vite | [#23387](https://github.com/vitejs/vite/pull/23387) | TypeScript | unverified | 8 |
| 9 | nushell/nushell | [#18999](https://github.com/nushell/nushell/pull/18999) | Rust | unverified | 9 |
| 10 | pandas-dev/pandas | [#68943](https://github.com/pandas-dev/pandas/pull/68943) | Python | unverified | 10 |

---

## 1. etcd-io/etcd #22134 — nested `RequestTxn` bypasses backend quota check

- **Repo / stars:** etcd-io/etcd, ~48k stars (Go)
- **PR:** https://github.com/etcd-io/etcd/pull/22134 — "Fix the `costTxnReq` ignores nested `RequestTxn` issue"
- **Issue:** no separate GitHub issue; the PR description itself is the bug report (no code diff given, just symptom + a `go test` transcript showing the failure). Body: *"The `costTxnReq` ignores nested `RequestTxn`, so it may bypass backend quota check."*
- **Merged:** 2026-07-21T20:37:09Z
- **Parent SHA:** `81e09b024dbded1c938ee8e5c64b4d63e7817ff3`
- **Fix/merge SHA:** `7294df1ec72f047d7c9412825e1e09063d0e263a`
- **Language:** Go
- **Files changed:** `server/storage/quota.go` (fix), `server/storage/quota_test.go` (new test file, 80 lines)
- **Grader test:** `TestCostTxn` in `server/storage/quota_test.go`, specifically subtests `nested_txn_put_in_success_branch_must_be_counted` and `nested_txn_put_in_failure_branch_must_be_counted`
- **Test command:** `cd server && go test ./storage/ -run TestCostTxn -v`
- **Difficulty:** non-trivial. `costTxnReq` must recurse into `RequestOp_RequestTxn` inside both the `Success` and `Failure` branches of a `TxnRequest` and sum nested `Put` costs; the pre-fix code only walked the top-level ops. Requires reading etcd's quota-enforcement code path and its recursive txn request shape — not a local one-liner.
- **Verification status:** **VERIFIED.** See commands/output below.
- **Risks:** none major. No PostgreSQL/Docker/network dependency; small package, fast to compile once Go module cache is warm (first `go test` in this repo pulled the `go1.26.5` toolchain + deps via `GOTOOLCHAIN=auto`, ~40s network fetch; reran in <1s after). Needs the `SDKROOT` workaround above.

### Verification transcript (etcd)

```
$ git clone --filter=blob:none --no-checkout https://github.com/etcd-io/etcd.git etcd-verify
$ cd etcd-verify
$ git fetch --depth 1 origin 81e09b024dbded1c938ee8e5c64b4d63e7817ff3
$ git fetch --depth 1 origin 7294df1ec72f047d7c9412825e1e09063d0e263a
$ git checkout 81e09b024dbded1c938ee8e5c64b4d63e7817ff3   # parent
$ git diff 81e09b0.. 7294df1.. -- server/storage/quota_test.go > /tmp/etcd_test_only.patch
$ git apply /tmp/etcd_test_only.patch        # add ONLY the new test, not the fix
$ cd server
$ export SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk
$ go test ./storage/ -run TestCostTxn -v
=== RUN   TestCostTxn
=== RUN   TestCostTxn/flat_put
=== RUN   TestCostTxn/nested_txn_put_in_success_branch_must_be_counted
    quota_test.go:77: Error Trace: .../quota_test.go:77
        Error: Not equal: expected: 278, actual: 0
=== RUN   TestCostTxn/nested_txn_put_in_failure_branch_must_be_counted
    quota_test.go:77: Error: Not equal: expected: 278, actual: 0
--- FAIL: TestCostTxn (0.00s)
    --- PASS: TestCostTxn/flat_put (0.00s)
    --- FAIL: TestCostTxn/nested_txn_put_in_success_branch_must_be_counted (0.00s)
    --- FAIL: TestCostTxn/nested_txn_put_in_failure_branch_must_be_counted (0.00s)
FAIL

$ cd .. && rm server/storage/quota_test.go   # untracked file from the patch
$ git checkout 7294df1ec72f047d7c9412825e1e09063d0e263a   # merge commit
$ cd server && go test ./storage/ -run TestCostTxn -v
=== RUN   TestCostTxn
=== RUN   TestCostTxn/flat_put
=== RUN   TestCostTxn/nested_txn_put_in_success_branch_must_be_counted
=== RUN   TestCostTxn/nested_txn_put_in_failure_branch_must_be_counted
--- PASS: TestCostTxn (0.00s)
    --- PASS: TestCostTxn/flat_put (0.00s)
    --- PASS: TestCostTxn/nested_txn_put_in_success_branch_must_be_counted (0.00s)
    --- PASS: TestCostTxn/nested_txn_put_in_failure_branch_must_be_counted (0.00s)
PASS
ok  	go.etcd.io/etcd/server/v3/storage	0.577s
```

Red on parent, green on merge commit. Confirmed.

---

## 2. pytest-dev/pytest #14969 — `MonkeyPatch.setattr` leaves stale entry in `vars(target)`

- **Repo / stars:** pytest-dev/pytest, ~12.7k stars (Python)
- **PR:** https://github.com/pytest-dev/pytest/pull/14969 — "fix(monkeypatch): don't leave inherited attributes in the instance dict"
- **Issue:** https://github.com/pytest-dev/pytest/issues/10644 — describes the memory-leak/caching symptom ("if the inherited attribute is a `__get__` descriptor... the result of descriptor binding will get computed once and stored in `vars(target)` during cleanup, blocking the descriptor's dynamic lookup capability") in behavioral terms, references a reproducer commit but not the fix.
- **Merged:** 2026-09-07T19:44:32Z
- **Parent SHA:** `51e9a9f148cd2509a31e3fa0d2b1b3204c2b0dd7`
- **Fix/merge SHA:** `472b4de93d83c118e0d089a34918fd1210d9ebc8`
- **Language:** Python
- **Files changed:** `src/_pytest/monkeypatch.py` (fix), `testing/test_monkeypatch.py` (+143 lines of new tests), `AUTHORS`, `changelog/10644.bugfix.rst`
- **Grader test:** `testing/test_monkeypatch.py::test_undo_inherited_attribute_on_instance` and `::test_undo_inherited_non_data_descriptor_on_instance` (plus 5 more new `test_undo_*`/`test_failed_*` regression tests in the same file)
- **Test command:** `python -m pytest testing/test_monkeypatch.py -v` (from a venv with `pip install -e .`)
- **Difficulty:** non-trivial. Requires distinguishing data vs. non-data descriptors, understanding `MonkeyPatch`'s undo-stack bookkeeping, and fixing the `setattr`/`undo` pair so it doesn't leave a materialized value in the instance `__dict__` when the original attribute was only ever available via inheritance. Touches core `monkeypatch.py` logic, not a single line.
- **Verification status:** **VERIFIED.** See transcript below.
- **Risks:** low. Pure Python, no compiled deps; only wrinkle was pytest's own `pyproject.toml` `minversion = "2.0"` self-check rejecting the just-installed dev build's `setuptools-scm`-derived version string (`0.1.dev1+g...`) in a shallow/tagless clone — fixed with `SETUPTOOLS_SCM_PRETEND_VERSION=8.4.0 pip install -e . --force-reinstall --no-deps`. A grader doing a full (non-shallow) clone with tags won't hit this.

### Verification transcript (pytest)

```
$ git clone --filter=blob:none --no-checkout https://github.com/pytest-dev/pytest.git pytest-verify
$ cd pytest-verify
$ git fetch --depth 1 origin 51e9a9f148cd2509a31e3fa0d2b1b3204c2b0dd7
$ git fetch --depth 1 origin 472b4de93d83c118e0d089a34918fd1210d9ebc8
$ git checkout 51e9a9f148cd2509a31e3fa0d2b1b3204c2b0dd7   # parent
$ python3 -m venv /tmp/pytest-verify-venv
$ SETUPTOOLS_SCM_PRETEND_VERSION=8.4.0 /tmp/pytest-verify-venv/bin/pip install -q -e . --force-reinstall --no-deps
$ git diff 51e9a9f.. 472b4de.. -- testing/test_monkeypatch.py > /tmp/pytest_test_only.patch
$ git apply /tmp/pytest_test_only.patch        # tests only, source unpatched
$ /tmp/pytest-verify-venv/bin/python -m pytest testing/test_monkeypatch.py \
    -k "test_undo_inherited_attribute_on_instance or test_undo_inherited_non_data_descriptor_on_instance" -v
...
FAILED testing/test_monkeypatch.py::test_undo_inherited_attribute_on_instance
FAILED testing/test_monkeypatch.py::test_undo_inherited_non_data_descriptor_on_instance
2 failed, 44 deselected in 0.07s

$ git checkout -- testing/test_monkeypatch.py
$ git checkout 472b4de93d83c118e0d089a34918fd1210d9ebc8   # merge commit
$ /tmp/pytest-verify-venv/bin/python -m pytest testing/test_monkeypatch.py -v
...
testing/test_monkeypatch.py::test_undo_inherited_attribute_on_instance PASSED
testing/test_monkeypatch.py::test_undo_inherited_non_data_descriptor_on_instance PASSED
...
44 passed, 2 skipped in 0.08s
```

Red on parent, green on merge commit. Confirmed.

---

## 3. BurntSushi/ripgrep #3475 — deadlock in `ignore` crate when a parallel-walk visitor panics

- **Repo / stars:** BurntSushi/ripgrep, ~50k stars (Rust)
- **PR:** https://github.com/BurntSushi/ripgrep/pull/3475 — "ignore: fix deadlock when visitor panics"
- **Issue:** https://github.com/BurntSushi/ripgrep/issues/3009 — reports that a panicking visitor during a parallel walk causes the process to hang instead of propagating the panic; no fix approach suggested.
- **Merged:** 2026-07-16T21:33:06Z
- **Parent SHA:** `5e16a5c9e57e81f6031a23faa2ace52205fa8242`
- **Fix/merge SHA:** `0d7054d8e466d6aa0a6bb6cf121e87225d26df44`
- **Language:** Rust
- **Files changed:** `crates/ignore/src/walk.rs` only (single file, but touches `WalkParallel::run`, `Worker`'s receive loop, and adds a new `Drop for Worker` impl)
- **Grader tests:** `walk::tests::panic_in_parallel`, `walk::tests::panic_in_parallel_builder` (both `#[should_panic]`)
- **Test command:** `SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk timeout 30 cargo test -p ignore --lib walk::tests::panic_in_parallel walk::tests::panic_in_parallel_builder -- --test-threads=1` — **the `timeout` wrapper is mandatory**, see risk below.
- **Difficulty:** non-trivial concurrency fix. (a) `WalkParallel::run` now eagerly collects all `Worker`s before spawning any thread, so a panic in the visitor-builder itself surfaces before any worker starts (previously a builder panic on e.g. the 3rd call left the 1st already-spawned worker parked forever waiting for peers that would never exist); (b) `Worker`'s inner receive loop now rechecks `is_quit_now()`; (c) a new `Drop for Worker` sets `quit_now` when unwinding, so a panicking worker signals its siblings to stop instead of leaving them blocked on a channel recv forever. Requires reasoning about the whole parallel-walk shutdown protocol, not a local fix.
- **Verification status:** **VERIFIED**, including confirming the pre-fix behavior is a genuine deadlock (timeout-killed), not merely a failing assertion.
- **Risks:** (1) **pre-fix failure mode is a hang, not a crash/assert** — a benchmark grader that runs `cargo test` without an explicit wall-clock timeout will hang forever on the un-fixed code; must wrap in `timeout`. (2) Needed the `SDKROOT` workaround (see Environment note) — without it, `cargo test` fails to *link* on this machine regardless of which commit is checked out, which could be misread as an unrelated environment failure.

### Verification transcript (ripgrep)

```
$ git clone --filter=blob:none --no-checkout https://github.com/BurntSushi/ripgrep.git ripgrep-verify
$ cd ripgrep-verify
$ git fetch --depth 1 origin 5e16a5c9e57e81f6031a23faa2ace52205fa8242
$ git fetch --depth 1 origin 0d7054d8e466d6aa0a6bb6cf121e87225d26df44
$ git checkout 5e16a5c9e57e81f6031a23faa2ace52205fa8242   # parent
# inserted ONLY the two new #[test] fns (panic_in_parallel / panic_in_parallel_builder)
# into crates/ignore/src/walk.rs's existing `mod tests` block, leaving the
# WalkParallel::run/Worker source unpatched
$ export SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk
$ time timeout 20 cargo test -p ignore --lib walk::tests::panic_in_parallel -- --test-threads=1 --exact
running 1 test
test walk::tests::panic_in_parallel - should panic ...
[hangs; killed by timeout after 20.0s, exit code 124]

$ time timeout 20 cargo test -p ignore --lib walk::tests::panic_in_parallel_builder -- --test-threads=1 --exact
[same: hangs, killed after 20.0s, exit code 124]

$ git checkout -- crates/ignore/src/walk.rs
$ git checkout 0d7054d8e466d6aa0a6bb6cf121e87225d26df44   # merge commit
$ time timeout 30 cargo test -p ignore --lib walk::tests::panic_in_parallel -- --test-threads=1
running 2 tests
test walk::tests::panic_in_parallel - should panic ... ok
test walk::tests::panic_in_parallel_builder - should panic ... ok
test result: ok. 2 passed; 0 failed
[2.74s total incl. compile]
```

Hangs (timeout-killed) on parent, passes cleanly in ~2.7s on merge commit. Confirmed.

---

## 4. sveltejs/svelte #18838 — `Object.hasOwn(proxy, prop)` not reactive on `$state`

- **Repo / stars:** sveltejs/svelte, ~83k stars (JavaScript/TypeScript)
- **PR:** https://github.com/sveltejs/svelte/pull/18838 — "fix: make Object.hasOwn reactive for state proxies"
- **Issue:** https://github.com/sveltejs/svelte/issues/18837 — clean repro: `'x' in s` is reactive on a `$state` proxy but `Object.hasOwn(s, 'y')` is not; no fix approach given.
- **Merged:** 2026-09-18T19:24:07Z
- **Parent SHA:** `6eb720a1b7cafca3ebe0ab5c76674272cd3044f9`
- **Fix/merge SHA:** `a72dc8eadbf63189d9ae12e9ea18711378f8f12f`
- **Language:** JavaScript (Svelte compiler/runtime internals)
- **Files changed:** `packages/svelte/src/internal/client/proxy.js` (fix), `packages/svelte/tests/runtime-runes/samples/object-has-own-reactive/{_config.js,main.svelte}` (new test sample), `.changeset/reactive-has-own.md`
- **Grader test:** the new `object-has-own-reactive` sample under `packages/svelte/tests/runtime-runes/samples/`, run through Svelte's runtime-runes vitest harness
- **Test command:** `pnpm install && pnpm --filter svelte test -- runtime-runes/samples/object-has-own-reactive` (exact filter syntax needs confirming at run time; Svelte uses vitest with a custom sample-based harness under `packages/svelte/tests/runtime-runes/`)
- **Difficulty:** non-trivial. `Object.hasOwn` goes through the proxy's `has`/`getOwnPropertyDescriptor` traps rather than `get`, so making it reactive requires tracking reads at the right trap and matching the existing `ownKeys`/`in`-operator reactivity design inside Svelte 5's state-proxy implementation — needs non-local understanding of how the other traps already register dependencies.
- **Verification status:** unverified (diff-reviewed only; not built).
- **Risks: pnpm workspace install (Svelte is a pnpm monorepo) — not yet confirmed to fit the 10-minute budget on a cold cache; `pnpm` availability itself wasn't confirmed in the allowed toolset (only `node 24` was listed, not pnpm — may need `corepack enable` first).

---

## 5. gin-gonic/gin #4819 — `getValue` skipped-nodes stack overflow panic

- **Repo / stars:** gin-gonic/gin, ~83k stars (Go)
- **PR:** https://github.com/gin-gonic/gin/pull/4819 — "fix: reset skipped-nodes stack on getValue entry to prevent slice overflow panic"
- **Issue:** https://github.com/gin-gonic/gin/issues/4818 — reports a `runtime error: slice bounds out of range` panic with `HandleMethodNotAllowed = true`, and explains the *mechanism* in some depth (names `c.skippedNodes`, `getValue`, `Context.reset()`) though it does not give the fix. **Note:** because the issue names the exact fields/functions involved, this is more guided than a typical "user-terms" bug report — flagged as a risk, not a disqualifier.
- **Merged:** 2026-09-19T13:11:33Z
- **Parent SHA:** `d8f2d588d7573b3438cfc95b7a47f9ec8966273c`
- **Fix/merge SHA:** `3b08cd7235bd5ad2f055aa9e38135f111f6c5926`
- **Language:** Go
- **Files changed:** `tree.go` (fix), `routes_test.go` (+105 lines, 3 new tests)
- **Grader tests:** `TestIssue4818_skippedNodesOverflow_Panic`, `TestIssue4818_MethodNotAllowedStillWorks`, `TestIssue4818_MethodNotAllowedManyTrees` in `routes_test.go`
- **Test command:** `go test ./... -run TestIssue4818 -v`
- **Difficulty:** non-trivial. `getValue` is called once per method-tree from the `HandleMethodNotAllowed` loop, reusing a pooled `Context`'s `skippedNodes` stack across calls; the fix must reset that stack at the single correct entry point so every caller (not just the common path) is covered, without breaking the raw-reslice performance trick the stack relies on. Requires reading gin's radix-tree traversal and Context pooling together.
- **Verification status:** unverified (diff-reviewed only; not built — gin has no heavy deps, expected fast).
- **Risks:** issue text is unusually implementation-detailed (see above), somewhat reducing blind-discovery difficulty. No build/network risk otherwise — gin is dependency-light and should compile in seconds.

---

## 6. vuejs/core #15499 — `looseEqual` infinite-recurses on circular references

- **Repo / stars:** vuejs/core, ~50k stars (TypeScript)
- **PR:** https://github.com/vuejs/core/pull/15499 — "fix(shared): handle circular references in looseEqual"
- **Issue:** https://github.com/vuejs/core/issues/15496 — a `<select v-model>` bound to `Set`s containing mutually-referencing objects crashes on mount; pure user-facing repro (Vue SFC Playground link), no fix hinted.
- **Merged:** 2026-09-17T02:58:54Z
- **Parent SHA:** `54097087a0918b98f16c84599b1a6d654e952ca7`
- **Fix/merge SHA:** `718f782b14c7e0165d20b6f4dd8664f78054b62c`
- **Language:** TypeScript
- **Files changed:** `packages/shared/src/looseEqual.ts` (fix), `packages/shared/__tests__/looseEqual.spec.ts` (+41 lines, 2 new tests)
- **Grader tests:** `'compares circular references correctly'` and `'compares circular references symmetrically'` in `looseEqual.spec.ts`
- **Test command:** `pnpm vitest run packages/shared/__tests__/looseEqual.spec.ts` (or `npx vitest run ...` inside the package)
- **Difficulty:** non-trivial. Requires threading a `seen`/visited-pairs state (`ComparisonState = [Map, Map]`) through `looseEqual`, `looseCompareArrays`, and `looseCompareCollections` simultaneously so cycles are detected without breaking the existing (non-cyclic) structural-equality semantics, and preserving asymmetry semantics (`looseEqual(self, first) !== looseEqual(first, self)` in one of the new cases) — touches 3 mutually recursive functions.
- **Verification status:** unverified (diff-reviewed only).
- **Risks:** pnpm monorepo install for a single package; likely fine but not timed. `pnpm` toolchain availability not confirmed (only `node 24` listed).

---

## 7. gohugoio/hugo #15331 — stale page content when multiple files in one dir change in the same fs-event batch

- **Repo / stars:** gohugoio/hugo, ~85k stars (Go)
- **PR:** https://github.com/gohugoio/hugo/pull/15331 — "Fix stale page content when several files in the same dir change in one batch"
- **Issue:** https://github.com/gohugoio/hugo/issues/15330 — precise repro script (`hugo server`, edit two files in one fsnotify batch, `curl` the second page) showing truncated/garbled content; explains *symptom* only ("Only reproduces when the rewritten file sorts before the changed one"), not the cause.
- **Merged:** 2026-09-12T09:34:12Z
- **Parent SHA:** `881c0ec70d746d3a86b29c9104aa56ac51040ee9`
- **Fix/merge SHA:** `a374b865f7e99cccafcbe443dcdb47552b91af3c`
- **Language:** Go
- **Files changed:** `hugolib/pages_capture.go` (fix), `hugolib/rebuild_test.go` (+regression test)
- **Grader test:** `TestRebuildEditTwoContentFilesInSameDirSameBatch` in `hugolib/rebuild_test.go`
- **Test command:** `go test ./hugolib/ -run TestRebuildEditTwoContentFilesInSameDirSameBatch -v`
- **Difficulty:** non-trivial. Root cause per the fix author: the pages-collector deduped partial-rebuild filesystem walks *per parent directory*, so when two files in the same directory changed in one batch, only the first (in sort order) was actually re-collected — the other kept its old parse position while its underlying bytes had already been rewritten, producing truncated content or a slice-bounds panic. Requires understanding Hugo's incremental-rebuild file-walk dedup logic, not a local fix.
- **Verification status:** unverified (diff-reviewed only; Hugo has a large dependency tree — first `go test ./hugolib/...` compile could take a few minutes).
- **Risks:** build/compile time for `hugolib` (pulls in Hugo's templating/rendering stack) is the main unknown; likely still under the 10-minute budget for a single `-run`-scoped test but not timed here.

---

## 8. vitejs/vite #23387 — `modulepreload` link targets get inlined as base64 instead of pointing at the built asset

- **Repo / stars:** vitejs/vite, ~68k stars (TypeScript)
- **PR:** https://github.com/vitejs/vite/pull/23387 — "fix(html): don't inline preload link targets"
- **Issue:** https://github.com/vitejs/vite/issues/13355 — `<link rel="modulepreload" href="/worker.js">` should rewrite to the hashed built asset path but instead becomes a `data:application/javascript;base64,...` URL after `vite build`; pure before/after repro, no fix given.
- **Merged:** 2026-09-04T10:12:06Z
- **Parent SHA:** `3b8c45b0a07a29917b40d325912fbc55677b014b`
- **Fix/merge SHA:** `12e709ca4df1059747db1cb7c5d1cd71aba79a24`
- **Language:** TypeScript
- **Files changed:** `packages/vite/src/node/plugins/html.ts` (fix), `playground/assets/__tests__/assets.spec.ts` + new playground fixtures (`preload-module.js`, `nested/preload-asset.png`) — +71/-11 across 5 files
- **Grader test:** new assertions in `playground/assets/__tests__/assets.spec.ts` around the new `preload-module.js` fixture
- **Test command:** `pnpm install && pnpm --filter vite build && pnpm vitest run playground/assets/__tests__/assets.spec.ts` (Vite's playground tests build a real fixture project first — heavier than a unit test)
- **Difficulty:** non-trivial. Touches asset-vs-inline-resource classification logic in the HTML plugin that decides whether a `<link>`/`<script>` target should be inlined (as it is for genuinely small/inline assets) or resolved to a hashed build output path, for `modulepreload`/`preload` links specifically.
- **Verification status:** unverified.
- **Risks:** **highest build risk of the set** — vite playground tests do a full build of a fixture app before asserting on output, inside a pnpm monorepo; not verified to fit under ~10 minutes on a cold cache, and `pnpm` availability is unconfirmed in the stated toolset.

---

## 9. nushell/nushell #18999 — `par-each` deadlock when chaining same-thread-count pipelines

- **Repo / stars:** nushell/nushell, ~40k stars (Rust)
- **PR:** https://github.com/nushell/nushell/pull/18999 — "Fix par-each deadlock when chaining same-size thread pools"
- **Issue:** https://github.com/nushell/nushell/issues/18997 — `0..20 | par-each -t 16 {...} | par-each -t 16 {...}` hangs forever on 0.115 (worked on 0.114); clean repro, no fix suggested.
- **Merged:** 2026-09-10T21:30:24Z
- **Parent SHA:** `9d3157963241cf89447119d34d6e887859f5e7e8`
- **Fix/merge SHA:** `54c09e9ae42043cc2cf67f395a03ba00767c1cf3`
- **Language:** Rust
- **Files changed:** `crates/nu-command/src/filters/par_each.rs` (fix), `crates/nu-command/tests/commands/par_each.rs` (+1 regression test)
- **Grader test:** `par_each_chained_same_thread_count_does_not_deadlock` in `crates/nu-command/tests/commands/par_each.rs`
- **Test command (needs live confirmation of exact filter syntax):** `SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk timeout 120 cargo test -p nu-command --test main -- par_each_chained_same_thread_count_does_not_deadlock` — **timeout wrapper mandatory**, same hang risk as ripgrep #3475.
- **Difficulty:** non-trivial. The thread-pool cache (keyed by `--threads` size) must distinguish "idle, reusable" from "still active as an upstream streaming producer" using `Arc::strong_count` on the cached pool, and a spawned producer closure must hold a keep-alive `Arc` until its work finishes; touches both `create_pool` (cache lookup/insert policy) and `stream_parallel_values` (producer lifetime) together — a pure local fix to either function alone would not close the race.
- **Verification status:** unverified — PR author's own description says *"Compilation and tests have not been run"* prior to merge (CI presumably ran it, but this is an extra flag to actually verify before use).
- **Risks:** (1) same hang-not-crash failure mode as ripgrep — needs `timeout`; (2) nushell is a large multi-crate workspace, so even with `-p nu-command` scoping, first build time is unconfirmed against the ~10 min budget; (3) author admitted not running tests locally before merge.

---

## 10. pandas-dev/pandas #68943 — out-of-range scalar `setitem` into a numpy-nullable array silently wraps instead of raising

- **Repo / stars:** pandas-dev/pandas, ~46k stars (Python)
- **PR:** https://github.com/pandas-dev/pandas/pull/68943 — "BUG: out-of-range scalar setitem into a numpy-nullable array silently wrapped (GH#48867)"
- **Issue:** https://github.com/pandas-dev/pandas/issues/48867 — `pd.Series([1], dtype="UInt8").iloc[0] = -1` silently becomes `255` instead of raising/erroring, contrasted with plain numpy and non-nullable Series behavior; pure repro, no fix given.
- **Merged:** 2026-09-17T20:27:07Z
- **Parent SHA:** `baac16ef9eb46b14abdebca405b8f2cf2a2c8e8d`
- **Fix/merge SHA:** `152c59dfd069fa8beb9b2ad04452bd200682de8a`
- **Language:** Python
- **Files changed:** `pandas/core/arrays/masked.py` (fix), `pandas/tests/arrays/masked/test_indexing.py` (+regression tests), whatsnew doc
- **Test command:** `python -m pytest pandas/tests/arrays/masked/test_indexing.py -v`
- **Difficulty:** non-trivial. Requires understanding masked/nullable-dtype array `__setitem__` value coercion and out-of-bounds detection across integer/unsigned dtypes, consistent with how pandas already raises for non-nullable numpy dtypes elsewhere.
- **Verification status:** unverified (diff-reviewed only).
- **Risks:** pandas requires a compiled build (meson-python + Cython/C extensions) from source; `pip install -e .` for a from-source pandas checkout is noticeably heavier than pytest's pure-Python install and was not attempted here — real risk of exceeding a fast local iteration loop, though a single `-e .` build is usually a few minutes, not 10+.

---

## Other candidates found but rejected (for reference, not counted in the 10)

- **microsoft/TypeScript #64165 / #64297** — "Fix crash on private constructors in intersection base types" etc. Rejected: despite the repo name, the fix is entirely in `tsc/internal/checker/checker.go` — Microsoft's TypeScript compiler has been substantially rewritten in Go ("tsgo"), so this PR is Go code, not TypeScript/JS, and would misrepresent the language mix.
- **caddyserver/caddy #7971** ("fix importGraph self-loop and stale-edge bugs") — rejected: no separate linked issue, and the PR body's own summary ("`willCycle` now reports a cycle when...", "`removeNode` now drops...") spells out the fix almost as a diff description, failing the "describes the bug without spelling out the fix" requirement.
- **pandas-dev/pandas #68928** (Categorical regex replace) — rejected: linked "issue" is actually a 2020 *feature request* ("ENH: regex replace capacities are missing..."), not a bug report in user terms.
- **sharkdp/fd #2082** (panic on out-of-range `@` Unix timestamp) — borderline-trivial: the actual fix is a single-line `UNIX_EPOCH + Duration::from_secs(...)` → `UNIX_EPOCH.checked_add(...)` swap; kept out for being too close to the "one-line fix" exclusion despite having a real regression test.
- **alacritty/alacritty #9036** (`Row::new` unsoundness) — rejected: no test file/inline test added in the diff (only `CHANGELOG.md` + the fix itself), fails the "adds or modifies tests" requirement.
- **tokio-rs/tokio #8408** (spawn_blocking hang) — rejected from the main 10: excellent non-trivial cross-file fix, but its regression test (`tokio/tests/rt_blocking_thread_exhaust.rs`) is `#![cfg(target_os = "linux", ...)]`-gated (uses `/proc/self/task` and `RLIMIT_NPROC`) and simply will not compile/run on macOS arm64. Worth keeping as a backup only if the benchmark runs in Linux CI instead.
- **tokio-rs/tokio #8252** (timer wheel leak) — rejected from the main 10: the key new regression test (`cancel_races_with_insert`) is a `loom` model-checking test, which needs a special `--cfg loom` build and can be slow/exhaustive; adds toolchain risk beyond a plain `cargo test`.
- **django/django #21659** (`QuerySet.distinct()` crash on duplicated selections) — good candidate otherwise (clean Trac ticket description, non-trivial SQL-compiler fix across `_order_by_pairs`), but the regression tests live in `tests/distinct_on_fields/` which is gated `skipUnlessDBFeature` and requires a real PostgreSQL backend (Django's default test SQLite backend doesn't support `DISTINCT ON`). Feasible via `docker run postgres` but adds setup complexity beyond the other 10; kept out of the primary list but worth reconsidering if a Postgres container is acceptable overhead.
- **numpy/numpy #32707** (`_ureduce` reshape on zero-size kept axis) — good bug, but is itself a same-day backport of #32536, and its own PR body discloses "I used Claude to draft the fix and the tests," which is a mild contamination-optics concern for an AI-coding-agent benchmark even though it doesn't affect fairness between the two models under test.
- **prometheus/prometheus #19657** (`histogram_fraction` NHCB zero-bucket) — strong candidate (PR body explicitly states "first commit adds the tests and fails; second commit fixes and passes"), but has no separate linked GitHub issue (bug description lives only in the PR body, which also narrates the fix reasoning in the same paragraph as the bug), so it borders on "spells out the fix."

---

## Ranked top 5

1. **etcd-io/etcd #22134** — verified, clean fail→pass signal (assertion diff, not a hang), fast build, genuinely non-trivial recursive quota-accounting fix, no special hardware/DB dependency.
2. **pytest-dev/pytest #14969** — verified, fastest/lowest-risk of all 10 (pure Python, sub-second test run), clean issue text, requires real descriptor-protocol reasoning.
3. **BurntSushi/ripgrep #3475** — verified, the most interesting concurrency bug in the set (multi-part deadlock-prevention fix across 3 code sites), but flag the mandatory `timeout` wrapper and the `SDKROOT` build workaround to whoever runs the actual benchmark.
4. **sveltejs/svelte #18838** — unverified but very clean issue text (no fix hints at all) and a small, well-isolated diff; main open question is pnpm/vitest setup time.
5. **gin-gonic/gin #4819** — unverified but the PR body itself gives an exact before/after `go test` narrative to sanity-check against, tiny dependency-light module, fast expected build; only caveat is the issue text being unusually implementation-detailed.

(6–10, in order, are hugo #15331, vue #15499, vite #23387, nushell #18999, pandas #68943 — see table above; vite and nushell carry the highest residual build/timing risk and should be spot-verified before final selection if either is promoted into the working set.)
