# Product Hunt · listing package and follow-up

Editorial notes: use this after the first-run path is proven with actual testers. Public
listing fields below are short by design; verify current field limits in the form. Submit
as the maker, not a fake independent hunter. B is a later technical discussion, not a second
listing for the unchanged release. Do not solicit upvotes.

## A · Listing fields

**Name:** Dream-RSI SDK

**Tagline:** Evolve executable agent search policies from replay feedback

**Description:** Independent Python alpha for recording agent exploration and iteratively
rewriting executable policies with LLM feedback. Configurable Docker-free execution,
validation and durable campaigns. Zero core dependencies. Not affiliated with Google.

**Product URL:** https://github.com/TheAstrayDev/dream-rsi-sdk#quickstart

**Install URL:** https://pypi.org/project/dreamrsi/0.1.0a2/

**License/pricing:** Apache-2.0 open source. Model inference and hosting, if used, have their
own costs. No SDK subscription is offered by this release.

**Gallery plan:** SDK banner; original architecture diagram; measured Bonsai graph with
task/denominator visible. Existing assets are listed in [demo.md](demo.md). No fabricated
customer logos, ratings or performance screenshots.

### Maker introduction

Hi, I'm TheAstrayDev, the independent maintainer of Dream-RSI SDK.

If your agent generates candidates and you can score them, there is still a search problem:
which branch should it refine, how should it batch work, and when should it stop?

This Python alpha records that search as a tree and evaluates exploration policies against
recorded outcomes. A developer LLM can write and iteratively revise executable policy code
from replay feedback. The discovery agent and evaluator stay fixed.

You can begin with a no-key demo; local LLM setup is optional. The core has no required
third-party dependencies. Generated policies run in a configurable bounded interpreter,
with an optional process backend and no Docker requirement.

A local Bonsai follow-up completed behavioral revision, stopping repair, held-out selection
and execution after source reload. It improved a fresh synthetic task at equal agent calls.
The report includes failures and earlier weaker runs; this is not a universal speedup claim.

I am looking for developers who can bring one small scored refinement task and explain where
the adapter or replay model becomes awkward. Start with the quickstart, then share the first
blocker. I am not affiliated with Google, and this is not an official SDK or a reproduction
of the paper's full benchmarks.

## B · Technical follow-up: a useful policy needs more than a new source hash

One detail behind Dream-RSI SDK's alpha is that a generated program can look different while
making exactly the same decisions. The experiment therefore tracks source structure and
replay behavior separately, and does not count failed generations as successful revisions.

In the documented local Bonsai follow-up, an intermediate policy reached 1,000 replay rounds.
Feedback showed 997 empty rounds. The model rewrote stopping logic and finished in four;
a later revision also reduced probes. The selected source was validated, saved, reloaded
and executed on a fresh input.

That is the mechanism I want early users to test on their own scored tasks. It is also why
the toy result is not a promise of lower cost on every agent workflow. Model-development
calls, replay compute and adapter complexity all count.

If you inspected the quickstart, which part would prevent a small integration in your system:
state isolation, defining the evaluator, model feedback, or reproducible baselines?

[Architecture and runnable examples](https://github.com/TheAstrayDev/dream-rsi-sdk).
Independent unofficial alpha; not affiliated with Google.
