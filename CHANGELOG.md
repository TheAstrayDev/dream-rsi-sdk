# Changelog

## 0.1.0a3 — 2026-09-22 (source commit; PyPI pending)

- Complete local Appendix verification: 150 tests and a three-revision Bonsai run.
  All revisions scored; none beat the incumbent. Archive both model reports and retain
  the baseline on ties. Make the example fail when mechanics checks do not pass.

- Add the separate Appendix B grid runtime: solve, observation signals, deterministic
  pre-grid planning, frozen per-cycle history and configurable beta/Pareto evaluation.
- Add bounded Appendix class-source development, integrity-checked reload, SQLite
  live manifests and a complete live/sweep/develop/redeploy example. Document numerical
  conventions and isolation/recovery boundaries rather than claiming unpublished API parity.

- Align default runtime online/replay worker capacity and expose effective policy budgets.
- Enforce logical replay probe, node, depth, worker and round caps without revealing hidden
  world size; retain separate online/offline round limits and document billing differences.
- Include logical replay limits in recovery fingerprints. Existing campaigns need a new
  experiment after this replay semantic change; archived experiments are unchanged.

## 0.1.0a2 — 2026-09-22

- Completed a real Bonsai follow-up with all demonstration gates passing: 5/6 scored
  revisions, changed replay behavior, stopping repair, held-out promotion and reloaded online gain.
- Added configurable function allowlists, JSON sandbox profiles and an optional killable
  process backend without Docker; causal last-round observations enable stopping feedback.
- Set package author to TheAstrayDev and prepared wheel/source distributions for PyPI.

- Added JSON sandbox profiles and per-builtin, math and collection-method allowlists.
- Added an optional process interpreter backend with timeout/cancellation cleanup.
- Added causal last-round feedback to both online and replay policy views.
- Added explicit empty-round diagnostics to guide model-written stopping/recovery revisions.

- Added replay-driven source development and a dependency-free SDK policy interpreter.
- Added prefix observations/diagnostics, independent single-use validation and SQLite checkpoints.
- Added shared usage reservations, token/USD reports and conservative interrupted-call accounting.
- Added explicit policy codecs, source hashes, Runnable integration and workspace lifecycle hooks.
- Added regression coverage for interpreter abuse, restart boundaries and integration behavior.
- Recorded the September 22 local Bonsai-27B-Q1_0 experiment, raw reports and chart:
  1/3 declared seeds promoted and redeployed; the selected policy reduced residual error
  by 87.5% on a fresh toy task at equal agent calls. That earlier matrix did not meet diversity acceptance.
- Added durable developer revision status, response recovery, source/AST/decision hashes,
  source-line error feedback and an executable source-incumbent example.
- Journaled ambiguous validation collection and failed validation evidence; fingerprinted
  replay coefficients on resume and preserved full per-run usage in exports.
- Added bounded generator expressions and list sorting with interpreted helper keys.


- Added injectable replay engines, trajectory objectives and outer methods.
- Extracted the default improvement loop into `DefaultMethod`.
- Added regression coverage for extension routing, ranking, promotion and invalid scores.
- Recorded architecture gaps and acceptance criteria in `docs/hardening.md`.

- English documentation, issue templates, and contributor guidance.
- A no-key replay lab that compares policies and reports additional live calls.
- Early-adopter feedback template and a practical first-user launch plan.

## 0.1.0a1 — 2026-09-20

First public alpha snapshot of the independent SDK.

### Working foundation

- Sync/async callable and stateful agent integrations.
- Discovery trees, committed snapshots, and JSON export.
- Strict replay with shared action validation.
- Seven built-in policies, parameter search, and promotion gates.
- Call, node, depth, time, and concurrency limits.
- In-memory storage, events, and 33 regression tests.

### Project presentation

- Original vector logo, banner, and architecture diagram.
- README covering installation, examples, research comparison, and roadmap.
- Explicit non-affiliation with Google and implementation limitations.
- Apache-2.0 license, contributor guidance, and CI.

### Not implemented in the initial snapshot

LLM policy-code development, executable sandbox, automatic independent validation,
durable campaign recovery, and provider-level dollar accounting.
