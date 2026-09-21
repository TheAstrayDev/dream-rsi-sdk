# Architecture hardening tracker

This tracks concrete gaps against [Dream-RSI section 3 and appendix B.2](https://arxiv.org/html/2609.14858v1).
The paper's fixed discovery agent and evaluator, recorded-transition replay, and
executable policy revision are the reference. The extensions below are SDK design
choices, not claims that the paper prescribes these Python interfaces.

## Completed in the first hardening increment

| Gap | Implementation | Verification |
| --- | --- | --- |
| Hard-coded replay engine | `replay=` constructor injection and `ReplayEngine` protocol; all default evaluation paths delegate to it | A recording fake checks direct replay, comparison, incumbent and challenger evaluation |
| Disconnected objective | `objective=` applied to copied trajectories before every default comparison | Reversed ranking promotes the expected challenger; non-finite scores fail; engine cache stays intact |
| Embedded outer loop | `DefaultMethod` extracted into `methods.py`; `method=` replaces the whole sequence | Custom method tested through async, sync and multi-task campaign entrypoints |

The default method still uses runtime internals for campaign state and events.
A public campaign context and persistence contract remain future work. The three
extension hooks do not make arbitrary external state or code safe automatically.

## Remaining work and acceptance criteria

| Priority | Gap | Required evidence before marking complete |
| --- | --- | --- |
| Critical | Real LLM policy developer | Provider-neutral developer callback generates executable source; multiple diagnosis/rewrite/replay iterations on a fixed training pool; source revision and measured feedback retained |
| Critical | Generated-code isolation | Enforced filesystem/network/process/resource boundary; timeout and hostile-code tests; no in-process `exec` of untrusted policies. A subprocess alone is not a security boundary |
| Critical | Automatic holdout pipeline | Independent task/world splits established before development; developer never sees held-out feedback; chosen candidate evaluated once under an explicit selection protocol; report sampling limits, not proof of generalization |
| High | Custom-policy optimizer | Explicit supported strategy or developer backend for arbitrary policies; avoid silent no-op evolution; tests on a user-defined policy |
| High | Iterative replay feedback | Preserve trajectories, diagnosis, source changes and per-revision results; failed revisions yield actionable feedback without replacing a working incumbent |
| High | Durable campaign / resume | Transactional checkpoint of worlds, policy versions, counters and method state; restart equivalence and interrupted-write tests |
| High | Executable artifacts | Source, content hash, schema version, parent revision and developer provenance; restore without unsafe deserialization or implicit code execution |
| High | Campaign budget | Shared allowance across tasks, online runs and developer work; reserve before dispatch; test concurrent exhaustion and resumption |
| High | Token / dollar accounting | Adapter-reported nested usage with explicit pricing and uncertainty; separate online, evaluator and developer spending; reservations and reconciliation before USD limits are accepted |
| High | Rich policy diagnostics | Identical online/replay view of revealed observations and history; tests ensure unrevealed outcomes do not leak |
| High | External workspace state | Explicit snapshot/restore/cleanup contract for files, browser, database or VM state; adapter-specific isolation tests |
| Medium | Real cancellation | Adapter cancellation hook and resource cleanup; distinguish cancelled waits from confirmed termination; tests for outstanding remote work |
| High | Framework integrations | One real, maintained integration first, with reproducible task, dependency versions and end-to-end evaluation; expand only after user evidence |

Recommended implementation order: artifact schema and execution boundary → iterative
policy developer → independent validation → campaign persistence and shared budgets.
Accounting and external-state adapters must be designed together with real integrations.
Do not market unfinished items as implemented or claim the original paper's gains.

## Validation

42 regression tests pass locally, plus Ruff and Pyright. Existing strict replay
semantics remain covered. This increment adds no model provider calls and no generated
code execution. The SDK remains an independent alpha, not a complete reproduction.
