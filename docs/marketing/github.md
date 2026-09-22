# GitHub · release and first-integration posts

Editorial notes: these are proposed publication texts, not existing releases/discussions.
Release A should reference the PyPI source commit documented in `docs/releasing.md`.
Use B in Discussions only if enabled; otherwise direct users to the existing issue template.

---

## A · Dream-RSI SDK 0.1.0a3 — executable policy development

This alpha adds a complete path from LLM-written exploration policy source to replay,
revision, validation, promotion and execution after reload.

```bash
python -m pip install dreamrsi==0.1.0a3
```

The discovery agent and evaluator stay fixed. `LLMPolicyDeveloper` writes and revises policy
source using measured feedback. Generated code runs in a configurable bounded interpreter;
an optional process backend supports worker termination without Docker.

The release also includes SQLite campaign checkpoints, source hashes and provenance,
shared usage reservations, replaceable replay/objective/method components, and workspace
lifecycle hooks for service-specific integration.

**Measured local-model result:** a Bonsai-27B-Q1_0 follow-up scored 5/6 revisions, produced
different replay behaviors, repaired stopping from 1,000 to 4 rounds, and selected a policy
that survived export/reload. On a fresh toy task, residual decreased from 1.5 to 0.1875 at
six discovery-agent calls per policy. This is limited mechanics evidence, not broad
generalization or a reproduction of the paper's benchmark results. Earlier failures remain public.

150 local tests passed, and release CI covered Python 3.11–3.14 on Linux and 3.14 on Windows.
The package installation and process worker were also checked after publication to PyPI.

- [Quickstart](https://github.com/TheAstrayDev/dream-rsi-sdk#quickstart)
- [Model experiment and raw reports](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/sandbox-v4-2026-09-22.md)
- [Sandbox profiles](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/sandbox.md)
- [Integration feedback](https://github.com/TheAstrayDev/dream-rsi-sdk/issues/new?template=early_adopter.yml)

I maintain this independently as TheAstrayDev. I am not a Google employee; this is not a
Google product or official SDK. APIs remain alpha. Generated source is a restricted language,
external state isolation belongs to the integration, and recorded replay cannot predict
unobserved outcomes.

---

## B · Trying your first adapter? Share one task and the first blocker

If you already have a generate/evaluate/refine loop, I would like to learn how Dream-RSI SDK
fits—or fails to fit—your task.

Start with the no-key replay lab or the small stateful quickstart. Then try one own-task
adapter under a fixed budget, keeping your existing baseline. There is no need to run Bonsai
or configure LLM policy development before the basic integration works.

A useful report contains:

- Python/OS and SDK version.
- One sentence about the task and how candidates are scored.
- Whether state contains plain data or external resources such as files, a browser or a DB.
- The command or minimal code you ran, expected behavior and actual result.
- Baseline and budget if you are comparing performance.
- Optionally, where you found the project and whether follow-up is welcome.

Do not paste API keys, private datasets or credentials. A synthetic reproduction is enough.
An equal or worse result is valuable feedback too; the project does not assume every task
benefits from additional policy development.

For reproducible bugs, use [Issues](https://github.com/TheAstrayDev/dream-rsi-sdk/issues).
For your first integration, use the
[early-adopter template](https://github.com/TheAstrayDev/dream-rsi-sdk/issues/new?template=early_adopter.yml).
If several people need the same adapter, that is a concrete signal for the next example.

This is an independent, unofficial alpha maintained by TheAstrayDev, not a Google product.
