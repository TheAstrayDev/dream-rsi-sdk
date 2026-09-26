import asyncio
import hashlib
import io
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from dreamrsi import AdaptivePolicyMemory
from dreamrsi.cli import (
    _ensure_local_gitignore,
    _saved_families_by_namespace,
    _validate_bundle_file,
    install_document,
    main,
    save_local_bundle,
)
from dreamrsi.discovery import DiscoveryTree
from dreamrsi.errors import ConfigurationError
from dreamrsi.packages import (
    GitHubAPI,
    GitHubAPIError,
    GitHubPackageRegistry,
    PackageError,
    make_bundle_collection,
    package_document,
    unpack_policy_bundles,
    validate_package_document,
)
from dreamrsi.policies import DepthFirstPolicy, GreedyPolicy
from dreamrsi.replay import ReplayWorld
from dreamrsi.storage import InMemoryStore, SQLiteStore


def _stub_bundle(family="labs"):
    payload = {
        "format": "dreamrsi.policy-bundle",
        "schema_version": 1,
        "family": family,
        "active_policy": None,
        "policies": [],
        "worlds": [],
    }
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False, ensure_ascii=False)
    return {**payload, "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}


async def _bundle(tmp_path, family="labs"):
    task = {"kind": family, "seed": 1}
    store = InMemoryStore()
    memory = AdaptivePolicyMemory(
        store=store,
        runtime_factory=lambda task, policy: None,
        family_of=lambda task: task["kind"],
        raw_quality=lambda task, result: 1.0,
        minimum_quality=lambda task: 0.5,
    )
    await memory.remember(task, GreedyPolicy(), origin="promoted", raw_quality=0.9)
    tree = DiscoveryTree()
    root = tree.create_root(state={"seed": 1})
    tree.add_node(root.id, state={"seed": 2}, score=0.9)
    tree.commit()
    await memory._remember_world(family, task, ReplayWorld(tree))
    path = tmp_path / f"{family}.dreamrsi.json"
    await memory.export_bundle(task, path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    await store.close()
    return bundle


def test_github_package_list_is_sorted_by_stars():
    class FakeAPI:
        def request(self, method, path, payload=None):
            query = parse_qs(urlparse(path).query)
            assert query["q"] == ["topic:dreamrsi-package"]
            assert query["sort"] == ["stars"]
            return {
                "items": [
                    {"owner": {"login": "astray"}, "name": "small", "description": None,
                     "stargazers_count": 2, "html_url": "https://github.com/astray/small"},
                    {"owner": {"login": "astray"}, "name": "popular", "description": "Nice",
                     "stargazers_count": 7, "html_url": "https://github.com/astray/popular"},
                ]
            }

    packages = GitHubPackageRegistry(FakeAPI()).list()
    assert [package.reference for package in packages] == ["astray/popular", "astray/small"]
    assert packages[0].stars == 7


def test_local_gitignore_preserves_existing_rules_and_protects_memory(tmp_path):
    data_dir = tmp_path / ".dreamrsi"
    data_dir.mkdir()
    ignore = data_dir / ".gitignore"
    ignore.write_text("# app rules\ncustom-cache/\n", encoding="utf-8")

    _ensure_local_gitignore(data_dir)
    _ensure_local_gitignore(data_dir)

    assert ignore.read_text(encoding="utf-8") == (
        "# app rules\ncustom-cache/\n/memory.sqlite3*\n"
    )


def test_package_list_handles_legacy_windows_console_encoding(monkeypatch):
    from dreamrsi.packages import PackageListing

    monkeypatch.setattr(
        GitHubPackageRegistry,
        "list",
        lambda self, limit: [
            PackageListing("astray", "demo", "Shared policy \U0001f680", 2, "https://github.com/astray/demo")
        ],
    )
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1251")
    monkeypatch.setattr(sys, "stdout", stream)
    assert main(["list"]) == 0
    stream.flush()
    output = buffer.getvalue().decode("cp1251")
    assert "astray/demo" in output and "stars=2" in output
    assert "\\U0001f680" in output


def test_package_manifest_binds_repo_name_owner_and_family():
    bundle = _stub_bundle()
    document = package_document(
        owner="astray", name="labs-policy", description="A shared policy", bundle=bundle
    )
    assert validate_package_document(document, owner="astray", name="labs-policy") is document
    with pytest.raises(PackageError, match="repository name"):
        validate_package_document(document, owner="astray", name="other")
    document["family"] = "other"
    with pytest.raises(PackageError, match="family"):
        validate_package_document(document)


async def test_multifamily_package_saves_and_installs_all_families(tmp_path):
    bundles = [
        await _bundle(tmp_path, "low_autocorrelation"),
        await _bundle(tmp_path, "circle_packing"),
    ]
    source = make_bundle_collection(bundles)
    assert [item["family"] for item in unpack_policy_bundles(source)] == [
        "low_autocorrelation",
        "circle_packing",
    ]
    document = package_document(
        owner="astray", name="shared-exploration", description="Two task families",
        bundles=bundles,
    )
    assert validate_package_document(document)["schema_version"] == 2

    collection_path = tmp_path / "collection.dreamrsi.json"
    collection_path.write_text(json.dumps(source), encoding="utf-8")
    checked_bundles, policies, worlds = await asyncio.to_thread(
        _validate_bundle_file, collection_path
    )
    assert len(checked_bundles) == 2
    assert (policies, worlds) == (2, 2)

    seed_project = tmp_path / "seed-project"
    await install_document(document, project_dir=seed_project)
    saved = await save_local_bundle(
        "all-exploration",
        ["low_autocorrelation", "circle_packing"],
        project_dir=seed_project,
        output=tmp_path / "all-exploration.dreamrsi.json",
    )
    assert (saved["policies"], saved["worlds"]) == (2, 2)
    saved_document = json.loads(Path(saved["path"]).read_text(encoding="utf-8"))
    assert [item["family"] for item in unpack_policy_bundles(saved_document)] == [
        "low_autocorrelation",
        "circle_packing",
    ]

    result = await install_document(document, project_dir=tmp_path / "recipient")
    assert result["families"] == ["low_autocorrelation", "circle_packing"]
    assert result["policies"] == 2
    assert result["worlds"] == 2
    assert len(list((tmp_path / "recipient" / ".dreamrsi" / "packages" / "astray"
                     / "shared-exploration" / "bundles").glob("*.dreamrsi.json"))) == 2

    store = SQLiteStore(result["database"])
    try:
        memory = AdaptivePolicyMemory(
            store=store,
            runtime_factory=lambda task, policy: None,
            family_of=lambda task: task["kind"],
            raw_quality=lambda task, run: 1.0,
            minimum_quality=lambda task: 0.5,
        )
        for family in result["families"]:
            assert isinstance(await memory.load(family, task={"kind": family}), GreedyPolicy)
            assert len(await memory._worlds(family)) == 1
    finally:
        await store.close()


async def test_multifamily_install_preflights_conflicts_before_importing(tmp_path):
    bundles = [await _bundle(tmp_path, "new_family"), await _bundle(tmp_path, "existing_family")]
    document = package_document(
        owner="astray", name="shared-exploration", description="", bundles=bundles
    )
    project = tmp_path / "recipient"
    database = project / ".dreamrsi" / "memory.sqlite3"
    database.parent.mkdir(parents=True)
    store = SQLiteStore(database)
    existing = AdaptivePolicyMemory(
        store=store,
        runtime_factory=lambda task, policy: None,
        family_of=lambda task: task["kind"],
        raw_quality=lambda task, run: 1.0,
        minimum_quality=lambda task: 0.5,
    )
    await existing.remember({"kind": "existing_family"}, DepthFirstPolicy())
    await store.close()

    with pytest.raises(ConfigurationError, match="already has different policies"):
        await install_document(document, project_dir=project)

    store = SQLiteStore(database)
    try:
        assert await store.get_checkpoint(existing._key("new_family")) is None
        saved = await store.get_checkpoint(existing._key("existing_family"))
        assert saved["versions"][0]["policy"]["name"] == "DepthFirstPolicy"
    finally:
        await store.close()


async def test_install_saves_bundle_and_imports_it_into_project_sqlite(tmp_path):
    bundle = await _bundle(tmp_path)
    document = package_document(
        owner="astray", name="labs-policy", description="Reusable labs policy", bundle=bundle
    )
    result = await install_document(document, project_dir=tmp_path)
    assert result["policies"] == 1
    assert result["worlds"] == 1
    assert (tmp_path / ".dreamrsi" / "packages" / "astray" / "labs-policy"
            / "bundle.dreamrsi.json").is_file()
    assert "memory.sqlite3*" in (tmp_path / ".dreamrsi" / ".gitignore").read_text()

    store = SQLiteStore(result["database"])
    try:
        memory = AdaptivePolicyMemory(
            store=store,
            runtime_factory=lambda task, policy: None,
            family_of=lambda task: task["kind"],
            raw_quality=lambda task, run: 1.0,
            minimum_quality=lambda task: 0.5,
        )
        assert isinstance(await memory.load("labs", task={"kind": "labs"}), GreedyPolicy)
        assert len(await memory._worlds("labs")) == 1
    finally:
        await store.close()


async def test_file_only_install_saves_bundle_without_creating_memory_db(tmp_path):
    bundle = await _bundle(tmp_path)
    document = package_document(owner="astray", name="labs-policy", description="", bundle=bundle)
    result = await install_document(document, project_dir=tmp_path, file_only=True)
    assert not result["imported"]
    assert result["policies"] == 1
    assert Path(result["path"]).is_file()
    assert not (tmp_path / ".dreamrsi" / "memory.sqlite3").exists()


async def test_install_does_not_replace_an_existing_champion(tmp_path):
    bundle = await _bundle(tmp_path)
    document = package_document(
        owner="astray", name="labs-policy", description="", bundle=bundle
    )
    database = tmp_path / ".dreamrsi" / "memory.sqlite3"
    database.parent.mkdir(parents=True)
    store = SQLiteStore(database)
    existing = AdaptivePolicyMemory(
        store=store,
        runtime_factory=lambda task, policy: None,
        family_of=lambda task: task["kind"],
        raw_quality=lambda task, run: 1.0,
        minimum_quality=lambda task: 0.5,
    )
    await existing.remember({"kind": "labs"}, DepthFirstPolicy())
    await store.close()

    with pytest.raises(ConfigurationError, match="fresh policy-memory namespace"):
        await install_document(document, project_dir=tmp_path)
    assert not (
        tmp_path / ".dreamrsi" / "packages" / "astray" / "labs-policy"
    ).exists()

    store = SQLiteStore(database)
    try:
        saved = await store.get_checkpoint(existing._key("labs"))
        assert saved["versions"][0]["sha256"] != bundle["policies"][0]["sha256"]
        assert saved["versions"][0]["policy"]["name"] == "DepthFirstPolicy"
    finally:
        await store.close()


async def test_save_exports_local_family_bundle_to_a_predictable_path(tmp_path):
    bundle = await _bundle(tmp_path)
    document = package_document(owner="astray", name="labs-policy", description="", bundle=bundle)
    await install_document(document, project_dir=tmp_path)
    result = await save_local_bundle(
        "labs-policy", "labs", project_dir=tmp_path
    )
    assert result["policies"] == 1
    assert result["worlds"] == 1
    assert result["path"].endswith("labs-policy.dreamrsi.json")


async def test_save_all_auto_detects_namespace_and_combines_saved_families(
    tmp_path, monkeypatch, capsys
):
    families = [
        await _bundle(tmp_path, "low_autocorrelation"),
        await _bundle(tmp_path, "lasso_tuning"),
    ]
    document = package_document(
        owner="astray",
        name="seed",
        description="",
        bundles=families,
    )
    database = tmp_path / "memory.sqlite3"
    await install_document(
        document,
        project_dir=tmp_path / "source",
        database=database,
        namespace="shared-seed",
    )

    assert _saved_families_by_namespace(database) == {
        "shared-seed": ["lasso_tuning", "low_autocorrelation"]
    }
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "combined.dreamrsi.json"
    exit_code = await asyncio.to_thread(
        main,
        [
            "save",
            "combined",
            "--all",
            "-d",
            str(database),
            "-n",
            "auto",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert "2 policy versions and 2 replay trees across 2 task families" in capsys.readouterr().out
    exported = json.loads(output.read_text(encoding="utf-8"))
    assert [item["family"] for item in unpack_policy_bundles(exported)] == [
        "lasso_tuning",
        "low_autocorrelation",
    ]


def test_save_all_ignores_non_mapping_checkpoints(tmp_path):
    database = tmp_path / "memory.sqlite3"
    store = SQLiteStore(database)

    async def seed() -> None:
        await store.save_checkpoint("ignored", "legacy checkpoint")
        await store.save_checkpoint(
            "valid",
            {
                "schema": 1,
                "namespace": "default",
                "family": "labs",
                "versions": [{"policy": {}}],
                "active": 0,
            },
        )
        await store.close()

    asyncio.run(seed())
    assert _saved_families_by_namespace(database) == {"default": ["labs"]}


def test_publish_creates_public_repo_uploads_bundle_and_registers_topic():
    bundle = _stub_bundle()
    document = package_document(
        owner="astray", name="labs-policy", description="Reusable labs policy", bundle=bundle
    )

    class FakeAPI:
        def __init__(self):
            self.calls = []
            self.uploaded = None

        def request(self, method, path, payload=None):
            self.calls.append((method, path, payload))
            if method == "GET" and path == "/user":
                return {"login": "astray"}
            if method == "GET" and path == "/repos/astray/labs-policy":
                raise GitHubAPIError(404, "Not Found")
            if method == "POST" and path == "/user/repos":
                assert payload["private"] is False
                return {"html_url": "https://github.com/astray/labs-policy"}
            if method == "POST" and path == "/repos/astray/labs-policy/releases":
                return {
                    "upload_url": "https://uploads.github.com/repos/astray/labs-policy/releases/1/assets{?name,label}"
                }
            return {}

        def upload_asset(self, upload_url, name, content):
            self.uploaded = (upload_url, name, content)

    api = FakeAPI()
    url = GitHubPackageRegistry(api).publish("labs-policy", document)
    assert url == "https://github.com/astray/labs-policy"
    assert api.uploaded[1] == "dreamrsi-package.json"
    uploaded = json.loads(api.uploaded[2])
    assert uploaded == document
    topics = next(call for call in api.calls if call[1].endswith("/topics"))
    assert "dreamrsi-package" in topics[2]["names"]


def test_publish_accepts_multi_family_package_manifest():
    document = package_document(
        owner="astray",
        name="shared-exploration",
        description="Several task families",
        bundles=[_stub_bundle("low_autocorrelation"), _stub_bundle("circle_packing")],
    )

    class FakeAPI:
        def __init__(self):
            self.uploaded = None

        def request(self, method, path, payload=None):
            if method == "GET" and path == "/user":
                return {"login": "astray"}
            if method == "GET" and path == "/repos/astray/shared-exploration":
                raise GitHubAPIError(404, "Not Found")
            if method == "POST" and path == "/user/repos":
                return {"html_url": "https://github.com/astray/shared-exploration"}
            if method == "POST" and path.endswith("/releases"):
                return {
                    "upload_url": "https://uploads.github.com/repos/astray/shared-exploration/releases/1/assets{?name,label}"
                }
            return {}

        def upload_asset(self, upload_url, name, content):
            self.uploaded = json.loads(content)

    api = FakeAPI()
    GitHubPackageRegistry(api).publish("shared-exploration", document)
    assert api.uploaded["schema_version"] == 2
    assert api.uploaded["families"] == ["low_autocorrelation", "circle_packing"]


def test_download_reads_the_package_asset_from_latest_release():
    document = package_document(
        owner="astray",
        name="labs-policy",
        description="Reusable labs policy",
        bundle=_stub_bundle(),
    )

    class FakeAPI:
        def __init__(self):
            self.urls = []

        def request(self, method, path, payload=None):
            assert method == "GET"
            assert path == "/repos/astray/labs-policy/releases/latest"
            return {
                "assets": [
                    {
                        "name": "dreamrsi-package.json",
                        "browser_download_url": "https://github.com/astray/labs-policy/releases/download/v0.1.0/dreamrsi-package.json",
                    }
                ]
            }

        def raw_file(self, url):
            self.urls.append(url)
            return json.dumps(document).encode("utf-8")

    api = FakeAPI()
    downloaded = GitHubPackageRegistry(api).download("astray", "labs-policy")
    assert downloaded == document
    assert api.urls[0].startswith("https://github.com/astray/labs-policy/releases/")


def test_release_asset_upload_uses_authenticated_binary_request(monkeypatch):
    import dreamrsi.packages as packages

    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"id": 3}'

    def fake_urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["method"] = request.get_method()
        observed["body"] = request.data
        observed["headers"] = request.headers
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(packages, "urlopen", fake_urlopen)
    api = GitHubAPI("secret-token")
    response = api.upload_asset(
        "https://uploads.github.com/repos/a/b/releases/3/assets{?name,label}",
        "dreamrsi-package.json",
        b"package-bytes",
    )
    assert response == {"id": 3}
    assert observed["url"].endswith("?name=dreamrsi-package.json")
    assert observed["method"] == "POST"
    assert observed["body"] == b"package-bytes"
    assert observed["headers"]["Content-type"] == "application/octet-stream"
    assert observed["headers"]["Authorization"] == "Bearer secret-token"
