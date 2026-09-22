# A 30-day plan to find the first repeat users

Planning assumptions: one maintainer, roughly 60–90 minutes each weekday, $0 paid media,
English public content, version 0.1.0a2. Days are relative to your actual start date;
this is not a schedule already running. Pause the calendar when support work needs the time.

## 1. The result we want

The first goal is **three developers who run the SDK on their own task and at least two
who return for another experiment**. Thirty-day planning targets: ten voluntarily reported
first runs, three own-task integrations, two repeat users, and one permission-approved
external case study. These are targets, not a forecast or a statement of existing adoption.

Stars, likes, PyPI download counts and article views help describe reach. None establishes
that someone successfully used the SDK. A CI system can download a package repeatedly.

The strongest initial offer is: **“Bring one scored refinement task; I will help you wire
the smallest adapter and compare it with your baseline.”** Offer at most three simultaneous
help slots. Do not imply a production SLA or unlimited free consulting.

## 2. Who to approach first

| Segment | Observable fit | Opening topic | First useful action |
| --- | --- | --- | --- |
| Python agent builders | Already generate candidates, score them and retry | Branch selection and reproducible replay | Run the no-key replay lab |
| Local inference developers | Already run llama.cpp and inspect model outputs | A local model rewriting actual policy code | Inspect the Bonsai source/feedback report |
| Research engineers | Care about fixed budgets, trace provenance and baselines | What replay can and cannot establish | Propose a harder task and evaluation protocol |

Look for explicit discussion of retry loops, evaluation, search budgets or branch selection.
Do not treat every person who mentions AI as a prospect. Avoid pitching teams whose main
need is browser/VM isolation that you cannot currently provide as a ready-made connector.

## 3. The path from a post to a user

```text
One concrete engineering problem
            ↓
Post with evidence and one next step
            ↓
GitHub quickstart / no-key replay lab
            ↓
Voluntary result or question
            ↓
Small own-task adapter + fixed baseline
            ↓
Second experiment and feedback
```

Make the first step cheap: no signup, email gate, paid model account or multi-GB download
for the basic demo. The Bonsai experiment is the second path for readers who already have
the hardware and model. Never send every newcomer straight into a 27B model setup.

At each stage make one request. An intro article asks readers to run the demo. A technical
report asks them to inspect or reproduce a result. A tester invitation asks for one task.
Do not end every piece with five requests for stars, follows, reposts, subscriptions and installs.

## 4. Channel order and effort

These priorities are strategic judgments about audience fit, not measured conversion rankings.

| Priority | Destination | Job | First-month effort cap | What earns more effort |
| --- | --- | --- | ---: | --- |
| P0 | GitHub + PyPI | Installation, evidence, support | 4 h setup + ongoing replies | Fewer onboarding failures |
| P1 | DEV | Runnable tutorial for Python developers | 3 h editorial + replies | Two qualified trials or a useful integration discussion |
| P1 | Hugging Face blog | Local-model evidence | 3 h editorial + replies | One reproduction or meaningful technical critique |
| P1 | Personal LinkedIn **or** X | Reach people who already know your work | 2 h total | Relevant conversations, not raw impressions |
| P2 | Hashnode | Durable engineering explanations | 2 h, choose one piece first | Search/referred visits with reported trials |
| P2 | Console newsletter | Curated developer-tool discovery | 30 min pitch | Editor response; no acceptance assumed |
| P2 | LocalLLaMA | Local-model feedback | Only if account/community eligibility fits | Useful technical exchange |
| P2 | Show HN | Runnable SDK feedback | One personally authored submission when ready | Actual trials and issues |
| P3 | Product Hunt | Broader launch visibility | 3 h only after activation works | Developer trials, not leaderboard position |
| P3 | Medium | Accessible conceptual explanation | Optional; 1 piece this month | Readers with relevant tasks |

Do not publish all sixteen articles/posts in the first week. Pick DEV plus one technical
follow-up channel and one existing personal social account. Everything else is reserve copy.
If you have no audience on either social account, spend that time on two useful public
technical conversations and improving onboarding; creating many empty profiles is not distribution.

## 5. Concrete calendar

