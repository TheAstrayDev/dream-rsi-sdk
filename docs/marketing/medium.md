# Medium · two explanatory article drafts

Editorial notes: publish publicly, not behind the Partner Program paywall. These drafts are
AI-generated and must not be passed off as wholly human-authored. Keep disclosure within
the first two paragraphs. See the [policy source](sources.md). A publication may decline
generated work even when disclosed; do not promise acceptance or broad distribution.

---

## Article A — When an AI system improves, what exactly is changing?

*This article was drafted with AI assistance using the Dream-RSI SDK's documentation and
experiment reports. I maintain the SDK independently and am not affiliated with Google.*

“Self-improvement” is a broad phrase. It can mean changing model weights, revising a prompt,
adding a tool, collecting more examples, or changing how a system searches for an answer.
Those are different mechanisms and should not be evaluated as though they were interchangeable.

Dream-RSI SDK focuses on the last one: exploration policy. The discovery agent and evaluator
stay fixed. What changes is the program deciding which known state to expand, how to group
work and when to stop.

Imagine a system that proposes candidate solutions and receives a score for each. It can
start over repeatedly, refine the strongest candidate, explore a weaker branch that might
lead somewhere useful, or stop. Even with an unchanged model, the choice among those actions
can affect how a finite budget is spent.

### Learning from a recorded search

The SDK records an exploration tree. Historical replay lets a policy inspect revealed
information and traverse transitions already collected by the discovery agent. That creates
a place to test alternative policies without recreating every known outcome through another
live agent call.

There is an immediate limitation: recorded experience is finite. Replay cannot tell you
what would have happened on a branch whose outcome was never observed. A strong replay score
therefore motivates further evaluation; it does not guarantee the next real run will improve.

A developer model can use replay feedback to write executable policy source and revise it.
The distinction from a parameter sweep is that the model can alter the logic itself. It may
change how branches are ranked or add a stopping condition, within the SDK's supported language.

### A small, inspectable result

In one documented local-model follow-up, Bonsai-27B-Q1_0 wrote policies for a toy agent that
repeatedly halved a number. One policy stalled at 1,000 replay rounds. Feedback identified
empty rounds; the next source revision stopped after four. A later policy used three probes,
passed validation and ran again after serialization and reload.

On a fresh input, its residual was 0.1875 compared with 1.5 for the baseline, at six agent
calls each. That result is deliberately narrow. It shows a useful policy-development loop
on a simple task, not a generally smarter model or a reproduction of the original paper's
scientific benchmarks.

The model did not update its weights, and the discovery agent was not itself an LLM. The
developer LLM wrote the search logic around that agent. Keeping those roles visible makes
the result easier to assess.

### Why expose this as a library?

An SDK lets someone with an existing scored refinement task test the mechanism without
adopting a whole new agent architecture. The integration still needs sound evaluation,
state isolation and accounting. Simplicity means making those responsibilities clear,
not pretending that every system is a two-line integration.

Dream-RSI SDK is an independent alpha based on publicly available research material. It is
not a Google product, and broad effectiveness remains an open empirical question.

If you build systems that generate and score candidate solutions, start with the
[no-key quickstart](https://github.com/TheAstrayDev/dream-rsi-sdk#quickstart).
The most interesting question is what happens on your task under a fixed baseline and budget.

---

## Article B — A successful AI experiment should keep the unsuccessful runs visible

*This article was drafted with AI assistance from archived project evidence. Dream-RSI SDK
is my independent, unofficial project, not a Google product.*

One chart from a local-model experiment is easy to summarize: the baseline's residual was
1.5, and a generated policy reached 0.1875 with the same six discovery-agent calls. That is
an 87.5% reduction on the documented toy task.

The chart becomes more useful when you can also see what did not work.

The initial three-seed matrix for Dream-RSI SDK requested four policy revisions per seed.
Seven of twelve revisions received valid scores. Only one of the three seeds produced a
policy that was promoted and executed after reload, and the stricter behavior-diversity
check did not pass.

Subsequent work improved the feedback and execution profile and changed reasoning settings.
A later six-revision follow-up passed the full demonstration: valid revisions changed their
replay decisions, a stopping bug was repaired, the chosen source passed validation, and the
saved artifact ran online. Five revisions scored; the final revision failed.

### Different questions need different denominators

“Can this mechanism work?” and “How reliably does this configuration work?” are not the
same question. A successful exploratory follow-up helps answer the first. It does not turn
the original three-seed matrix into three successes, nor does it estimate reliability on
unseen problem families.

Even a valid program may be unhelpful. A changed source hash may only reflect new comments.
A changed action sequence may have the same final quality. A better replay objective may
not survive a fresh online task. Each transition needs its own evidence.

That is why the SDK reports revision status, source ancestry, executable-structure hashes,
replay decisions and deployment results. Failed revisions remain failed; they do not inherit
the previous program's successful evaluation simply because it appears in the feedback context.

### The task also limits the claim

The discovery agent in this experiment divided a value by two. The developer model wrote
the branching and stopping policy. Training, validation and fresh online inputs were scaled
instances of the same task, and validation inputs were reused during engineering iteration.

This is an integration experiment with inspectable mechanics. It is not evidence of broad
generalization, universal cost savings or a model that recursively improves its own weights.
The developer calls and replay computation also belong in any practical cost comparison.

### What I want from the next users

The next useful result is a repeatable external task with a clear baseline. It could show
improvement, no difference or a failure to justify policy-development overhead. All three
would help determine where the SDK is useful.

Publishing the unsuccessful runs makes it easier for another developer to decide whether
to try the idea and what to change. It also sets a standard for future claims: source,
configuration, budget, outcome and limitations should travel together.

The [reports and raw artifacts](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/sandbox-v4-2026-09-22.md)
are public. If you want to test the library, `dreamrsi==0.1.0a2` is on PyPI. Start with a
small task you can evaluate well, and keep the result even if it is not the one you hoped for.
