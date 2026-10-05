# All-in call accounting and strict preparation caps

`EconomyPlan` computes a preparation allowance before the SDK starts training or
policy development. It performs integer arithmetic locally and never calls a model.
It does not optimize a weighted quality-minus-cost score: raw quality must pass its
independent promotion checks before any call saving can count as a successful result.

Let `B` be baseline calls per task, `H` the planned number of tasks, `m` an optimistic
minimum deployment call count per task, `P_old` historical preparation calls and
`P_new` new preparation calls. Strictly lower lifetime call cost requires:

```text
P_old + P_new + deployment_calls < H * B
```

Because counts are integers, the largest new total-call budget is:

```text
max_new_total_calls = H * B - 1 - P_old
```

Reserving at least `H * m` deployment calls gives the largest optimistic preparation
budget:

```text
max_new_preparation_calls = H * (B - m) - 1 - P_old
```

This is an exact necessary condition under the declared floor. If it is negative,
a strict saving cannot be reached in that horizon even with no further preparation.
`feasible` is false and `preparation_budget()` returns a zero-call budget. A feasible
plan is not proof that a quality-preserving policy exists, or that deployment will
actually reach the floor. A policy may require more calls, fail validation or never
be promoted. Those are failures to record, not reasons to omit preparation costs.

```python
from dreamrsi import EconomyPlan

plan = EconomyPlan(
    baseline_calls_per_task=4,
    horizon=6,
    minimum_deployment_calls_per_task=1,
    historical_preparation_calls=0,
)
assert plan.max_new_total_calls == 23
assert plan.max_new_preparation_calls == 17
budget = plan.preparation_budget()  # Budget(total_llm_calls=17)

# Supply actual measurements after preparation and deployment.
report = plan.report(preparation_calls=8, deployment_calls=6, tasks_completed=6)
assert report["all_in_calls"] == 14
assert report["baseline_calls"] == 24
assert report["saved_calls"] == 10
```

## Recompute the allowance before paying again

The initial preparation cap alone is insufficient after deployment starts. Let
`P` and `D` be actual new preparation and deployment calls already charged, including
pending reservations, and `n` the number of completed deployment tasks. The optimistic
remaining cost is `max(0, H - n) * m`. An additional preparation cost `a` can still
fit a strictly cheaper experiment only if:

```text
P_old + P + D + a + max(0, H - n) * m < H * B

remaining_preparation_calls = max(
    0, H * B - 1 - P_old - P - D - max(0, H - n) * m
)
```

This follows directly by subtracting known charges and the unfinished deployment
reserve from the integer total-call cap. It is a necessary optimistic condition,
not a prediction of later quality or savings. Zero additional allowance can mean
the target has already become impossible. Stopping further policy preparation does
not change a completed answer or truncate the full deployment fallback.

For example, with `B=4`, `H=6`, `m=1`, two preparation calls and two completed tasks
that cost eight deployment calls, a static allowance would permit **15** more
preparation calls. Actual spending leaves **9**: `24 - 1 - 2 - 8 - 4`. Spending the
extra six cannot pay back within this horizon even if every remaining task reaches
the one-call floor. Calls spent on aborted or unfinished deployments count in `D`
without releasing a completed-task reserve.

![Static and dynamic preparation allowances, including spent calls and unfinished-task reserve](../assets/beta-preparation-headroom.png)

This figure illustrates the exact accounting example above. Its optimistic totals
are not measured deployment results. [Curated data and reproduction](verification/0.3.0b1.md)
keep this calculation separate from interpreter timings and quality-invariant checks.

```python
assert plan.remaining_preparation_calls(
    preparation_calls=2,
    deployment_calls=8,
    tasks_completed=2,
) == 9
```

Completing more tasks does not silently enlarge the original `H * B` budget; only
the unfinished-task reserve reaches zero. Choose a new explicit plan if the
experiment's horizon changes. Reporting later measured payback remains supported.

