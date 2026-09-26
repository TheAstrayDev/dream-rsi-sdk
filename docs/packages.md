# GitHub package sharing

Dream-RSI packages use public GitHub repositories as both the catalog and file
storage. There is no Dream-RSI package server or account. A package repository
has the `dreamrsi-package` topic and a GitHub Release containing one
`dreamrsi-package.json` asset with one or more family bundles. `dreamrsi list` searches
GitHub for that topic and sorts by
stars; stars are the popularity signal, not a quality or safety guarantee.

The commands below are available in the `0.2.0a2` source release:

```bash
python -m pip install "git+https://github.com/TheAstrayDev/dream-rsi-sdk.git@v0.2.0a2"
dreamrsi --help
```

`list` and `install` need internet access but no account. Publishing needs
[GitHub CLI](https://cli.github.com/) (`gh`); Dream-RSI starts its browser login
flow when needed and reads the token from `gh` for the upload. The token is not
written by Dream-RSI. GitHub owns the public repositories, visibility, search,
and star counts.

## Find and install

```bash
dreamrsi list
dreamrsi install OWNER/REPOSITORY
```

Replace `OWNER/REPOSITORY` with a real published package. You can install by short
name when it identifies exactly one result. Otherwise
use `OWNER/REPOSITORY`. The package and its bundle files are saved under
`.dreamrsi/packages/OWNER/REPOSITORY/`. The installer validates the manifest,
policy codecs, replay trees and checksums, then imports all bundled families into
`.dreamrsi/memory.sqlite3`. It creates a local `.dreamrsi/.gitignore` for the
SQLite database because memory may contain private task data; the package files
remain in the project.

Point your app's memory at that same database and use the package's task-family
key. For a package whose family is `labs`:

```python
from dreamrsi import AdaptivePolicyMemory, SQLiteStore

memory = AdaptivePolicyMemory(
    store=SQLiteStore(".dreamrsi/memory.sqlite3"),
    runtime_factory=build_runtime,  # pass its saved policy into DreamRSI(policy=...)
    family_of=lambda task: task["kind"],
    raw_quality=measure_quality,
    minimum_quality=quality_floor,
)
outcome = await memory.run({"kind": "labs", "input": "..."})
```

The runtime factory must pass its second argument to `DreamRSI(policy=...)`.
Otherwise the bundle is stored, but the runtime cannot use its policy. Dream-RSI
checks the policy on each new task and may still train if it is missing or below
the configured quality floor. The normal agent still performs the task.

`AdaptivePolicyMemory.run` requires `DefaultMethod(online=False)` and an independent
`HoldoutPipeline` on the runtime. Both are shown in the
[complete recipient example](releases/0.2.0a2.md#connect-an-imported-policy-and-its-trees-to-your-agent).
The [runnable transfer demo](../examples/shared_policy_bundle.py) verifies the
sender and recipient with separate SQLite databases and no network or model account.
For a multi-family package, `package.json` maps family keys to individual files in
`bundle_files`; `memory.import_bundle` expects one of those family files, not the
outer multi-family collection.

## Save and publish

The default memory database is `.dreamrsi/memory.sqlite3`, the same path used by
`install`. Saving reads the already stored policy versions and replay trees; it
does not call a model or start training. Use `--all` to collect every family in
the chosen namespace, or repeat `--family` to select families explicitly:

```bash
dreamrsi save my-policy-pack --all
dreamrsi save exploration-pack --family low_autocorrelation --family circle_packing
```

For a non-default SQLite path, pass `-d PATH`. `-n auto` chooses the namespace
when the database contains exactly one; if there are several, choose one with
`-n NAME`. The export is one `.dreamrsi.json` file containing each selected
family's saved policy versions and replay trees. The command prints its path and
the matching publish command:

```bash
dreamrsi save exploration-pack --all -d path/to/memory.sqlite3 -n auto
dreamrsi publish .dreamrsi/packages/exports/exploration-pack.dreamrsi.json
```

If needed, `publish` asks `gh` to open GitHub's browser authorization flow. It
then asks for a lowercase repository name, checks whether that name is already
used in your account, and creates a **public** repository and a `v0.1.0` GitHub
Release under the signed-in account. GitHub repository names are unique within
an account, not across all GitHub; the shared identifier is `OWNER/REPOSITORY`.
One package can include multiple task families; installing it imports each family
into the same local memory database.
The package and replay data become public. Inspect the bundle first, especially
if tasks contain prompts, source code, observations or private data.

GitHub search can take a short time to index a new topic, so a just-published
repository may not immediately appear in `dreamrsi list`; its direct
`OWNER/REPOSITORY` install reference works as soon as GitHub serves the new
release. Installation fetches the latest release; this alpha does not provide
version pinning or automatic upgrades. GitHub release assets must each be under
2 GiB ([GitHub release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)).

## Current boundaries

- Listing depends on GitHub's public repository search and its rate limits.
- Popularity means stars only; the catalog does not claim benchmark quality.
- The CLI imports built-in policies and source policies supported by its default
  sandbox profile. Applications with custom policy codecs or sandbox profiles
  can use `dreamrsi install OWNER/REPOSITORY --file-only` to save the checked
  bundle envelope without decoding it, then call
  `AdaptivePolicyMemory.import_bundle` with their registered codec and
  compatible sandbox. That final import performs full policy and tree checks.
- GitHub's repository and file-size limits apply. No package is uploaded to a
  separate Dream-RSI service.

## Troubleshooting

| Message or symptom | Action |
| --- | --- |
| Database not found | Run from your project directory or pass an absolute path with `-d`. `save` reads existing memory; it does not create training data. |
| File already exists | The CLI protects the previous snapshot. Choose another package name or pass `--output PATH`. |
| GitHub CLI missing | Install `gh`, reopen the terminal so `PATH` refreshes, and retry. `gh auth login --hostname github.com --web` can complete sign-in separately. |
| Different local champion | Install with `--namespace NAME` and configure the receiver with that same new namespace. |
| Source sandbox or custom codec mismatch | Download with `--file-only`, register the compatible codec/sandbox in your app, then import each family file. |
| Policy installed but not used | Check the database path, namespace, family key, admission rule and `policy=saved_policy` in the runtime factory. |
