# Ternary Bonsai on varied intermediate-score scales

This separately frozen local experiment tests the SDK's policy-development loop on a varied branch fixture. It is evidence for **this local mechanism**, not a reproduction of Google's Dream-RSI benchmark. The discovery agent and evaluator are deterministic; Bonsai is a real local LLM only for policy-code generation.

The manifest SHA-256 is `a13bf142dc3f11f9d1dd782730b65ef5c846f9c64cf22918096130096eb583b4`. Training used two tasks (signal shifts −0.2 and +0.1); validation used two separate tasks (−0.15 and +0.05). Before generation, 64 fresh tasks were fixed: 16 at each shift −0.2, −0.1, 0 and +0.1. Every task keeps the same terminal payoff structure, but the visible depth-one signal scale changes. The [model and evaluation record](ternary-bonsai-diverse-2026-09-24/generation-and-audit.json) retains the counts and selected source hashes.

The developer made eight local request attempts. Seven returned model responses; the eighth was rejected by `llama-server` with HTTP 400 because its 12,501-token prompt exceeded the configured 12,288-token context. This failed attempt was **still charged** in the all-in call budget. Of the seven responses, the sixth produced the promoted executable `SourcePolicy` (source SHA-256 `5709560e5b2496f58a4070c3020a0efd0dd4490d25654560508e44cede5832da`). It was sandboxed and replayed; both validation tasks retained raw quality 0.9, with 3 and 4 attempted expansions versus the baseline's 4 and 4.

| Stage | Logical calls |
|---|---:|
| Two baseline training tasks | 8 |
| Eight developer attempts, including rejected context request | 8 |
| Two validation tasks, baseline and challenger | 8 |
| **Preparation** | **24** |
| Learned policy on 64 fresh tasks | 224 |
| **All-in learned-policy path** | **248** |
| Fixed baseline on the same 64 fresh tasks | **256** |

Both paths attained raw quality 0.9 on **all 64** fresh tasks. The learned policy used three calls on 32 tasks and four on 32. Its full cost was eight calls lower than baseline, a **3.125% reduction**. This is smaller than the earlier 18.75% result but better supported because the signal scale varies across training, holdout and fresh tasks. The cost advantage still depends on this 64-task reuse horizon: preparation is paid once, then amortized.

![Diverse-signal local benchmark graph](../../assets/ternary-bonsai-diverse-local.png)

The selected code still contains absolute score thresholds, so it should not be treated as a generally reliable policy. Fresh tasks at −0.2 and +0.1 reuse the **training score scales** with new seeds; −0.1 and 0 are unseen scales between them. Seeds still represent only two branch-order patterns. The experiment therefore establishes working source-writing, revision, validation, promotion and reuse on a controlled local task; it does not establish cross-domain gains, performance with real discovery-agent model calls, or the original paper's results.
