# Dream-RSI SDK · Alpha

**Bring your agent. Record its search. Evolve executable exploration policies.**

An independent, unofficial Python SDK inspired by Dream-RSI research. Maintained by
**TheAstrayDev**, who is not a Google or Google DeepMind employee. This is a personal
research initiative, not a commercial Google development, official SDK or endorsed product.

Python 3.11+ · zero core third-party dependencies · Apache-2.0 · version **0.2.0a1**.

## Install

```bash
python -m pip install dreamrsi==0.2.0a1
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
Version 0.2.0a1 adds opt-in persistent champion reuse and more conservative replay
cost accounting. It can replay already recorded runs without a new training call,
delays holdout collection until a replay-improving candidate exists, and stops
repeated policy revisions. The default promotion gate requires paired raw-quality
and probe evidence; applications needing score-only decisions can explicitly use
`ReplayOnlyGate`. An end-to-end cost advantage for an LLM discovery agent has
not been proven.
The SDK includes configurable Docker-free policy interpreters, optional process execution,
held-out validation, SQLite recovery and reported token/USD accounting.

## Two measured experiments

In the [Bonsai Q2 experiment](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/ternary-bonsai-diverse-2026-09-24.md),
a real local model wrote executable policy code while a deterministic agent solved
the tasks. Across 64 fresh fixture tasks, counted operations fell from 256 to 248
with raw quality 0.9 throughout. This is a logical-operation proxy, not a measured
token or dollar saving for an LLM agent.

In the [GPT-6 Luna xhigh experiment](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/luna-xhigh-discovery-v1.md),
the real model both solved tasks and developed policies. Deployment fell from
24 to six model requests across six held-out tasks, but 94 preparation requests
made the full path **100 versus 24**. Mean reported score was slightly lower.
This demonstrates learning and reuse, not an all-in economic win.

- [Full documentation and roadmap](https://github.com/TheAstrayDev/dream-rsi-sdk#readme)
- [Bonsai Q2 experiment](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/ternary-bonsai-diverse-2026-09-24.md)
- [GPT-6 Luna experiment](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/luna-xhigh-discovery-v1.md)
- [Integration and recovery](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/research-loop.md)
- [Sandbox configuration](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/sandbox.md)
- [Issues](https://github.com/TheAstrayDev/dream-rsi-sdk/issues)
- [Original Dream-RSI paper](https://arxiv.org/abs/2609.14858)

Alpha APIs may change. Generated source runs in a bounded Python-syntax subset, not
arbitrary Python. External state isolation and remote cancellation require adapter support.
Usage caps depend on accurate provider reports and ceilings. Research-scale performance
and broad generalization remain unverified.
