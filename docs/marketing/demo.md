# A 60-second demo that leads to a first run

Status: storyboard, not a recorded video. Use your own terminal and the published code.

| Time | Screen | Narration |
| --- | --- | --- |
| 0–8 s | SDK banner, one sentence | “This is an independent Python alpha for changing how an agent explores candidates.” |
| 8–20 s | Install command and replay lab | “The basic demo needs no model key. It records a small search, then compares policies on those recorded outcomes.” |
| 20–30 s | Zero-additional-call counters | “Replay made no new discovery-agent or evaluator calls. This does not make model-driven policy development free.” |
| 30–45 s | Archived Bonsai revision chart | “In this separate recorded experiment, Bonsai rewrote policy code, repaired a stalled loop and produced a policy we could reload.” |
| 45–53 s | Fresh-task comparison plus toy-task caption | “The toy residual went from 1.5 to 0.1875 at six calls each. Broader performance is still unverified.” |
| 53–60 s | Quickstart URL and issue template | “Try the no-key lab, then tell me what would block an adapter for your task.” |

Do not edit a failed command into an apparent success. Label the Bonsai graph as archived
evidence, not a live inference session. Keep the model name, axes, task caveat and denominator
readable. If a 60-second cut cannot include them, show less data rather than removing context.

## Existing assets

- Banner: [assets/banner.svg](../../assets/banner.svg).
- Logo: [assets/logo.svg](../../assets/logo.svg).
- Architecture: [assets/architecture.svg](../../assets/architecture.svg).
- Latest measured chart: [assets/bonsai-development-v4.png](../../assets/bonsai-development-v4.png).
- Chart generator and raw-source hash: [experiment tooling](../experiments/plot_policy_development.py).

Use PNG for platforms that do not accept SVG uploads. A landscape screenshot of the graph
is useful for technical articles; a mobile feed may need a simpler image with a link to the
full chart. No new image, video or hosted live demo has been created as part of this kit.

## Demo commands

```bash
git clone https://github.com/TheAstrayDev/dream-rsi-sdk.git
cd dream-rsi-sdk
git checkout aa337c20923554e751a7db5cff0e3ad5d00a6346
python -m venv .venv
```

Activate with `source .venv/bin/activate` on Linux/macOS or
`.venv\Scripts\Activate.ps1` in PowerShell, then:

```bash
python -m pip install -e .
python examples/02_replay_lab.py
```

For a package-only trial, use `python -m pip install dreamrsi==0.1.0a2` and the small
inline example in the DEV article. Repository examples require the checkout above.
