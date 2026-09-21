# Changelog

## Unreleased

- Added injectable replay engines, trajectory objectives and outer methods.
- Extracted the default improvement loop into `DefaultMethod`.
- Added regression coverage for extension routing, ranking, promotion and invalid scores.
- Recorded architecture gaps and acceptance criteria in `docs/hardening.md`.

- English documentation, issue templates, and contributor guidance.
- A no-key replay lab that compares policies and reports additional live calls.
- Early-adopter feedback template and a practical first-user launch plan.

## 0.1.0a1 — 2026-09-20

First public alpha snapshot of the independent SDK.

### Working foundation

- Sync/async callable and stateful agent integrations.
- Discovery trees, committed snapshots, and JSON export.
- Strict replay with shared action validation.
- Seven built-in policies, parameter search, and promotion gates.
- Call, node, depth, time, and concurrency limits.
- In-memory storage, events, and 33 regression tests.

### Project presentation

- Original vector logo, banner, and architecture diagram.
- README covering installation, examples, research comparison, and roadmap.
- Explicit non-affiliation with Google and implementation limitations.
- Apache-2.0 license, contributor guidance, and CI.

### Not implemented yet

LLM policy-code development, executable sandbox, automatic independent validation,
durable campaign recovery, and provider-level dollar accounting.
