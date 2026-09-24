Findings, ranked by impact:

1. **High: Opus’s only C conformance failure is likely a grader-ordering bug, changing all three Opus C verdicts if corrected.**

   The conformance check expects legacy `initialize` to reach method dispatch and return HTTP 404 / JSON-RPC `-32601` (`hidden/tests/protocol.test.ts:162-174`; grader output in all three Opus files). Opus instead returns HTTP 400 / `-32022`.

   The spec does not clearly require the grader’s ordering. The versioning spec says `initialize` is an unknown method, but explicitly says that on HTTP a request missing required headers is rejected with `400 Bad Request` by transport validation (`docs/.../basic/versioning.md:154-157, 164-170`). The test request omits the modern headers. Therefore 400 is at least specification-consistent, and the exact 404 expectation is not justified for this HTTP input. This is a real bias against Opus, not an agent violation.

2. **Medium: GPT C failures sampled are generally genuine violations, not README/spec omissions.**

   Representative failures across both GPT models:

   - Missing `ttlMs`/`cacheScope` on resource reads: required by the changelog and resource result schema (`changelog.md:34-37`; `server/resources.md:128-129, 167-168`), and README caching policy (`README.md:154-158`).
   - Returning old missing-resource code `-32002` instead of `-32602`: explicitly required by the changelog (`changelog.md:36-37`) and README (`README.md:123-124`).
   - Failing base64 decoding and consistency checks for `Mcp-Name`/`Mcp-Param-Notebook`: required by the header-extension specification (`server/tools.md:343-395`) and directly reflected in the README’s routing/header requirement (`README.md:58-62`).
   - Failing elicitation/MRTR behavior, subscription streams, and progress-on-request-stream: explicitly required by README (`README.md:81-94`, `96-107`, `126-133`) and the 2026-07-28 changelog (`changelog.md:18,24`).

   I found no sampled GPT failure that is merely an unrequired implementation detail. These failures leave GPT C verdicts unchanged.

3. **Low: Hidden tests use exact values, but the values are specified rather than style-matched.**

   Exact assertions such as `Delete note "<title>"?`, `Indexed <k>/<steps>`, `ttlMs=300000`, `cacheScope=public`, and `-32602` appear in hidden tests (`hidden/tests/app.test.ts:135,278`; `protocol.test.ts:38-47,77-84`) and are also stated verbatim or semantically in README/spec (`README.md:81-89,100-105,154-158`). This is not coincidence with one model’s coding style. No verdict change.

4. **D-sqlx GPT-Sol r1 failure is genuine and severe, not a grader artifact.**

   Its differential run has 64 mismatches, including `semicolons_only`, comment-only, and trailing-comment cases timing out where pristine returns successfully (`results/graded/D-sqlx__gpt-6-sol__r1.json`, `grade.differential.mismatches`). The candidate’s `split_statements` implementation in `results/raw/.../repo.diff` produces non-progressing empty/comment slices, causing these hangs. The performance harness also times out for every candidate benchmark (`grade.perf.error`), so failure is correctly behavior/performance based.

5. **D passes and the 5×@80k threshold are applied identically.**

   `hidden/grade.py:304-337` computes pristine/candidate medians, speedup, off-grid speedup, and scaling with one shared `MIN_SPEEDUP_80K = 5.0`. Passing runs show the same threshold object and checks; no model-specific branches or special-casing. Differential checks compare exact JSON behavior over 142 cases (`tasks/D-perf/README.md:59-69`), and checksum equality is required before perf pass (`grade.py:325-335`). Verdicts for passing Astra/Sol/Opus runs are legitimate.

6. **Minor D concern, not verdict-changing: NUL behavior is intentionally informational in the implementation despite README wording.**

   Candidates and pristine commonly time out on embedded-NUL cases; `grade.py` records this separately and `summary.overall_pass` does not include `nul_pass` (`grade.py:252-276, 435-446`). The README describes NUL as a diagnostic section and says pristine outcomes are informational (`README.md:70-71`). Thus this does not unfairly distinguish models, although the wording “candidate must return an error” could confuse readers.

Overall, the principal comparison defect is the Opus `initialize` conformance expectation. Correcting or excluding that check would improve all three Opus C scores; the GPT C and GPT-Sol D failures otherwise appear substantively valid.