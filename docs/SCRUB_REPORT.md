# Privacy scrub report

The run records in `results/` are the CLIs' own event streams: every shell command an
agent ran and everything it printed. Some agents explored the operator's machine
(`env`, `lsof`, `ps aux`, `find /tmp`, `ls ~/.cache`), so the logs originally contained
the operator's username, home directory, shell environment, proxy settings, local
process list and file names from unrelated projects. Before publication every text
file in this repository was passed through a scrub script (kept outside the repo).
This report says what was changed and what the residual scan still finds. The
scan patterns are described in words here rather than quoted, so that this file
does not itself reintroduce the strings it reports on.

## What was changed

Applied to every text file (`results/`, `docs/`, `harness/`, `README.md`, and the
path/identity rules also to `tasks/`):

| Rule | Replacement |
|---|---|
| The operator's home directory (`/Users/<username>`, also the truncated forms pytest prints) | `~` |
| The benchmark's working directory under the operator's `~/dev/...` | `<BENCH>` |
| Claude Code's per-cwd temp-dir slug `-Users-<username>--bench-runs-...` | `-Users-HOME--bench-runs-...` |
| Username, machine hostname, the operator's e-mail, the GitHub handle | `<user>`, `<host>`, `[redacted-email]`, `<owner>` (the handle is kept only in the intended repository URL and the license line) |
| Local HTTP proxy on loopback port 1087, and the bare port number in agent commands | `127.0.0.1:<proxy-port>`, `<proxy-port>` |
| `PATH` values in `meta.json` / graded JSON | `[redacted: PATH]` |
| Signed URLs (OpenAI file-CDN links carrying a `sig=` parameter), OpenAI-style `sk-` keys, JWT-shaped strings, `Bearer <token>`, common token prefixes, `"token"/"api_key": "..."` JSON fields | `[redacted-...]` (none survived; see the residual scan) |

Applied to agent tool outputs in `events.jsonl` (parsed line by line; every string
value is scrubbed, JSON structure and line count preserved) and to strings in the
other JSON/JSONL files:

| Situation | Replacement |
|---|---|
| Output of a bare `env` / `printenv` / `set` (also when piped into `grep`/`rg`/`sort`) | every `KEY=value` line replaced by one `[redacted: environment dump]` line; other output kept |
| Any `KEY=value` line whose key is `PATH`, `HOME`, `USER`, a proxy variable, `*_URL`, `*TOKEN*`, `*SECRET*`, `*_KEY`, `HISTFILE`, tool-specific prefixes, etc. | `KEY=[redacted]` |
| Output of `lsof`, `ps`, `netstat`, `who`, `hostname`, `scutil`, `sw_vers`, `system_profiler`, `ifconfig`, `launchctl`, `defaults`, `security` | `[redacted: local process/port listing]` (whole output) |
| Output of `ls`/`find`/`cat`/`head`/`grep`/... with an argument under `/tmp`, `/private/tmp`, `~`, `$HOME`, `/Users`, `/Library`, `/Applications`, or `find /` (i.e. reads outside the run directory) | `[redacted: output of a command that reads outside the run directory (shell)]` (whole output) |
| Individual lines naming unrelated local files or software: other repositories under `~/dev`, `~/Library/...`, Claude/Codex session and cache paths not belonging to the run, the proxy/mirror hostnames from the operator's shell config, the names of unrelated local applications | `[redacted: unrelated local file]` |
| Consecutive redacted lines | collapsed to one |

Not changed: the agents' final messages (`final.txt`) and diffs (`repo.diff`) beyond
the path/identity substitutions above (46 changed lines across 34 files, each one a
home-directory path rewritten to `~/...`; verified line by line against the
originals), the task trees under `tasks/` (upstream code is untouched; the path
substitutions found nothing there), and the article text. Commands the agents typed
are kept verbatim except for the substitutions in the first table; only their
outputs are dropped.

Files deliberately left out of the public copy rather than scrubbed: the raw
transcripts of the review sessions (`results/*.log` of the article, C/D and
methodology reviews, and `results/blind*/review_openai.log`; the reviewers' conclusions
are in the `.md`/`.jsonl` files that are included), `results/orchestrate.log`, a
`results/tmp_leftovers_*` directory of files recovered from the shared temp folder, and
a file listing the operator's Claude temp directories. The excluded logs are agent
transcripts with the same kind of environment exposure as `events.jsonl` and no
evidentiary value beyond the published reviews.

## Residual scan

`grep -rIoE` over the whole tree (excluding `.git`) after the scrub, with the number
of matching files. Every non-zero row is explained below.

| Pattern | Hits | Files |
|---|---|---|
| the operator's username | 0 | 0 |
| `/Users/` | 4 | 3 |
| `@gmail` | 34 | 21 |
| `@mail.` | 0 | 0 |
| `sk-` + 8 token characters | 124 | 45 |
| `eyJ` + 10 base64 characters | 76 | 23 |
| `Bearer` | 17 | 8 |
| the OpenAI file-CDN hostname | 1 | 1 |
| `127.0.0.1:` + 4 digits | 1056 | 132 |
| `localhost:` + 4 digits | 269 | 55 |
| the operator's `dev/...` workspace path fragment | 0 | 0 |
| the machine's hostname | 0 | 0 |
| the GitHub handle | 2 | 2 |
| the operator's e-mail local part | 0 | 0 |
| the name of a local chat application (in `lsof` output) | 0 | 0 |
| `printenv` | 0 | 0 |
| `vck_` | 0 | 0 |
| `Authorization` | 443 | 69 |
| `cookie` (any case) | 162 | 19 |
| `auth.json` | 21 | 9 |
| `HTTP_PROXY` / `http_proxy` / `https_proxy` | 9 | 4 |
| `/private/tmp` or `/tmp/` | 1686 | 150 |
| Claude shell-snapshot paths | 0 | 0 |
| unrelated local tool paths (an editor vendor, `.nvm/`, `.cargo/bin`, a terminal app) | 3 | 3 |
| `password` / `passwd` | 709 | 111 |

