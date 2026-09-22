# LinkedIn · two articles and feed introductions

Editorial notes: use your personal profile, review the first-person statements, and publish
one article at a time. Add the full measured chart with its caveat as an inline image.
Suggested hashtags for the feed introduction: #Python #OpenSource #AIAgents. No claim is
made that hashtags or hiding links in comments improve distribution.

## A · Feed introduction

I have published an independent Python alpha for experimenting with how an agent explores
candidates. Dream-RSI SDK separates the agent, evaluator and exploration policy, then uses
recorded replay to evaluate policy changes. I am looking for a few developers with a small
scored refinement task to try the integration. The article explains what it does—and the
work an adapter still needs to own.

---

## Article A — The exploration loop deserves an interface

*This article was drafted with AI assistance from project documentation. I maintain Dream-RSI
SDK independently; I am not affiliated with Google or Google DeepMind.*

When an AI system produces an unsatisfactory result, a common response is to try again.
But a retry loop contains several design decisions: what to retry, which intermediate
result to refine, how many attempts to run together, and when another attempt is no longer useful.

Those decisions can materially change a workflow even when the model and scoring function
remain the same. They also deserve to be visible when evaluating an agent system.

Dream-RSI SDK is a Python alpha that separates exploration policy from the discovery agent
and evaluator. It records attempts in a tree and can compare policies against recorded
transitions. A developer model can then write and revise executable policy source using
replay feedback, rather than only adjust a preset strategy's parameters.

The intended user is not everyone building an AI application. It is someone with an existing
generate/evaluate/refine loop, a meaningful score, and a task small enough to inspect.
For that developer, the experiment can start with an adapter rather than a framework migration.

### What a first integration should establish

The first run should make three things explicit: what state a branch owns, what a score means,
and what budget the experiment is allowed to use. A model client belongs in the adapter;
the tree should contain copyable state or a descriptor of an immutable snapshot.

If the task touches a browser, database or remote machine, the integration must implement
real isolation and cancellation. The SDK cannot clone those resources by copying a Python
object. That work is part of fitting an orchestration layer into a real system.

After the basic loop works, replay offers a way to inspect policy changes without paying
for new discovery-agent and evaluator calls on already-recorded transitions. There are
still development-model calls and local compute. Recorded history cannot answer questions
about outcomes that were never collected.

### Why I am releasing an alpha

The current version, 0.1.0a2, includes configurable Docker-free execution for generated
policies, held-out validation, source artifacts and SQLite campaign recovery. These are
working mechanisms, not a claim of production readiness for every architecture.

A local Bonsai experiment completed source revision, selection and execution after reload.
It is useful evidence that the loop can operate, but the task was synthetic. The original
research benchmarks and broad performance gains remain unverified by this SDK.

The next valuable input is a concrete integration attempt. If your system already produces
scored candidates, choose one small task and keep your current baseline. Try the SDK under
the same online budget and report what broke or failed to help.

I would rather learn that a state boundary is awkward than collect a vague endorsement.
That feedback can improve the library before its interface becomes harder to change.

[Start with the runnable quickstart](https://github.com/TheAstrayDev/dream-rsi-sdk#quickstart).
The package is available as `dreamrsi==0.1.0a2` on PyPI.

---

## B · Feed introduction

The most useful moment in a local-model experiment was not a bigger headline score. It was
a policy rewriting its stopping logic after replay showed 997 empty rounds. Here is what
the archived result establishes, why the earlier failures remain public, and what still needs
to be tested before calling the approach broadly useful.

---

## Article B — What counts as evidence that an LLM changed a search strategy?

*AI-assisted draft based on archived Dream-RSI SDK experiments. This is my independent,
unofficial project, not a commercial Google development or an official implementation.*

A policy developer can return a new program without changing anything meaningful. Comments
can change, variables can be renamed, and branches can be rearranged while the resulting
actions stay identical. A useful evaluation therefore needs to observe behavior, not just text.

In a local Dream-RSI SDK experiment, Bonsai-27B-Q1_0 wrote policies for a fixed toy refinement
agent. The model received measured replay feedback between source revisions. The final
follow-up produced five scored revisions out of six requested, with four distinct successful
replay behaviors. The failed revision is preserved with its error.

One intermediate policy reached a cap of 1,000 decision rounds. Most of those rounds produced
no new observations. After feedback, the model changed its stopping logic and finished in four
rounds. A later revision reached the same recorded task quality with three probes.

That sequence matters because it connects diagnosis to a change in executable behavior.
The selected policy then passed a three-world validation comparison, was saved and reloaded,
and ran on a fresh input. At six discovery-agent calls each, the baseline reached residual
1.5 and the generated policy reached 0.1875.

### The result has a narrow scope

The fresh residual was 87.5% lower. It would be inaccurate to turn that into a claim about
general intelligence, model-token savings or wall-clock speed. The agent simply halved a
number. Training and validation inputs belonged to that same small problem family.

The successful follow-up also came after engineering iteration. An earlier three-seed matrix
promoted only one seed and did not pass the full diversity gate. Later feedback and reasoning
settings changed. Keeping those reports prevents an exploratory success from masquerading
as a controlled reliability estimate.

### A practical standard for the next experiment

For a more realistic task, I want an unchanged baseline, explicit online and development
budgets, fresh validation data, saved source artifacts, and outcomes that include failed
generations. If the new policy does not help, the report should say so.

This standard is useful beyond one library. Any system claiming to improve a strategy needs
to distinguish a proposal from valid code, valid code from changed behavior, and changed
behavior from better outcomes. Serialization and replay are ways to make those transitions
auditable; they do not remove the need for a good task design.

The current SDK gives developers a small place to run that experiment. The next challenge
is finding tasks where the added policy-development work earns its cost.

[Read the complete report and inspect the source artifacts](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/sandbox-v4-2026-09-22.md).
If you can describe a repeatable scored task where branch selection matters, that is the
kind of early-user feedback I am looking for.
