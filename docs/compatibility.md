# Compatibility and release gates

The SDK keeps the discovery agent and evaluator fixed while improving exploration
policies. A quality result belongs to the tasks, evaluator, model and validation
protocol used to measure it. Installing a newer SDK or importing another person's
policy does not establish equal quality on an unseen task.

## Public integration contract

Use `DreamRSI(...)` and its public operations: `run`, `improve`, `record_world`,
`add_recorded_world`, `replay`, `compare_policies`, `promote`, `freeze_policy` and
`unfreeze_policy`. Synchronous applications can use `run_sync` and `improve_sync`.
`AdaptivePolicyMemory` provides explicit saving, loading, bundle import and export
without restoring a campaign's external side effects.

Replaceable components use structural protocols from `dreamrsi.protocols`:
`AgentAdapter`, `Evaluator`, `ExplorationPolicy`, `PolicyOptimizer`, `PolicyDeveloper`,
`ReplayEngine`, `Objective`, `PromotionGate`, `Method`, `SandboxExecutor` and `Store`.
Implement the methods; inheriting an SDK class is optional. Private names beginning
with `_` are implementation details and are not the integration contract.

`PolicyOptimizer.generate(...)` produces candidates. `PolicyDeveloper.develop(...)`
receives the incumbent, training trajectories, a replay evaluation callback and
optional budget, accounting, persistence and session callbacks. It returns revisions;
the orchestration method still owns comparison and promotion. Set
`supports_sessions = True` only when the developer supports the supplied session IDs.
Neither a generator nor a developer may use validation worlds as training feedback.

Public method names and the component injection points above form the Beta integration
surface. New optional arguments may be added. Breaking behavior or signature changes
must be documented in release notes; private runtime internals carry no such promise.

## Quality preservation and economy planning

`LiveInspector` is an optional observer introduced in 0.3.0b2. Attach it through
`DreamRSI(..., inspector=inspector)`; omitting it preserves the previous integration.
`PolicyDecision.reason` is optional. The local journal and standalone HTML report
are observation artifacts, separate from policy bundles and campaign checkpoints.
Capture does not steer search but adds CPU/disk overhead. See the
[Inspector guide](inspector.md) for limits, privacy settings and comparisons.

Beta releases include optional `quality=QualityContract(...)` and
`economy=EconomyPlan(...)` arguments. Install the current package with
`python -m pip install --pre --upgrade dreamrsi==0.3.0b2`.

`QualityContract(preserve_policy=True)` keeps the supplied baseline policy's complete
decisions and skips optimizer/developer rewrites. The SDK selects results by the
contract's raw quality and may stop only when a valid observation exactly reaches a
proven upper bound. Missing or unavailable bounds delegate to the same baseline
policy; a replay plateau never proves that future improvements are impossible.
The bound must be valid for every feasible answer to that task, including unseen
model responses. Its mathematical correctness remains the caller's responsibility.
The default method runs at most one collection round in this mode; repeatedly
requesting improvement does not silently launch a policy-development campaign.

When a quality contract is active, the runtime removes imported replay-derived
`PrefixPolicy` caps and existing certificate wrappers before applying the matching
contract to the underlying policy. A learned stopping round is evidence about
recorded tasks, not a mathematical certificate for the new task. Without a quality
contract, imported alpha policies retain their original behavior.

```python
from dreamrsi import Budget, DreamRSI, EconomyPlan, HoldoutPipeline, QualityContract

def raw_quality(record):
    return record["observation"]["quality"]

# Use 1.0 only if the evaluator proves quality is globally bounded by 1.0.
quality = QualityContract(
    id="my-bounded-quality-v1",
    metric=raw_quality,
    upper_bound=1.0,
    preserve_policy=True,
)
rsi = DreamRSI(
    agent=my_agent,
    evaluator=my_evaluator,
    policy=my_baseline_policy,
    quality=quality,
    economy=EconomyPlan(baseline_calls_per_task=4, horizon=6),
    validation=HoldoutPipeline(
        my_held_out_tasks,
        quality_metric=raw_quality,
        quality_metric_id="my-bounded-quality-v1",
    ),
    budget=Budget(model_calls=4),
)
```

Replace the application's agent, evaluator, baseline policy and independent held-out
tasks in this snippet. If validation is supplied, its `quality_metric` must be the
same callable as `QualityContract.metric`; this avoids comparing different meanings
of quality. Change the contract ID and `experiment_version` when those meanings or
the feasible domain change.

Set `preserve_policy=False` explicitly to allow experimental policy rewrites.
Replay and independent validation can then measure transfer, but finite recorded
trees do not establish universal no-loss guarantees on unseen tasks. Existing alpha
applications without a quality contract retain their original policy-development
behavior.

