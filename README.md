<p align="center">
  <img src="assets/banner.svg" alt="Dream-RSI SDK Alpha — independent exploration-policy SDK" width="100%">
</p>

<p align="center">
  <a href="https://github.com/TheAstrayDev/dream-rsi-sdk/actions/workflows/ci.yml"><img src="https://github.com/TheAstrayDev/dream-rsi-sdk/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/status-alpha-eebc73?style=flat-square" alt="Alpha">
  <img src="https://img.shields.io/badge/Python-3.11%2B-75e0be?style=flat-square" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/runtime_dependencies-0-75e0be?style=flat-square" alt="Zero runtime dependencies">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-c3d0d4?style=flat-square" alt="Apache 2.0"></a>
</p>

<p align="center"><strong>Bring your agent. Record its search. Replay alternative exploration strategies.</strong></p>
<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="#architecture">How it works</a> ·
  <a href="#comparison">Research comparison</a> ·
  <a href="#roadmap">Roadmap</a> ·
  <a href="docs/integration.md">Integration guide</a>
</p>

> [!IMPORTANT]
> **An independent, unofficial project. Not a Google product.**
>
> I am [TheAstrayDev](https://github.com/TheAstrayDev), an independent developer.
> I am not an employee of Google or Google DeepMind. This repository is my personal
> research initiative, **not a commercial development by Google**, an official SDK,
> or a project sponsored or endorsed by Google or the research authors.
>
> I have attempted to build a Dream-RSI SDK from publicly available information:
> the paper, project website, and authors' materials. I plan to keep improving it,
> testing it in practice, and closing the gap between this implementation and the research.

## What is this?

**Dream-RSI SDK** is a small Python orchestration layer for exploring candidate solutions
and comparing exploration policies on recorded experience. You supply the agent and evaluator;
the SDK handles attempts, discovery trees, historical replay, and policy selection.

It is designed for developers who already have a **generate → evaluate → refine** loop
and want to experiment with how their search branches, batches work, and stops.
The core has no dependency on a model provider or agent framework.

**Alpha means a working foundation, not a complete reproduction of the paper.**
The default optimizer searches built-in parameters. `LLMPolicyDeveloper` can instead
revise executable policy source through your model client and measured replay feedback.
Its lightweight interpreter needs no Docker and supports a restricted SDK language.

| At a glance | Current state |
| :--- | :--- |
| Runtime | Python 3.11+ · zero required third-party dependencies |
| Integration | Sync/async callables · stateful function adapter · full agent protocol |
| Validation | Regression tests · Ruff · Pyright · wheel build and installation |
| Version | `0.1.0a3` · source commit · APIs may change |
| Distribution | [PyPI](https://pypi.org/project/dreamrsi/0.1.0a2/) · source · GitHub installation |

**Try it without an API key:** run the [replay lab](examples/02_replay_lab.py) to record a toy
search and compare three policies. It reports whether replay caused any additional agent
or evaluator calls. This is an executable mechanics demo, not an LLM performance benchmark.

## Tested with a real local model

**Bonsai-27B-Q1_0, running through llama.cpp, wrote and repaired executable policy code
from replay feedback.** One candidate passed held-out replay, was saved and reloaded,
then improved a fresh toy refinement run with the discovery agent and evaluator unchanged.

![Bonsai-27B-Q1_0: measured source revisions, replay rounds, and fresh online results](assets/bonsai-development-v4.svg)

| Fresh online task · seed 43 | Balanced baseline | Reloaded generated policy |
| :--- | ---: | ---: |
| Agent calls | 6 | 6 |
| Final absolute state (lower is better) | 1.5000 | 0.1875 |
| Best evaluator score (higher is better) | -1.5000 | -0.1875 |

This is **87.5% less residual error on one synthetic task**, not a speedup or a general
AI benchmark. The latest follow-up passed every demonstration gate: **5/6 revisions
scored**, with different executable structures and replay decisions, held-out promotion,
and reloaded execution. The model repaired a stalled policy from **1,000 to 4 replay
rounds**, then reduced probes from 5 to 3. See the
[latest report and raw evidence](docs/experiments/sandbox-v4-2026-09-22.md).

The earlier three-seed matrix promoted **1/3 seeds**, with **7/12 revisions scored**;
its stricter diversity gate did not pass. These are separate configurations, not pooled
success rates. The [original matrix](docs/experiments/bonsai-2026-09-22.md) remains available.

## What's new in 0.1.0a3

This source commit adds the Appendix B grid workflow, bounded source reloads with
SQLite manifests, replay-capacity accounting, and the corresponding local evidence.
The full test suite passes (**150 tests**); the three-revision Bonsai follow-up scored
every revision and kept the incumbent on ties. The Appendix B implementation is
source-only for now; the published PyPI install remains `0.1.0a2` until the next
release is published.

<a id="quickstart"></a>
## Install and try

You need **Python 3.11+**. Install the published alpha in your virtual environment:

```bash
python -m pip install dreamrsi==0.1.0a2
```

To run the repository examples or contribute, install from source with Git:

```bash
git clone https://github.com/TheAstrayDev/dream-rsi-sdk.git
cd dream-rsi-sdk
python -m venv .venv
```

```bash
# Linux / macOS
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
python -m pip install -e .
python examples/02_replay_lab.py
```

The demo prints a table of recorded best scores, probes, and decision rounds, followed by
`Additional agent calls during replay: 0` and `Additional evaluator calls during replay: 0`.
No model account or API key is needed. These are SDK call counts, not dollar savings.

For the full online/replay loop, run:

```bash
python examples/01_toy_optimization.py
```

You can also install directly from GitHub:

```bash
python -m pip install "git+https://github.com/TheAstrayDev/dream-rsi-sdk.git@main"
```

This installs the current `main` branch. Replace `main` with a commit SHA to pin your
installation. The package and import name are **`dreamrsi`**.

## Start with two functions

```python
from dreamrsi import Budget, DreamRSI

def agent(task):
    # Replace this with your existing model or agent call.
    return task.upper()

def evaluate(answer):
    return float(len(answer))

rsi = DreamRSI(agent=agent, evaluator=evaluate, budget=Budget(model_calls=4))
result = rsi.run_sync("hello")

print(result.best)                 # HELLO
print(result.best_score)           # 5.0
print(result.costs.model_calls)    # 4
```

This demonstrates the interface, not a quality improvement: the deterministic agent
returns the same answer each time. In simple callable mode, every attempt receives
**the original task**. Use a stateful adapter to refine a previous result.

## Refine a candidate

```python
from dreamrsi import Budget, DreamRSI, FunctionalAgentAdapter
from dreamrsi.policies import DepthFirstPolicy

def refine(state, context):
    return {"x": state["x"] * 0.5}

rsi = DreamRSI(
    adapter=FunctionalAgentAdapter(refine),
    evaluator=lambda candidate: -(candidate["x"] ** 2),
    policy=DepthFirstPolicy(),
    budget=Budget(model_calls=6),
)

result = rsi.run_sync({"x": 8.0})
print(result.best)        # {'x': 0.125}
print(result.best_score)  # -0.015625
```

Each output becomes the next state in its branch. **Higher scores are always better**;
this example uses `-x²` to express a minimization objective.

## Run the improvement loop

```python
import asyncio
from dreamrsi import Budget, DreamRSI, FunctionalAgentAdapter

async def main():
    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(lambda state: {"x": state["x"] * 0.5}),
        evaluator=lambda candidate: -(candidate["x"] ** 2),
        budget=Budget(model_calls=20, max_parallelism=4, max_depth=8),
    )
    result = await rsi.improve({"x": 8.0}, rounds=3)
    print("Best:", result.best)
    print("Worlds:", len(result.worlds))
    print("Promotions:", result.metrics["policy_promotions"])

asyncio.run(main())
```

The budget applies to **each online run**: this example permits up to 60 `propose` calls
across three runs. No promotion is a valid outcome. Inside an existing event loop,
use `await rsi.run(...)` or `await rsi.improve(...)` directly instead of the sync wrappers.

<a id="architecture"></a>
## How it works

Dream-RSI turns previous discovery runs into replay environments for exploration policies.
The agent and evaluator stay fixed while the search strategy changes.
See the [authors' method overview](https://dream-rsi.com/#method).

<p align="center">
  <img src="assets/architecture.svg" alt="Online exploration creates discovery trees; committed trees become replay worlds; policies are evaluated and selected for the next run. Source development, validation, checkpoints and a bounded policy interpreter support the loop." width="100%">
</p>

*An original SDK diagram mapped to Figure 1 and section 3 of the
[Dream-RSI paper](https://arxiv.org/html/2609.14858v1#S3), not an official Google figure.
Green denotes implemented components; the lower row records execution and recovery boundaries.*

1. **Online explore:** select root or leaf nodes, run bounded parallel attempts, evaluate
   their results, and record states and observations in a `DiscoveryTree`.
2. **Replay worlds:** commit the tree and wrap it as a `ReplayWorld`. Replaying policies
   uses recorded transitions without calling the discovery agent or evaluator.
3. **Dream and select:** compare the incumbent and candidate policies on the same world
   pool. An evidence gate selects a policy for the next online run.

Replay cannot predict outcomes outside the recorded tree. Improvement on fixed historical
replay scores does not guarantee improvement on the next real run.

## Fit it into your architecture

| Integration level | Interface | Use case |
| :--- | :--- | :--- |
| Minimal | `agent(task)` + `evaluator(candidate)` | Independent attempts with an existing model API |
| Stateful | `FunctionalAgentAdapter(step)` | Refining an answer, program, parameter set, or plan |
| Full control | `AgentAdapter` | Custom memory, tools, execution, and workspace snapshots |

The full adapter needs no inheritance. Implement five methods:

```text
initial_state(task)
    └─ propose(state, context)
          └─ execute(proposal, state, context)
                └─ observe(execution, state)
                      ├─ evaluator(observation, context)
                      └─ next_state(observation, state)
```

Methods may be sync or async. Keep model clients **inside the adapter** and state in
copyable snapshots. Your adapter must isolate external files and processes between branches.

[Read the integration guide: state, context, budgets, cancellation, and export →](docs/integration.md)

| Extension point | Responsibility | Included implementations |
| :--- | :--- | :--- |
| Agent | Generate and execute candidates | CallableAgentAdapter, FunctionalAgentAdapter |
| Evaluator | Score results | Callable, Numeric, Composite |
| ExplorationPolicy | Choose branches | Balanced, Greedy, BreadthFirst, DepthFirst, Random, EpsilonGreedy, FixedParallel |
| PolicyOptimizer | Propose strategies | DeterministicPolicyOptimizer, ParameterSearchOptimizer |
| Policy development | Write and revise executable source | LLMPolicyDeveloper, SourcePolicy, PolicySandbox |
| PromotionGate | Decide whether to adopt | ReplayOnlyGate, HoldoutGate, CompositeGate |
| Store | Save runs and evidence | InMemoryStore, SQLiteStore |

<a id="comparison"></a>
## Replace the orchestration pieces

`DreamRSI(..., replay=my_engine, objective=my_objective, method=my_method)`
accepts independent components. Defaults retain strict recorded-tree replay and the
paper-inspired phase order. A custom objective changes policy ranking everywhere,
including promotion; it does not replace the fixed task evaluator.

See [extension contracts](docs/integration.md#replaceable-replay-objective-and-method)
and the [architecture hardening tracker](docs/hardening.md). Source development, a bounded interpreter, validation and durable checkpoints are
available in the SDK. See the [research-loop guide](docs/research-loop.md).

The unreleased source-only [Appendix B mode](docs/appendix-b.md), not included in
PyPI 0.1.0a2, adds `OptimalPolicy.solve()`,
observation helpers, pre-cycle `plan_grid()`, persisted earlier-live history and beta
sweeps. `AppendixPolicyDeveloper` rewrites complete class source against those sweeps.
Its AUC normalization is explicitly SDK-versioned; unpublished numerical details are
not claimed as exact research-code parity.


## Original research vs. this SDK

Based on [section 3](https://arxiv.org/html/2609.14858v1#S3),
[appendix B.2](https://arxiv.org/html/2609.14858v1#A2.SS2), and the
[project website](https://dream-rsi.com/). This compares the **published method with this
SDK's code**, not compatibility with an official implementation. On September 20, 2026,
the [official repository](https://github.com/zhengkid/Dream-RSI) stated that code was being prepared for release.

**✓ Implemented** · **◐ Partial** · **○ Planned**

| Research component | SDK | Implementation or difference |
| :--- | :---: | :--- |
| Fixed discovery agent and evaluator | ✓ | Separate integrations; model weights are not updated |
| Discovery trees with states and outcomes | ✓ | Python snapshots; external workspace isolation belongs to the adapter |
| Root/leaf selection and batched work | ✓ | Shared action validation and concurrent online execution |
| Replay of recorded transitions | ✓ | StrictReplay; unrevealed outcomes stay hidden |
| Growing historical world pool | ✓ | SQLite checkpoints and restart recovery; uncertain external calls require reconciliation |
| Decisions based on revealed observations | ✓ | Shared prefix-only observations, diagnostics and history |
| Quality/work/parallelism objective | ✓ | Section 3 β₁/β₂; separate Appendix B beta sweep with documented SDK AUC conventions |
| Appendix B solve, helpers and grid planning | ✓ | Separate grid runtime with bounded class-source execution and prior-live planning snapshots |
| LLM-driven iterative policy-code revision | ◐ | Executable source revision and error repair verified with local Bonsai; restricted language, toy evidence rather than research benchmarks |
| Incumbent comparison and online redeployment | ✓ | Improve loop and evidence gate on a shared world pool |
| Algorithm, math, and GPU experiments | ○ | Toy demos and SDK tests; published results have not been reproduced |

`HoldoutPipeline` collects separate worlds and consumes each validation batch once.
`PolicySandbox` interprets a bounded policy language without Docker or host `exec`.
Its [configuration guide](docs/sandbox.md) covers resource limits, per-function allowlists,
JSON profiles and an optional interruptible worker process.
These are SDK implementations, not reproductions of every research execution detail.

## Alpha limitations

- **No universal speedup claim.** A compatible interface is not evidence of effectiveness
  on every AI architecture. Meaningful evaluation and controlled experiments are essential.
- **Restricted generated-policy language.** Helpers, bounded collections and a math proxy
  are supported; arbitrary Python, host imports and external tools are unavailable.
- **Reported costs.** USD/token limits require explicit ceilings; nested API usage requires
  adapter reporting. Unknown usage is conservatively estimated.
- **Recovery boundaries.** SQLite restores saved phases; uncertain external work must be
  reconciled before skipping an interrupted round. State must be JSON-compatible.
- **Service-specific cancellation.** Adapters confirm remote termination; a cancelled wait
  alone cannot stop a thread or a remote job.
- **Experimental evidence.** A local model produced a useful policy on a toy task.
  Robust multi-seed gains, broad generalization and the original benchmarks remain unverified.
  Earlier candidates reached the replay round cap; the latest model-written policy repaired
  that behavior on the recorded toy worlds. Robust stopping on other tasks remains unverified.

<a id="roadmap"></a>
## Roadmap

These are priorities, not promised release dates. Progress means working code and
reproducible checks rather than a growing list of framework names.

| Phase | Deliverable | Completion criterion |
| :--- | :--- | :--- |
| **01 · Foundation** ✓ | Adapters, trees, replay, policies, budgets, tests | Executable examples and contract checks |
| **02 · Observable policies** ✓ | Revealed observations, diagnostics, historical context | Tests exclude future-information leakage |
| **03 · Reliable campaigns** ◐ | Persistent storage, resume, campaign-wide limits | Resume after a restart without losing history |
| **04 · Evidence before promotion** ✓ | Independent validation worlds and reports | Separate train/validation evidence and reproducible decisions |
| **05 · Dreaming with code** ◐ | LLM policy developer and bounded execution | Behavioral revision, stopping repair, promotion and reload verified on a toy task; broaden evaluation |
| **06 · Real integrations** ◐ | Real-agent examples and provider cost accounting | Public comparisons under equal, documented budgets |
| **07 · Stable SDK** ○ | Stable APIs, versioned data, package publication | Compatibility checks and migration guidance |

See [ARCHITECTURE.md](ARCHITECTURE.md) for the technical audit and implementation priorities.

## Help shape the next iteration

Already building a generate/evaluate loop? Try one task with your own adapter and
[tell me what blocked you](https://github.com/TheAstrayDev/dream-rsi-sdk/issues/new?template=early_adopter.yml).
Useful feedback includes the interface you needed, your scoring method, and a minimal
reproduction. Positive results, failures, and "this does not fit my workflow" are all useful.

For fixes and larger changes, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src tests examples
python -m pyright
```

```bash
python -m pip install build
python -m build
```

The initial public commit passed CI on Python 3.11–3.14 on Linux and 3.14 on Windows.
See [Actions](https://github.com/TheAstrayDev/dream-rsi-sdk/actions) for the current commit's
status. Tests need no paid APIs or model credentials.

```text
src/dreamrsi/
├── adapters.py     # existing-agent integration
├── runtime.py      # online exploration and shared operations
├── methods.py      # replaceable outer improvement loop
├── discovery/      # attempt trees and snapshots
├── replay/         # recorded-history replay
├── policies/       # seven built-in strategies
├── optimization/   # candidate policies and version management
├── promotion/      # evidence-based adoption decisions
├── evaluation/     # scoring and composition
├── storage/        # in-memory and SQLite storage
├── events/         # events and callbacks
├── models/         # shared data types
└── protocols/      # extension contracts
```

## Research credit and project ownership

The research is by **Tong Zheng and coauthors**, affiliated with Google, Google DeepMind,
the University of Maryland, and the University of Virginia. Original materials:

- [Dream-RSI: Recursive Self-Improvement through Evolving Worlds — arXiv:2609.14858](https://arxiv.org/abs/2609.14858)
- [Official project website](https://dream-rsi.com/)
- [Official research repository](https://github.com/zhengkid/Dream-RSI)

This independent SDK is maintained by **[TheAstrayDev](https://github.com/TheAstrayDev)**.
Please distinguish research citations from references to this implementation.
The logo and architecture illustration are original SDK assets, not Google branding.

Licensed under [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for attribution and
non-affiliation. The personal nature of this initiative does not change the license terms.

---

<p align="center"><img src="assets/logo.svg" width="48" alt="Independent Dream-RSI SDK logo"><br><sub>Built independently. Grounded in recorded experience. Still evolving.</sub></p>
