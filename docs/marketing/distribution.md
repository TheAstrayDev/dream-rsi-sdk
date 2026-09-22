# Where to publish, list and submit

Nothing in this checklist has been executed. Suggested tags/categories are choices to
confirm in each site's current UI, not guaranteed available fields.

## GitHub — the destination every channel should lead to

Open [the repository](https://github.com/TheAstrayDev/dream-rsi-sdk). In About, use:

> Independent Python SDK for recorded-tree replay and LLM-driven executable exploration policies. Alpha, Docker-free, zero core dependencies.

Suggested topics: `python`, `ai-agents`, `llm`, `search`, `replay`, `recursive-self-improvement`,
`agent-evaluation`. Use only relevant labels, not a large set of unrelated trending terms.
Set the website field to the PyPI package or the most useful documentation entry point.

Create a GitHub Release for the already-published 0.1.0a2 source, with a tag pointing to
`aa337c20923554e751a7db5cff0e3ad5d00a6346`; do not accidentally tag a later implementation
as the same PyPI release. Paste piece A from [github.md](github.md). Release/tag creation
is proposed here, not done. If Discussions is enabled, pin piece B in a suitable category.
Otherwise use the existing early-adopter issue template instead of opening a fake user issue.

Pin the repository on your personal profile if it belongs among your main projects.
Use the measured graph as a preview image if it remains readable at thumbnail size;
otherwise use the existing SDK banner. Do not place a Google logo on your SDK listing.

## DEV — first external long-form article

Go to [DEV](https://dev.to/), sign in as yourself, create a post, and use A from
[dev-community.md](dev-community.md). Suggested tags: `python`, `ai`, `opensource`, `showdev`.
Preview code and links. Choose an accurate AI disclosure level; these drafts are generated
until you meaningfully author and verify them. Keep the opening disclosure in the body.

Publish A on day 3, B no sooner than a week later if readers asked for the deeper experiment.
For each article, put one next action near the end: run the lab for A, inspect/reproduce
the measured revision sequence for B. Reply on DEV itself, not only in GitHub issues.

## Hashnode — two durable engineering explanations

Start at [Hashnode](https://hashnode.com/), use your publication's dashboard and its new
article action. Do not assume a publication or custom domain already exists. Choose one
article from [hashnode.md](hashnode.md): adapters for integrators, sandbox design for
runtime developers. Suggested topics: Python, AI agents, open source, software architecture.

If this is your main technical blog, publish originals there and use a canonical URL when
republishing the same article elsewhere if the destination supports it. Set that URL only
after the original is live. Distinct drafts in this kit do not need pretend canonical links.
Custom-domain setup and SEO tools are optional; do not delay first-user support for them.

## LinkedIn — reach builders through your personal profile

Use desktop [LinkedIn](https://www.linkedin.com/) → Write article. Pieces in
[linkedin.md](linkedin.md) include the article and a short feed introduction. Put the
article in your Featured section if your profile supports it. Use the measured graph with
a caption explaining the synthetic task. Mention people only with an actual reason;
do not tag research authors to imply endorsement or trigger attention.

Publish A first, B after a week or more. If your account has little relevant readership,
one concise feed post may be more practical than two long articles. Code is optional here;
the link to an executable quickstart is essential.

## Medium — optional explanatory writing

Use [Medium](https://medium.com/) → Write, publish to your own profile initially.
Choose A or B in [medium.md](medium.md). Do not put these generated drafts behind a paywall.
Keep the disclosure near the beginning. A publication may impose stricter authorship or
submission rules; read its current instructions before asking an editor to include the article.
This channel is lower priority than helping developers already trying the package.

## Hugging Face — local-model evidence first

Use [Community Blogs](https://huggingface.co/blog/community) and the signed-in authoring
route available to your account. Use [hugging-face.md](hugging-face.md): A is a reproducible
local-model account; B examines the feedback contract. Link the Bonsai model card as a
dependency/reference, not as an endorsement of this SDK.

Optional later project listing: create a **static Space** called `dream-rsi-replay-lab`
if the name is available. It would display the archived graph, revision table, policy source
and installation command. Clearly label it an **archived-run explorer**, not live LLM execution.
No model upload, inference server or GPU is required for that design. Building this Space is
future work; do not announce a live demo URL until it exists and has been tested.

## Product Hunt — add the project after activation works

At [Product Hunt](https://www.producthunt.com/), use Submit → New Product from your maker
account when eligible. Prepare fields in [product-hunt.md](product-hunt.md): name, tagline,
short description, links, thumbnail, gallery and maker comment. There is no need to hire
a hunter. Do not pay for votes or ask for upvotes.

Suggested categories, if present: Developer Tools, Open Source, Artificial Intelligence.
Send people to the GitHub quickstart. Use piece B as an appropriate discussion/update only
when it adds engineering detail; do not relaunch the unchanged package just to post again.
The internal launch gate is a working demo and several known successful first runs, not a
particular star count. Stay available to answer questions on launch day.

## X — two short, complete threads

Use [X](https://x.com/) from your own account. Copy one numbered block at a time from
[x.md](x.md), attach the graph to the indicated post, and check the final rendered length.
Pin the first post if this is your main project. Keep the install command and quickstart
easy to find. Do not reply with the link to unrelated posts or send the same mention to
many large accounts. Thread B explains a real result; it is not “day 2, same launch.”

## Hacker News and LocalLLaMA — human-authored, conditional

Use [community-briefs.md](community-briefs.md). These are not copy-paste posts.
Show HN should link to a runnable project, not a marketing article or waitlist.
For LocalLLaMA, inspect the current rules and your account's participation before submitting
a local-model experiment. If you cannot post, wait and contribute usefully where you already
have something to say; do not manufacture comments to reach a ratio or evade moderation.

## Curated lists and newsletters

**Console:** email the verified public submission address `hello@console.dev`, with one
pitch from [outreach.md](outreach.md). Include installation, repo and one reason a Python
developer would use it. Ask for consideration as an alpha developer tool; never claim an
editorial review has been accepted. One relevant follow-up after at least a week is enough.

**Python Weekly:** start at [the official site](https://www.pythonweekly.com/) and inspect
the current newsletter/footer/contact route. The topic fits its stated remit, but no current
submission address was verified. Use the second pitch only after finding an official contact;
do not guess an email or use sponsorship sales as an assumed free editorial channel.

**Awesome agent lists:** inspect
[e2b-dev/awesome-ai-agents](https://github.com/e2b-dev/awesome-ai-agents) as a candidate.
Find the current contribution instructions and a tools/SDK category. If only complete
autonomous agents are accepted, skip it. A candidate PR description:

> Adds Dream-RSI SDK, an independent Apache-2.0 Python alpha for recorded-tree replay and
> executable exploration-policy development. I maintain the project. It is a supporting SDK,
> not a standalone autonomous agent. Installation and evidence are linked below; please
> exclude it if that is outside this list's scope.

Suggested list entry, only if the format fits:

> [Dream-RSI SDK](https://github.com/TheAstrayDev/dream-rsi-sdk) — Python SDK for recorded-tree
> replay and LLM-driven exploration policy code; configurable Docker-free interpreter. Alpha.

Limit the first month to one relevant list submission. A maintained, relevant list matters
more than 50 generic AI directories. Do not add an agent SDK to the MCP Registry unless it
actually provides an MCP server; do not submit a library as a model on a model registry.

## Posting time and duplicate content

Use a window when you can answer for the next hour. There is no verified “best time” for
this project's audience. The maintainer's timezone is UTC+7; record timestamps in UTC in
the tracker so comparisons are possible. Do not treat engagement differences across two
small posts as a controlled A/B test. Space substantial pieces apart and change the
engineering question, not just the title.