Set `certified_stopping=False` on an otherwise identical contract for a full-search
reference. This retains quality selection, initial evaluation and view metadata.
The no-loss argument compares the same realized responses and complete decisions;
independent stochastic runs and different wall-time cutoffs need separate evidence.

`EconomyPlan` reserves minimum deployment calls before preparation, counts historical
preparation in lifetime costs and reports measured call savings. It neither changes
quality acceptance nor promises a cheaper result when no valid early stop exists.
The runtime recalculates its preparation allowance before each dispatch during
`improve`, using actual spending and the persisted completed-deployment count.
Legacy usage journals without that count default to zero, conservatively keeping
the unfinished deployment reserve.
Per-run and campaign deployment limits remain explicit `Budget` settings; a
preparation allowance does not grant unlimited deployment or prove a strict saving.
See [all-in accounting](all-in.md) for the exact integer limits and strict payback
formula. The SDK cannot guarantee strict all-in savings for every possible task:
some tasks require every baseline call to achieve baseline quality.

## Versioned artifacts

| Artifact | Supported format | Compatibility rule |
| --- | --- | --- |
| Portable policy bundle | `dreamrsi.policy-bundle`, schema 1 | Older alpha bundles remain readable with compatible task families, policy codecs and sandbox profiles. |
| Shared GitHub package | `dreamrsi.github-package`, schemas 1 and 2 | The package reader checks its format, schema and integrity before installing contained bundles. |
| Bundle collection | `dreamrsi.policy-bundle-collection`, schema 1 | Multiple task families stay separate; each contained bundle is validated. |
| Executable policy source | Policy artifact schema 1 | Source hashes are verified; importing source never executes it. A matching explicit sandbox profile is required when decoding. |
| Named campaign checkpoint | Schema 1 plus configuration fingerprint | Resume requires the same task, component settings, validation partition and experiment version. |
| Core JSON records | `_schema_version: "1"` | Unknown declared versions are rejected; unversioned legacy records remain readable. |
| Custom policy | Registered `PolicyCodec` | Register the same codec on both sides; arbitrary Python objects are not imported implicitly. |

Unknown bundle, package, policy-artifact, core-record or checkpoint schema versions
are rejected.
There is no automatic interpretation of a future schema. Keep the original file and
use an SDK release that explicitly supports it. Integrity hashes detect modified
contents; they do not certify an author's claims or a policy's quality.

Schema-1 alpha bundles containing only the original built-in or source policies do
not require retraining. Prefix policies require SDK 0.2.0a4 or later. Certified
policies require the new Beta reader introduced in 0.3.0b1. New policy kinds
require a reader that supports that kind; an older SDK must not silently substitute
a different policy. Import bundles through `AdaptivePolicyMemory.import_bundle`;
do not rewrite schema fields to bypass validation.

Campaign recovery and portable policy reuse are different operations. A checkpoint
resumes measured campaign state and reserves its previous costs. A bundle imports
recorded trees and policy versions into a compatible memory family. It does not
resume an external request, restore model weights or erase preparation costs.

## Custom callbacks and experiments

The SDK cannot hash the behavior of arbitrary functions or remote services. Change
`DreamRSI(experiment_version="...")` when changing a custom evaluator, raw-quality
extractor, adapter, objective, replay engine, promotion rule or other callback
semantics. Give changed experiments a new campaign ID and use a separate policy
memory namespace when saved quality or task-family meanings change. Reusing the
same Python class name is not proof of semantic compatibility.

Review imported task-family rules and quality floors before deploying a policy.
Independent held-out tasks must stay separate from replay development. A compatible
file format says that a policy can be loaded; it does not say that stopping early
will preserve quality on a different task distribution.

## Installed-wheel gate

The CI workflow is configured to test supported Python versions and run a separate
wheel gate on Linux and Windows. That gate builds a wheel from the checked-out
source, installs it without runtime dependencies in a
fresh virtual environment, changes directory outside the source checkout and starts
Python with `-I`. It checks the installed version and location, recursive
source/prefix/certified codec round-trips, sandbox JSON profiles and cache isolation,
quality certificates and dynamic economy planning,
an actual `ProcessPolicySandbox` worker decision, and both the installed
`dreamrsi --help` command and `python -m dreamrsi --help`.
The publication workflow repeats the installed-wheel gate before uploading
distributions for PyPI publication.

This catches packaging errors that editable-source tests cannot detect. The process
sandbox gate verifies the worker launches from the installed wheel; its security
contract remains the bounded language described in [sandbox.md](sandbox.md), rather
than an OS filesystem or network isolation boundary.

Local validation and remote CI are distinct evidence. The installed-wheel gate can
be run locally with a fresh virtual environment; passing that gate does not mark a
GitHub Actions run successful. The prepared Beta changes have not yet been committed,
published or verified by remote CI. Consult the Actions result for the exact commit
before claiming its Linux/Windows matrix passed.
