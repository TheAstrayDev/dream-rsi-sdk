# X · two short threads

Editorial notes: each numbered block is one post. Review before posting, check the UI's
character counter and disclose AI drafting where appropriate. The text blocks are designed
for ordinary-length posts; platform URL counting can differ from raw text length. Attach
the full measured graph to thread B's first post. Do not paste file headings or editorial notes.

## Thread A · launch

### 1

I published Dream-RSI SDK 0.1.0a2: a Python alpha for evolving executable exploration policies from replay feedback. Independent and unofficial; not affiliated with Google. The agent and evaluator stay fixed.

### 2

The loop: record an agent's search → replay known outcomes → let a developer LLM write/revise policy code → validate → deploy. This changes branching and stopping logic, not model weights.

### 3

Zero core runtime dependencies. No Docker required. Generated policies use a bounded Python-syntax interpreter; an optional worker supports cancellation. This is not arbitrary Python execution or a universal security guarantee.

### 4

Start without a model key: the repository includes a recorded-tree replay lab. The local Bonsai experiment is a separate, more involved path. Install the alpha with: python -m pip install dreamrsi==0.1.0a2

### 5

Looking for a few developers with a scored generate/evaluate/refine task to try one adapter. Tell me the first blocker, including “this doesn't help my task.” Quickstart: https://github.com/TheAstrayDev/dream-rsi-sdk#quickstart

## Thread B · measured behavior

### 1

Bonsai-27B-Q1_0 wrote and revised executable policies in a local Dream-RSI SDK experiment: 6 revisions, 5 scored, 1 failed. The graph shows measured replay behavior, not a general AI benchmark. AI-assisted summary of archived results.

### 2

One revision used 5 probes but hit 1,000 replay rounds—997 were empty. After feedback, Bonsai rewrote stopping logic: 4 rounds. A later revision used 3 probes. No manual edits to the generated policy source.

### 3

After validation and source reload, the policy reached residual 0.1875 vs 1.5 for the baseline, with 6 agent calls each. The task was deterministic halving. That's 87.5% less toy residual, not an 8× speedup.

### 4

The earlier 3-seed matrix promoted only 1/3 seeds and missed the diversity gate. Later settings changed. Both successes and failures are public; this follow-up is not a controlled estimate of reliability or generalization.

### 5

Independent unofficial alpha, not affiliated with Google. Reports, source and a no-key first demo: https://github.com/TheAstrayDev/dream-rsi-sdk. I'm interested in harder scored tasks where branch selection actually matters.
