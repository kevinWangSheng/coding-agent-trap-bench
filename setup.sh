#!/usr/bin/env bash
# One-time setup: download everything the offline benchmark runs and graders need.
#
# The agents run with no network, so every dependency is fetched here, into cache/ and
# into the task trees, at the versions recorded in docs/tasks/*/README.md and
# docs/HARNESS_NOTES.md. Safe to re-run; each step is skipped or refreshed in place.
# Expect roughly 4.7 GB of downloads (Go modules ~4 GB, sqlx crates ~0.5 GB).
set -euo pipefail

BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE="$BENCH/cache"
TASKS="$BENCH/tasks"

GO_TOOLCHAIN=go1.26.5     # tasks/A-fresh-bugs/A1-etcd/repo/go.work pins this toolchain
SQLX_RUST=1.95.0          # tasks/D-perf/D-sqlx/repo/rust-toolchain.toml
PYTHON=3.12               # harness venvs (uv)
# B graders' venv (tasks/B-shortcut/*/hidden/.venv), versions as shipped in the study
B_VENV_PKGS=(pytest==9.1.1 pluggy==1.6.0 iniconfig==2.3.0 packaging==26.3 pygments==2.21.0)

log() { printf '\n== %s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1  ($2)" >&2; exit 1; }; }

[ "$(uname -s)" = Darwin ] || echo "warning: the harness relies on macOS seatbelt (sandbox-exec); other platforms are untested" >&2
need uv "https://docs.astral.sh/uv/"
need go "https://go.dev/dl/ (any recent release; the pinned toolchain is auto-downloaded)"
need cargo "https://rustup.rs/"
need rustup "https://rustup.rs/"
need node "Node.js >= 24"
need npm "comes with Node.js"
need git "git"
need rsync "rsync (used by the D grader)"
need timeout "GNU coreutils: brew install coreutils (used by the A3 grader)"
need xcrun "Xcode Command Line Tools: xcode-select --install"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 24 ] || { echo "Node >= 24 required (found $(node --version))" >&2; exit 1; }
mkdir -p "$CACHE"

log "Python $PYTHON via uv"
uv python install "$PYTHON"

log "Go modules for A1-etcd -> cache/gomod (about 4 GB, includes the $GO_TOOLCHAIN toolchain)"
(
  cd "$TASKS/A-fresh-bugs/A1-etcd/repo"
  export GOMODCACHE="$CACHE/gomod" GOTOOLCHAIN="$GO_TOOLCHAIN" GOFLAGS= GOTELEMETRY=off
  go version                              # downloads the pinned toolchain into GOMODCACHE
  go mod download all                     # every module in the workspace build list
  go list -deps -test ./... >/dev/null    # resolves test dependencies of all workspace modules
  GOPROXY=off go list -deps -test ./... >/dev/null && echo "etcd module graph resolves offline"
)

vendor_crates() {  # <repo> <name> [cargo args...]
  local repo="$1" name="$2"; shift 2
  log "Rust crates for $name -> cache/$name-vendor"
  ( cd "$repo" && cargo "$@" vendor --locked "$CACHE/$name-vendor" >/dev/null )
  cat > "$CACHE/$name-vendor.config.toml" <<EOF
[source.crates-io]
replace-with = "vendored-sources"

[source.vendored-sources]
directory = "$CACHE/$name-vendor"
EOF
}
vendor_crates "$TASKS/A-fresh-bugs/A3-ripgrep/repo" ripgrep
rustup toolchain install "$SQLX_RUST" --profile minimal
vendor_crates "$TASKS/D-perf/D-sqlx/repo" sqlx "+$SQLX_RUST"

