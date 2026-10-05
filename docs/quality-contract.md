# Certified stopping and raw-quality preservation

A fixed replay prefix can lose quality on a fresh task even when training and
validation showed a plateau. The actual Bonsai LABS pilot contains such a case:
the one-call prefix scored 0.05938697318007664, while a later baseline response
raised quality to 0.07013574660633484. A plateau is evidence about those recorded
responses, not a proof that future responses cannot improve.

## The exact stopping rule

Let the baseline produce complete batches of candidates, with an initial valid
candidate of quality q0 when one exists. Define

`q(t) = max(q0, q1, ..., qt)`.

An optional task contract supplies a proven finite bound U such that every
feasible future candidate has raw quality at most U. Stop only when `q(t) = U`.
If a bound is unavailable, invalid, inconsistent with observed quality or belongs
to another contract identity, continue the original policy.

Until stopping, the wrapper delegates every original decision unchanged, with
the same policy state, candidate order and complete batches. Therefore the
visible trajectory is a baseline prefix. At a certified stop all later baseline
qualities are at most U, while the returned incumbent already has quality U:

`q(stopped) = q(full baseline)` and `calls(stopped) <= calls(full baseline)`.

This is a pathwise result under the declared bound and matching task/evaluator
semantics: compare the same realized responses and original decisions, including
the same quality-view metadata, node identifiers, state snapshots and remaining
resource allowances. It does not guarantee equality between independent
random model runs. A wall-time cutoff or external cancellation that changes which
responses are obtained also falls outside that unchanged-prefix argument.
The rule does not require a learned plateau or additional model calls.
On a task without an attained certificate it preserves baseline work and
quality; it does not promise positive savings on every task.

By default, `QualityContract(preserve_policy=True)` preserves the original
policy supplied to the runtime. It removes fixed `PrefixPolicy` caps before
attaching the certified wrapper and does not replace the original search with
a different promoted policy. Otherwise a one-depth replacement could stop
before attaining the bound and repeat the original delayed-improvement loss.

Certified stopping needs no policy training. Use `run(task)` directly: its
decision depends on the verified bound and observations from the current task.
`improve()` skips the optimizer, developer and holdout collection in this mode;
an online method collects at most one rollout rather than repeatedly paying
for training. An offline method uses recorded history without new model calls.

Set `preserve_policy=False` explicitly to permit empirical branching or source
changes. They still require configured promotion checks, but finite evidence
cannot guarantee preservation of the original baseline's quality on every
fresh task. This opt-out is part of the checkpoint fingerprint.

For a fair full-search reference, use the same contract with
`certified_stopping=False`. It retains the same raw-quality selector, initial
evaluation and view metadata but does not add an early-stop wrapper. The option
is independently configurable and participates in checkpoint matching:

```python
from dataclasses import replace

reference_contract = replace(quality, certified_stopping=False)
```

This matters for custom policies that inspect diagnostics: adding contract
metadata only to one arm could change its branching even without early stopping.

## The actual returned candidate matters

The quality contract selects the returned observation by raw quality. Keeping
only a work-penalized composite score can violate that promise. For example,
candidate A can have raw quality 0.95 and composite score 0.70, while B has raw
quality 0.90 and composite score 0.80. A gate that sees the maximum raw quality
must return A, rather than validate 0.95 and return B at 0.90.

An optional initial candidate is evaluated through the ordinary evaluator and
recorded at the root. It remains a selectable incumbent when later model
responses are worse or invalid. Its evaluator usage is charged; its presence
does not imply free evaluation or trusted quality.

A fair baseline must use the same initial candidate, evaluator, raw-quality
selector, quality metadata and rollout limits. Initial evaluation consumes one evaluator slot.
If a reference budget permits five evaluations, adding an initial evaluation
leaves four discovery evaluations; it cannot be silently compared against a
different baseline that still receives five discovery attempts. Add an
evaluator slot to both arms when five discovery attempts are intended.

## Contract and provenance

```python
from dreamrsi.quality import QualityContract

quality = QualityContract(
    id="my-task-raw-quality-v1",
    metric=lambda record: record["observation"]["raw_quality"],
    upper_bound=1.0,  # Only when 1.0 is a proven bound for the feasible domain.
    initial_candidate=lambda state, task: state["initial_observation"],
)
```

The metric receives the same record as `HoldoutPipeline.quality_metric`, with
`observation`, `diagnostics`, `score`, `depth`, `parent_id` and `status`. It
measures the actual returned observation. Without a metric, evaluator score is
raw quality. A custom metric receives a defensive copy, so accidental mutation
cannot alter the stored answer or diagnostics. If copying or metric evaluation
fails, quality is unknown and cannot certify an early stop. The metric must still
be deterministic: copying does not control its external state or side effects.
The bound may be a finite scalar or a local `bound(task)`
function returning a finite scalar or None. The initial candidate hook returns
an observation that still requires evaluation. These hooks must not dispatch
models or hide paid work. Change the contract id when any semantics change.

The runtime stamps revealed observation diagnostics with the contract id and
their measured raw quality; the root also holds the task bound. A portable
stopping policy consumes only these revealed diagnostics. It cannot inspect
unrevealed replay nodes or invent a new bound from their scores.

A wrong finite upper bound is a broken caller contract. Observed quality above
it exposes the contradiction, but no generic SDK can detect every false bound
without doing the work it was meant to avoid. Bounds should follow from the
task's feasible domain or a verified local proof, not a sample maximum.

## All-in accounting

For N tasks, let P include acquisition, validation, policy development and all
other preparation. Let B_i and T_i be baseline and certified deployment costs
for task i. Strict all-in saving requires

`P < sum(B_i - T_i)`.

With constant baseline B and deployment T, strict break-even first occurs at
`floor(P / (B - T)) + 1` tasks when B > T. If B = T, no amount of reuse recovers
a positive preparation expense. Budget planning must count fallback work,
failed requests and validation; stored history has an acquisition cost even
when it incurs no new request today.

For measured call counts the formula is exact. Dollar or token savings require
measured corresponding costs; unknown usage cannot be replaced by zero.

## What cannot be guaranteed

Two tasks may share every visible response before a proposed stop, while one
has a later improvement. A prefix-only rule cannot distinguish them. Without
an additional sound bound, stopping can lose quality; running the remaining
baseline preserves quality but sacrifices that saving. Finite holdout results
can support an empirical claim, never a universal no-loss guarantee.

The contract tests enumerate all 243 length-four trajectories over qualities
0, 0.5 and 1, including three initial qualities. With the valid upper bound 1,
195 cases stop early and all retain the full baseline's quality. This is an
exact software invariant test, not a real-model performance benchmark.

The same enumeration was run through `DreamRSI.run`, with a deterministic adapter,
four discovery steps and an evaluated initial candidate. All 243 returned qualities
matched; the protected observations were checked to be a reference prefix. Logical
agent dispatches totaled 972 for the full reference and 390 for certified stopping.
Both arms also charged 243 initial local evaluations; total local evaluations were
1,215 and 633 respectively. No external model requests occurred.

![Raw-quality equality and mean logical calls in the exhaustive SDK runtime check](../assets/beta-quality-preservation.png)

These enumerated cases are deliberately finite software checks, not a sampled task
distribution or evidence of real-model savings. See the
[verification record and reproducer](verification/0.3.0b1.md).
