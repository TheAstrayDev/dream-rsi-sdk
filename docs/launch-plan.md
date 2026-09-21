# First-user launch plan

Status: prepared, not published. Budget: $0. Owner: project maintainer.

## Positioning

**Record your agent's search once. Compare exploration strategies on that history without additional agent or evaluator calls.**

Start with Python developers who already have a generate/evaluate/refine loop and a repeatable scoring function. Research engineers exploring branching and stopping decisions are a second audience. The current alpha is an experiment toolkit; it does not establish better real-world performance or reproduce the complete paper.

Keep the independent, unofficial, non-Google disclaimer visible. Never reuse the paper's performance numbers as SDK benchmarks. Model-agnostic integration requires an adapter; do not promise one-line support for every framework.

## Activation and targets

The first useful journey is repository → install → replay lab → own task → feedback issue. The demo needs no API key. Ask users to measure a fixed-budget baseline on their own task before judging usefulness.

Fourteen-day targets, not forecasts: 10 reported demo trials, 3 real adapter attempts and 2 people running a second experiment. Stars are a secondary signal. No paid advertisements until repeat usage and a clear use case exist.

## Fourteen days, about one hour per day

| Days | Action | Deliverable / decision |
| --- | --- | --- |
| 1–2 | Run installation on a fresh machine; record the replay lab and the limitation statement. | A 45–60 second honest demo; fix every onboarding blocker. |
| 3 | Publish one announcement on the maintainer's own X or LinkedIn account. | Use the drafts below; link directly to the quickstart. |
| 4–5 | Speak with up to five relevant developers already known to the maintainer, where contact is welcome. | Ask about their evaluation loop and offer help with one adapter. No bulk messages. |
| 6–7 | Help the first users reproduce their task and baseline. | Two small, permission-approved integration examples; document failures as well as successes. |
| 8–9 | Share a concrete result in one relevant developer community after checking its current rules. | Explain task, budget, baseline, results and limitations. No cross-post flood or vote requests. |
| 10 | Review friction and feedback. | Improve the most common blocker before more exposure. |
| 11–12 | Consider Show HN when the runnable demo is ready. The maintainer must personally write the post. | Fact checklist: independent author, working demo, measured behavior, missing features, specific feedback wanted. |
| 13–14 | Publish a progress note on owned channels and respond to every actionable issue. | Report actual trials and changes; select one integration to support next. |

LocalLLaMA is appropriate only after a real local-model example exists. Check moderator rules before posting and write the contribution personally. Do not use generated promotional text where prohibited. Do not invent testimonials, endorsements, downloads or users.

## Demo storyboard

0–10s: state the developer problem and independent alpha status. 10–25s: install and run `examples/02_replay_lab.py`. 25–40s: show policy results and both measured zero-additional-call counters. 40–50s: explain that replay covers recorded outcomes only. 50–60s: point to the custom-agent quickstart and ask for one integration report.

## Measurement without SDK telemetry

Keep a weekly manual log. GitHub aggregate traffic is an exposure signal; it cannot prove installation or use. Trials and repeat usage require voluntary reports. Leave unknown values blank.

| Week | Channel | Unique visitors (aggregate) | Reported trials | Adapter attempts | Repeat users | Main blocker |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | To be recorded | | | | | |
| 2 | To be recorded | | | | | |

After 20 qualified visits with no reported trials, ask whether the promise and installation are clear; do not infer a precise conversion rate from incomplete reports. If trials happen but integrations do not, narrow the example to one real use case. If people integrate but do not return, prioritize usefulness and reliability before spending on reach.

## Channel rules and references

Reviewed 2026-09-21. Recheck before publication.

- [Show HN guidance](https://news.ycombinator.com/showhn.html): provide something people can try and avoid soliciting votes.
- [HN guidelines](https://news.ycombinator.com/newsguidelines.html): generated or AI-edited posts are prohibited. No ready-to-post HN draft is provided here.
- [LocalLLaMA moderator update](https://www.reddit.com/r/LocalLLaMA/comments/1su3ao4/rlocalllama_rule_updates/): review authorship and content expectations before contributing.
- [Open Source Guides: building community](https://opensource.guide/building-community/): make participation clear and respond constructively to contributors.

See [owned-channel drafts](launch-copy.md). These are prepared copy, not evidence that any promotion has been published.
