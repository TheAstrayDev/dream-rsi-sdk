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

## Published 0.1.0a2

- Source commit: [aa337c2](https://github.com/TheAstrayDev/dream-rsi-sdk/commit/aa337c20923554e751a7db5cff0e3ad5d00a6346).
- [CI passed](https://github.com/TheAstrayDev/dream-rsi-sdk/actions/runs/35711547369):
  Python 3.11–3.14 on Linux, Python 3.14 on Windows, quality and optional integration.
- [Publication succeeded](https://github.com/TheAstrayDev/dream-rsi-sdk/actions/runs/35711714572)
  under the TheAstrayDev PyPI account; metadata lists only TheAstrayDev as author.
- [PyPI release](https://pypi.org/project/dreamrsi/0.1.0a2/).
- Wheel SHA-256: `fdf55ae579705cc1ac7af283916e00298d2d0e64fc8af7d33de1529618cf73de`.
- Source archive SHA-256: `bf013c7884239ccfdc495d5c9d43a5c6c038aadde0510c341315546e93ab9bdf`.

## Published 0.1.0a3

- Source commit: [71be153](https://github.com/TheAstrayDev/dream-rsi-sdk/commit/71be153).
- Publication workflow: [run 35748923102](https://github.com/TheAstrayDev/dream-rsi-sdk/actions/runs/35748923102).
- [PyPI release](https://pypi.org/project/dreamrsi/0.1.0a3/).
- Package metadata lists only `TheAstrayDev` as author; wheel and source archive were published.
