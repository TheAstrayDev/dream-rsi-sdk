# Appendix B grid-policy mode

Status: included in the PyPI 0.1.0a3 alpha release.
The [completed local test](experiments/appendix-b-local.md) records three scored Bonsai
revisions and two live cycles. The incumbent was retained: no model improvement was measured.

`dreamrsi.appendix` implements a separate grid episode API based on the published
[Appendix B.2 contract](https://arxiv.org/html/2609.14858v1#A2.SS2). It does not rename
the section-3 tree `decide(view)` interface or change its objective. This is an
independent implementation, not an import-compatible release of the authors' code.

| Requested component | Public implementation |
| --- | --- |
| Complete `OptimalPolicy.solve(question, budget=None)` | `OptimalPolicy`, `GridQuestion`, `SimResult`; editable source in `examples/appendix_policy.py` |
| Observation helpers | `dreamrsi.appendix.observation_signal` |
| Deterministic `plan_grid(context)` | `GridPlan`, `GridPlanningContext`, pre-grid validation |
| Cross-cycle live history | `GridCampaign`, persisted manifests, per-trace historical planning snapshots |
| Offline beta sweep | `beta_sweep`, versioned Pareto reward, frontier and episode traces |
| LLM revision of this API | `AppendixPolicyDeveloper`, bounded `AppendixSourcePolicy`, portable integrity-checked artifacts |

## Run the complete path

```shell
python examples/07_appendix_b.py --output temp/appendix-demo.json
python examples/07_appendix_b.py --model-url http://127.0.0.1:8087 --revisions 3 \
  --output temp/appendix-model.json
```

The first command uses the supplied reference code. The second asks the configured
model to rewrite complete class source and evaluates every revision on every frozen
world at every beta. Failed revisions have no score. Selection retains the best
measured version, then saves/reloads it for a second live cycle. The example's
discovery task is synthetic; it is not a reproduction of the scientific benchmarks.

```python
from dreamrsi import SQLiteStore
from dreamrsi.appendix import GridCampaign, GridPlanningContext, Observation, OptimalPolicy

campaign = GridCampaign(
    "experiment-1",
    GridPlanningContext(fallback_branch_count=4, fallback_refine_count=3),
    store=SQLiteStore("appendix.sqlite"),
    baseline_score=0.0,
)

async def evaluate(meta, parent_observation, direction):
    # Call your fixed discovery agent and fixed evaluator here.
    # Directions are supplied separately, after grid planning.
    return Observation(meta.branch, meta.attempt, score=0.1,
                       evaluated=True, valid=True, fail_class="ok")

policy = OptimalPolicy({"beta": 0.6})
manifest = await campaign.run_cycle(policy, evaluate)
sweep = await campaign.evaluate_sweep(lambda beta: OptimalPolicy({"beta": beta}))
next_context = await campaign.planning_context()
```

Use a new campaign ID when configuration or the external discovery experiment changes.
Serialize operations through one campaign owner. SQLite checkpoints are durable, but
they are not a distributed ownership lock. Interrupted external calls are left
`in_flight` and never automatically retried; reconcile the external work before starting
a replacement experiment. The new developer records history in memory and does not
yet resume a partially completed model-development session automatically.

## Prefix and observation guarantees

All batch members must be distinct and legal before dispatch. A child cannot accompany
its parent. A batch larger than the worker limit or remaining explicit probe budget
is rejected before external calls. Live callbacks run concurrently; results, callbacks
and curves are committed in requested order. Return `Observation` even for expected
evaluation failures; an unexpected callback exception leaves external work uncertain.

Only disclosed observations appear in `observed()`. Metadata contains structure and
direction tags, never scores. Generated source cannot read the resolver, private
objects, `best_so_far` or `budget_spent`. The latter two are runner bookkeeping for
trusted code. Successful scores use the maximize direction. Baseline and parent deltas
are computed from revealed successful evaluations, not guessed from hidden outcomes.

An evaluated result with no error and `fail_class="ok"` is successful even if
`valid=False` or valid counts are missing. Helpers never use zero valid cases alone
to declare a permanent failure. The SDK's hard-failure classes are explicit environment,
dependency and hard-unrecoverable labels; `compile_other` is not hard by itself.
`trajectory_signal` retains a successful anchor, requires consecutive hard failures
for its hard-closure signal, and clears that signal after a later success. These
conservative helper definitions are SDK choices; the paper does not publish their code.

## Planning and history

Every plan includes positive width, nonnegative refinement count and a factual reason.
The plan is validated before directions, cells or live callbacks are created. Refinement
count excludes the root attempt. Width and depth can be arbitrary integers within
the hard caps. Unsupported replay plans get **no reward**, rather than silently shrinking.
A policy can explicitly choose a smaller plan using the disclosed structural support.

Planning receives compact summaries of completed earlier live cycles: planned/effective
grids, actual work and depth, outcomes, beta and matched sweep summaries. Current-cycle
results and full execution archives are excluded. Every collected trace saves the
history available before that live cycle, so replaying an old trace cannot accidentally
use newer live outcomes. Full traces remain available as between-revision developer
feedback. A frozen trace may have unopened branches and unequal recorded depths.

`choose_default_beta(history)` uses recent paired live/sweep evidence, retains or moves
the previous default in small steps, and returns 0.6 when evidence is insufficient.
The developer supplies that recommendation to the model. The model chooses its next
baked-in default; the runner does not change beta during an episode. Sweep instances
must honor the requested beta. A beta sweep is separate from section-3 beta1/beta2.

## Numerical convention: `appendix-pareto-v1`

The published reward has the form AUC minus a weighted parallelism penalty, but the
full normalization, interpolation and default coefficient implementation are not public.
This SDK therefore versions its conventions explicitly:

1. Per trace, normalize final successful score gain by the best recorded successful
   gain over baseline. A trace with no positive gain contributes zero attainment.
   The hidden reference score is used only by the evaluator, never given to the policy.
2. Normalize total probes by the number of recorded cells in that trace, independently
   of the policy's requested smaller grid. This prevents a smaller plan shrinking its
   evaluation denominator.
3. Integrate the right-continuous upper envelope of the sweep's final
   `(normalized work, attainment)` points over `[0,1]`, with zero attainment before
   the first point. Average those AUCs equally across traces. Episode per-probe curves
   are also exported for diagnosis; they are not substituted for sweep endpoints.
4. Average `effective_sequential_rounds / total_probes` equally across all episodes.
   Each legal batch contributes `ceil(batch_size / workers)` effective rounds.
   A zero-probe episode receives penalty 1, avoiding a free empty-policy advantage.
5. `reward = mean_auc - parallel_weight * mean_penalty`, with configurable
   `parallel_weight=0.1`. Any failed/unsupported episode makes reward unavailable.

Compare candidates only under identical traces, beta grid, objective version and weight.
Legacy AUC-only results are not numerically interchangeable. The report flags a
degenerate mean attainment/work curve; this flag is diagnostic, not proof of generalization.

## Source execution boundary

`AppendixSourcePolicy` lowers the declared class into bounded interpreter functions.
Virtual imports from `see.policy.api` and `see.policy.observation_signal` are recognized
only inside this source interpreter. They do not install a `see` package or enable
host imports. Full Python, arbitrary classes, decorators, exceptions, sets, `super()`
and external tools remain unsupported. JSON values use the SDK interpreter's copying
semantics; do not depend on Python object aliasing across assignments or loop bindings.

Configure a `PolicySandbox(SandboxConfig(...))` for operation, allocation, call-depth
and function limits. Appendix execution currently supports the inline interpreter
profile, running off the application event loop during campaign/developer work.
It does **not** claim the separate section-3 `ProcessPolicySandbox` isolation;
passing that backend is rejected. A policy timeout includes time spent in synchronous
question callbacks; it cannot kill a running external callback. Native Python policies
are trusted integrations and do not receive an interpreter security boundary.

The reference controller is a deterministic starting point with relative trajectory
ranking and recovery, not the authors' hidden `OptimalPolicy` implementation. Meaningful
multi-task holdout evaluation and research benchmark reproduction remain separate work.
