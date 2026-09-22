# Research loop, without Docker

This SDK follows the phase separation in [Dream-RSI section 3 and appendix B.2](https://arxiv.org/html/2609.14858v1): keep the discovery agent and task evaluator fixed, record outcomes, revise executable exploration policies on replay feedback, and deploy a selected policy for further collection. It does not reproduce the published experiment results.

## Shared policy limits

The default runtime replay now uses the online worker capacity (`Budget.max_parallelism`,
or `DreamRSIConfig.default_batch_size`, normally 4). Previously it silently used 32.
`replay_max_parallelism=None` inherits that capacity; an explicit value can reduce it,
but cannot exceed the online capacity. A reduced replay capacity is an experimental
override, not section 3's shared-W setup. Standalone `StrictReplay` still defaults to 32.

Both default paths provide `view.budget_remaining`, including effective node, depth,
worker and round limits. `None` fields mean unlimited or unavailable. Runtime replay
inherits the configured model/evaluator call limits and online node/depth limits
(defaults: 500 nodes including root, depth 20). Only prefix-visible nodes consume
the node allowance; the hidden world's size never becomes a policy budget.

Replay charges **one logical model call and evaluator call per revealed probe**.
An unrecorded continuation consumes a round, without a probe. This is not a simulation
of provider billing: adapters with multiple model calls per attempt or failed/skipped
evaluation can have different live counters. Replay cannot predict those costs;
token, USD, developer-call and wall-time limits are rejected by `StrictReplay(budget=...)`.
The runtime passes only supported logical limits. An injected engine owns its own
contract and is not silently reconfigured.

Online K1 and offline K2 remain independent: the default online round limit is 100;
`DreamRSIConfig.replay_max_rounds` defaults to 1000. Standalone replay can additionally
cap K2 using `Budget.max_rounds`. All replay limits enter checkpoint fingerprints;
old campaigns must start a new experiment after this semantic change. Historical
Bonsai reports retain their original settings and are not results for this new contract.

## Source development

```python
from dreamrsi import Budget, DreamRSI, LLMPolicyDeveloper

async def generate_source(request):
    # Send instruction, source, view_contract and feedback to your fixed model.
    # Return raw policy-language source, not Markdown fences.
    # request["report_usage"] accepts Usage(...) for the model call.
    return 'def decide(view):\n    return {"expand": [], "stop": True}'

rsi = DreamRSI(
    agent=lambda task: task, evaluator=float,
    policy_optimizer=LLMPolicyDeveloper(generate_source, revisions=3),
    budget=Budget(model_calls=4),
    campaign_budget=Budget(model_calls=20, developer_calls=6),
)
result = rsi.improve_sync(10, rounds=2)
```

The callback above is a plumbing example, not an actual LLM. Use `LLMPolicyDeveloper.from_runnable(chat_model, usage_extract=...)` with your existing LangChain model, or provide any model client behind the callback. Core dependencies remain empty. Credentials belong to your application. A provider call is necessary to use a real model; the SDK does not ship credentials or silently choose a paid model.

Each revision receives previous source and measured training trajectories (including revealed observations), or the preceding revision's error. All successful revisions are compared with the incumbent on the same training pool. Syntax/execution failures produce feedback and do not replace the incumbent. `developer.history` keeps source artifacts, parent hashes, provenance and results. Named campaigns journal this history to the store.

`DeveloperConfig(response_format="python")` requests a complete source program; `"json"` requests `{source, diagnosis, changes}`. Both paths execute model-written source through the same interpreter. Feedback includes the baseline trajectories, candidate measurements, objective coefficients and score components, legal frontiers at each decision, and source-line errors. Repeated identical replay rounds are compressed with their repetition count; truncation is explicit. A failed revision has no score, even when earlier successful trajectories remain available as diagnostic context.

Revision records distinguish generation, received output, replay failure, unscored output and successfully scored code. They retain the raw model response and hashes of source, parsed structure and replay decisions. Different source hashes alone do not establish a changed algorithm. Automatically promoted versions retain their per-world replay scores and the promotion decision referencing the same saved version IDs.

To use an already running local llama.cpp server:

```python
from dreamrsi import DeveloperConfig, LlamaCppPolicyModel, LLMPolicyDeveloper

model = LlamaCppPolicyModel(
    "http://127.0.0.1:8080", model="local", max_tokens=8192,
    temperature=0.7, top_p=0.95, top_k=20, timeout_s=240,
)
developer = LLMPolicyDeveloper(
    model,
    config=DeveloperConfig(revisions=6, response_format="python", model_timeout_s=240),
)
# Pass policy_optimizer=developer to DreamRSI.
```

Generation settings depend on the model. The example sampling settings follow the [Bonsai model card](https://huggingface.co/prism-ml/Bonsai-27B-gguf#best-practices); context and output limits must also accommodate feedback, reasoning and the complete program. Truncated generations are charged but rejected, never executed as complete policies. No model is downloaded or server started by this client.

`examples/05_local_llamacpp.py` runs a real-model mechanics experiment. Its report includes every revision, decisions, scores, provider usage and a fresh online comparison after JSON export/reload of the selected source. Acceptance requires multiple scored revisions, distinct executable structures and replay decisions, a promotion, and execution of the reloaded artifact. A run that merely changes comments, repeatedly emits the same decisions or fails to promote exits unsuccessfully. This small synthetic experiment does not establish research-benchmark performance or generalization to arbitrary tasks.

The [September 22 Bonsai report](experiments/bonsai-2026-09-22.md) records an actual
repair/promotion/reload success alongside the unsuccessful seeds and unmet diversity gate.
Use `--source-incumbent` to start from readable source equivalent to BalancedPolicy;
that initial source is a handwritten baseline, not an LLM-generated challenger.

## SDK policy language

`PolicySandbox` is a bounded interpreter implemented for this SDK. It interprets AST nodes directly; it never executes generated Python bytecode. No Docker, child process or third-party package is needed.

See [sandbox configuration](sandbox.md) for fine-grained function/method allowlists,
JSON profiles, resource limits and the optional `ProcessPolicySandbox` worker backend.

A program defines `def decide(view):` and returns a dictionary with `expand`, optional `stop` and optional `parallelism`. Supported syntax includes helper functions and bounded recursion, variable assignment, `if/else`, `for` and `while`, list/dictionary comprehensions, tuple unpacking, JSON literals, indexing/slicing, arithmetic except exponentiation, comparisons and boolean operators. Collection operations include sorting with a lambda or helper key and supported collection methods. `PolicySandbox.capabilities()` exposes the built-ins and supported math functions to the developer.

`SandboxConfig` independently enables helpers, comprehensions, collection methods and a restricted `math` proxy. Arbitrary host imports, object access, filesystem, environment variables, network and process APIs are unavailable. Each decision starts fresh; persistent policy information must be reconstructed from `view.history` and `view.observations`. This remains a restricted language rather than arbitrary Python.

Generator expressions are eagerly materialized under the collection limits. `list.sort`
supports stable sorting with an interpreted helper/lambda key. Execution is synchronous
within a decision; logical step/deadline limits do not provide OS process isolation.

Default limits are 128 KiB source, 16,000 AST nodes, 100,000 interpreter steps, 20,000 items per value, 2,000,000 cumulative value units, value depth 48, call depth 32 and 512-bit integers. Configure these through `SandboxConfig` or keyword overrides to `PolicySandbox`. A monotonic deadline bounds interpreted work. Value units are a logical allocation bound, not an OS memory/RSS quota. Trusted handwritten policies and integration callbacks still run as normal application code. The interpreter is new and has adversarial regression tests; it is not a formally verified security boundary for arbitrary Python.

```python
from dreamrsi import PolicyArtifact, PolicySandbox, SourcePolicy

policy = SourcePolicy(PolicyArtifact('''def decide(view):
    best = None
    for node in view["frontier"]:
        if best is None or node["depth"] > best["depth"]:
            best = node
    if best is None or view["calls_used"] >= 10:
        return {"expand": [], "stop": True}
    return {"expand": [best["id"]]}
'''), PolicySandbox())
```

## Independent validation

```python
from dreamrsi import HoldoutPipeline, split_tasks

train, validation = split_tasks([1, 2, 3, 4, 5], validation_count=2, seed=7)
# Add validation=HoldoutPipeline(validation) to DreamRSI before development.
```

The pipeline collects its own worlds using the fixed initial collector policy before development. Exact task overlap is rejected. The caller must ensure tasks are semantically independent: a JSON split cannot detect near duplicates or shared data leakage. The developer sees training feedback only. The selected training winner and incumbent are checked on the same fresh held-out batch; each batch is consumed once, including on execution failure. Exhausted validation means insufficient evidence and prevents default promotion. The default gate becomes `HoldoutGate` when a pipeline is supplied.

Consumption is journaled before validation replay in a named campaign, so a crash cannot make the batch fresh again. More held-out tasks allow more promotion checks. Finite holdout evidence is not proof of generalization; report sample size and online follow-up results. `ReplayOnlyGate` remains available for experiments explicitly using training replay alone.

Validation collection also journals its in-flight task. An ambiguous interrupted collection
cannot be silently repeated. After reconciling external work, `HoldoutPipeline(...,
abandon_inflight=True)` skips that task and retains its charges. Failed policy evaluations
remain in per-world validation reports and yield insufficient evidence rather than promotion.

## Usage and budgets

`budget=` limits each online run. `campaign_budget=` shares call, token, USD and active wall-time allowances across this runtime's online runs, validation collection and developer calls. Tree-depth, node, parallelism and online-round limits belong in the per-run budget; unsupported campaign fields are rejected.

SDK `model_calls` count agent attempts, `evaluator_calls` count evaluator invocations, and `developer_calls` count developer invocations. Nested provider requests are reported separately as `Usage.provider_calls`. `Usage` also holds input/output tokens and USD. The full propose/execute/observe stage shares one reporter, available as `context["report_usage"]`. Evaluation gets its own reporter. Snapshot/next-state operations should not perform unreported paid calls.

```python
from dreamrsi import Usage

ceilings = {
    "agent": Usage(input_tokens=1000, output_tokens=500, usd=0.02),
    "evaluator": Usage(),
    "developer": Usage(input_tokens=4000, output_tokens=1000, usd=0.05),
}
# These are illustrative upper bounds, NOT provider prices.
# Pass usage_limits=ceilings with USD/token budgets.
```

Reservations happen before dispatch. Actual reports reconcile reservations. Missing reports or interrupted calls retain conservative estimates. Overruns are recorded and block further calls; the SDK cannot undo a provider charge. A hard dollar cap therefore requires the integration to supply and enforce valid upper bounds (including nested requests). No hidden pricing assumptions are made. Without a usage report or configured ceiling, zero monetary fields mean unknown/unreported usage, not proof of free execution. `rsi.usage.records` labels estimates. Named campaigns write metering before dispatch; pending reservations remain charged after restart.

`improve()` cost totals are cumulative for the runtime, including validation; `run()` costs describe that online run. Replay trajectories expose recorded `total_cost`, enabling a custom cost objective. They describe historical work, not new API spending during replay. Default replay scoring remains the section 3 formula, not the appendix B.2 Pareto sweep.

## Durable campaigns and recovery

```python
from dreamrsi import DefaultMethod, SQLiteStore

store = SQLiteStore("experiment.sqlite3")
# First runtime: method=DefaultMethod("experiment-01"), store=store.
# New process, same integrations/configuration:
# method=DefaultMethod("experiment-01", resume=True), store=SQLiteStore(...).
# improve(task, rounds=10) means 10 TOTAL rounds, not 10 additional rounds.
```

Checkpoints store worlds, built-in policy/RNG state or policy source, hashes, ancestry, developer history, validation consumption and budget accounting. JSON serialization never imports classes or executes source. Register an explicit `PolicyCodec` for a custom handwritten policy. State/task data must be JSON-compatible. Source integrity is checked on load. SQLite transactions preserve the previous checkpoint when a new serialization/write fails.

A checkpoint after online collection resumes at dreaming without recollecting that tree. A crash during an external online run is different: external side effects may be uncertain. Resume refuses to repeat it silently. After reconciling/stopping the external operation, explicitly set `abandon_inflight=True` to skip the interrupted round while retaining reserved charges. Recovery does not claim exactly-once remote execution. External workspace snapshot storage must also be durable.

Within dreaming, completed developer revisions are reused. A durably received model response can be replayed after restart without issuing another model call. An interrupted request with no recorded response remains ambiguous and is refused; it requires reconciliation rather than an implicit retry. Session fingerprints cover baseline trajectories, objective evidence and interpreter capabilities.

Changing recorded budget/configuration or validation partition is rejected on resume. Set `experiment_version` to identify your agent/evaluator/custom-objective implementation, and change it when those semantics change; the SDK cannot fingerprint arbitrary callbacks. Do not run concurrent improvement campaigns on one runtime or share a campaign ID across writers.

## Frameworks, state and cancellation

`RunnableAgentAdapter` connects actual LangChain `Runnable` interfaces; tested against `langchain-core 1.6.3`. Install `.[langchain]` and run `examples/04_runnable.py`. Compiled graphs with the same interface need schema transforms and their own checkpoint/thread isolation; the SDK does not claim every graph is automatically safe.

`WorkspaceAgentAdapter(backend, agent)` keeps live resources out of discovery state. Implement `initial(task)`, `checkout(descriptor, attempt_id)`, `snapshot(handle)`, `release(handle)` and `cancel(attempt_id)`. Descriptors are JSON dictionaries identifying immutable snapshots. The backend owns file/DB/VM isolation and snapshot retention. Confirm cancellation before releasing resources still owned by external work. This is a lifecycle integration contract, not a universal clone operation.

Async cancellation invokes an adapter's optional `cancel(attempt_id)` with a five-second callback deadline. Skipped-node metadata records whether external termination was confirmed. Cancelling an asyncio wait cannot force-stop a running thread or an arbitrary remote API; an adapter must implement the service-specific operation. Unconfirmed work remains uncertain and conservatively charged.

## Reproducible checks

The [latest local Bonsai follow-up](experiments/sandbox-v4-2026-09-22.md) passed all
demonstration gates, including different successful replay decisions and stopping repair.
This complements the credential-free regression suite below; it is not a research benchmark.

Run `python examples/03_policy_development.py` for fixture-source development and `python examples/04_runnable.py` for a real framework interface. The local regression suite covers interpreter abuse, source integrity, revision repair, prefix visibility, admission/overruns, atomic persistence, restart boundaries, validation isolation and workspace cancellation. No paid model call or research benchmark has been run as part of these tests.
