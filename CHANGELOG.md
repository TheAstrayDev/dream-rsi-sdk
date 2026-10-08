# Changelog

## 0.3.0b2 — Live Inspector, 2026-10-08

- Add opt-in `LiveInspector` capture with a bounded background SQLite writer
  and a read-only local browser viewer. Animate actual in-flight branches;
  inspect recorded answers, quality, failures and optional policy reasons.
- Add pan/zoom, branch collapse, follow-active mode, timeline playback,
  keyboard navigation and reduced-motion support for desktop and mobile.
- Record offline comparisons through the configured replay engine, preserving
  unknown continuations and the effective policy under quality contracts.
  Comparison never promotes a policy.
- Add `dreamrsi watch`, `init`, `doctor` and `inspect`; generate a runnable
  starter without overwriting existing files. Add `RunResult.report()`.
- Export standalone HTML reports with the selected run's history and bundled
  assets; no hosting, Node.js, CDN or new runtime dependency is required.
- Display settled, reserved and declared historical call costs separately from
  quality. Keep incomplete token and dollar usage unknown.
- Bound captured content and redact common credential patterns without running
  custom object serializers. Document privacy controls and observer overhead.
- Extend installed-wheel gates to exercise the Inspector's HTTP assets and CLI.
  Include screenshots, installation instructions and a focused verification record.

Existing quality contracts, budgets and policy-selection behavior are unchanged.
The Inspector is optional instrumentation, not a new reasoning algorithm or
proof of improved all-in ROI. See the [release notes](docs/releases/0.3.0b2.md).

## 0.3.0b1 — Beta, 2026-10-05

- Add opt-in `QualityContract` and `CertifiedPolicy`: retain the original search
  and complete batches, stopping only at an attained sound quality bound.
  Strict mode skips policy rewrites and repeated training; missing bounds keep
  the original search. Existing empirical development remains available.
- Select the actual returned answer by valid raw quality when configured,
  including an evaluated initial candidate. Keep composite scores separate.
- Add `EconomyPlan` with exact integer preparation limits, historical costs and
  measured payback. Recalculate remaining preparation from actual deployment
  spending and a persisted completed-task count before admitting each request.
  Track preparation/deployment purposes and reported nested
  provider calls through budgets and restored ledgers. Keep concurrent deployment
  separate from an improvement task's preparation allowance.
- Add finite sandbox presets, JSON profile save/load and a configurable bounded
  cache of validated syntax trees. Each execution keeps fresh state and resource
  checks; the balanced preset preserves existing defaults.
- Isolate raw-quality callback records from stored observations, infer source
  sandbox profiles through nested policies, and atomically reserve holdouts in
  built-in stores. Legacy custom stores retain their existing interface.
- Reject unsupported explicit artifact schemas while accepting existing v1 and
  legacy payloads; serialize nested certified/source policies.
- Export the public `PolicyDeveloper` protocol and add isolated installed-wheel
  CI gates for the CLI, codecs and process sandbox on Linux and Windows.
- Document Beta compatibility, the quality proof, all-in accounting and a
  deterministic mechanics example. No new real-model speedup is claimed.
- Include English PNG/SVG figures with curated engineering evidence and local
  reproduction tools for sandbox timing, preparation headroom and exhaustive
  runtime quality checks. Keep model benchmarks separate from these checks.

This Beta prerelease keeps pre-release APIs explicit. Strict
quality preservation depends on a correct task bound and matching reference
configuration; it does not imply savings on every task. See the
[Beta notes](docs/releases/0.3.0b1.md).

## 0.2.0a4 — 2026-09-30

- Derive a bounded incumbent prefix directly from recorded raw-quality replay
  trajectories before spending model requests on a stopping rule. Preserve
  original decisions and complete parallel batches until the stopping round.
- Support nested built-in, custom and source prefix policies in policy codecs,
  portable bundles and campaign checkpoints; custom policies need their codecs.
- Add `DreamRSIConfig.optimizer_prefix_search` and standalone optimizer
  `prefix_search` controls. Candidate limits and independent holdout gates remain.
