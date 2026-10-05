# Bonsai Q2 structural dreams — recovered control comparison

Collected locally on **2026-10-05**. This record separates the original campaign,
its transport failure, an independent control repeat and historical research costs.
The original preregistered run is **not** counted as a clean success.

![Fresh-campaign calls, exact answer quality and cumulative historical costs](../../assets/bonsai-structural-dream-2026-10-05.png)

## Model and task conditions

- **Model:** `Ternary-Bonsai-27B-Q2_g64`, local llama.cpp b11154 CUDA, RTX 4070.
- **Sampling:** temperature 0, top-p 1, top-k 0, seed 20261004; reasoning budget
  2,048 tokens, maximum output 3,072 tokens, context size 4,096.
- **Family:** rational Lasso coefficients, two features and three observations.
  The objective is `F(b) = ||Xb-y||²/2 + λ||b||₁`, with no division by sample count.
  This is a different task from the earlier `lasso_tuning` benchmark.
- **Frozen worlds:** one preparation task, six deployment tasks and two
  confirmation tasks. All cases were fixed before the first generation and kept.
- **Memory:** initially empty. A process-level Python audit hook blocked reads
  of previous experiment files; it is not an operating-system sandbox.
- **Control:** the original `FixedParallelPolicy(branches=1, max_depth=2)` on
  each of the same eight application tasks, with the same prompt and sampling.
  Control answers never trained the Dream memory.

The GGUF SHA256 is
`59a45d1ecef702b14531b06d22949f33b25c1897da31a8c0b298e01e4d9138eb`.
The frozen task/protocol SHA256 is
`bbefba5925f5b2cd71f29c136c5dcad0db5a62c5213b153db5b3123059ced1fd`.

## What is real, and what is computed locally?

The LLM generated every preparation and fallback candidate. Its responses were
recorded without coefficient repair. The SDK returned the best evaluated answer
and stored the actual discovery tree. Independent exact-solver diagnostics were
calculated only after each run and never supplied answers to the agent or memory.

A local module extracts an active support and signs from a recorded exact optimum.
For a new task it solves that pattern's linear system, then checks all rational
KKT conditions. Successful certification supplies an initial candidate through
the SDK's `QualityContract` hooks, requiring one local evaluation and zero LLM
requests. An incompatible pattern falls back to the full original two-call policy.

For `g = Xᵀ(Xb-y)`, active coordinates require `g_j = -λ sign(b_j)` and inactive
coordinates require `|g_j| ≤ λ`. If these conditions hold, choose a subgradient
`u` with `g + λu = 0`. Convexity gives, for every feasible `z`,

```text
F(z) - F(b) ≥ ||X(z-b)||²/2 + (g + λu)ᵀ(z-b)
            = ||X(z-b)||²/2 ≥ 0.
```

This certifies an accepted transfer as a global optimum. It does not certify a
failed model fallback or guarantee that an unknown task will match a saved pattern.
The preparation answer failed certification. The first deployment task provided
the first useful pattern; deployment task 5 added the opposite sign. Confirmation
used physically saved/reloaded memory without adding new patterns.

**Implementation status:** the structural module remains in an isolated local
experiment. It is not an installed SDK API, an LLM policy-code developer result,
or a reproduction of the original research benchmark. Model weights were unchanged.

## Matched results after independent control recovery

Lower exact objective gap is better; zero means a global optimum.

| Task | Baseline calls | Dream calls | Baseline gap | Dream gap |
| :--- | ---: | ---: | ---: | ---: |
| Deployment 1 | 2 | 2 | 0 | 0 |
| Deployment 2 | 2 | 0 | 0 | 0 |
| Deployment 3 | 2 | 0 | 75/187 | 0 |
| Deployment 4 | 2 | 0 | 0 | 0 |
| Deployment 5 | 2 | 2 | 0 | 0 |
| Deployment 6, recovered control | 2 | 2 | 1363/180 | 1363/180 |
| Confirmation 1 | 2 | 0 | 4/7 | 0 |
| Confirmation 2 | 2 | 2 | 4524/245 | 4524/245 |

Dream reached six exact optima versus four for the recovered control. Its raw
quality was equal or better in every pair, including the two nonoptimal fallbacks.
These are observed outcomes on eight fixed tasks, not an estimated success rate
over arbitrary workloads. Independent model runs are not a universal no-loss proof.

## Cost boundaries and the transport failure

| Cost boundary | Calls |
| :--- | ---: |
| New Dream preparation | 2 |
| Dream application across eight tasks | 8 |
| **Fresh Dream all-in** | **10** |
| Matched normal two-call baseline | 16 |
| Originally affected control calls retained as overhead | 2 |
| **All actual control calls** | **18** |
| **Whole new experiment, both arms and control repeat** | **28** |

One request in baseline deployment task 6 timed out after 90 seconds as GPU
throughput decreased. It remained a dispatched call with unknown token usage.
The second original control request completed, yielding a gap of `58/5`.
The campaign stopped after that pair. Only the remaining confirmation tasks
continued, with a documented transport timeout of 300 seconds; no preparation
or completed application task was rerun during continuation.

The affected control alone was then checked in a separate fixed two-call run,
selected for its transport failure. The prompt, task, sampling, policy and Dream
answer stayed unchanged. The repeat consumed two calls and returned gap `1363/180`,
matching Dream. Its first generation took about 100 seconds, confirming that the
original timeout was too short under that load.

The primary report was preserved. The recovered 16-call comparison includes the
successful repeat and excludes the two originally affected control calls from
that nominal matched set. Those calls remain charged separately as overhead.
**The original preregistered success flag remains false.** The recovered comparison
is follow-up evidence and does not retroactively repair the original protocol.

Matched token counts, including reasoning, were **23,102 Dream** and **36,960
baseline**. Token usage for the complete 18-call control remains unknown because
of the timed-out request. Dollar and energy costs were not measured.

## Fresh payback and historical research

For this fresh eight-task campaign:

```text
Baseline = 16 calls
Dream = 2 preparation + 8 application = 10 calls
Call reduction = (16 - 10) / 16 = 37.5%
Call-cost ROI = (16 - 10) / 10 = 60%
```

Costs tie after the second application task; savings start after the third.
The plotted dashed curve adds **12 earlier pilot/settings-research calls** recorded
in the previous session. That gives **22 Dream-side calls**, so this series has
not recovered all historical research against its 16-call matched control. No
previous trees, answers or champions were imported into the fresh campaign.

A conventional exact solver can solve these small problems without any LLM call.
The result therefore supports narrowly scoped transfer through the SDK hooks,
not an advantage over classical optimization, a general multi-category win, or
a financial ROI claim.

## Figure data and verification

[Curated JSON](bonsai-structural-dream-2026-10-05.json) includes the frozen tasks,
actual matched coefficient vectors, exact errors, counted costs and hashes of
the private evidence. It excludes raw model reasoning, full trees, credentials
and personal paths. The primary logs and trees remain local.

The audit verified 18 actual SDK trees against recorded responses, exact objective
gaps, frozen confirmation memory and cost totals. The focused engineering checks
passed **138 tests**. At collection time, 117 source/test/document files, Git HEAD
and staging were unchanged. The subsequent documentation edit changes README
files only; it does not integrate the experimental module into the SDK.

To redraw the English PNG and SVG from curated data, install matplotlib in the
development environment and run:

```bash
python tools/render_bonsai_structural_followup.py
```

The renderer validates the aggregate counts before drawing and makes no model
requests. Plotting does not add a runtime dependency to the SDK.
