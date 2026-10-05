![Dream-RSI SDK Beta](https://raw.githubusercontent.com/TheAstrayDev/dream-rsi-sdk/v0.3.0b1/assets/banner.png)

# Dream-RSI SDK · Beta

**Bring your agent. Preserve verified quality. Account for every model request.**

An independent, unofficial Python SDK inspired by Dream-RSI research. Maintained by
**TheAstrayDev**, who is not a Google or Google DeepMind employee. This is a personal
research initiative, not a commercial Google development, official SDK or endorsed product.

Python 3.11+ · zero core third-party dependencies · Apache-2.0 · version **0.3.0b1**.

## Install

```bash
python -m pip install --pre --upgrade dreamrsi==0.3.0b1
```

For a source checkout, install with `python -m pip install -e .`.

The package includes the Python API and the `dreamrsi` command. Publishing policy
packages to GitHub additionally requires GitHub CLI (`gh`).

## What's new 0.3.0b1

`QualityContract` protects the supplied original policy's search and complete
batches. Stop only when the best valid raw quality exactly reaches a proven task
maximum. Unknown bounds continue the original search. The actual returned answer
is selected by raw quality rather than a work-penalized composite score.

```python
from dreamrsi import Budget, DreamRSI, EconomyPlan, QualityContract

rsi = DreamRSI(
    agent=my_agent,
    evaluator=my_evaluator,
    policy=my_original_policy,
    budget=Budget(model_calls=4),
    quality=QualityContract(id="exact-quality-v1", upper_bound=1.0),
    economy=EconomyPlan(baseline_calls_per_task=4, horizon=6),
)
result = await rsi.run(task)
```

Replace these application integrations. Use `1.0` only when it is a sound global
bound for the feasible answer domain. Strict mode requires no policy training.
Custom raw-quality extractors, local task-bound functions and an evaluated initial
candidate are supported. Reference and SDK budgets and initial candidates must match.
Use an otherwise identical contract with `certified_stopping=False` for the full
reference, preserving quality metadata in both arms. The no-loss argument compares
the same response trajectory, not independent stochastic runs or different time cutoffs.

`EconomyPlan` recalculates preparation headroom from actual spending, historical
costs and the unfinished deployment floor before each request. Completed-task
counters survive recovery; measured strict payback uses actual deployment costs.
Purpose-tagged ledgers count reported
nested provider calls and failed requests. Unknown tokens/dollars remain unknown.
The economic target does not truncate quality-preserving fallback search.

The sandbox now has finite `small`, `balanced` and `large` presets and JSON profile
save/load. All supported language features remain enabled in each preset; individual
limits and allowlists are configurable. A bounded validated-code cache keeps fresh
execution state and checks. Local paired interpreter timings improved by 2.90x with
one frontier node and 1.41x with eight; these are not model-call savings.

```python
from dreamrsi import PolicySandbox, SandboxConfig

sandbox = PolicySandbox.from_preset("large", max_steps=2_000_000)
SandboxConfig.preset("large").save("sandbox.json")
sandbox = PolicySandbox.from_file("sandbox.json")
```

Raw-quality callbacks receive isolated records. Built-in stores atomically reserve
holdouts, and nested source policies retain their sandbox profile during recovery.

Existing applications retain empirical policy development without a quality
contract. Set `preserve_policy=False` explicitly to enable policy rewrites with
the contract. Holdout evidence does not prove universal no-loss transfer.

The public `PolicyDeveloper` protocol, versioned schema rejection, legacy bundle
checks and installed-wheel CLI/sandbox gates form the Beta integration surface.
Nested certified artifacts require 0.3.0b1 or newer. See the
[Beta notes](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/releases/0.3.0b1.md),
[quality proof](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/quality-contract.md)
and [all-in guide](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/all-in.md).

## Third-party policy and replay packages

Portable JSON bundles and GitHub-hosted package sharing transfer recorded experience.
Community developers can distribute policy versions and recorded discovery trees;
recipients import them into local SQLite memory with their own agent, quality metric,
task-family contract and acceptance rules. These replay datasets contain observed
search transitions, not model weights. Saved policies can avoid repeated development
when they meet the recipient's quality floor; new tasks still run the recipient's agent.

```bash
dreamrsi list
dreamrsi install OWNER/REPOSITORY
dreamrsi save my-policy-pack --all
dreamrsi publish .dreamrsi/packages/exports/my-policy-pack.dreamrsi.json
```

Use a real package reference for `OWNER/REPOSITORY`. Export requires previously saved
memory; publication requires GitHub CLI and creates a public repository. See the
[complete walkthrough](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/releases/0.2.0a2.md)
for the diagram, executable integration example, and compatibility requirements.

## Basic agent integration

```python
from dreamrsi import Budget, DreamRSI

rsi = DreamRSI(
    agent=lambda task: task.upper(),
    evaluator=lambda answer: float(len(answer)),
    budget=Budget(model_calls=4),
)
result = rsi.run_sync("hello")
print(result.best)  # HELLO
```

This example demonstrates integration, not quality improvement. Stateful adapters support
generate/evaluate/refine tasks. Replay uses recorded outcomes without new discovery calls.
`LLMPolicyDeveloper` writes and iteratively rewrites executable source from measured feedback.
Persistent champion reuse and recorded-history replay can avoid repeated development.
Promotion uses independent validation and paired raw-quality/probe evidence.
Broad end-to-end economics remain unverified; the narrow follow-up below has
separate limits.
The SDK includes configurable Docker-free policy interpreters, optional process execution,
held-out validation, SQLite recovery and reported token/USD accounting.

## Measured experiments

### Latest local follow-up: real Bonsai Q2 answers and structural transfer

An isolated experimental Lasso module using the SDK's `QualityContract` hooks
started with empty memory and eight new application tasks. Local Bonsai Q2
generated preparation and fallback answers; a mathematical active-pattern transfer
made no model requests when exact rational KKT checks certified the new answer.
This module is not included in the installed SDK and did not generate policy code.

| Recovered matched comparison, eight tasks | Baseline | Experimental Dream path |
| :--- | ---: | ---: |
| Calls, including preparation | 16 | **10** |
| Matched input + output tokens | 36,960 | 23,102 |
| Exact global optima | 4/8 | **6/8** |

Raw quality was equal or better on every paired task after a separate control
repeat. The fresh campaign saved **37.5% of calls**, including two preparation
calls; four application tasks needed no LLM request. One baseline request timed
out, so the original preregistered success flag remains false. The affected control
was repeated separately, and all **28 actual calls** are retained in accounting.
Complete control token usage and dollar ROI remain unknown. Adding 12 earlier
research calls gives 22 Dream-side calls; historical research has not paid back
against this series's 16-call matched baseline.

This is a small two-feature Lasso follow-up, with two nonoptimal Dream answers.
A conventional exact solver also needs zero LLM calls on these tasks. It does
not prove universal SDK savings or an advantage over classical optimization.
See the [figure and verification record](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/verification/bonsai-structural-dream-2026-10-05.md).

Earlier policy-development records remain available in the linked experiment documentation.

- [Full documentation and roadmap](https://github.com/TheAstrayDev/dream-rsi-sdk#readme)
- [Bonsai Q2 experiment](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/ternary-bonsai-diverse-2026-09-24.md)
- [GPT-6 Luna experiment](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/luna-xhigh-discovery-v1.md)
- [Integration and recovery](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/research-loop.md)
- [Sandbox configuration](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/sandbox.md)
- [Issues](https://github.com/TheAstrayDev/dream-rsi-sdk/issues)
- [Original Dream-RSI paper](https://arxiv.org/abs/2609.14858)

Beta integration contracts are documented; pre-release APIs may still evolve.
Generated source runs in a bounded Python-syntax subset, not
arbitrary Python. External state isolation and remote cancellation require adapter support.
Usage caps depend on accurate provider reports and ceilings. Research-scale performance
and broad generalization remain unverified.
