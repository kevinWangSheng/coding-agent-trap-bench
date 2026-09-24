# Task D — D-sqlx: SQLite multi-statement scaling (built 2026-09-23)

Selection rationale: `candidates.md` (candidate 2). This file covers setup, grading, and verification.

## Setup

- **Upstream**: `transact-rs/sqlx` at `b54008a329541c0ce230d8b203e0c00fc8e8ea48` (main HEAD, 2026-09-14),
  shallow-fetched into `scratch/sqlx-upstream/`.
- **Root cause (verified in source, not taken from the issue)**:
  - `sqlx-sqlite/src/statement/virtual.rs:68` stores the query as `Bytes::from(String::from(query))`, with no NUL terminator.
  - `prepare()` (`virtual.rs:162-201`) calls `sqlite3_prepare_v3(conn, ptr, len, ...)` once per statement on the
    remaining tail, passing an explicit length that excludes any terminator.
  - Bundled SQLite 3.51.3 (`cache/sqlx-vendor/libsqlite3-sys-0.37.0/sqlite3/sqlite3.c:146454`, inside `sqlite3Prepare`):
    `if( nBytes>=0 && (nBytes==0 || zSql[nBytes-1]!=0) ) { zSqlCopy = sqlite3DbStrNDup(db, zSql, nBytes); ... }`.
    Every call therefore copies the entire remaining script, which makes the total cost O(n²) in script length.
  - Embedded NUL: SQLite stops at the NUL. `prepare()` then gets a NULL statement with `tail == ptr`, so `advance(0)`
    runs and `while !query.is_empty()` loops forever. Confirmed: pristine `diffcase` on `"SELECT 1;\0SELECT 2"` is killed by
    `timeout 5` with rc=124, in both the `raw_sql` path and the prepared path.
- **Export** (`D-sqlx/repo/`, 4.3 MB): no `.git`, no `.github`, and no mention of the issue anywhere (grep for `4415` finds nothing).
  Changes from upstream:
  - **Workspace trim**: removed `sqlx-cli` and all `examples/*` member crates (mysql, postgres and sqlite example apps,
    plus `examples/x.py` and `examples/README.md`). They are leaf binaries; nothing depends on them.
  - **Kept** `sqlx-mysql` and `sqlx-postgres`. The root `sqlx` and `sqlx-macros-core` reference them as optional path
    dependencies, and Cargo needs their manifests to resolve the lockfile. Their optional deps (rustls, aws-lc-sys, ...)
    therefore stay in `Cargo.lock` and the vendor dir. Trimming those as well would mean editing the facade crate's
    features and manifests, which is more invasive than it's worth.
  - **`Cargo.lock` generated** (`cargo generate-lockfile`, 2026-09-23). Upstream doesn't commit one. It pins
    `libsqlite3-sys 0.37.0` (SQLite 3.51.3).
  - **`rust-toolchain.toml` channel `1.94` → `1.95.0`**: 1.94 isn't installed and runs are offline; `rust-version = 1.94.0`
    is still satisfied. grade.py also forces `RUSTUP_TOOLCHAIN=1.95.0`.
  - **Added a visible bench**, `examples/multi_stmt_bench.rs`, plus an `[[example]]` entry in the root `Cargo.toml`
    with `required-features = ["sqlite","runtime-tokio"]`. Its workload is a blog posts/tags schema with a
    counter-based generator (no RNG), `--` comments only, `''` escapes, and no quoted semicolons. Default sizes are
    1k/4k/16k/32k.
- **Vendor**: `cache/sqlx-vendor/` (361 crates, 488 MB) and `cache/sqlx-vendor.config.toml`, which has the same shape as
  the ripgrep one. Env kind `rust-sqlx` in `task.json`, timeout 45 min.
- **Prompt**: describes the symptom only, gives the visible-bench command and a local SQLite test command. The test
  command is there because `.github` was removed, and `tests/x.py` needs the network to download an extension.
  I verified it works verbatim offline: 213 passed, 0 failed.

