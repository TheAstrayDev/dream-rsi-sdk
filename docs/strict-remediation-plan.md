# Strict remediation plan — Dream-RSI SDK

## September 22 follow-up

The subsequent F02 fix aligns default worker capacity and adds effective budget views,
logical replay caps and regression tests. See the [shared limits contract](research-loop.md#shared-policy-limits)
for the remaining distinction between replay probes and live provider usage. Separate K1/K2
round limits are intentional. Historical entries below describe the original failures.

The audit below is historical. Subsequent implementation added richer source feedback,
durable revision recovery, policy provenance, per-run usage exports, replay configuration
fingerprints and ambiguous validation-collection journaling. The user subsequently authorized
publication. See [current hardening status](hardening.md) and the
[Bonsai experiment](experiments/bonsai-2026-09-22.md). Real source repair and online
improvement are now demonstrated on a toy task; robust behavioral diversity, stopping,
research benchmarks and generalization remain open. This is not a claim that every audit
acceptance criterion has been satisfied.

## Original audit

Audit date: 2026-09-21. Status: proposed work, not completed implementation.
Public main and local HEAD both resolve to `fc43dec8718e957398f2982e64dac87205116105`.
The working tree contains substantial additional, unpublished implementation.
No implementation changes, commits or publication are authorized by this planning document alone.

## Scope and authority

Reviewed the available user/assistant conversation history from task
`01a0bf8a-a4af-7ab2-9412-707856dcf3f1`, including later corrections and the interrupted
Bonsai experiments; public repository/README; local core, integration and recovery code;
Roadmap, hardening tracker, tests and live-run reports. Hidden internal state is not available.
Conversation claims are historical assertions, not verification evidence.

Priority comes from the user's requirements: independent unofficial SDK, simple integration,
English public documentation, no Docker, configurable policy execution with minimal unnecessary
language restrictions, real iterative LLM-written executable policies, and no commits while the
identified weaknesses remain unresolved. Bonsai-27B-Q1_0 via existing llama.cpp is the primary
local test model. Do not silently replace it or require a paid service.

Research sources:
- [Paper, section 3](https://arxiv.org/html/2609.14858v1#S3).
- [Published controller-development prompt, appendix B.2](https://arxiv.org/html/2609.14858v1#A2.SS2).
- [Official research repository](https://github.com/zhengkid/Dream-RSI).
- [Authors' project site](https://dream-rsi.com/).
- [SDK public repository](https://github.com/TheAstrayDev/dream-rsi-sdk).

The official repository still says its code and reproduction scripts are being prepared.
This audit can establish agreement with the published specification, not API compatibility
with unavailable official code. Section 3 describes fixed agent/evaluator, frozen recorded
worlds, prefix-visible policy decisions and selection on a common replay pool. Appendix B.2
adds a richer experimental policy workflow. These are separate fidelity targets.
Independent promotion validation and robust SDK recovery are additional engineering requirements;
do not attribute the SDK's specific holdout design or sandbox choice to Google.

## Evidence and severity

P0 = blocks trustworthy continuation/release of the new functionality.
P1 = required before claiming a reliable research alpha.
P2 = later stabilization or scale work. A lower priority is not a claim of completion.

Evidence labels:
- **Reproduced**: a focused execution demonstrated the failure.
- **Inspected**: the behavior follows from the current implementation; targeted failure tests remain required.
- **Unproven**: the functionality or effectiveness lacks the necessary experiment.

Local checks: 87 tests pass; Ruff over src/tests/examples and Pyright pass.
These results do not invalidate the failures below. Focused probes:
`temp/audit-probes.py`, results `temp/audit-probes.json`.
Historical/recent model reports: `temp/bonsai-real-run-01.json` through `04.json`.
These local ignored files are evidence for this audit, not portable release artifacts.

| ID | Priority / evidence | Finding and consequence |
| --- | --- | --- |
| F01 | P0 / Reproduced | Real Bonsai run 04 produces rewritten code but 0/3 successfully scored revisions. Nested math imports/helpers trigger generic `Unsupported statement`; earlier responses used a status label as source or were truncated. A fixture-based developer test does not close this gap. |
| F02 | P0 / Reproduced | A budget-aware policy runs online for two calls but replay raises `AttributeError` because `budget_remaining` is None. The default online/replay worker limits also differ, and effective limits are not a complete shared view contract. |
| F03 | P0 / Reproduced | Two injected `StrictReplay` instances with beta1=0.01 and beta1=0.9 have identical checkpoint configuration. Class names do not identify component semantics; changing an experiment can pass the resume check. |
| F04 | P0 / Reproduced | Interruption before validation checkpoint persistence causes resume to execute validation task 9 again: recorded calls [9, 9, 1]. Validation collection lacks the in-flight phase protection used for training collection. This is not a claim of SQLite corruption; the failure is the missing orchestration boundary. |
| F05 | P0 / Reproduced | An agent reports 3 input + 4 output tokens and one provider call. Ledger records 7 tokens, but `run().costs` reports zero tokens/provider calls. Public cost reports can disagree with accounting. |
| F06 | P0 / Reproduced + Inspected | After an automatic promotion, stored champion replay scores are empty. `DefaultMethod` creates temporary policy IDs for gate evaluation, while `_save_policy` creates another ID and omits the decision evidence. Validation results are likewise not persisted on that version by this path. |
| F07 | P0 / Inspected | Developer failures retain earlier replay summaries inside the same feedback object. The example's false-success counter was fixed, but the core record still conflates previous context with current evaluation. Resume restores history, not the active revision index/candidates/best-source state. |
| F08 | P1 / Inspected | Sandbox capabilities list functions/math without a precise placement/signature contract. Interpretation runs synchronously inside an async method; logical bounds are not an OS memory limit or proof of event-loop responsiveness. This is an execution-isolation limitation, not a demonstrated host escape. |
| F09 | P1 / Inspected | Policy history in `views.py` is the current revealed tree, not an explicit earlier-cycle context. Developer requests include latest feedback and best source, but not a structured digest of all earlier revision outcomes/live-cycle history. Generic observations need a stable diagnostic schema. |
| F10 | P1 / Inspected | Holdout collection/single-use batches exist, but policy exceptions propagate, the pipeline lacks rich per-world decision reports, and semantically independent evaluation has not been demonstrated. Three scaled versions of one toy task are not broad generalization evidence. |
| F11 | P1 / Inspected | Workspace cancellation first calls backend.cancel inside the adapter without the runtime's five-second deadline; the runtime can call cancel again. Delayed confirmation/release and checkout-time cancellation lack demonstrated coverage. |
| F12 | P1 / Inspected | Section-3 scoring exists; beta sweeps, attainment curves and appendix-style experiment artifacts do not. `Objective.score(trajectory)` alone is insufficient for evaluating a family of policy settings. |
| F13 | P1 / Unproven | Runnable tests use a real library with fixture callbacks; they do not demonstrate a real coding agent, durable filesystem branches or useful multi-round LLM discovery. |
| F14 | P1 / Inspected | Public and local feature states differ. Local Roadmap checkmarks imply stronger completion than the evidence. README still says no imports although a math proxy exists. CI quality excludes examples; export omits new accounting fields. |
| F15 | P2 / Inspected | Replays repeatedly copy/scan committed trees; candidate evaluation is repeated after development; SQLite queries load all records of a kind and checkpoints serialize whole history. Cheap replay at large pools is unmeasured. |
| F16 | P1 / Inspected | Replaceable Method exists, but default method/checkpoints/validation rely heavily on private runtime fields. Iterative `develop` is duck-typed outside the published optimizer protocol; campaign/task and result-cost scopes need an explicit contract. |

## Work order and acceptance gates

### Stage 0 — Freeze the evidence contract (P0)

Dependencies: none. Files: developer.py, models, examples/05_local_llamacpp.py, reporting.

1. Introduce an explicit revision result with distinct generation, parse, validation and
   evaluation states, a source hash, parent hash and the exact evaluation world set.
2. Separate previous-feedback context from current-revision evaluation. Failed/truncated
   responses cannot inherit a successful score. Distinguish unavailable, failed and measured zero.
3. Record all requests/responses, model and server configuration, usage, timing and errors.
   A response archive must distinguish executable code from replay provenance labels.
4. Count accepted executable versions, normalized-code changes and changed decision traces
   separately. Different source hashes alone do not establish different algorithms.
5. Turn F02–F06 probes into focused regression tests alongside each corresponding fix.

**Gate G0:** mixed success/failure/truncation/unscored fixtures produce exact counts and no
false success; a report is reconstructible from revision records. Retain failing Bonsai runs.

### Stage 1 — Make online/replay semantics consistent (P0)

Dependencies: G0 for reliable reporting. Files: runtime.py, replay/, views.py, _policy.py,
models/policy.py, models/replay.py, discovery/.

1. Define one policy observation/action contract, including effective worker capacity,
   remaining logical limits, eligible nodes and the meaning of failed/skipped attempts.
2. Preserve separate K1/K2 round limits where deliberate; distinguish historical work from
   live spending. Do not copy live elapsed time into deterministic replay.
3. Remove accidental None-vs-object budget differences. Specify depth filtering and batch
   truncation explicitly; never score a strategy under silently more generous concurrency.
4. Validate recorded transition order, unique non-root continuation and root child order.
   On deserialization, reject ambiguous order/structure/schema instead of trusting it.
5. Add generated-tree/metamorphic tests: changing hidden suffix values must not change the
   next prefix decision; renaming IDs must preserve equivalent decisions; input mutation must
   not alter worlds; replay must issue zero discovery-agent/evaluator calls.
6. Provide prior-cycle context through a separately defined, immutable, causal interface.
   It must never expose the suffix of the current replay world or holdout information.

**Gate G1:** the budget-aware repro passes both paths; deterministic test worlds have
hand-verifiable probes/rounds/scores; stochastic online execution is not falsely required to
equal replay. Every intentional difference is documented and tested.

### Stage 2 — Make policy execution expressive and predictable (P0/P1)

Dependencies: G1 interface. Files: sandbox.py, artifacts.py, protocols/sandbox.py, developer.py.

1. Write a tested language specification from the interpreter's actual behavior. Include
   function placement, imports, defaults, supported keywords/methods, sorting stability and
   reset/state semantics. Generate capability documentation from that same specification.
2. Support common policy constructs demonstrated by the failed runs where feasible, including
   local pure helpers/math use, or provide exact preflight diagnostics and an explicit supported
   equivalent. Do not silently rewrite the model's algorithm to make a demonstration pass.
3. Keep feature and resource controls public and simple. Defaults must support general
   branch ranking, recovery decisions, batching and stopping rather than fixed templates.
4. Return error phase, AST node, source line/column and allowed alternatives.
5. Preserve the bounded interpreter; add a lightweight optional/standard worker execution
   path without Docker where hard interruption and event-loop isolation are required.
   Document actual platform guarantees. A plain subprocess is not an arbitrary-Python sandbox.
6. Test resource-heavy valid programs, malformed source, native operations, recursion and
   deadline/cancellation behavior. Do not call logical value units an RSS quota.

**Gate G2:** a conformance corpus of materially different policies executes; disabled
capabilities fail before replay with precise errors; deliberately nonterminating code stops
within the documented bound without blocking unrelated runtime work. Runtime code never
switches to unrestricted exec as a compatibility shortcut.

### Stage 3 — Complete the iterative LLM developer (P0)

Dependencies: G0–G2. Files: developer.py, methods.py, transports, developer protocol, artifacts.

1. Define a public iterative developer protocol and a session state: revision cursor,
   candidates, last evaluated source, best source, errors and prior-feedback digest.
2. Supply an executable seed policy or complete incumbent behavior description when source
   is unavailable. Mark examples as syntax guidance, not candidate solutions inserted by SDK.
3. Feed per-step prefix/action/outcome traces and diagnostic trends back to the model.
   Truncation must preserve balanced world coverage and causal branch summaries, not silently
   drop the newest worlds while retaining only aggregate scores.
4. Supply earlier revision diagnoses and live-cycle summaries within an explicit prompt budget.
   Keep task solver/evaluator fixed; prevent holdout traces and trace-specific lookup strategies
   from entering deployable policy logic.
5. Validate → replay on the frozen training pool → update evidence → revise. Bound generation,
   repair attempts and replay work. Do not reset charges or delete failed attempts.
6. Avoid unnecessary duplicate replay of identical (code, world, objective, configuration, seed)
   tuples, while keeping reproducibility checks separate.
7. Continue primary live testing with Bonsai and archive every attempt.

**Gate G3:** on a predeclared mechanics suite, real Bonsai generation produces at least two
valid behaviorally distinct policies, with a later change grounded in actual earlier feedback,
and demonstrates error repair without manually editing generated code. Run at least three
predeclared seeds and report failures and denominator. These are proposed SDK acceptance
criteria, not paper thresholds. Code diversity is not itself an effectiveness result.

### Stage 4 — Repair recovery, accounting and promotion provenance (P0)

Dependencies: G0; session contract from Stage 3. Files: checkpoints.py, accounting.py,
methods.py, runtime.py, storage/, artifacts.py, validation.py.

1. Checkpoint validation collection as in-flight before external dispatch; require explicit
   reconciliation for ambiguous work. The F04 repro must never silently repeat task 9.
2. Persist developer revision progress, accepted candidates and best-source state so restarting
   dreaming continues the remaining work instead of regenerating completed revisions.
3. Fingerprint serialized configuration of replay, objective, developer/model generation,
   sandbox, evaluator/agent experiment identity, validation and promotion gate. For arbitrary
   callbacks require explicit version identifiers. Different coefficients must be detected.
4. Link one stable policy artifact/version ID to replay evidence, holdout decision, promotion
   and checkpoint. Promotion plus champion replacement must be an atomic store operation,
   with campaign-scoped ownership.
5. Reconcile per-run, per-campaign and lifetime counters. Fill token/provider fields in
   RunResult and export all advertised fields. Include developer replay compute and validation
   cost, distinguishing recorded replay work from new spending.
6. Exercise named multi-task campaign semantics rather than reusing one task-key checkpoint
   accidentally. Define whether reuse of a runtime intentionally shares budget/history.
7. Test crashes at each write boundary, partial batches, truncated responses, cancellation,
   over-reported usage and conservative uncertain charges.

**Gate G4:** new-process SQLite recovery passes the failure matrix; configuration changes are
rejected; no completed revision/validation call is silently repeated; exact measured counters
match report/export; a promoted artifact explains its selection after restart. No exactly-once
claim for arbitrary remote effects.

### Stage 5 — Validate selection and recovery decisions (P1)

Dependencies: G1, G3, G4. Files: validation.py, promotion/, evaluation/, models, experiment tools.

1. Give observations a documented extensible diagnostic envelope: outcome, score validity,
   failure category, recoverability, parent-relative change and branch trajectory.
   Task-specific diagnoses remain adapters' responsibility.
2. Classify candidate failure on validation as rejection/insufficient evidence with a persisted
   reason and preserved incumbent, rather than losing the entire campaign.
3. Keep development training, promotion validation and final untouched test data separate.
   Record dataset/task-family identities and split manifests before generation.
4. Persist per-world scores, sample count, uncertainty, all exhausted/failed cases and the
   effect threshold. One tiny positive mean difference is insufficient for broad claims.
5. Test consumption across restart, direct and indirect leakage paths, score rescaling and
   exact task overlap. Explain semantic overlap that JSON hashes cannot detect.

**Gate G5:** decision reports can be recomputed independently; failed/incomplete validation
never promotes; exhausted validation fails closed; heldout data never reaches developer
requests. Generalization remains an empirical claim, not a property of HoldoutPipeline alone.

### Stage 6 — Add an explicit research evaluation profile (P1)

Dependencies: G1 and G3–G5 evidence. Files: objectives, evaluation orchestration, report tools.

Retain the section-3 scalar profile. Implement a separate experimental profile for policy
parameter sweeps, normalized attainment/work curves and effective-round cost; version its
scoring and dataset normalization. Do not relabel replay_beta1/replay_beta2 as the policy's
experimental beta parameter. Add live-cycle manifests and baseline comparisons, including
scope decisions for grid planning and richer branch diagnostics.

**Gate G6:** synthetic known curves yield hand-checkable metrics; a constant/degenerate sweep
is identified; decisions are invariant to task score-unit changes under the chosen
normalization; replay-policy and objective versions are archived. Document remaining
differences from appendix B.2 instead of claiming full paper reproduction.

### Stage 7 — Demonstrate useful closed-loop integration (P1)

Dependencies: G3–G5, plus G6 for appendix-profile claims. Files: workspaces.py, integrations.py,
real examples and benchmark runner.

1. Fix bounded, idempotent cancellation and ownership transfer across checkout, agent work,
   snapshot, release and late confirmation. Prove branch isolation with a real temporary
   filesystem backend; keep unrelated processes outside its control.
2. Run a local model-backed discovery example with a fixed evaluator. The current halving
   example remains a mechanics smoke test.
3. Compare frozen initial policy, parameter search and LLM code development under matched
   discovery budgets; report developer tokens/time separately and total end-to-end cost.
4. Use several outer rounds and fresh online outcomes after promotion, not only the training
   replay score. Include multiple task families/seeds and baseline saturation/failure cases.
5. Predeclare tasks, budgets, seeds and evaluation rules before the acceptance run.
   Publish all raw results, including no-improvement outcomes.
6. Measure replay throughput/memory on growing pools before claiming large-scale cheap search.

**Gate G7:** installation and complete experiments run from documented commands; source,
model digest/settings, split manifest, decisions and costs are archived. A usefulness claim
requires a reproducible quality/cost advantage on a named benchmark with stated uncertainty.
Failure to show an advantage must produce an honest experimental-alpha status, not a
fabricated success. Reproducing the paper's scientific benchmarks is a separate later target.

### Stage 8 — Reconcile Roadmap and prepare release (P1/P2)

Dependencies: applicable gates above.

- Give every feature one status: planned, implemented locally, contract-tested, real-model-tested,
  or effectiveness-measured. Avoid a single green checkmark covering all five.
- Update README, architecture diagram, hardening tracker, examples and launch material together.
- Add installed-wheel smoke tests outside src, optional-dependency tests and example linting
  to supported Python/OS CI. Version checkpoint and artifact schemas with migration policy.
- Expose stable public method/developer/session/store contracts; reduce private runtime coupling.
- Profile immutable replay projections, tree indexing, SQLite indexed reads and incremental
  checkpoints before redesigning them. Preserve isolation while optimizing.
- Archive a release evidence manifest. Existing public CI does not validate uncommitted work.
- Retain the independent/unofficial/non-Google attribution and English documentation.
- Marketing follows reproducible functionality; the old calendar is not permission to
  advertise features that have not passed their gates.

**Gate G8:** every release claim maps to a passing artifact/check, all declared release-blocking
findings are closed, and remaining research/scale work is explicitly deferred. The user's
no-commit condition remains in force; do not mark unresolved weaknesses fixed to enable a push.

## Mapping all 16 user-raised weaknesses

| User concern | Current assessment | Required stage |
| --- | --- | --- |
| LLM policy developer | Implemented locally; real-model acceptance fails | 0, 2, 3, 7 |
| Hard-coded StrictReplay | Injection implemented; shared-contract defect remains | 1 |
| Embedded outer loop | Replaceable Method exists; private coupling remains | 4, 8 |
| Disconnected Objective | Injection works; fingerprints and richer evaluation missing | 4, 6 |
| Sandbox only a protocol | Interpreter exists; language/isolation gaps remain | 2 |
| No automatic holdout | Pipeline exists; restart/reporting/empirical gaps remain | 4, 5 |
| Fragile default optimizer | Custom policies explicitly rejected; algorithmic development still unproven | 3 |
| Weak replay feedback | Basic feedback exists; provenance/history/diagnostics incomplete | 0, 1, 3 |
| Only InMemoryStore | SQLite exists; crash semantics incomplete | 4 |
| Nonserializable executable policies | Source codec exists; complete experiment lineage incomplete | 4 |
| No campaign budget | Reservations exist; scope/recovery correctness needs hardening | 4 |
| No token/USD accounting | Ledger exists; public per-run counters demonstrably wrong | 4 |
| Limited PolicyView | Richer prefix exists; budget parity and earlier-cycle context incomplete | 1, 5 |
| External state copying | Lifecycle adapter exists; real backend proof absent | 7 |
| Cancellation incomplete | Hooks exist; bounded cleanup/late confirmation need repair | 7 |
| Production framework connectors | Runnable smoke tests exist; real-agent experiment absent | 7, 8 |

## Strict interpretation of the Roadmap

Foundation: retain credit for working core, but reopen shared-contract defects.
Observable policies: partial until G1 and diagnostic/causal-history checks pass.
Reliable campaigns: partial until G4.
Evidence before promotion: partial until G5, not complete because a class exists.
Dreaming with code: incomplete until G2–G3 and redeployment acceptance.
Real integrations: partial until G7.
Stable SDK: planned until G8.

The immediate implementation order is G0 → G1 → G2 → G3, with recovery/accounting
work designed early and completed before trusting a promoted policy. No new framework list,
logo revision, broad advertising or paper-performance claim takes priority over these failures.
