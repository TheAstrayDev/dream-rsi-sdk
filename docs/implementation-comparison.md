# Implementation comparison and engineering direction

Reviewed on 2026-09-22. This is a source-level comparison, not a benchmark ranking.
The four projects below are independent implementations: GitHub reports `fork: false`.
Their existence does not establish fidelity or superiority. No third-party code was executed
or copied into the SDK during this review.

The [official repository](https://github.com/zhengkid/Dream-RSI) still marks the full codebase
and reproduction scripts as being prepared. The SDK therefore targets the published method,
not an unavailable reference API. It remains independent of Google and Google DeepMind.

| Project and inspected revision | Concrete mechanism inspected | Useful direction for this SDK |
| --- | --- | --- |
| [pi-Dream-RSI](https://github.com/juanmackie/pi-Dream-RSI/tree/7504afe425751a6d9eb0bc9cc83dbe9c7b07038d) | `engine/dream.ts` evaluates archived policy versions on a fixed world pool, checks determinism, and retains sweep and per-world evidence. | Immutable source-to-result provenance, explicit determinism checks, and optional sweep diagnostics. Preserve the SDK's framework-neutral API rather than requiring Pi. |
| [dream-rsi-skill](https://github.com/Harkit2004/dream-rsi-skill/tree/47c8ff63efce76032048eb50fc5905278b0b99a3) | `src/dream_rsi/develop.py` separates revision context, prior reports and rejected source, and distinguishes development calls from accepted versions. | Keep failed source and its error, separate current evaluation from historical context, and make the developer contract public. |
| [hermes-dream-rsi](https://github.com/lesterppo/hermes-dream-rsi/tree/3767bf836132a427b09df3299c71c394ee11928c) | `dream_rsi/dream.py` records beta-specific results, attainment/work diagnostics, failed versions and a Pareto frontier. Its loader executes Python modules. | Add optional quality/work analysis without replacing section-3 scoring; its loader is not a security boundary to copy into this SDK. |
| [dream-rsi-local](https://github.com/itsgg/dream-rsi-local/tree/02dafb9a1b953f003acb4b62099d881f8d63b6be) | `RESULTS.md` reports a three-seed null result, failed revisions and the distinction between replay success and held-out effectiveness. | Predeclare seeds, keep failures in the denominator, and report online quality alongside saved calls. A single attractive run is insufficient. |

## Immediate priorities

1. Finish the real-model evidence chain: generation, repair, behaviorally distinct replay,
   selection, reload, and another online run. No hand edits to generated policies.
2. Prevent ambiguous validation work from being silently repeated on recovery. Preserve its
   charges and require explicit external reconciliation before abandoning the uncertain task.
3. Detect changed replay semantics on resume, including coefficients and decision limits.
   Custom replay engines can expose `checkpoint_config()` returning JSON-compatible settings;
   opaque callback changes still require the caller's `experiment_version`.
4. Report library mechanisms, reliability checks, and model effectiveness separately.
   A failed generation must never inherit a prior revision's success status.
5. Retain the small integration surface. Sweep tools, model connectors and execution backends
   should remain replaceable components rather than prerequisites for a simple agent.

## Local evidence at the start of this continuation

The alternative project task added stricter developer status records, source validation,
revision recovery, behavior hashes and promotion provenance. These changes were inspected
in the shared working tree, rather than inferred from the public repository.

Historical Bonsai run 08 scored six of eight revisions and produced two replay behaviors,
but did not promote a policy or demonstrate loaded-code deployment. Its best score matched
the incumbent. This is evidence of executable revision and error repair, not improvement.
The halving task is a mechanics example; scaled inputs do not establish broad generalization.

A new matrix was declared before execution: seeds 7, 19 and 43; four revisions per seed;
Bonsai-27B-Q1_0; 4096 generated tokens maximum; temperature 0.7; the existing local server;
the same halving task and three held-out inputs. All outcomes, including failures, remain in
the local `temp/bonsai-matrix-seed-*.json` artifacts. These ignored artifacts must be packaged
with model/server versions and implementation hashes before a public reproducibility claim.

The checked matrix and subsequent follow-ups are now archived in the
[experiment report](experiments/bonsai-2026-09-22.md) and
[v4 development report](experiments/sandbox-v4-2026-09-22.md). The final follow-up
passed the mechanics demonstration; broad effectiveness remains unverified.
