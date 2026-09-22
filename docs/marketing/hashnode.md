# Hashnode · two article drafts

Editorial notes: A targets integrators; B targets runtime developers. Publish one first.
Suggested topics: Python, AI agents, open source, software architecture. Use the existing
architecture image for A and the sandbox documentation for B. These are AI-drafted texts;
verify them, disclose assistance and add your own implementation observations.

---

## Article A — Put exploration behind an interface before connecting another AI framework

*AI-assisted draft based on Dream-RSI SDK's implementation. I maintain the SDK independently;
I am not a Google employee and this is not an official Google SDK.*

“Works with any agent” is an easy phrase to write and a difficult interface to design.
A stateless function, an agent using a database, and an agent controlling a browser do not
have the same state or cancellation semantics.

Dream-RSI SDK starts from a narrower contract: an existing system proposes a candidate,
executes work if needed, produces an observation and gets a score. An exploration policy
decides which state to expand next. The SDK records that process as a discovery tree.

The separation lets you ask a useful question without replacing your whole application:
could a different branching, batching or stopping strategy make better use of this task's budget?

### Choose the smallest integration that represents your task

For independent attempts, pass an agent function and an evaluator. Each attempt receives
the original task. This is appropriate when candidates do not refine a prior state.

For refinement, use a stateful adapter. A simple example is:

```python
from dreamrsi import Budget, DreamRSI, FunctionalAgentAdapter
from dreamrsi.policies import DepthFirstPolicy

rsi = DreamRSI(
    adapter=FunctionalAgentAdapter(lambda state: {"x": state["x"] / 2}),
    evaluator=lambda result: -abs(result["x"]),
    policy=DepthFirstPolicy(),
    budget=Budget(model_calls=6),
)
result = rsi.run_sync({"x": 8.0})
print(result.best)
```

Install `dreamrsi==0.1.0a2` with Python 3.11 or newer before running it. The example is
deliberately deterministic: it illustrates state transitions, not an AI benchmark.

For more control, implement the full adapter protocol around your existing model client,
tools and execution environment. Keep live service clients inside that integration. Put
serializable state or immutable snapshot descriptors in the discovery tree.

### External state changes the problem

Copying a Python dictionary does not clone a database transaction or browser session.
The SDK's workspace interface gives the backend responsibility for checkout, snapshot,
release and cancellation. That backend still has to implement actual service-specific
isolation. An abstract hook is not a working VM snapshot service.

Similarly, canceling a Python wait does not necessarily cancel a remote job. The adapter
must report whether termination was confirmed. Durable campaigns preserve uncertainty
rather than claiming that a potentially billable request never happened.

### Keep the optimizer and the task separate

With integration in place, the developer model can revise exploration policy source using
recorded replay feedback. The agent and evaluator remain fixed. You can replace the replay
engine, objective or outer method independently if the default research-inspired sequence
does not fit your experiment.

This is why a small interface is useful: it isolates the mechanism being studied. It does
not eliminate the need to understand the host system. A filesystem agent needs different
integration work from the toy dictionary example, even when both expose the same protocol.

My initial target is developers who already have a small scored refinement loop. If that
describes your project, the best first experiment is one task, one baseline and one explicit
budget. Leave elaborate policy generation until that integration is observable and repeatable.

[Integration guide](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/integration.md)
and [first-user feedback](https://github.com/TheAstrayDev/dream-rsi-sdk/issues/new?template=early_adopter.yml).

---

## Article B — Running LLM-written policy code without Docker: the execution boundary matters

*AI-assisted draft based on the SDK's source and tests. Dream-RSI SDK is my independent,
unofficial project, not a Google product.*

An LLM policy developer is more interesting when it can change the algorithm, rather than
pick a parameter from a menu. It is also harder to integrate: the output is executable logic.

In Dream-RSI SDK, generated code describes how to select branches, batch work and stop.
The execution environment is a bounded interpreter for a Python-syntax subset. It does not
evaluate generated Python bytecode, and it does not expose arbitrary files, sockets or
process APIs to the policy.

This choice keeps the core dependency-free and avoids requiring Docker just to try the SDK.
It also introduces a language boundary that needs to be visible to both the developer and
the model generating code.

### Configure the profile instead of editing the interpreter

```python
from dreamrsi import PolicySandbox, SandboxConfig

profile = SandboxConfig(
    max_steps=200_000,
    max_items=40_000,
    allowed_builtins=("len", "min", "max", "sum", "sorted", "range", "abs"),
    allowed_math=("sqrt", "log"),
    allowed_methods=("dict.get", "dict.items", "list.append", "list.sort"),
)
sandbox = PolicySandbox(profile)
print(sandbox.capabilities()["language"])
```

The lists narrow supported operations; they cannot enable a host function such as `open`.
Limits also cover source size, AST size, value depth, helper-call depth and integer magnitude.
The policy developer receives the active capabilities so it can target the actual environment.

Helpers, loops, comprehensions and sorting are useful for writing new policies. Generator
expressions are eagerly materialized under collection limits, so they are not general Python
generators. Value-copy behavior also differs from ordinary Python object aliasing. Those
differences are documented rather than hidden behind a claim of full Python compatibility.

### Pick the execution backend for the host application

The inline `PolicySandbox` has low overhead, but interpreter work is synchronous within
a decision. An async method signature alone does not make that work nonblocking.

`ProcessPolicySandbox` runs the same interpreter and profile in a fresh Python worker for
each decision. The host can terminate and reap the worker on timeout or cancellation.
It needs no Docker, but process startup can be expensive in a large replay loop.

Neither backend should be described as an OS filesystem/network sandbox for arbitrary
Python. Host access is excluded by the interpreter's allowed operations. Logical resource
limits are not RSS quotas, and regression tests are not a formal security proof.

### Keep source and profile together

An executable policy artifact includes source, hashes and provenance. Loading checks source
integrity and compatibility with the active execution profile. If you change the language
or allowlists, silently treating an old result as evidence for the new environment would be
misleading. Migrate deliberately and validate again.

The practical result is a configurable, lightweight boundary for this SDK's policy language.
If your policies need arbitrary third-party imports or external tools, that is a different
execution requirement; do not disable checks until a restricted interpreter becomes an
accidental host-code loader.

The [sandbox guide](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/sandbox.md)
contains the complete defaults, backend tradeoffs and examples. I would particularly value
small policy programs that express a useful algorithm but expose an unnecessary language
restriction, with the expected behavior stated clearly.
