# Hugging Face community blog · two article drafts

Editorial notes: target readers already running local models. A is the reproduction story;
B is the feedback-design story. Do not upload model weights or present the SDK as a model.
Check the current blog editor and disclose that these are AI-assisted editorial drafts.

---

## Article A — Bonsai-27B-Q1_0 as an executable policy developer: a local experiment

*AI-assisted draft based on archived runs. I maintain Dream-RSI SDK independently; this is
not a Google product or an official reproduction of the Dream-RSI benchmarks.*

I tested Bonsai-27B-Q1_0 through a local llama.cpp server as a developer of executable
exploration policies. Its job was to rewrite the strategy around a fixed discovery agent,
using source code and replay feedback between revisions.

The model was [Bonsai-27B-Q1_0](https://huggingface.co/prism-ml/Bonsai-27B-gguf).
The recorded setup used llama.cpp `b10107-c0bc8591e`, an RTX 4070 with 12 GB VRAM,
32 GB system RAM and a 16,384-token context. The final follow-up used seed 43,
six revisions, an 8,192-token output limit and a server reasoning budget of 4,096.
Sampling was temperature 0.7, top-p 0.95 and top-k 20.

### The task isolates policy development

The discovery agent deterministically divided the current value by two. The evaluator
returned `-abs(observation)`. The LLM did not perform those refinements; it wrote a program
that chose which revealed node to expand and when to stop.

This deliberately small task helps separate source-generation failures, interpreter errors
and actual changes in replay behavior. It does not represent a realistic coding-agent benchmark.

The developer began with readable source equivalent to the built-in baseline. That initial
program was handwritten. The challenger revisions in the report came from the model without
manual source edits.

### What the revisions changed

The first valid revision matched the baseline's replay objective. The second used five probes
but reached the 1,000-round cap, including 997 empty rounds. With feedback about empty
continuations, revision 3 stopped after four rounds. Revision 4 used three probes in four rounds
and became the selected policy. Revision 5 matched it; revision 6 failed.

The run therefore has five scored revisions out of six and four distinct successful replay
behaviors. It passed held-out selection and execution after source serialization/reload.
On a fresh initial value of 12, the generated policy reached residual 0.1875 versus the
baseline's 1.5, with six discovery-agent calls each.

### Reproduction path

Clone the repository and use the published release source commit:

```bash
git clone https://github.com/TheAstrayDev/dream-rsi-sdk.git
cd dream-rsi-sdk
git checkout aa337c20923554e751a7db5cff0e3ad5d00a6346
python -m pip install -e .
```

Use a Python 3.11+ virtual environment. With your existing llama.cpp server configured as
above on port 8087, run:

```bash
python examples/05_local_llamacpp.py --url http://127.0.0.1:8087 --model Bonsai-27B-Q1_0 --source-incumbent --revisions 6 --max-tokens 8192 --timeout 300 --seed 43 --output temp/bonsai-reproduction.json
```

The SDK client does not download or start a model. Sampling and backend differences can
change outputs; the seed is not a cross-machine determinism guarantee.

### What remains unresolved

An earlier three-seed matrix promoted only one seed. The later follow-up changed settings
after examining failures, and validation tasks were related scaled inputs reused during
development. This is evidence of a working code-revision loop, not a controlled estimate of
general performance or overall compute savings.

The [full report](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/sandbox-v4-2026-09-22.md)
includes compressed raw reports, model responses, source artifacts, failure status and hashes.
If you reproduce it, please report both the backend configuration and the complete acceptance
flags—even when the result does not improve.

---

## Article B — Replay feedback for an LLM should explain what the policy actually did

*AI-assisted draft based on Dream-RSI SDK's implementation and measured runs. The SDK is
independent and unofficial; I am not affiliated with Google.*

When a model is asked to revise code, “the score was worse” gives it very little to work with.
For an exploration policy, even a better score may hide a behavior that should be repaired.
One local Bonsai policy used fewer probes but spent almost all of its replay rounds revealing
nothing new.

Dream-RSI SDK's developer loop treats feedback as a structured engineering interface. A
revision request includes the previous program, the active interpreter capabilities, the
baseline evidence, and measurements from the candidate's own evaluation. Failed code gets
its execution error rather than a borrowed score from a previous version.

### A trajectory is more informative than one number

The relevant details include which nodes were legally available, what the policy selected,
which observations became visible and how quality changed. Work counts matter too: probes,
decision rounds and empty rounds can distinguish a useful search change from a stall.

The policy view contains a causal `last_round` field. It is initially absent as an observation,
then describes the preceding executed batch and its revealed nodes and scores. The policy
can react to a past empty continuation without seeing hidden future children.

That boundary is important. Handing the policy the whole frozen tree would make historical
replay look good by giving it information unavailable during online exploration. Feedback
needs to be informative without changing the experiment into hindsight selection.

### Make the execution target explicit

Generated policies run in a bounded Python-syntax interpreter. Helpers, collection operations,
sorting and supported math functions let the model express new algorithms. Source-line errors
and the active capability profile tell it which constructs need repair.

The environment remains a restricted language. It does not permit arbitrary imports, network
requests or host callbacks. A model asked to write unrestricted Python would have a misleading
contract. The SDK makes its limitations part of the generation request instead.

### Preserve failed attempts and provenance

Source hashes, ancestry, executable-structure hashes and decision hashes answer different
questions. Did the text change? Did its structure change? Did it make different replay decisions?
Only scored revisions belong in the successful-behavior count.

The final documented Bonsai follow-up changed stopping from 1,000 rounds to four, then
reached the same recorded quality with three probes. Five of six revisions scored, and the
selected code was deployed after saving and reloading. Those changes were made by the model;
the failed last revision remains visible in the report.

This still does not establish broad utility. The discovery task was synthetic, and developer
generation has its own cost. A better next experiment needs a harder task, untouched validation
data and complete accounting across development and online execution.

If you are experimenting with code-generating agents, the question I would bring to this
interface is concrete: what information would let a developer repair a bad decision without
leaking future outcomes? The [source and feedback reports](https://github.com/TheAstrayDev/dream-rsi-sdk/blob/main/docs/experiments/sandbox-v4-2026-09-22.md)
make that discussion inspectable.