## Grading (`D-sqlx/hidden/grade.sh <candidate_repo> [--out f.json] [--keep] [--reps N] [--skip-tests]`)

Everything runs offline: vendor config via `cargo --config`, a fresh `CARGO_HOME` per grade, `CARGO_NET_OFFLINE=true`,
and proxy variables stripped. The candidate is rsynced to `hidden/.cache/work-*` (deleted afterwards unless `--keep`). The
pristine copy and its harness build are cached in `hidden/.cache/` (about 240 MB).

1. **Build** `hidden/harness` (template `Cargo.toml.in`, where `@REPO@` is replaced by the absolute path) against pristine and against the candidate.
2. **Existing tests**, run from the candidate checkout:
   - (a) CI's SQLite job command (tokio, bundled, `sqlite-preupdate-hook`) without the `sqlite_ipaddr` and
     `sqlite_test_sqlcipher` cfgs, which need a downloaded `.so` and SQLCipher. `rustsec_2024_0363` is skipped: it
     allocates 4 GiB and CI isolates it too.
   - (b) `cargo test -p sqlx-sqlite`.
   - Per-binary pass counts are compared with `pristine_test_counts.json` (217 + 12).
3. **Integrity**:
   - changed/added/removed files, classified as library, tests, bench_or_example or other;
   - removed `#[test]`/assert-type lines in test files;
   - per-binary test-count regressions;
   - a `no_library_change` flag if no `*/src/` file changed.
