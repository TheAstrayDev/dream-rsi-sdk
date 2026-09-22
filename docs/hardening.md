# Architecture hardening status

Implementation status as of September 22, 2026. Reference:
[Dream-RSI section 3 and appendix B.2](https://arxiv.org/html/2609.14858v1).
Read the [complete integration and recovery guide](research-loop.md) before using a long campaign.

| Original gap | Implemented response | Boundary / evidence |
| --- | --- | --- |
| No LLM policy developer | `LLMPolicyDeveloper`, provider callback and `from_runnable` transport | Real Bonsai source repair, replay, promotion and reload demonstrated on a toy task; 1/3 matrix seeds promoted |
| Hard-coded replay | `replay=` and `ReplayEngine` | Direct replay, comparison and default improvement paths tested |
| Embedded outer loop | `method=` and `DefaultMethod` | Replace entire orchestration; default method still coordinates runtime internals |
| Disconnected objective | `objective=` with isolated trajectories | Applied consistently before selection; recorded cost available |
| Sandbox interface only | Bounded AST interpreter, JSON profiles, per-function allowlists and optional `ProcessPolicySandbox` | Worker timeout/cancellation and event-loop responsiveness tested on Windows; no Docker or arbitrary Python execution |
| No holdout pipeline | `HoldoutPipeline` and deterministic task splitting | Separate collection, no developer feedback, single-use batches; semantic independence belongs to dataset design |
| Fragile default optimizer | Explicit rejection of unsupported custom policies; source developer works independently of built-in classes | Custom policies need a supplied developer/optimizer rather than silent no-op behavior |
| Weak feedback | Trajectories, revealed observations, line errors, objective components and source ancestry | Latest Bonsai follow-up changed replay behavior and repaired stopping; broader robustness remains unverified |
| In-memory-only campaigns | `SQLiteStore`, phase checkpoints and metering journal | Restart after online collection tested; interrupted external work requires reconciliation |
| Nonportable policies | `PolicyArtifact`, SHA-256 integrity, `PolicyCodec` | Built-in RNG state, source and explicit custom codecs; no pickle/dynamic imports |
| No campaign budget | Shared reservation ledger | Across online, validation and developer work; concurrent admissions cannot over-reserve |
| Missing token/USD accounting | `Usage`, reports and explicit per-stage ceilings | Nested calls need adapter reports; unknown usage stays estimated; overruns block later work |
| Limited policy view | Prefix-only observations, diagnostics, revealed history and `last_round` outcomes | Past empty continuations are visible; hidden outcomes and mutation leakage covered by tests |
| Online/replay budget mismatch (F02) | Shared default worker capacity, effective budget views and logical replay caps | Separate K1/K2 preserved; probe accounting does not simulate variable provider billing; see [limits contract](research-loop.md#shared-policy-limits) |
| Unsafe external state copies | Workspace checkout/snapshot/release/cancel lifecycle | Backend must implement its service-specific isolation; descriptors stay in trees |
| Incomplete cancellation | Adapter cancellation hook and confirmed/uncertain status | Cannot magically stop an arbitrary thread or remote service; backend confirmation required |
| No framework adapter | `RunnableAgentAdapter` | Tested with actual LangChain 1.6.3; schema transforms and remote state isolation remain integration-specific |

## Research differences that remain

The portable policy language intentionally restricts Python for bounded execution without an external sandbox.
The [Appendix B mode](appendix-b.md) now implements grid solve, observation helpers,
pre-cycle planning, earlier-live history and beta sweeps. Its Pareto AUC conventions
are explicitly versioned SDK choices where the published prompt leaves details unspecified.
Published scientific benchmarks are not reproduced. Generalization and real-model cost
savings require experiments; unit tests do not establish them.

## Verification

The local suite passed 135 tests and covers shared replay limits, recovery boundaries, policy development, interpreter idioms,
source-incumbent equivalence, configurable profiles and worker lifecycle. See the
[latest real-model report](experiments/sandbox-v4-2026-09-22.md) for measured revision
changes and the [earlier matrix](experiments/bonsai-2026-09-22.md) for full denominators.
Local tests and remote CI are separate evidence; consult Actions for the current commit.
