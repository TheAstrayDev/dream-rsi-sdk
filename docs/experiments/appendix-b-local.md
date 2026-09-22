# Appendix B local verification

The new grid-policy implementation completed its synthetic live → beta sweep → model
revision → source reload → second live cycle. This is unreleased source functionality,
not part of the published 0.1.0a2 package.

Model: Bonsai-27B-Q1_0 through local llama.cpp at port 8087. Recorded generation settings:
seed 43, temperature 0.7, maximum output 8,192 tokens. The server was started with a
32,768-token context and reasoning budget 4,096. Three revisions were requested.

| Policy | SDK Pareto reward |
| --- | ---: |
| Incumbent | 0.33755050505050505 |
| Model revision 1 | 0.33755050505050505 |
| Model revision 2 | -0.1 |
| Model revision 3 | -0.1 |

All three revisions scored, but none improved on the incumbent. Selection correctly retained
the incumbent, reloaded it and executed the second live cycle. All four recorded mechanics
checks passed: scored sweep, non-degenerate beta tradeoff, available cross-cycle history,
and execution after reload. This is not evidence of an improved generated policy.

An earlier request exceeded the context window. Planning input was then reduced to compact
live manifests and sweep summaries; detailed trajectories remain revision feedback.
The earlier and completed reports are preserved without editing their generated source.

- [Completed raw report](appendix-b-local/compact.json.gz)
- [Earlier report](appendix-b-local/initial.json.gz)
- [SHA-256 manifest](appendix-b-local/manifest.json)

The local suite passed 150 tests, Ruff and Pyright. Tests cover the solve interface,
observation helpers, grid planning, historical replay snapshots, numerical sweep conventions,
source execution and recovery boundaries. This does not reproduce the original scientific
benchmarks. The SDK's explicitly versioned AUC convention is documented in
[the integration guide](../appendix-b.md).

Reproduce the fixture without model inference:

```bash
python examples/07_appendix_b.py --output temp/appendix-demo.json
```

With the already configured local server, add `--model-url http://127.0.0.1:8087 --revisions 3`.
The example exits unsuccessfully if mechanics checks fail or no model revision scores.
