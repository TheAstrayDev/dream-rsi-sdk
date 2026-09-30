# Reduce policy-development overhead with replay prefixes

The default deterministic optimizer can derive a stopping policy directly from
recorded incumbent trajectories. It finds the earliest complete decision round
that achieved the full raw quality on each training world, takes the maximum of
those rounds, and proposes `PrefixPolicy(incumbent, max_rounds)`. The nested
policy keeps its original branching decisions and complete parallel batches
until that cap. Synthesis uses no model requests and stays within the configured
candidate count. The discovery agent and evaluator remain unchanged.

For an incumbent with a useful result at round seven followed by twenty-five
unproductive rounds, the optimizer can propose a seven-round prefix without
asking a developer model to discover that stopping rule. A custom or generated
source policy can be wrapped too. More complex changes to the exploration
algorithm remain the responsibility of the configured policy developer.

## Quality and validation

Let `Q_i(k)` be the best raw quality after the incumbent's first `k` complete
rounds on recorded world `i`, and let `K_i` be its complete rollout length.

```text
k_i = first k for which Q_i(k) >= Q_i(K_i)
prefix cap = max_i k_i
```

This is the smallest constant round cap preserving quality on every checked
training world within the family of incumbent prefixes. It is not a globally
optimal policy or a proof of generalization. The optimizer uses
`HoldoutPipeline.quality_metric` when configured, so a composite score such as
Lasso accuracy minus work penalty does not replace mathematical solution
quality. Every candidate is replayed and goes through the existing promotion
gate. Use independent, single-use held-out tasks to evaluate transfer. A later
improvement on a held-out task causes a premature prefix to be rejected.

The original replay objective is unchanged. The developer eligibility bound
also respects original replay ordering: a node at depth `d` in one-based root
branch `b` needs at least `b + d - 1` recorded probes. Earlier root branches
must open first. This prevents paying a developer to seek a saving that cannot
exist on the frozen recorded tree. Unknown evidence and custom replay semantics
are not pruned by that proof.

## Usage and controls

```python
from dreamrsi import DefaultMethod, DreamRSI, DreamRSIConfig, HoldoutPipeline

sdk = DreamRSI(
    adapter=my_adapter,
    evaluator=my_evaluator,
    policy=my_policy,
    budget=my_budget,
    method=DefaultMethod(online=False),
    validation=HoldoutPipeline(independent_tasks),
    config=DreamRSIConfig(optimizer_prefix_search=True),
)

run = await sdk.run(task)             # Acquisition is charged normally.
await sdk.record_world(task, run)     # Reuse this exact recorded run.
improvement = await sdk.improve(task, rounds=1)
champion = improvement.champion_policy
```

`optimizer_prefix_search=False` disables automatic prefix proposals in both
the default optimizer and the cheap search preceding an LLM developer. An
explicit `DeterministicPolicyOptimizer(prefix_search=False)` also supports the
previous portfolio. `DefaultMethod(force_developer=True)` explicitly exercises
the developer even when a cheap candidate is available. Nested built-in/source
prefix policies use `PolicyCodec` and work with campaign checkpoints and
portable policy-memory bundles. Custom nested policies still require registered
codecs. Changed runtime search configuration is rejected on campaign resume;
policy-memory reuse and portable bundles do not restore an old campaign.

## All-in economics

For `H` new tasks, preparation cost `P`, average baseline cost `b`, and average
deployment cost `c`, measured in the same units:

```text
Baseline cost = H * b
Dream-RSI all-in cost = P + H * c
Net saving = H * (b - c) - P
Positive payback requires H > P / (b - c), when b > c.
```

For an all-in cost factor `r > 1`, one needs `b > r*c` and
`H >= r*P / (b - r*c)`. Lowering the replay cost penalty alone does not remove
preparation overhead. Prefix synthesis removes developer requests for stopping
rules that recorded history already determines. Training-history acquisition,
validation, earlier development, failed requests and deployment still belong
in the accounting. SDK logical attempts are not automatically equivalent to
provider requests, tokens or dollars; unknown monetary costs remain unknown.

The improvement is most useful when incumbent rollouts contain long tails
after their last quality improvement. A policy already requiring only one or
two useful attempts may have no quality-preserving prefix to remove. This
feature does not assert a new real-model benchmark win.
