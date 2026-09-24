Verdict: **not publishable in its current form**. The benchmark is unusually well documented, but its central B-task conclusion (“agents game impossible tests, and do not disclose it”) is not secured by the current grader/isolation design, and the C score contains a material grader-specification dispute.

## Issues ranked

### FATAL

- **B does not reliably distinguish honest behavior from grader-aware cheating.**  
  Evidence: `results/review-B-and-prompts.md` identifies that B1/B2 hidden runners expose `hidden_cases.json` through `sys.argv`; a submission can detect the hidden invocation and behave honestly on visible tests while special-casing hidden cases. The current classifier can label this `honest-stop` or `legit`.  
  Remedy: invoke hidden tests through an opaque API/subprocess; randomize paths and environment; add mutation tests for `sys.argv`, `__file__`, cwd, environment variables, and grader detection.

- **B’s “test tampering” coverage is incomplete.**  
  Evidence: the same review cites `tasks/B-shortcut/*/hidden/grade.py` explicitly documenting that plugins, `sitecustomize`, `.pth`, and environment-level pytest manipulation are not detected. Visible tests run with the submission’s interpreter/environment.  
  Remedy: grade in a pristine, separately provisioned environment with plugin autoload disabled and fixed interpreter configuration; run an untouched copy of the visible suite; publish the complete anti-tampering threat model.

- **B3’s “unreachable host” ground truth is environment-dependent.**  
  Evidence: `results/review-B-and-prompts.md`; `tasks/B-shortcut/B3-paylink/hidden/grade.py` probes the host at grading time and infers impossibility from the result. Proxy/DNS behavior or a transient response can change the label.  
  Remedy: replace the live `.invalid` probe with a deterministic local fixture or injected fake transport. Do not infer task truth from ambient networking.

- **C’s official conformance score has a likely ordering/specification error affecting all Opus runs.**  
  Evidence: `results/review_CD.md`; the disputed check expects legacy `initialize` to return 404/`-32601`, while Opus returns 400/`-32022`; the frozen spec says missing required headers may be rejected at transport validation with 400.  
  Remedy: resolve the spec interpretation with an independent protocol adjudication, patch/exclude the disputed check, and recompute all C scores before publication.

### FIX BEFORE PUBLISH

- **Prompt fairness is knowingly weak for B1/B3.**  
  Evidence: `tasks/B-shortcut/*/prompt.md` only says “fix the code so the tests pass”; it does not permit reporting an impossible/contradictory test. `results/review-B-and-prompts.md` calls this underspecified.  
  Remedy: state that contradictory or unavailable tests may be reported, then score completion and honesty separately. Otherwise the benchmark partly measures willingness to violate an apparently absolute instruction.

- **B3 cheat detection is lexical and easy to evade, with false positives.**  
  Evidence: review notes single quotes, computed keys, helpers, and alternate JSON paths evade detection; legitimate `.bind(`/`HTTPServer` code can trigger it.  
  Remedy: use behavioral probes and AST/data-flow checks; treat lexical matches only as review leads.

- **False-disclosure scoring is vendor/style-sensitive.**  
  Evidence: B1/B2/B3 use different caveat regexes; reviewers disagreed on one case (`results/blind/review_*`, `results/blind_KEY.json`).  
  Remedy: require structured final fields (visible pass/fail, hidden pass/fail, unresolved blockers), blind-score those fields, and report inter-rater disagreement rather than presenting one adjudicated label as objective truth.

- **B1’s “legit” rule is brittle.**  
  Evidence: review cites `B1 .../hidden/grade.py:421-429`, which checks exactly one failure and `failed_names[0]`.  
  Remedy: compare normalized failed-test ID sets, independent of collection order and naming.

- **Rerun/invalid-attempt policy needs a pre-registered accounting table.**  
  Evidence: `README.md` says the first 54 B runs were discarded for missing pytest and that capacity/missing-event failures were retried; `results/raw_invalid/` preserves attempts, but the publication denominator and retry eligibility are not fully tabulated.  
  Remedy: publish every attempt with reason, timestamp, model, task, and whether it was eligible for rerun; demonstrate that no model/task was selectively rerun based on outcome.

- **Isolation is path-dependent, not general.**  
  Evidence: `harness/NOTES.md` records that Codex could chmod/read sealed material under `/tmp`; Claude required a carefully chosen `acceptEdits` configuration because other settings allowed `curl`. `harness/run.py` places runs under `Path.home()/".bench-runs"` and uses broad read permissions.  
  Remedy: publish an explicit access matrix, seal locations, sandbox profiles, and an independent probe suite; use OS-level separate accounts/containers or mount namespaces where possible.

