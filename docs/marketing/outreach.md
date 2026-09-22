# Curator pitches, opt-in invitations and response bank

Prepared messages only. Do not send automatically. Personalize only with facts you know;
remove bracketed placeholders before sending. Do not reuse these on platforms that prohibit
AI-written messages. Curator submission is not permission to begin a repeated marketing sequence.

## Curator pitch A · Console

Verified destination: `hello@console.dev`, listed in
[Console's selection criteria](https://console.dev/selection-criteria).

**Subject:** Alpha developer tool: Dream-RSI SDK — executable exploration policies

Hello Console team,

I'm TheAstrayDev, the maintainer of Dream-RSI SDK, an independent Apache-2.0 Python alpha.
I'd like to submit it for consideration in your developer-tool beta coverage.

It records an agent's exploration tree, replays policies against recorded outcomes, and can
use an LLM to write and iteratively revise executable exploration policy code. The target
user already has a scored generate/evaluate/refine loop and wants to experiment with its
branching and stopping strategy.

Python 3.11+, zero core dependencies, configurable Docker-free policy execution. The first
demo needs no model key. Installation: `python -m pip install dreamrsi==0.1.0a2`.

Repository and quickstart: https://github.com/TheAstrayDev/dream-rsi-sdk

The repository includes a documented local Bonsai experiment and failed runs. Its positive
result is limited to a synthetic task; the SDK does not claim general speedups or reproduce
the paper's full benchmarks. I am not affiliated with Google, and this is not an official SDK.

Thank you for considering it,
TheAstrayDev

## Curator pitch B · Python-focused newsletter

Candidate: Python Weekly. **Find a current official editorial contact first**; the website's
coverage is verified but an email address is not. This draft does not imply an accepted pitch.

**Subject:** Python library submission: replay-driven policy development, without core dependencies

Hello,

I'd like to submit Dream-RSI SDK 0.1.0a2, a small independent Python library for recording
agent exploration and experimenting with executable search policies.

Developers can start with a function adapter and evaluator, then use recorded replay or
an LLM policy developer to explore branching and stopping behavior. It includes a bounded
policy interpreter, an optional cancellable process backend and SQLite recovery. The core
requires Python 3.11+ and no third-party packages.

PyPI: https://pypi.org/project/dreamrsi/0.1.0a2/
Code and runnable examples: https://github.com/TheAstrayDev/dream-rsi-sdk

It is an alpha, maintained by me as TheAstrayDev. It is not affiliated with Google. The
public local-model report is a toy mechanics experiment, not a broad performance claim.

If the library fits your editorial scope, the no-key replay example may be the easiest
starting point for readers. Thank you for taking a look.

TheAstrayDev

## One curator follow-up, if useful

Send no sooner than seven days after the original, only if the destination accepts follow-ups.
Do not send after a refusal. If there is no useful new information, skip it.

> A brief follow-up on the Dream-RSI SDK submission below. The easiest evaluation path is
> the no-key replay lab in the repository; the local-model setup is optional. Happy to answer
> an installation or scope question if that helps. No problem if it is not a fit.

## Invitation to someone who expressed interest

> You mentioned [specific scored refinement task]. I'm the maintainer of an independent
> Dream-RSI-inspired Python alpha that may fit that loop. If useful, we could try one small
> adapter and compare it with your existing baseline under the same call budget. Would you
> prefer the no-key example or a short discussion of the state/evaluator interface?

Use only where contact is welcome or after a relevant conversation. Do not scrape a list
of AI developers or pretend to have read work you did not inspect.

## Follow-up after an agreed trial

> Did you get as far as running the example or connecting your own task? Either outcome
> helps. If something blocked you, the command/error and your Python/OS versions are enough
> to start. Please omit keys and private data. If it was simply not useful, that is helpful
> feedback too; no need to continue the experiment.

Ask once, respecting the person's preference. No response is not a testimonial or a failure report.

## Response bank for owned channels

### “Is this from Google?”

> No. I maintain it independently as TheAstrayDev and am not a Google or Google DeepMind
> employee. It is inspired by the public research, not an official SDK or Google product.

### “Does it train or improve the model weights?”

> No. The discovery agent and evaluator remain fixed. The optional developer model rewrites
> the executable policy controlling branch selection, batching and stopping.

### “Is the 87.5% result a cost saving?”

> It is a reduction in final residual on one deterministic toy task, at six agent calls for
> each policy. It is not a token, dollar or latency reduction. Developer calls and replay
> computation would need to be included in a full cost comparison.

### “Did all seeds work?”

> No. The earlier matrix promoted one of three seeds and missed the diversity gate. The
> later follow-up passed the full demonstration after configuration and feedback changes.
> Both reports are public; they should not be pooled as a controlled success rate.

### “How is this different from parameter tuning?”

> The default optimizer does tune built-in parameters. `LLMPolicyDeveloper` is the source-
> writing path: it can revise algorithmic logic, then receive measured replay feedback.
> The report tracks executable structure and decisions rather than treating every text edit
> as an algorithmic change.

### “Can it run arbitrary Python safely?”

> No. Generated source uses a bounded Python-syntax subset with explicit capabilities and
> limits. The optional worker adds interruptibility, not a complete OS security boundary.

### “Will it work with my framework?”

> Possibly through an adapter. The important questions are task/state shape, evaluator,
> snapshot isolation and cancellation. A compatible function signature alone does not
> prove that external browser, DB or VM state is safely isolated.

### “It failed to install / run.”

> Thanks for trying it. Please share the SDK version, Python/OS version, exact command and
> traceback, with secrets removed. If possible, use the smallest example that still fails.
> I will first try to reproduce that case before suggesting changes to your application.

### “I tried it and saw no gain.”

> That is a useful result. If you can share the task, baseline, online/developer budgets and
> how candidates were scored, we can distinguish integration problems from a method that
> does not help on that task. Please keep the unsuccessful outcome in the report.

### “Can I contribute?”

> A minimal external task with a repeatable evaluator would help. So would a small policy
> program exposing an unnecessary interpreter limitation or a reproducible recovery bug.
> Please discuss substantial changes in an issue first so we can agree on a useful scope.

## Consent for a case study

> Your experiment could make a useful example. May I publish the specific task description,
> budget and result we discussed, with [chosen attribution or anonymous credit]? I can send
> the exact draft for your review first. No private data or code will be included without
> your explicit agreement.

Do not publish the case study until the user has approved the actual content and attribution.
