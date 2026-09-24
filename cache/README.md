# cache/

Offline dependency caches, filled by `../setup.sh`:

- `gomod/` — Go module cache for the etcd task, including the pinned `go1.26.5` toolchain (about 4 GB)
- `ripgrep-vendor/` + `ripgrep-vendor.config.toml` — `cargo vendor` output for the ripgrep task
- `sqlx-vendor/` + `sqlx-vendor.config.toml` — `cargo vendor` output for the sqlx task (about 0.5 GB)
- `mcp-conformance/node_modules/` — the pinned `@modelcontextprotocol/conformance` CLI used by the C grader

Only this file and `mcp-conformance/package.json` + `package-lock.json` are committed.
