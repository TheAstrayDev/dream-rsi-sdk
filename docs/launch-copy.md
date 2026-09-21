# Launch copy for owned social channels

Drafts for the maintainer to review and publish. Do not reuse these on platforms that prohibit AI-written posts.

## Short post

I built Dream-RSI SDK, an independent Python alpha inspired by Dream-RSI. Record an agent's search, then compare policies without more agent/evaluator calls. No-key demo included. Looking for first testers. Not affiliated with Google.
https://github.com/TheAstrayDev/dream-rsi-sdk

## Longer post

If your AI agent generates candidates and you can score them, how do you decide which branch to explore next?

I'm building Dream-RSI SDK, an independent, unofficial Python library inspired by the Dream-RSI research. It records an exploration tree and lets you replay different branching and stopping policies over the recorded outcomes.

The repository includes a no-key toy demo that measures additional agent and evaluator calls during replay: both are zero. That demonstrates the replay mechanism; it is not evidence of improved LLM performance.

This is an early alpha. The complete research pipeline is not reproduced, and production integrations still need work. I am not a Google employee, and this is not a commercial Google product.

I'm looking for developers with a small generate/evaluate/refine task to try the demo and tell me where integration breaks. A useful first contribution is a reproducible task and a clear scoring function.

Try it: https://github.com/TheAstrayDev/dream-rsi-sdk#quickstart
Feedback: https://github.com/TheAstrayDev/dream-rsi-sdk/issues/new?template=early_adopter.yml

## Warm outreach, only where welcome

I'm testing an independent Dream-RSI-inspired Python SDK. Your work on [specific relevant task] seems close to the generate/evaluate/refine workflow it supports. Would a recorded-tree replay demo be useful to you? I'd value feedback on whether the adapter fits your task. It is an alpha, and I'm happy to help reproduce a small example.

Personalize the bracketed reference accurately. Do not send bulk unsolicited messages.
