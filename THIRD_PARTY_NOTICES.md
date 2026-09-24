# Third-party notices

The harness, the original tasks/graders and the write-up are MIT licensed (see
`LICENSE`). The task trees under `tasks/` redistribute upstream projects so that
the benchmark is reproducible; each keeps its own license and license files, which
are left in place inside the trees. This table was built from the license files
found in the redistributed trees (paths below), not from memory.

| Path in this repo | Project and pinned revision | License | Evidence in tree |
|---|---|---|---|
| `tasks/A-fresh-bugs/A1-etcd/repo/` | [etcd](https://github.com/etcd-io/etcd) at `e7fe4e80f12a7f9bd77d26f13b9a13ed9c417b20` (parent of fix `7294df1e`) | Apache-2.0 | `repo/LICENSE` (Apache License, Version 2.0, January 2004) |
| `tasks/A-fresh-bugs/A1-etcd/hidden/{fix.diff,quota_test.go}` | etcd fix commit `7294df1ec72f047d7c9412825e1e09063d0e263a` and its maintainer test | Apache-2.0 | derived from the same project |
| `tasks/A-fresh-bugs/A2-pytest/repo/` | [pytest](https://github.com/pytest-dev/pytest) at `ae777851d8b324de5eb3d0e860c28b219ce3fcd8` (parent of fix `472b4de9`) | MIT | `repo/LICENSE` ("The MIT License (MIT), Copyright (c) 2004 Holger Krekel and others") |
| `tasks/A-fresh-bugs/A2-pytest/hidden/{fix.diff,test_monkeypatch.py}` | pytest fix commit `472b4de93d83c118e0d089a34918fd1210d9ebc8` and its maintainer test | MIT | derived from the same project |
| `tasks/A-fresh-bugs/A3-ripgrep/repo/` | [ripgrep](https://github.com/BurntSushi/ripgrep) at `5e16a5c9e57e81f6031a23faa2ace52205fa8242` (parent of fix `0d7054d8`) | Unlicense OR MIT (dual) | `repo/COPYING` ("dual-licensed under the Unlicense and MIT licenses"), `repo/UNLICENSE`, `repo/LICENSE-MIT` (Copyright (c) 2015 Andrew Gallant); the `ignore` crate carries the same three files in `repo/crates/ignore/` |
| `tasks/A-fresh-bugs/A3-ripgrep/hidden/{fix.diff,hidden_tests.rs}` | ripgrep fix commit `0d7054d8e466d6aa0a6bb6cf121e87225d26df44` and its tests | Unlicense OR MIT | derived from the same project |
| `tasks/D-perf/D-sqlx/repo/` | [sqlx](https://github.com/transact-rs/sqlx) at `b54008a329541c0ce230d8b203e0c00fc8e8ea48`, workspace trimmed and a `Cargo.lock`, `examples/multi_stmt_bench.rs` and a `rust-toolchain.toml` bump added by the benchmark (see `docs/tasks/D-perf/README.md`) | MIT OR Apache-2.0 (dual) | `repo/LICENSE-MIT` ("Copyright (C) SQLx Contributors, portions Copyright (C) LaunchBadge, LLC"), `repo/LICENSE-APACHE` |
| `tasks/D-perf/D-sqlx/hidden/reference.patch` | benchmark-written fix to sqlx (`sqlx-sqlite/src/statement/virtual.rs`) | modification of sqlx code; MIT OR Apache-2.0 | — |

## Fetched at setup time, not redistributed

`setup.sh` downloads these into ignored locations; they are not part of this
repository and are covered by their own licenses:

- Go modules required by etcd (`cache/gomod`, from the module proxy per `go.sum`).
- Rust crates required by ripgrep and sqlx (`cache/ripgrep-vendor`, `cache/sqlx-vendor`, per each `Cargo.lock`).
- The Model Context Protocol specification, revision 2026-07-28, from commit `c7400a0796045cbf102cb80b9b41422c7ce8e7af` of https://github.com/modelcontextprotocol/modelcontextprotocol (`docs/specification/2026-07-28/**` saved with `.mdx` renamed to `.md`, and `schema/2026-07-28/` saved as `schema-ts/`), into `tasks/C-new-spec/C-mcp/repo/docs/mcp-spec-2026-07-28/`. It is not redistributed here because its per-file license terms (a MIT to Apache-2.0 transition, with CC-BY-4.0 for other docs; see the upstream `LICENSE` copied to `docs/upstream-licenses/`) could not be determined. `setup.sh` verifies the download against `cache/mcp-spec-2026-07-28.sha256`, so the files are byte-identical to what the agents saw.
- npm packages: `typescript 5.9.3` and `@types/node 24.13.6` for the C task (`tasks/C-new-spec/C-mcp/repo/node_modules`), and `@modelcontextprotocol/conformance 0.2.0-alpha.11` with its dependencies (`cache/mcp-conformance/node_modules`), per the committed `package-lock.json` files.
- PyPI packages: `pytest` and its dependencies for the B graders' venvs and for the per-run venvs (uv cache).

## Agent output in `results/`

`results/raw/*/repo.diff` and the blind-review packs contain patches that the
benchmarked agents produced against the trees above. Where they modify upstream
code they are derivative of that code and are published here for review under
the upstream project's license; the rest of `results/` is MIT like the harness.