Additional targeted checks, all zero: JWT-shaped strings (three dot-separated base64
segments starting with `eyJ`), `sk-` followed by 16+ token characters, the bare proxy
port in `results/` and `docs/`, the hostname in any spelling, the operator's e-mail,
and any command in the logs that reads an `auth.json` (the agents only listed the
file name).

Explanation of the non-zero rows:

- **`/Users/` (4):** `C:\Users\test\project` in pytest's own test suite, an example path in etcd's upstream `etcdutl/README.md`, and `/Users/*/multi_stmt_bench` in a macOS crash report quoted in one sqlx run, where the OS itself masks the username.
- **`@gmail` (34):** all in the upstream trees: ripgrep's `Cargo.toml` author field and generated docs, etcd `OWNERS`/`OWNERS_ALIASES` and a robustness patch, pytest's code of conduct and release script, sqlx's `Cargo.toml`. These are the upstream projects' public maintainer addresses; `results/`, `docs/` and `harness/` contain no `@gmail` address.
- **`sk-` (124):** the substring in `task-supporting`, `tasks-dispatch`, `desk-...` etc. (MCP conformance check names and review text). Zero matches for `sk-` followed by a 16+ character token.
- **`eyJ` (76):** base64 pagination cursors from the MCP specification examples (`eyJwYWdlIjogMn0=` decodes to `{"page": 2}`), quoted by agents and present in the spec snapshot, plus `h1:` hashes in etcd's `go.sum` and cargo checksums. No three-segment JWT anywhere.
- **`Bearer` (17):** specification text (the `WWW-Authenticate` header with the `Bearer` scheme) in the MCP snapshot and in agents' `cat` output of it, and etcd's auth store code. No bearer token values.
- **OpenAI file-CDN hostname (1):** a sentence in `results/methodology_review_opus.md` where the reviewer recommends scrubbing a signed URL of that host before publication. The URLs themselves (in two discarded runs' `grep` output over the operator's Codex cache) were removed with the surrounding lines.
- **`127.0.0.1:NNNN` (1056) and `localhost:NNNN` (269):** etcd's own tests and docs (`127.0.0.1:2379` and friends, 655 hits), the C-mcp grader's logs where the conformance CLI talks to the server under test on a random loopback port (about 51 per run), and agents probing `localhost:8000` / `127.0.0.1:8000` for a payment gateway during the trap task. The proxy address was the only one that identified the operator's machine and it is now `<proxy-port>`.
- **GitHub handle (2):** the intended repository URL in `README.md` and the copyright line in `LICENSE`; the handle was removed everywhere else (one mention in the task research notes became `<owner>`).
- **`Authorization` (443) / `cookie` (162):** MCP specification text and agents' reads of it, urllib source quoted in pytest tracebacks (`Proxy-Authorization`), etcd and pytest code, and the conformance CLI's own package files. No header values.
- **`auth.json` (21):** the harness docs describing that the Codex login file is copied into a throwaway home, the methodology review discussing it, and agents' directory listings of `~/.bench-runs` showing the file name `codexhome-*/auth.json`. No run read the file (checked: no `cat`/`head`/`open` of it in any log).
- **`HTTP_PROXY` etc. (9):** agent commands such as `env -u HTTPS_PROXY ... python` and `env | grep -E 'PAYMENTS|HTTP_PROXY'`, and the C grader's list of proxy variables it unsets. The values printed by those commands were redacted.
- **`/tmp/` (1690):** overwhelmingly upstream code (ripgrep's tests and docs, etcd), then agents writing their own scratch files (`cat > /tmp/patch.diff`) and the harness notes. Listings of the shared temp folder were redacted as described above.
- **Unrelated local tool paths (3):** an editor vendor named in etcd's `ADOPTERS.md`, and `~/.cargo/bin` / `~/.cargo/registry` in agent commands, which are the standard rustup and cargo paths.
- **`password|passwd` (709):** etcd's authentication code and tests, sqlx's connection-string handling, `/etc/passwd` used as a negative test URI by the MCP grader, and the CLIs' system prompts quoted in the logs. No credentials.

## Redaction markers in the published tree

| Marker | Count |
|---|---|
| `[redacted: output of a command that reads outside the run directory (shell)]` | 99 |
| `[redacted: environment dump]` | 34 |
| `[redacted: local process/port listing]` | 10 |
| `[redacted: unrelated local file]` | 6 |
| `[redacted: PATH]` | 156 |
| `<proxy-port>` | 79 |
| `<host>` | 1 |
| `<user>` (mostly the owner column of `ls -l` output, plus `pyvenv.cfg` paths and similar) | about 2900 |
| `<BENCH>` | about 1700 |

The counts in the residual-scan table were taken with this report file excluded;
running the same scan with it included adds a few hits per row, all of them the
pattern names and examples quoted above (for instance the words `printenv` and
`vck_` in the tables), none of them data.

Every `events.jsonl` still parses line by line with the same number of lines as the
original, and every `.json`/`.jsonl` file is valid JSON.