- Include root-branch order in the minimum recorded probe cost used to reject
  futile source-development searches; unknown evidence remains eligible.
- Cover raw-quality extraction, delayed-payoff rejection, source sandbox execution,
  one-candidate budgets, bundle reuse and recovery with regression tests.

Recorded prefix quality is not a guarantee for unseen tasks. Prefix bundles
require 0.2.0a4 or newer. The runtime configuration fingerprint has changed:
use a new campaign ID for older checkpoints; stored trees and older bundles
remain readable. See the [release notes](docs/releases/0.2.0a4.md).

## 0.2.0a3 — 2026-09-28

- Snapshot root and attempt payloads when adding discovery-tree nodes, preserving
  recorded observations and diagnostics if an agent later mutates its input objects.
- Give the default, zero-LLM optimizer a bounded portfolio of short branching
  and stopping policies before incumbent-specific parameter variations. On a
  deterministic replay counterexample, a newly reachable candidate preserves
  raw quality while reducing attempted expansions from three to one.
- Keep independent validation and the existing cost/quality promotion gate;
  the counterexample is not evidence of a general deployment speedup.
- Restrict source distributions to SDK source and release documentation so
  untracked local benchmarks and drafts cannot enter PyPI archives.

See the [release notes](docs/releases/0.2.0a3.md).

## 0.2.0a2 — 2026-09-27

- Export and import a family's saved policy versions and replay trees as one
  checksummed JSON bundle. Import validates the family, policy codecs, and tree
  structure; it does not replace a different local champion.
- Add `dreamrsi list`, `install`, `save`, and `publish` for sharing bundles through
  public GitHub repositories and Release assets without a separate package host.
- Allow one package to combine multiple task families and install them together,
  checking all local policy conflicts before importing any family.
- Add `save --all`, repeated `--family` selection, `-d` for the source database,
  and `-n auto` for an unambiguous namespace. Saving makes no model requests and
  refuses to overwrite an existing CLI export.
- Document third-party policy and replay datasets, compatibility requirements,
  receiver-controlled admission and training, and a runnable two-store example.
- Keep package listings usable in legacy Windows consoles by escaping characters
  that the terminal encoding cannot represent.

Local policy memory can be shared as portable, community-authored artifacts.
The package-sharing interface remains experimental.
See the [release walkthrough](docs/releases/0.2.0a2.md) and
[package guide](docs/packages.md).

## 0.2.0a1 — 2026-09-24

- Add opt-in durable `AdaptivePolicyMemory` so a saved champion can be tried on
  related tasks before running another training campaign; admission and fallback
  remain configurable.
- Count replay attempts at the edge of a recorded tree conservatively and make
  source-development feedback explain unsupported expansions and repeated actions.
- Publish two clearly separated experiment records: a local Bonsai Q2 policy
  developer on a deterministic discovery fixture, and a GPT-6 Luna xhigh
  model-agent run. Include preparation in every all-in comparison.

The jump to `0.2.0a1` marks a larger, still experimental policy-reuse and
measurement interface with changed replay semantics; it does **not** claim a
general research reproduction or an all-in LLM-agent cost win. Both reports
describe their limits, and alpha APIs may still change.

## 0.1.0a4 — 2026-09-23

- Reuse recorded search trees for an offline improvement pass with no new training run.
- Delay held-out collection until a candidate improves training replay; retain single-use
  validation and crash recovery.
- Compare raw quality and probe counts separately, cap combined agent/developer calls,
  and stop repeated or stalled policy revisions.
- Update the validation recovery test for lazy collection so the clean CI matrix passes.

**Behavior change:** The default promotion gate requires paired raw-quality and probe
evidence. Pass `ReplayOnlyGate` explicitly for score-only promotion. Built-in policy
variants are tried before an LLM developer; set `DefaultMethod(force_developer=True)`
to also run source development when a cheap candidate already qualifies. These changes
limit avoidable calls but are not yet evidence of a full-campaign cost win.

## 0.1.0a3 — 2026-09-22

Published to PyPI as `dreamrsi==0.1.0a3` under the sole author `TheAstrayDev`.

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
