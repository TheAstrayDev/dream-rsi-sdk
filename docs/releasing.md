# Publishing a release

Package author: **TheAstrayDev**. Package name: `dreamrsi`.

1. Update `pyproject.toml`, `dreamrsi.__version__`, README and package README to the
   same version; record evidence and limitations in CHANGELOG.
2. Run tests, Ruff, Pyright, build and `twine check --strict`. Verify an installed wheel,
   including the process worker. Commit and push all release inputs to GitHub first.
3. Configure the PyPI Trusted Publisher for owner `TheAstrayDev`, repository
   `dream-rsi-sdk`, workflow `publish.yml`, environment `pypi`. For the first upload,
   configure a pending publisher for project `dreamrsi` under the owner's PyPI account.
4. Run **Publish to PyPI** manually on `main`, supplying the exact version. The workflow
   checks the author/version, reruns validation, builds distributions, then publishes
   those artifacts with short-lived OIDC credentials. No permanent PyPI API token is needed.
5. Verify the public PyPI metadata, distribution hashes and installation from the index.

The workflow does not publish on ordinary pushes. PyPI versions cannot be overwritten;
fixes after publication require a new version. Test results describe SDK reliability,
while model experiment reports describe effectiveness on their documented tasks.
