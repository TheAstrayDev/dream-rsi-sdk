# Integration guide

Dream-RSI SDK is an independent alpha Python library for exploration and historical
policy replay. The core requires Python 3.11+ and no third-party runtime dependencies.

## Choose an integration level

| Interface | Behavior | Best fit |
| --- | --- | --- |
| `DreamRSI(agent=fn, evaluator=score)` | Calls `fn(task)` with the original task each time | Independent sampling |
| `FunctionalAgentAdapter(step)` | Scores each output and uses it as the next branch state | Candidate refinement |
| Full `AgentAdapter` object | Separates proposal, execution, observation, and state | Custom tools and workspaces |

All integration methods may be synchronous or asynchronous. No inheritance is required.
A callable object that also implements all adapter methods is treated as a full adapter.

Use `await rsi.run(task)` or `await rsi.improve(task, rounds=5)` in async applications.
Use `run_sync` or `improve_sync` only when no event loop is already running.

## Full adapter contract

1. `initial_state(task)` creates the starting snapshot.
2. `propose(state, context)` creates a candidate.
3. `execute(proposal, state, context)` runs it or returns it unchanged.
4. `observe(execution, state)` extracts the value passed to the evaluator.
5. `next_state(observation, state)` creates the snapshot for subsequent refinement.

The evaluator receives the observation and an optional context. It returns a number,
an `Evaluation`, or an object with `.score`. Higher scores are better; negate a minimization
objective. Exceptions and non-finite scores produce failed attempts, not fabricated successes.
Inspect `result.metrics["failed_nodes"]` and error events.

The context contains `task`, `round`, `tree_size`, `parent_id`, and `parent_score`.
Callable evaluators may omit context or accept it as a positional or keyword argument.
User exceptions are not retried merely because they are `TypeError` exceptions.

## State ownership

Store clients, connections, and tools in the adapter. Store copyable data snapshots in
state. Before each attempt, the runtime copies the parent's state; an optional
`clone_state(state)` method can customize that operation. Stored tree states must still
support `deepcopy` for snapshots and persistence.

For filesystem environments, store immutable snapshot identifiers and create a separate
working copy inside the adapter. Copying a Python object does not isolate external files,
processes, databases, or remote side effects.

## Budgets and accounting

A `Budget` applies to one `run`, including each run within `improve`.
When fields are unset, the runtime uses safety limits: 100 rounds, 500 nodes, depth 20,
and `default_batch_size` workers (4 by default).

`max_nodes` includes the root and must be at least 1. Zero call, round, depth, or concurrency
limits prevent the corresponding work. Slots are reserved before scheduling a batch.

`result.costs.model_calls` counts `propose` invocations, including failed calls.
`evaluator_calls` counts invocations of the SDK evaluator. Nested provider requests are
not visible to the SDK. Monetary fields are not populated automatically, and `Budget(usd=...)`
is explicitly rejected. These counters are not token counts or dollar estimates.

Independent attempts run concurrently. Synchronous integrations use worker threads;
they must support concurrent calls or run with `max_parallelism=1`.
A timeout cancels async waiting. Running threads and external services need their own
cancellation. Completed results in the current batch are retained; unfinished attempts
are marked `SKIPPED`.

## Policies and replay

Policies receive a `PolicyView` and return a `PolicyDecision`. Selecting the root opens
a branch; selecting a leaf continues one. Duplicate and non-frontier IDs raise `PolicyError`.
Online and replay execution share action validation.

Each episode receives a deep copy of the policy prototype. Use an explicit seed for
random policies when reproducibility matters. Runtime policy views currently contain
frontier summaries, not the full observation and diagnostic history.

Replay reads committed recorded transitions without calling the agent or evaluator.
A missing continuation reveals nothing but consumes a decision round. Set objective
coefficients with `DreamRSIConfig.replay_beta1` and `replay_beta2`.

The default optimizer searches parameters of selected built-in policy families.
Custom policies may use `ParameterSearchOptimizer` or implement `PolicyOptimizer`.
LLM-based policy-code generation is not included.

`ReplayOnlyGate` uses historical replay evidence. `HoldoutGate` requires independently
obtained validation scores; `improve()` does not relabel training scores as validation.
A full automatic holdout workflow remains planned.

## Persistence and export

`InMemoryStore` records runs, nodes, events, evaluations, and promoted policy versions.
`get_tree(run_id)` reconstructs a stored run tree. The process loses in-memory data on exit.
The world pool and selected policies stay on the same `DreamRSI` instance between calls.

`export_run(result, path, fmt="json")` requires JSON-compatible data and does not stringify
unsupported objects silently. It is an export, not a durable campaign-resume mechanism.
`RunResult` contains live policy and tree objects; it is not a portable executable policy package.

See the [architecture audit](../ARCHITECTURE.md) and [README](../README.md) for current limits.

## Replaceable replay, objective and method

All three components are optional constructor arguments. Their structural protocols
are exported from `dreamrsi.protocols`. Async implementations are recommended;
synchronous implementations are also supported through the invocation bridge.

- `ReplayEngine.replay(world, policy, policy_id="") -> ReplayTrajectory` replaces
  offline mechanics. The SDK uses it for direct replay, comparisons and the default
  improvement loop. A replacement is responsible for documenting any departure
  from strict recorded-transition semantics and for isolating policy state.
- `Objective.score(trajectory, context=None) -> ObjectiveResult` replaces the
  trajectory score consistently in those paths. Larger is better. Non-finite scores
  are rejected before comparison. The objective receives an isolated trajectory,
  never the hidden world; the engine's cached result is not modified. Context is
  currently omitted. Provider dollar costs are not available in this trajectory.
- `Method.improve(runtime, task, rounds=5) -> RunResult` replaces the whole outer
  sequence. `improve_sync` and `run_campaign` also delegate to this method. Use the
  public `run`, `replay`, `compare_policies` and `promote` operations to compose your
  method; calling `runtime.improve` inside it would recurse. Custom methods own
  their recording, budget, selection and validation semantics.

```python
from dreamrsi import Budget, DreamRSI
from dreamrsi.models.objectives import ObjectiveResult

class ProbePenalty:
    def score(self, trajectory, context=None):
        # Explicit convention for an empty trajectory; choose for your task.
        quality = trajectory.best_score if trajectory.best_score is not None else -1000
        return ObjectiveResult(score=quality - 0.02 * trajectory.total_probes)

class OnlineOnly:
    async def improve(self, runtime, task, rounds=5):
        return await runtime.run(task)

rsi = DreamRSI(
    agent=lambda task: task.upper(), evaluator=lambda output: len(output),
    budget=Budget(model_calls=2), objective=ProbePenalty(), method=OnlineOnly(),
)
result = rsi.improve_sync("hello")
assert result.best == "HELLO"
```

`DefaultMethod` remains available from `dreamrsi`. It preserves online exploration,
world construction, replay, candidate generation, comparison and promotion.
Its internal integration with runtime state is not yet a public campaign context API.
