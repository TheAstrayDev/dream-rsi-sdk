# Claims and evidence

Use this sheet as the factual contract for every article, listing and reply.

## Positioning

**A Python SDK for recording agent exploration and evolving executable search policies
from replay feedback.** The agent and evaluator stay fixed; the policy chooses which
revealed branches to expand, how to batch work and when to stop.

Primary reader: a Python developer with a repeatable generate/evaluate/refine task.
Secondary readers: local-model experimenters and research engineers testing search policies.
Not the initial target: people seeking a ready-made chatbot, guaranteed cost reduction,
production support for every agent framework, or autonomous model-weight training.

## Verified release facts

| Statement | Evidence / qualification |
| --- | --- |
| Package `dreamrsi==0.1.0a2`, Python 3.11+ | [PyPI](https://pypi.org/project/dreamrsi/0.1.0a2/) |
| Author TheAstrayDev; Apache-2.0 | Package metadata and repository license |
| Zero required third-party runtime dependencies | Core package only; optional integrations, development tools and a model backend are separate |
| Generated executable source, iterative replay feedback | `LLMPolicyDeveloper`; this is optional, not the default parameter optimizer |
| No Docker required | Inline bounded interpreter and optional fresh-process backend |
| Sandbox is configurable | Limits, function allowlists, policy deadlines; not arbitrary Python or a proven OS security boundary |
| Replay avoids new discovery-agent/evaluator calls | Recorded transitions only; developer LLM generation and local replay computation still cost resources |
| SQLite recovery and campaign accounting | Uncertain external calls need reconciliation; provider costs require accurate integration reports |
| 125 local tests at this release | [Release CI](https://github.com/TheAstrayDev/dream-rsi-sdk/actions/runs/35711547369); tests do not prove model effectiveness |

## Model evidence

[Latest report](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/sandbox-v4-2026-09-22.md):
Bonsai-27B-Q1_0 through local llama.cpp, seed 43, six requested source revisions,
five scored and one failed. Four distinct successful replay behaviors. Revision 2
took 1,000 rounds; revision 3 repaired stopping to 4; revision 4 used 3 probes in 4 rounds.
The selected source was promoted, serialized, reloaded and executed online.

Fresh task residual: **1.5 → 0.1875**, six agent calls each. Arithmetic:
`(1 - 0.1875 / 1.5) × 100 = 87.5%`. This is lower residual on a deterministic toy
halving task, **not** 87.5% higher general intelligence, 87.5% lower token spending,
or 8× execution speed. The LLM wrote the policy; the discovery agent was not an LLM.

Training initial state: 8; validation: 6/10/14; fresh online: 12. These are closely related
tasks. Validation inputs were also reused during engineering follow-ups. Do not call this
an untouched final generalization benchmark.

[Earlier matrix](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/bonsai-2026-09-22.md):
seeds 7/19/43, four revisions each, 7/12 scored, 1/3 promoted/reloaded; diversity acceptance
unmet. Later follow-ups used changed configurations. Never pool them into a success rate.

## Required identity language

Long form: “I maintain this independently. I am not a Google or Google DeepMind employee;
this is not a Google product, commercial Google development, or an official reproduction.”

Short form: “Independent, unofficial alpha; not affiliated with Google.”

Credit the [original Dream-RSI paper](https://arxiv.org/abs/2609.14858) when explaining
the research. The SDK implements mechanisms inspired by public material; it does not
own the research or reproduce the paper's reported benchmark results.

## Claims to avoid

| Avoid | Accurate alternative |
| --- | --- |
| “Google's Dream-RSI SDK” | “Independent Dream-RSI-inspired Python SDK” |
| “Makes any AI smarter in one line” | “Adapters let you experiment with an existing scored refinement loop” |
| “The AI rewrites itself” | “The developer model rewrites executable exploration policy source” |
| “Free optimization” | “Recorded replay avoids new discovery calls; generation and computation remain” |
| “Secure execution of any Python” | “Bounded Python-syntax interpreter with an optional killable worker” |
| “Proven 8× improvement” | “8× smaller residual on one documented toy task” |
| “Production-ready” | “Alpha; compatibility, cost reporting and external state need integration work” |
| “Hundreds of developers use it” | State only voluntarily confirmed usage; currently no such claim is established |

## Stable destinations

- Start: https://github.com/TheAstrayDev/dream-rsi-sdk#quickstart
- Install: https://pypi.org/project/dreamrsi/0.1.0a2/
- Feedback: https://github.com/TheAstrayDev/dream-rsi-sdk/issues/new?template=early_adopter.yml
- Current graph: https://raw.githubusercontent.com/TheAstrayDev/dream-rsi-sdk/main/assets/bonsai-development-v4.png
- Original matrix and latest follow-up: links above.

For reproducible code in articles, pin the checkout to release source commit
`aa337c20923554e751a7db5cff0e3ad5d00a6346`. Do not assume `pip install` installs repository examples.
