# Architecture hardening status

Implementation status for the 0.3.0b2 Beta, October 8, 2026. Reference:
[Dream-RSI section 3 and appendix B.2](https://arxiv.org/html/2609.14858v1).
Use the [integration and recovery guide](research-loop.md) for long campaigns and
the [compatibility contract](compatibility.md) before importing saved policies.
This page describes implemented behavior and its boundaries; it does not claim a
new real-model benchmark result. See the [current release notes](releases/0.3.0b2.md)
for the local Inspector and simpler setup commands.

| Original gap | Implemented response | Boundary / evidence |
| --- | --- | --- |
| No LLM policy developer | `LLMPolicyDeveloper`, provider callback, `from_runnable` and structural `PolicyDeveloper` protocol | Iterative source/replay/feedback development is available with a supplied model; quality-preserving mode deliberately skips rewrites. |
| Hard-coded replay | `replay=` and `ReplayEngine` | Direct replay, comparison and default improvement paths use the supplied engine; its semantics remain the integration's responsibility. |
| Embedded outer loop | `method=` and `DefaultMethod` | A custom method owns orchestration; the default method coordinates collection, replay, development and promotion. |
| Disconnected objective | `objective=` with isolated trajectories | Applied before replay comparison; raw-quality selection can be supplied separately through `QualityContract`. |
| Sandbox interface only | Bounded AST interpreter, configurable profiles, allowlists and `ProcessPolicySandbox` | No Docker or arbitrary host Python execution; the worker is killable, but does not provide an OS filesystem/network security boundary. |
| No holdout pipeline | `HoldoutPipeline`, deterministic splitting and deferred collection | Separate developer feedback, single-use batches and persisted metric identity; semantic independence belongs to dataset design. |
| Fragile default optimizer | Built-in variants and generic incumbent replay prefixes | Prefix caps preserve checked replay outcomes only; custom policy persistence requires an explicit codec. |
| Weak feedback | Trajectories, observations, line errors, source ancestry and stalled-revision stopping | Model-written policies receive measured replay feedback; short summaries and duplicate stopping reduce repeated requests without proving transfer. |
| In-memory-only campaigns | `SQLiteStore`, phase checkpoints and reservation journal | Interrupted external work requires reconciliation; recovery never silently repeats an uncertain model request. |
| Nonportable policies | `PolicyArtifact`, hashes, recursive `PolicyCodec`, one-file bundles and GitHub packages | Built-in, source, prefix, certified and registered custom policies are portable; no pickle or implicit dynamic imports. |
| Unknown data versions accepted silently | Shared schema validation for core JSON records | Schema 1 and unversioned legacy records remain readable; unknown declared schemas fail rather than being guessed. |
| No campaign budget | Shared reservation ledger and `Budget.total_llm_calls` | Reported nested provider calls are counted with an agent/developer floor; validation and failed dispatches remain part of all-in accounting. |
| Preparation hides deployment savings | `EconomyPlan` and purpose-specific ledger counts | Preparation is capped after reserving a declared minimum deployment allowance; historical costs remain visible and measured deployment determines the result. |
| Composite scores select weaker answers | `QualityContract.metric` and shared raw-quality extraction | Returned candidates use the same raw metric as validation; invalid or unknown quality never becomes a selectable zero. |
| Replay plateaus cause premature stopping | `CertifiedPolicy` and `QualityContract(preserve_policy=True)` | Complete underlying baseline decisions are retained until a proven bound is attained; unknown bounds retain search. The caller must establish the bound mathematically. |
| Missing token/USD accounting | `Usage`, adapter reports and per-stage ceilings | Logical dispatch counts differ from nested provider calls; unknown token/USD values in call-only economy reports remain `None`. |
| Limited policy view | Revealed observations, diagnostics, history and `last_round` outcomes | Hidden replay outcomes are excluded; richer context does not authorize access to future answers. |
| Online/replay budget mismatch | Shared worker capacity, initial-evaluation charges and recorded provider usage | Separate online K1/replay K2 remain; only revealed usage enters replay, and unseen provider billing cannot be predicted. |
| Unsafe external state copies | Workspace snapshot/checkout/release/cancel lifecycle | A backend must supply service-specific isolation; the SDK cannot safely clone an arbitrary filesystem, browser or remote VM by itself. |
| Incomplete cancellation | Adapter cancellation hooks and confirmed/uncertain status | Worker cancellation is controlled by the SDK; arbitrary external requests require backend cancellation and confirmation. |
| Framework integration requires manual wrappers | Optional `RunnableAgentAdapter` and functional adapters | LangChain/Runnable integration is supplied; other frameworks can implement the adapter protocol, with their own state and usage semantics. |
| Editable tests miss wheel defects | Separate installed-wheel gate in CI | Fresh installation outside the checkout tests recursive codecs, quality, economy, process worker and both CLI entry paths. |

## Quality and economy boundaries

The quality contract is optional. With `preserve_policy=True`, the default method
does not develop or promote replacement policies. Imported learned prefix caps are
removed under a quality contract because a past stopping round is not proof about
an unseen task. A matching certificate can stop the underlying baseline search at
its exact global quality maximum. If no certificate is available, its search
continues under the configured budgets.

Set `preserve_policy=False` explicitly for empirical policy development. Finite
replay and held-out comparisons can measure that mode; they cannot establish
universal no-loss guarantees. The portable language still restricts Python for
bounded execution without an external sandbox.

No formula can guarantee strict all-in savings on every task without assumptions:
if the final baseline call is necessary to reach its quality, equal quality requires
that call. `EconomyPlan` rejects preparation that cannot fit the declared horizon
even under its optimistic deployment floor. It does not turn that floor into an
expected cost or silently relax the quality criterion. See [all-in.md](all-in.md)
for exact integer caps, measured payback and historical cost accounting.

The [Appendix B mode](appendix-b.md) implements grid solve, observation helpers,
pre-cycle planning, earlier-live history and beta sweeps. Its Pareto AUC conventions
are versioned SDK choices where the published prompt leaves details unspecified.
Published scientific results are not reproduced by these engineering checks.

## Verification status

The local checks for this preparation cover quality certificates and fallback,
raw-quality selection, purpose-specific all-in budgets, recovery, portable schemas,
policy development, sandbox execution and optional adapter boundaries. The wheel
gate additionally installs the actual built artifact in a fresh environment outside
the checkout and launches its process worker.

Local results must be reported with the tested source state and command. An exported
clean-source suite excludes unpublished local benchmark scripts and private data;
its count can differ from the full working-directory suite. Neither count proves
new real-model savings or cross-platform execution.

The workflow now includes Linux and Windows wheel gates, but remote CI for the
uncommitted Beta has not run yet. Earlier Actions results and historical benchmark
reports belong to their respective commits and settings. Confirm the exact future
Beta commit's Actions result separately before calling that matrix green.
