# Dream-RSI: research mapping and SDK architecture

Initial audit: September 20, 2026. Documentation updated September 21, 2026.

## Research basis

Sources: [paper and appendices](https://arxiv.org/html/2609.14858v1),
[project website](https://dream-rsi.com/), and
[official research repository](https://github.com/zhengkid/Dream-RSI).
At the initial audit, the official repository stated that code was being prepared for release.
This SDK is neither the official implementation nor a verified reproduction of its experiments.

The method improves search orchestration around a fixed discovery agent and evaluator.
Recorded attempts form a tree; policies replay its transitions using revealed information.
Replay does not predict outcomes beyond recorded support. The section 3 objective is
`V = best_score - beta1 * N + beta2 * N / max(1, K)`.
Selection compares policies on a fixed world pool. Its historical-score guarantee does
not guarantee better outcomes in the next real run.

## SDK design goal

Provide a small Python orchestration layer independent of a model's internals.
Applications own candidate generation, execution state, and scoring. The SDK owns search
allocation, recording, replay, and policy comparison. A basic integration should need only
two functions, with explicit adapters for more control.

## Initial implementation audit

The starting project contained modules and one numerical example, but no README or tests.
Several subsystems were incompatible scaffolds: a protocol or class name did not imply
an executable feature. The initial example failed at the first policy decision.

| Original defect | Correction |
| --- | --- |
| Policies used missing `node_id` and `visit_count` fields | Use the actual shared NodeSummary fields |
| Runtime and models defined incompatible duplicate types | Shared model classes with execution-module reexports |
| Callable evaluators and built-in evaluation constructors failed | Sync/async function support, valid fields, finite-score checks |
| Toy refinement repeatedly received the original task | FunctionalAgentAdapter passes the selected parent's state |
| Call/time budgets were ignored and zero limits lost | Check limits before scheduling and count attempted calls |
| Parallelism was a sequential loop | Concurrent attempts with stable batch recording order |
| Replay hid boundaries using unrevealed information | Build eligible nodes from the revealed tree and validate actions |
| Set iteration and mutable RNG state changed replay results | Stable creation order and isolated policy prototypes |
| Replay configuration coefficients were ignored | Pass coefficients through all public replay paths |
| Promotion used inconsistent evidence and fabricated holdout inputs | Correct evidence keys, decision fields, and missing-evidence handling |
| Optimizers and version management used nonexistent arguments | Correct constructors, identifiers, and status transitions |
| Runtime did not persist results; get_tree always returned None | Save runs, nodes, events, evaluations, and reconstruct trees |
| Committed trees remained mutable through returned references | Snapshot copies and isolated committed reads |
| Export discarded states and observations | Preserve node data and reject unsupported JSON values |
| Nodes were reported as rounds, calls as monetary cost | Separate call counters and actual decision-round counts |
| Example claimed guaranteed online improvement | Limit the claim to selection on fixed replay history |

## Module map

1. `adapters.py`, `protocols/agent.py`: integration boundary.
2. `runtime.py`: online runs, budgets, events, worlds, and policy selection.
3. `models/`: shared data values and contracts.
4. `discovery/`: trees, commits, serialization, and structural invariants.
5. `replay/`, `_policy.py`: replay and shared action validation.
6. `policies/`, `optimization/`, `promotion/`: strategy decisions and adoption.
7. `evaluation/`, `storage/`, `events/`: scoring, persistence interfaces, observability.
8. `tests/`: regression checks and executable integration contracts.

`ReplayWorldRecord` stores metadata; `ReplayWorld` is an executable replay environment.
They serve different purposes. `RunResult` holds live policy and tree objects; use
`export_run` for a JSON data export.

## Remaining engineering work

- Iterative policy-code development with feedback between revisions. Current optimization
  searches parameters and exposes a custom optimizer protocol.
- Independent validation worlds and generalization reports. HoldoutGate alone does not
  create the dataset, splits, or validation process.
- Durable storage and resume, including policy/configuration serialization.
- Provider token/dollar accounting and campaign-wide limits.
- Isolated generated-code execution. SandboxExecutor is a protocol only.
- Full revealed observations, diagnostics, and a historical-context contract for policies.
- Real adapters and equal-budget comparative experiments across architectures.
- Performance measurements for large states and repeated view construction.

Prioritize reliable contracts, observable policy context, and independent evidence before
adding program generation and framework integrations. Framework names without working
adapters do not make the SDK more universal.

## Validation evidence

The initial public commit passed 33 regression tests on Python 3.11–3.14 on Linux and
Python 3.14 on Windows in [CI](https://github.com/TheAstrayDev/dream-rsi-sdk/actions/runs/35523999053).
Ruff, Pyright, and package builds also passed. Locally, a wheel was installed and imported
from site-packages in isolated Python mode.

The tests cover all seven policies, zero budgets, evaluation failures, concurrency,
timeouts with partial results, promotion, absent holdout evidence, replay reproducibility,
and snapshot isolation. No real external model was used.

The numerical example completed five cycles with 135 agent and 135 evaluator calls;
one observed run reached approximately -0.002940 without policy promotion. A separate
regression test exercises actual promotion. The replay lab reports measured call deltas;
its toy scores must not be presented as evidence of LLM cost or quality improvements.