Preparation includes training-agent, validation-agent and policy-developer requests,
including failed requests and retries. A shared `Budget.total_llm_calls` counts agent
and developer dispatches together; counting only agent calls hides policy-development
costs. Deterministic replay and mathematical evaluators do not dispatch LLM requests,
but they still consume compute and time. An adapter must report nested provider usage
when one logical dispatch makes several external requests. `Usage.provider_calls`
is included in `Budget.total_llm_calls`; agent/developer dispatches have a conservative
one-call floor, while an LLM evaluator contributes its reported provider calls.
Supply explicit ceilings to reserve multi-request work before dispatch. An unexpectedly
larger report is retained, marks the ledger breached and blocks later requests;
already dispatched work cannot be undone.

Pass `economy=plan` to `DreamRSI` to enforce the preparation allowance across
`improve()` calls. Purpose tags are local to each asynchronous task: a concurrent
deployment does not become preparation because another task is improving policy.
The remaining allowance must use actual deployment calls instead of treating every
completed deployment as its optimistic floor. An intervening deployment does not
consume the preparation allowance twice.
Restored old untagged usage is
conservatively treated as preparation. Check measured totals with:

```python
report = plan.report(
    preparation_calls=rsi.usage.calls_for("preparation"),
    deployment_calls=rsi.usage.calls_for("deployment"),
    tasks_completed=rsi.usage.completed_deployments,
)
```

Before each preparation dispatch, the runtime checks the dynamic allowance against
the request's declared provider-call ceiling, including outstanding reservations.
The ledger persists `completed_deployments`: a finished `run()` outside
`improve()` counts once, including a zero-call run. Training and validation do not
increment it. This is an economic counter, not a quality verdict; repeated calls
must not be presented as independent generalization evidence. Interrupted runs
retain their costs without releasing the unfinished deployment floor.

A completed zero-call deployment releases its unused floor, so the remaining
allowance can increase relative to the initial estimate. Concurrent unfinished
deployments are treated conservatively. A local evaluator making no provider
requests can still run when the preparation allowance is zero.

Legacy aggregate charges survive incomplete journals. If journaled provider calls
exceed an older logical aggregate, recovery keeps the larger known charge; a
restored over-budget campaign blocks dispatch. Pending reservations remain counted
once, including after repeated restarts.

The economic plan caps **preparation**, not the quality-preserving deployment fallback.
Use `campaign_budget` for a separate hard resource limit. An optimistic floor may
never be reached: full baseline search can exceed `max_new_total_calls`. Record that
as a failed savings target instead of truncating the search and claiming unchanged
quality. More preparation cannot recover money already spent by an infeasible
experiment. Call-only savings and raw-quality acceptance must both be checked.

## Measured payback and historical costs

`report` always includes `P_old`; importing a tree or policy does not erase the cost
of creating it. A recipient may have zero personal import cost while the artifact's
lifetime cost still includes its original preparation. State both perspectives
explicitly rather than calling history free.

`historical_preparation_calls` covers only external history absent from the usage
ledger passed as `preparation_calls`. Restored campaign charges already present in
that ledger must not also be added as external history: that would count the same
calls twice. Include an imported artifact's preparation once, either through its
restored usage ledger or this explicit external-history field.

For `n > 0` completed tasks and `D` measured deployment calls, the observed average
deployment cost is `d = D / n`. Assuming that measured average stays unchanged, the
first strictly cheaper task count is:

```text
payback_tasks = floor((P_old + P_new) * n / (n * B - D)) + 1
```

The formula applies only when `n * B > D`. Otherwise the measured deployment has
no positive per-task saving and `payback_tasks` is unknown (`None`). The extra one
handles exact ties: with six preparation calls and a three-call saving per task,
two tasks only break even and the first strict saving occurs on task three.

The report uses measured deployment calls, never `m`. It may report task counts
beyond the original horizon to show lifetime amortization. A payback extrapolation
is conditional on the observed average continuing; it does not promise future
quality or call savings. With no completed tasks, per-task payback is unknown.

`tokens` and `usd` are `None` in this call-only report. Supply provider measurements
through the SDK usage ledger to assess those costs separately. Unknown token usage,
energy cost or API prices are not zero. Full all-in success requires both measured
cost savings and the unchanged raw-quality acceptance criteria on the fixed tasks.
