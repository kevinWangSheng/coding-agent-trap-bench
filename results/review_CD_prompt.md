You are an independent auditor (not affiliated with any model vendor) for a coding-agent benchmark: Claude Opus 5.5 vs GPT-6 Astra vs GPT-6 Sol. The orchestrator that built the graders is itself Claude Opus 5.5, and the results favor Opus on tasks C and D, so your job is to look for grading bias or grader bugs. Read-only; do not modify files.

Task C (MCP server per spec 2026-07-28): task files tasks/C-new-spec/C-mcp/ (prompt.md, repo/README.md, repo/docs/mcp-spec-2026-07-28/, hidden/grade.py, hidden/tests/, hidden/stale_api_check.py, hidden/conformance_expected.json). Per-run grades: results/graded/C-mcp__*.json (keys conformance, hidden_tests, stale_api). Agent code: ~/.bench-runs/C-mcp__<model>__r<n>/repo/src.
Task D (sqlx SQLite multi-statement perf): tasks/D-perf/D-sqlx/ (prompt.md, hidden/grade.py, README at tasks/D-perf/README.md). Grades: results/graded/D-sqlx__*.json. Agent diffs: results/raw/D-sqlx__*/repo.diff.

Check, with file:line evidence:
1. C: For the GPT runs' failed conformance checks and hidden tests, are the failures genuine spec/README violations by the agent, or grader strictness on details the README/spec do not actually require? Sample at least 3 failures per GPT model and all Opus failures. Opus fails one conformance check (initialize -> expected 404/-32601, got 400/-32022): is that ordering actually specified by the spec text?
2. C: Is any hidden test or conformance expectation written in a way that matches one model's style by coincidence (e.g. exact message strings not in README)?
3. D: Is D-sqlx__gpt-6-sol__r1's failure real (behavior change on hidden inputs / timeout), and are the passes for all others legitimate (no benchmark special-casing)? Is the 5x@80k threshold applied identically?
4. Anything else that makes the C/D comparison unfair.
Output: findings list ranked by impact on the published comparison, each with evidence and whether it changes any run's verdict. Be concise.
