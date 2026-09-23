# Dream-RSI SDK · Alpha

**Bring your agent. Record its search. Evolve executable exploration policies.**

An independent, unofficial Python SDK inspired by Dream-RSI research. Maintained by
**TheAstrayDev**, who is not a Google or Google DeepMind employee. This is a personal
research initiative, not a commercial Google development, official SDK or endorsed product.

Python 3.11+ · zero core third-party dependencies · Apache-2.0 · version **0.1.0a4**.

## Install

```bash
python -m pip install dreamrsi==0.1.0a4
```

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
Version 0.1.0a4 can replay already recorded runs without a new training call, delays
holdout collection until a replay-improving candidate exists, and stops repeated policy
revisions. The default promotion gate now requires paired raw-quality and probe evidence;
applications needing score-only decisions can explicitly use `ReplayOnlyGate`.
These changes reduce avoidable calls, but an end-to-end cost advantage has not been proven.
The SDK includes configurable Docker-free policy interpreters, optional process execution,
held-out validation, SQLite recovery and reported token/USD accounting.

## Tested with Bonsai-27B-Q1_0

![Measured Bonsai policy development](https://raw.githubusercontent.com/TheAstrayDev/dream-rsi-sdk/main/assets/bonsai-development-v4.png)

A local llama.cpp follow-up scored 5/6 revisions, repaired stopping from 1,000 to 4
replay rounds, promoted a policy and reloaded it for a fresh toy run. Residual error
decreased from 1.5 to 0.1875 at six agent calls per policy. This is limited mechanics
evidence, not a broad AI benchmark or a reproduction of the paper's performance.
Earlier failures and all run denominators remain in the public reports.

- [Full documentation and roadmap](https://github.com/TheAstrayDev/dream-rsi-sdk#readme)
- [Real-model evidence](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/sandbox-v4-2026-09-22.md)
- [Integration and recovery](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/research-loop.md)
- [Sandbox configuration](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/sandbox.md)
- [Issues](https://github.com/TheAstrayDev/dream-rsi-sdk/issues)
- [Original Dream-RSI paper](https://arxiv.org/abs/2609.14858)

Alpha APIs may change. Generated source runs in a bounded Python-syntax subset, not
arbitrary Python. External state isolation and remote cancellation require adapter support.
Usage caps depend on accurate provider reports and ceilings. Research-scale performance
and broad generalization remain unverified.