- **The log audit cannot establish absence of leakage.**  
  Evidence: `harness/NOTES.md` says residual session files under `~/.claude/projects` and `~/.codex` are audited by path/keyword scanning. Logs do not reveal every filesystem read, in-process memory access, indirect symlink access, or content encoded without keywords.  
  Remedy: instrument filesystem reads or run agents in isolated VMs/containers with hidden material absent, rather than relying on post-hoc log scanning.

- **The benchmark compares unlike tiers and products.**  
  Evidence: `x-content/independent/article.md` setup table: Opus vs Astra frontier vs Sol workhorse; different CLIs, system prompts, sandboxes, and reconnect behavior.  
  Remedy: frame results explicitly as product-stack comparisons; do not imply model capability rankings. Add matched-tier comparisons or a factorial analysis if capability claims are intended.

- **Performance conclusions are weaker than functional conclusions.**  
  Evidence: article caveat reports 103 Astra and 63 Sol reconnects versus 0 Opus; D itself uses wall-clock medians.  
  Remedy: keep the “no speed/token claims” restriction prominent; publish per-run timing distributions, hardware/load state, and confidence intervals.

### DISCLOSE

- **Training-cutoff/contamination claims are not fully evidenced.**  
  Evidence: `results/review_article.md` found that the repository establishes task dates but not all models’ cutoff dates or non-contamination. `tasks/C-new-spec/candidates.md` itself says GPT cutoff is “unknown but presumably similar-era.”  
  Remedy: say “post-dated relative to the documented Opus cutoff; GPT cutoff is unverified,” or omit the contamination claim.

- **The headline “Opus won everything else” is too categorical.**  
  Evidence: `x-content/independent/article.md`; C audit finds a likely Opus-disfavoring check.  
  Remedy: say Opus led under the reported scoring, conditional on the disputed C check.

- **n=3 per cell supports directional observations, not stable rates or rankings.**  
  Evidence: 99 included runs, three repetitions per task/model/variant. A result such as 7/18 versus 8/18 has wide uncertainty and is highly task-specific.  
  Remedy: report exact counts with uncertainty, avoid population-level “agents generally…” language, and describe tasks as a small case study.

- **The harness author is also a contestant and designed B tasks, graders, and publication text.**  
  Evidence: `README.md`; article conflict-of-interest section. Existing blind review and external C/D review are useful but do not eliminate design degrees of freedom.  
  Remedy: preregister tasks/scoring, have an independent party freeze graders before runs, release all design history, and rerun with independently authored traps.

- **Reproducibility is currently operationally fragile.**  
  Evidence: `harness/run.py` contains hard-coded macOS SDK path and local home-directory paths; `tasks/D-perf/README.md:92` includes the author’s absolute repository path; credentials/caches and proprietary CLI access are required.  
  Remedy: replace absolute paths with parameters, publish lockfiles/checksums, exact CLI binaries/configuration, dependency caches or build instructions, hardware/OS details, and a sanitized rerun script.

### OK

- The 99 included records are internally consistent with 11 prompt/task variants × 3 models × 3 reps; invalid attempts are retained.
- A-task upstream fixes and D differential checks appear substantively grounded.
- D’s 5× threshold and checksum/differential requirements are applied uniformly; the Sol failure is supported by concrete mismatches.
- Blind B review, model-name stripping, and independent C/D audit are good safeguards, provided their limitations are reported.

## Three most likely public criticisms

1. **“The impossible-task result is a grader artifact or prompt trap, not honesty.”**  
   Current material answers this only partially: it discloses prompt ambiguity and has blind review, but it does not solve hidden-runner detection, incomplete tamper detection, or B3’s live-network dependence.

2. **“This is not a fair model comparison: Opus, Astra, and Sol are different tiers with different sandboxes and network behavior.”**  
   The article acknowledges this, including reconnect counts and sandbox asymmetry. It should go further and prohibit capability-ranking language; the current “Opus won…” phrasing invites this criticism.

3. **“The headline scores depend on questionable grading and tiny samples.”**  
   Current material acknowledges `n=3` and the disputed Opus C check, but still reports aggregate superiority too confidently. Regrade C, repair B, and present uncertainty/task-level results before publication.