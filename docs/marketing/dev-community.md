# DEV Community · two article drafts

Editorial notes, not part of either article: start with A; consider B a week later.
Suggested tags: `python`, `ai`, `opensource`, `showdev` for A; replace `showdev` with
`machinelearning` for B if that tag fits the editor. Select truthful AI disclosure.
Copy only the chosen article below. Review all first-person statements before publishing.

---

## Article A — Record an agent's search, then experiment with its exploration policy

*Disclosure: this article was drafted with AI assistance from the SDK's code and experiment
reports. Dream-RSI SDK is my independent, unofficial project; I am not affiliated with Google.*

An agent that generates and scores candidates still needs a search strategy. Should it refine
the best result, try another branch, run several attempts together, or stop? Those choices
often end up scattered through a retry loop.

Dream-RSI SDK puts that strategy behind a Python interface. You supply a discovery agent and
an evaluator. The SDK records exploration as a tree, lets policies replay recorded outcomes,
and can ask a developer model to write new executable policy code from replay feedback.

The current release is `0.1.0a2`. It has no required third-party runtime dependencies and
requires Python 3.11 or later. It is an alpha, so start with a small task.

### First, run a scored refinement loop

Install it inside a virtual environment:

```bash
python -m pip install dreamrsi==0.1.0a2
```

Save this as `first_run.py`:

```python
from dreamrsi import Budget, DreamRSI, FunctionalAgentAdapter
from dreamrsi.policies import DepthFirstPolicy

def refine(state):
    return {"x": state["x"] / 2}

rsi = DreamRSI(
    adapter=FunctionalAgentAdapter(refine),
    evaluator=lambda candidate: -(candidate["x"] ** 2),
    policy=DepthFirstPolicy(),
    budget=Budget(model_calls=6),
)
result = rsi.run_sync({"x": 8.0})
print(result.best)
print(result.best_score)
print(result.costs.model_calls)
```

Run `python first_run.py`. The expected best candidate is `{'x': 0.125}`, its score is
`-0.015625`, and the run uses six agent calls. This deliberately simple example shows how
state passes between refinements. It does not demonstrate an LLM becoming more capable.

The negative squared error matters: scores are maximized, so turning error into a negative
score expresses a minimization task. In your adapter, the state might contain an answer,
a candidate program or a parameter set. Your evaluator needs to measure something useful.

### Next, compare policies on recorded experience

The repository contains `examples/02_replay_lab.py`, which records a toy search and replays
several policies. After cloning the repository and installing it, run that example. It prints
the additional discovery-agent and evaluator calls made during replay: both should be zero.

That boundary is useful. You can inspect alternative exploration behavior without sending
the discovery agent out to recreate every known result. Replay still computes locally and
cannot predict outcomes outside the tree. It is evidence from a finite history, not an oracle.

### Where the local LLM fits

The default optimizer searches built-in policy parameters. To develop new executable source,
use `LLMPolicyDeveloper` with your model client. A candidate program is interpreted, evaluated
on training replay, and given feedback for another revision. Promotion can require separate
validation worlds before another online run.

There is a local Bonsai experiment in the repository, including unsuccessful revisions and
serialized policy artifacts. It demonstrates this mechanism on a toy problem. It does not
establish general performance gains, and you do not need to download that model to try the
basic integration above.

If you already have a generate/evaluate/refine loop, the useful next step is small: run this
example, then replace the refinement function and evaluator with one task you understand.
If state includes live browser sessions, files or databases, read the workspace integration
contract before treating that state as copyable.

[Quickstart and replay lab](https://github.com/TheAstrayDev/dream-rsi-sdk#quickstart).
If integration fails, [report the task shape and the first blocker](https://github.com/TheAstrayDev/dream-rsi-sdk/issues/new?template=early_adopter.yml).

---

## Article B — A local LLM rewrote a search policy: the useful part was the replay feedback

*Disclosure: this article was drafted with AI assistance using archived project reports.
I maintain Dream-RSI SDK independently; it is not a Google product or an official reproduction.*

A different source file is not necessarily a different algorithm. That distinction became
important while testing a local model as a policy developer for Dream-RSI SDK.

The experiment kept a tiny discovery agent fixed: each refinement divided a number by two.
The evaluator preferred values closer to zero. Bonsai-27B-Q1_0, served locally through
llama.cpp, wrote the code that chose which revealed branches to expand and when to stop.

This is a toy task, but it makes the moving parts inspectable. The LLM is writing exploration
logic; it is not answering the task directly or modifying its own weights.

### Six revisions, including the failure

The final follow-up requested six source revisions. Five received valid replay scores.
The sixth failed and remains in the archived report with no invented score.

| Revision | Replay score ↑ | Probes | Decision rounds |
| --- | ---: | ---: | ---: |
| 1 | -1.050000 | 6 | 3 |
| 2 | -1.049975 | 5 | 1000 |
| 3 | -1.043750 | 5 | 4 |
| 4, selected | -1.026250 | 3 | 4 |
| 5 | -1.026250 | 3 | 4 |
| 6 | Failed | — | — |

Revision 2 exposes why a headline score alone is inadequate. It used fewer probes than the
baseline but spent 997 rounds without new observations. The replay round cap ended the run.
After feedback about this behavior, the model rewrote stopping logic; revision 3 finished
in four rounds. Revision 4 changed branch selection and used three probes.

The feedback contract included previous source, measured trajectories, score components,
errors and causal information about the last executed round. A policy could detect that a
past continuation revealed nothing without being shown hidden future outcomes.

### Selection was not the final test

The selected source passed replay on three separate validation worlds. It was serialized,
reloaded with its source hash preserved, and executed on a fresh initial value. At six
discovery-agent calls each, the baseline reached residual 1.5 and the generated policy
reached 0.1875: an 87.5% reduction in that task's residual.

This does not mean an 87.5% reduction in LLM spending. The developer model made its own
requests, and replay consumed compute. It also does not mean generalization has been proved:
training, validation and the fresh task were scaled versions of the same halving problem.

### Why the earlier runs still matter

The earlier three-seed matrix promoted only one of three seeds, with seven scored revisions
out of twelve. It did not pass the stricter behavior-diversity gate. The later follow-up
changed feedback and reasoning settings after those failures. It should be reported as a
follow-up, not silently substituted for a controlled multi-seed success rate.

For me, the useful engineering result is a complete evidence chain: model-written source,
measured behavioral changes, stopping repair, validation, promotion and execution after
reload. Whether this produces worthwhile gains on harder tasks is the next question.

If you want to examine that chain, start with the
[report, raw artifacts and chart](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/sandbox-v4-2026-09-22.md).
If you have a harder scored refinement task, a minimal example is more valuable feedback
than a star or an abstract prediction about recursive self-improvement.