| Day | Action | Exact material / destination | Completion evidence |
| --- | --- | --- | --- |
| 1 | Check the first-run path on a clean environment | PyPI install; replay lab; [demo](demo.md) | Commands work and outputs are understandable |
| 2 | Prepare the repository as a landing destination | About/topics, release note, pinned integration discussion; [GitHub drafts](github.md) | Public release and support path, if you choose to publish them |
| 3 | Publish the primary tutorial | DEV A in [DEV drafts](dev-community.md) | URL in tracker; correct AI disclosure; working code |
| 4 | Share one short explanation | X A **or** LinkedIn A; link to quickstart | One public post, not identical cross-posts everywhere |
| 5 | Answer questions and offer three integration slots | Existing opt-in conversations; [outreach](outreach.md) | At least a recorded question/blocker, including “not useful” |
| 6–7 | Support and review | Reproduce issues; no required new posts | Fix or document the first-run blocker |
| 8 | Publish the measured local-model account | Hugging Face A, or DEV B if that audience is already engaged | Full report and failed-revision denominator linked |
| 9 | Submit one curator pitch | Console `hello@console.dev`; [pitch](outreach.md) | One sent message logged, only when you decide to send |
| 10 | Check one relevant curated list | See [distribution](distribution.md) | Fit decision first; PR only if its rules/category fit |
| 11–12 | Help an own-task integration | Agree task, evaluator, baseline, budget and failure criteria | Reproducible small example; no invented success |
| 13 | Use one community opportunity | Personally written LocalLLaMA or Show HN, only if eligible | A substantive discussion, or a deliberate defer decision |
| 14 | Review activation | [Tracker](tracker.md) | Which channel led to attempts? Which blocker repeated? |
| 15–16 | Publish a different engineering topic | Hashnode B on sandbox boundaries, or Hashnode A on adapters | New useful content, not a rewritten launch announcement |
| 17 | Ask existing testers about the second run | Only testers who welcomed follow-up | Actual repeat-run report or clear reason for stopping |
| 18 | One follow-up to an editor if appropriate | At least 7 days after initial pitch; only if useful | No repeated chase after silence or refusal |
| 19–20 | Draft a case study only if evidence exists | Task, baseline, costs, outcome, permission | A reviewed draft, including a null result if that is what happened |
| 21 | Decide whether Product Hunt is earned | Three first runs and a clear install path are an internal gate | Launch prepared, or deferred with no penalty |
| 22 | Product Hunt launch if the gate passes | [Listing + maker comment](product-hunt.md) | Accurate listing, live links, available maintainer |
| 23–24 | Reply and fix | New issues before new announcements | Responses and concrete fixes |
| 25 | Publish a conceptual piece if useful | Medium A/B or LinkedIn B, not both by default | Honest disclosure and a distinct audience reason |
| 26–27 | Ask what would justify continued use | Existing testers; no bulk DM campaign | One prioritized use case and explicit unmet needs |
| 28 | Share an actual progress update | GitHub discussion; choose facts collected this month | No invented users, testimonials or release features |
| 29 | Compare channels | Time spent vs confirmed trials/integrations | Keep two useful channels; stop the rest |
| 30 | Choose the next engineering/marketing cycle | Fix dominant blocker, test next task | A small roadmap based on real feedback |

If a post generates support work, move later publishing days. A maintainer who replies
clearly is more useful to an early adopter than another announcement.

## 6. How to run an integration session

Before the session: ask for task shape, one input/output example, evaluator, Python version,
and whether state includes files, browser sessions, databases or remote jobs. Do not request
credentials or private datasets in public issues. Use a synthetic example if necessary.

During a 30–45 minute session: define the current baseline, fix the call budget, write the
smallest adapter, run one task, inspect observations and failures. Only then consider policy
development. Track developer generation costs separately from discovery calls.

Afterward: send a minimal reproduction and exact next command. With consent, ask once a few
days later whether they ran it again. Ask permission before publishing their name, code or result.
If the fit is poor, record why instead of forcing the project into their architecture.

## 7. Daily support routine

Allocate 15 minutes to comments, 30–45 to reproduction/help, and 15 to the tracker or one
content edit. Aim to respond by the next working day when practical; do not promise 24/7 support.
For bug reports: acknowledge, request a reproduction, record severity, link the fix. For hype
questions: answer with the factual boundary in [facts](facts.md). For disagreement: explain
the experiment, accept valid criticism and update misleading wording promptly.

## 8. Decisions after fourteen days

| Observed pattern | Likely question to investigate | Next action |
| --- | --- | --- |
| Relevant views but no reported trials | Is the first command too hard, or the promise unclear? | Observe two consenting users trying it; simplify one blocker |
| Demo runs but no own-task attempts | Is there a concrete use case? | Publish one adapter walkthrough; ask about actual task constraints |
| Integrations but no second run | Is replay useful enough to keep? | Compare with their baseline; prioritize usefulness over reach |
| Many abstract RSI debates | Is the name attracting the wrong expectation? | Lead with “recorded-tree exploration policies” and show the API |
| Frequent state-isolation questions | Does the target audience need a missing connector? | Narrow audience or implement one reliable backend first |
| One channel produces two useful integrations | Does repeating the useful topic work? | Spend the next week there and support those users |

Small samples are qualitative feedback, not conversion-rate science. Unknown outcomes stay
unknown; silence does not equal a failed install.

## 9. Money and reach

Spend $0 on ads, directory bundles and paid “hunters” for this month. The main cost is your
time and any local-model experimentation. Do not buy votes, followers or fabricated reviews.
Do not scrape personal contact data or send bulk outreach. No paid experiment is scheduled;
reconsider one only after repeat usage exists and you can state the exact audience and
activation event it would buy. Set a budget before spending anything.

## 10. Readiness gate before each public piece

Use correct 0.1.0a2 commands, inspect the graph, keep the Google disclaimer, include one
primary next step, check the site's current rules and your account's eligibility, and reserve
time for replies. These are practical launch checks, not a demand to wait for a perfect SDK.
An honest alpha is ready for targeted feedback; a claim of universal performance is not.