log "MCP spec snapshot 2026-07-28 (fetched, not redistributed) into tasks/C-new-spec/C-mcp/repo/docs/"
# Pinned upstream commit; .mdx pages are saved as .md and schema/2026-07-28 as schema-ts/ (the schema.mdx stub is dropped),
# exactly as during the study. The checksum list in cache/ proves the result is byte-identical.
MCP_COMMIT=c7400a0796045cbf102cb80b9b41422c7ce8e7af
SPEC="$TASKS/C-new-spec/C-mcp/repo/docs/mcp-spec-2026-07-28"
tmp="$(mktemp -d)"
curl -fsSL --retry 3 "https://codeload.github.com/modelcontextprotocol/modelcontextprotocol/tar.gz/$MCP_COMMIT" | tar -xz -C "$tmp"
up="$tmp/modelcontextprotocol-$MCP_COMMIT"
( cd "$up/docs/specification/2026-07-28" && find . -type f | while read -r f; do
    case "$f" in *.mdx) d="$SPEC/${f%.mdx}.md" ;; *) d="$SPEC/$f" ;; esac
    mkdir -p "$(dirname "$d")"; cp "$f" "$d"; done )
( cd "$up/schema/2026-07-28" && find . -type f ! -name schema.mdx | while read -r f; do
    mkdir -p "$SPEC/schema-ts/$(dirname "$f")"; cp "$f" "$SPEC/schema-ts/$f"; done )
rm -rf "$tmp"
( cd "$SPEC" && shasum -a 256 -c --quiet "$CACHE/mcp-spec-2026-07-28.sha256" )

log "Node packages for C-mcp (repo/node_modules) and the pinned MCP conformance CLI (cache/mcp-conformance)"
( cd "$TASKS/C-new-spec/C-mcp/repo" && npm ci --no-audit --no-fund )
( cd "$CACHE/mcp-conformance" && npm ci --no-audit --no-fund )
node "$CACHE/mcp-conformance/node_modules/@modelcontextprotocol/conformance/dist/index.js" --help >/dev/null

log "Grader venvs for the B tasks (tasks/B-shortcut/*/hidden/.venv)"
for t in B1-flexdate B2-exprcalc B3-paylink; do
  v="$TASKS/B-shortcut/$t/hidden/.venv"
  [ -x "$v/bin/python" ] || uv venv -q --python "$PYTHON" "$v"
  uv pip install -q --python "$v/bin/python" "${B_VENV_PKGS[@]}"
done

log "Warming the uv cache so run.py can build each run's venv offline"
# run.py installs the task package (editable) plus pytest with `uv pip install --offline`;
# that only works if the wheels/sdists are already in uv's cache. Install each once, online.
warm() {  # <repo> [extras]
  local tmp; tmp="$(mktemp -d)"
  uv venv -q --python "$PYTHON" "$tmp/venv"
  ( cd "$(dirname "$1")" && VIRTUAL_ENV="$tmp/venv" SETUPTOOLS_SCM_PRETEND_VERSION=9.1.0.dev0 \
      uv pip install -q -e "./$(basename "$1")${2:-}" pytest )
  rm -rf "$tmp"
}
warm "$TASKS/A-fresh-bugs/A2-pytest/repo" "[dev]"
for t in B1-flexdate B2-exprcalc B3-paylink; do warm "$TASKS/B-shortcut/$t/repo"; done
warm "$BENCH/harness/smoke/repo"
# prove the offline path works for the smoke task
tmp="$(mktemp -d)"; uv venv -q --python "$PYTHON" "$tmp/venv"
( cd "$BENCH/harness/smoke" && VIRTUAL_ENV="$tmp/venv" uv pip install -q --offline -e ./repo pytest ) && echo "offline venv build OK"
rm -rf "$tmp"

log "Done"
cat <<EOF
Next:
  python3 harness/run.py S0-smoke opus-5.5 0        # smoke test one CLI (needs a Claude Code login)
  python3 harness/run.py S0-smoke gpt-6-sol 0       # ... and the other (needs a Codex login)
  python3 harness/orchestrate.py --dry              # show the 99-run plan
See README.md, "Rerun it".
EOF