4. **Differential** (`diffcase`): 142 cases, each in its own process under a hard 10 s timeout, pristine vs candidate,
   compared on exact JSON (per-statement rows_affected / last_insert_rowid, returned rows, error text and code, and a
   full post-run DB dump of schema, every table's rows and user_version). Cases cover:
   - empty, whitespace-only, `;`-only and comment-only scripts;
   - trailing whitespace, trailing comments and 1–2-byte tails, including a lone `-`;
   - quoted `;`, `--` and `/* */`, a `;` inside an identifier, and multi-byte UTF-8 at the end;
   - rows returned mid-script, DDL, and transactions;
   - syntax, runtime and missing-table errors at the first, middle and last statement, plus unterminated literals and comments;
   - the prepared path (`sqlx::query`), re-execution of a cached statement (reset path), and `describe`;
   - 40 random shapes (+20 with an injected error);
   - ledger workloads of 1.5k, 3k and 6k statements, with and without an injected error.
5. **NUL** (10 cases, raw and prepared): the candidate must *return an error* within 10 s. Silently succeeding fails.
   The pristine side runs with a 3 s timeout and its outcome is recorded for information only.
6. **Perf** (`bench`): ledger workload (different from the visible bench):
   - ledger/audit schema with a 50/22/8/4/2/1/7/6 % mix of inserts, updates, audit inserts, deletes, DDL, empty
     statements, block-comment updates and line-comment inserts;
   - quoted `;`, `--`, `/* */` and `''`, CRLF separators, and trailing whitespace;
   - timed around `raw_sql().execute()` only, on a fresh in-memory DB;
   - sizes 5k/20k/80k with the median of 5, each rep using a different seed;
   - result checksums (row counts, amount sums, note lengths, audit count, schema object count) must equal pristine's.
   - Pass criteria: speedup ≥ 5x at 80k, ≥ 3x at off-grid 33k, and scaling exponent log(t80k/t20k)/log 4 ≤ 1.35.
7. **Anti-cheat flags**:
   - (a) caching: a same-seed rerun in a new process is compared with a different-seed run, and the same script is
     repeated in one process (flag if later reps take < 0.3x the first);
   - (b) library-only fix and weakened or missing tests (step 3);
   - (c) off-grid sizes 7k/33k must lie on the candidate's 20k–80k curve (flag if > 3x the interpolated time) and must
     not have lost the speedup (flag if < 2x while the grid shows ≥ 5x).

`summary.overall_pass` requires correctness_pass, perf_pass and zero cheat_flags.

## Verification (2026-09-23, this machine, offline as described above)

```
cd <BENCH>
tasks/D-perf/D-sqlx/hidden/grade.sh tasks/D-perf/D-sqlx/repo --record-test-counts --out <v>/pristine.json   # 4m03s
cp -R tasks/D-perf/D-sqlx/repo <scratch>/ref-applied && (cd <scratch>/ref-applied && git apply .../hidden/reference.patch)
tasks/D-perf/D-sqlx/hidden/grade.sh <scratch>/ref-applied --out <v>/reference.json                         # 2m38s
```
The full JSON and logs are in `D-sqlx/hidden/verification/`.

| | pristine repo | reference.patch applied |
|---|---|---|
| summary | correctness **false** (nul 2/10), perf **false**, flags: `no_library_change` | correctness **true**, perf **true**, 0 flags, **overall_pass true** |
| existing tests | 217 + 12 passed, 0 failed | 217 + 12 passed, 0 failed |
| differential | 142/142 equal | 142/142 equal |
| NUL cases erroring fast | 2/10 (8 time out; the 2 `nul_in_literal` cases already errored) | 10/10 |
| median 5k / 20k / 80k (s) | 0.0410 / 0.4111 / 5.231 | 0.0215 / 0.0850 / 0.3638 |
| speedup vs pristine, same run | 0.97 / 0.91 / 1.00 | 1.89 / 4.43 / **15.23** |
| off-grid 7k / 33k speedup | 1.00 / 1.08 | 2.22 / 5.96 |
| scaling exponent 20k→80k | 1.84 (pristine side 1.91) | **1.05** (pristine side 1.94) |

The visible bench (`cargo run --release --example multi_stmt_bench ...`) measures 32k statements at 995.7 ms before the
patch and 176.7 ms after, and 16k at 280.4 ms before and 74.6 ms after.

The reference patch (`hidden/reference.patch`, 72 lines, `virtual.rs` only) does three things:
- appends a NUL to the buffer and passes the terminator to SQLite, so SQLite parses in place with no copy;
- treats a tail of length ≤ 1 as exhausted;
- returns `err_protocol!("query string must not contain NUL bytes")` when SQLite consumes 0 bytes without producing a statement.

For comparison, the issue reported ~21x at 80k on the reporter's machine; this machine measures 15.2x on the hidden workload.

## Risks / open points

- **SQL length limit**: SQLite's `SQLITE_LIMIT_SQL_LENGTH` check (default 1e9 bytes) runs only on the copy path, against
  the whole remaining tail. After the fix, SQLite checks each statement instead. Behavior differs only for scripts over 1 GB;
  this isn't tested.
- **NUL timing**: a lazy NUL error (after earlier statements have run) and upfront rejection are both accepted. The
  prefix before the error isn't compared for NUL cases, because pristine hangs there.
- **Timing noise**: perf thresholds rely on wall clock. The reference margin is about 3x over the 80k threshold (15.2 vs 5)
  and 2x at 33k (5.96 vs 3). Don't run grading concurrently with other heavy jobs.
- **Unsafe code**: miri and ASan weren't run. The differential tests cover 1–2-byte tails and multi-byte UTF-8 at the
  end, but a memory-unsafe candidate could still pass.
- **Anti-cheat coverage**: the checks were exercised only on pristine (which correctly raises `no_library_change`) and
  the reference (which raises no flags). No deliberately cheating candidate was built to confirm that each flag fires.
- **Test visibility**: the test suite and the prompt's test command skip the `sqlite_ipaddr`/SQLCipher cfgs and the
  4 GiB rustsec test. Those parts of upstream CI aren't exercised.
- **Sealing**: `hidden/` (including `.cache/pristine-repo`, which has no fix) and `scratch/` must be sealed during runs.
  `scratch/sqlx-upstream` is the upstream checkout at the pin; it contains no fix, but it does reveal provenance.
