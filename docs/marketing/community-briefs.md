# Community-specific preparation: Hacker News and LocalLLaMA

These are **research/editorial briefs, not ready-to-post community text**. Write the actual
submission yourself from your experience. This matters particularly on HN, whose
[guidelines](https://news.ycombinator.com/newsguidelines.html) prohibit generated and AI-edited
posts. Do not simply paraphrase this file with another model and call it human-authored.

## Hacker News · brief A: runnable SDK

**When:** after the no-key demo and install path work and you can stay for questions.
Account eligibility may prevent a Show HN; see the [current restriction note](https://news.ycombinator.com/showlim).

**Destination:** [Show HN guidance](https://news.ycombinator.com/showhn.html), then the site's
Submit action. Submit the usable repository, not an article, signup form or future demo.
Write your own title with the required Show HN prefix and a plain factual description.

**Facts to choose from, in your own words:**

- You maintain an independent alpha inspired by the public Dream-RSI research.
- The library separates discovery agent, evaluator and exploration policy.
- Recorded replay uses collected transitions; it cannot reveal unknown outcomes.
- The optional developer writes source instead of only selecting built-in parameters.
- Python 3.11+, PyPI 0.1.0a2, zero core dependencies, no-key example.
- Bounded policy interpreter; optional process worker; no Docker requirement.
- Adapters still own external state and remote cancellation.

**Personal material only you can supply:** the actual reason you chose this problem,
the integration that motivated it, one design choice you considered and rejected, and what
you personally learned. No invented origin story is provided.

**Useful technical question:** identify the particular design tradeoff on which you want
feedback, rather than soliciting votes or generic support. Be ready to explain why a restricted
language, what replay omits, and how total optimization costs should be measured.

**Stop conditions:** no runnable demo; inability to explain the code; an account restriction;
or no time to respond. Do not delete and repost to chase ranking or organize friends to vote.

## Hacker News · brief B: later engineering story

**When:** only after a substantive engineering write-up exists, not the next day as another
Show HN for the same version. A regular article submission is distinct from Show HN.

**Possible subject:** the difference between a source rewrite, a behavioral change and a
measured improvement. Explain the 1,000-round stall, the feedback needed to repair it, and
the cost/quality tradeoff. Do not title it around a universal intelligence gain.

**Evidence to inspect before personally writing:** latest report, failed revision, earlier
three-seed matrix, source artifact, replay-round counts and fresh online budget.

**Missing evidence to state:** harder tasks, untouched validation data, total lifecycle cost,
controlled multi-seed reliability. The article should teach an engineering lesson on its own;
the SDK link is supporting context, not the whole reason to submit.

## Reddit / LocalLLaMA · brief A: local Bonsai experiment

**When:** your account is eligible and your participation fits the current self-promotion
rules. Read the sidebar/rules and [moderator update](https://www.reddit.com/r/LocalLLaMA/comments/1su3ao4/rlocalllama_rule_updates/).
Do not assume “open source” exempts a post from promotion rules or that an AI label makes
a copied generated post acceptable. If uncertain, ask moderators through the site's designated
channel before posting, and accept their answer.

**Format:** personally written experiment report with model/settings, one measured graph,
failure cases and a concrete question. Lead with what you actually ran, not a product slogan.

**Facts:** Bonsai-27B-Q1_0; llama.cpp b10107-c0bc8591e; RTX 4070 12 GB; 32 GB RAM;
context 16,384; final reasoning budget 4,096; max output 8,192; seed 43;
temperature 0.7/top-p 0.95/top-k 20; six requested revisions, five scored.

**Core observation:** revision 2 reached 1,000 rounds; revision 3 repaired stopping to four;
revision 4 used three probes. The selected policy passed validation and source reload.
Fresh residual 1.5 → 0.1875 at six calls each on the synthetic halving task.

**Required context:** you are the SDK maintainer; the discovery agent was deterministic;
this was an exploratory follow-up after weaker runs; scaled task inputs are not broad
generalization. State accurately how AI was used in code and text. Do not imply Bonsai's
creators or Google endorse the project.

**Discussion focus:** what local-model settings or feedback fields would be worth testing
under a fixed protocol next? Ask for reproducible reports rather than “please star.”

## Reddit / LocalLLaMA · brief B: interpreter/profile design

**When:** later, with a distinct useful engineering point; not a repost of the launch.
Do not post just to satisfy a two-post plan. If there is no new substance, skip it.

**Subject:** how a small Python-syntax interpreter exposes enough helpers, sorting and
collections for a local model to write policies, while keeping host APIs unavailable.

**Include:** a tiny real policy, a profile configuration, one actual error and repair, the
inline/process tradeoff, and the fact that a worker process is not a complete OS security
sandbox. Prefer direct technical evidence over a logo or promotional carousel.

**Question to develop personally:** which missing language construct prevents a useful
policy, and can the reader show the minimal program? Keep the discussion about actual
policy development, not hypothetical unlimited code execution.

For other subreddits, inspect their own rules first. This plan does not establish eligibility
for r/MachineLearning, r/Python or r/SideProject, and does not prescribe posting the same copy
across them. No Reddit posts or moderator messages have been sent.
