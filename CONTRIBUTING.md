# Contributing to Dream-RSI SDK

This independent project prioritizes simple integrations, correct replay, and measured
results. It is not an official Google repository.

## Report a problem or propose a change

Include your Python and SDK versions, a minimal reproduction without private data,
expected behavior, and actual behavior. For API proposals, describe the integration
problem and show how the calling code would become simpler.

Open an issue before substantial work so it can be aligned with the
[roadmap](README.md#roadmap). A small fix for a reproducible bug can go directly to a PR.
If you are trying the SDK for the first time, use the early-adopter feedback issue template.

## Local checks

```bash
python -m venv .venv
# Activate the virtual environment for your operating system.
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src tests
python -m pyright
```

Tests must run without secrets, paid APIs, or a connected model. Add a regression test
for behavior changes. New adapters should include an example and explain state isolation,
concurrency, cancellation, and operation costs.

## Invariants

- Never expose unrevealed outcomes to a replay policy.
- Keep training and validation evidence separate.
- Never turn exceptions or missing data into successful scores.
- Do not present SDK call counts as provider dollar costs.
- Keep framework-specific dependencies out of the required core.
- Do not claim research results without a reproducible experiment.

Explain what changes for users, why, and how you checked it. Contributions are distributed
under the project's [Apache-2.0 license](LICENSE).
