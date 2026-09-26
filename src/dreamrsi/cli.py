"""Command-line UX for sharing Dream-RSI policy bundles through GitHub."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from dreamrsi.errors import ConfigurationError, PolicyError
from dreamrsi.packages import (
    PACKAGE_TOPIC,
    GitHubAPI,
    GitHubPackageRegistry,
    PackageError,
    is_package_slug,
    make_bundle_collection,
    package_document,
    unpack_policy_bundles,
    validate_package_document,
)
from dreamrsi.policy_memory import AdaptivePolicyMemory
from dreamrsi.storage import InMemoryStore, SQLiteStore


def _memory(store: Any, namespace: str) -> AdaptivePolicyMemory:
    return AdaptivePolicyMemory(
        store=store,
        runtime_factory=lambda task, policy: None,
        family_of=lambda family: family,
        raw_quality=lambda task, result: 0.0,
        minimum_quality=lambda task: 0.0,
        namespace=namespace,
    )


def _saved_families_by_namespace(database: Path) -> dict[str, list[str]]:
    """Read family names from an SDK SQLite store without opening it for writes."""
    if not database.is_file():
        raise PackageError(f"Policy memory database was not found at {database}")
    uri = f"{database.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        try:
            rows = connection.execute("SELECT data FROM records WHERE kind='checkpoint'")
            families: dict[str, set[str]] = {}
            for (raw,) in rows:
                try:
                    entry = json.loads(raw)
                except (TypeError, json.JSONDecodeError) as exc:
                    raise PackageError("Policy memory contains an invalid checkpoint") from exc
                if not isinstance(entry, dict):
                    continue
                namespace = entry.get("namespace")
                family = entry.get("family")
                has_policies = isinstance(entry.get("versions"), list) and bool(entry["versions"])
                has_worlds = isinstance(entry.get("worlds"), list) and bool(entry["worlds"])
                if (
                    isinstance(namespace, str)
                    and isinstance(family, str)
                    and family
                    and (has_policies or has_worlds)
                ):
                    families.setdefault(namespace, set()).add(family)
            return {key: sorted(value) for key, value in families.items()}
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise PackageError(f"Could not read policy memory database {database}: {exc}") from exc


def _write_json_atomic(path: Path, value: dict) -> None:
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = stream.name
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError) as exc:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
        raise PackageError(f"Could not save {path}: {exc}") from exc


def _ensure_local_gitignore(data_dir: Path) -> None:
    ignore = data_dir / ".gitignore"
    try:
        existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    except (OSError, UnicodeError) as exc:
        raise PackageError(f"Could not read {ignore}: {exc}") from exc
    if "/memory.sqlite3*" in existing.splitlines():
        return
    prefix = existing
    if prefix and not prefix.endswith(("\n", "\r")):
        prefix += "\n"
    if not existing:
        prefix = "# Local policy memory may contain private task data.\n"
    _write_text_atomic(ignore, f"{prefix}/memory.sqlite3*\n")


def _write_text_atomic(path: Path, content: str) -> None:
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
        raise PackageError(f"Could not save {path}: {exc}") from exc


async def install_document(
    document: dict,
    *,
    project_dir: Path,
    database: Path | None = None,
    namespace: str = "default",
    file_only: bool = False,
) -> dict[str, Any]:
    """Validate, save and import a public package into a project's local memory."""
    validate_package_document(document)
    bundles = (
        [document["bundle"]]
        if document["schema_version"] == 1
        else document["bundles"]
    )
    families = [bundle["family"] for bundle in bundles]
    project_dir = project_dir.resolve()
    data_dir = project_dir / ".dreamrsi"
    package_dir = data_dir / "packages" / document["author"] / document["name"]
    if len(bundles) == 1:
        bundle_paths = {families[0]: package_dir / "bundle.dreamrsi.json"}
    else:
        bundle_paths = {
            family: package_dir
            / "bundles"
            / f"{hashlib.sha256(family.encode('utf-8')).hexdigest()[:16]}.dreamrsi.json"
            for family in families
        }
    manifest_path = package_dir / "package.json"
    database_path = database or data_dir / "memory.sqlite3"

    with tempfile.TemporaryDirectory(prefix="dreamrsi-package-") as temporary_dir:
        staged_bundles = {}
        for index, bundle in enumerate(bundles):
            staged_bundle = Path(temporary_dir) / f"bundle-{index}.dreamrsi.json"
            staged_bundle.write_text(
                json.dumps(bundle, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                encoding="utf-8",
            )
            staged_bundles[bundle["family"]] = staged_bundle
        if not file_only:
            validator_store = InMemoryStore()
            validator = _memory(validator_store, namespace)
            try:
                for family in families:
                    await validator.import_bundle(staged_bundles[family], task=family)
            finally:
                await validator_store.close()

            database_path.parent.mkdir(parents=True, exist_ok=True)
            store = SQLiteStore(database_path)
            try:
                memory = _memory(store, namespace)
                # Check every family before writing any one of them, so a name clash
                # cannot leave a partially installed multi-family package.
                for family, bundle in zip(families, bundles, strict=True):
                    existing = await memory._entry(family)
                    if existing is not None and existing["versions"] and bundle["policies"]:
                        current = [version["sha256"] for version in existing["versions"]]
                        incoming = [version["sha256"] for version in bundle["policies"]]
                        if current != incoming or existing["active"] != bundle["active_policy"]:
                            raise ConfigurationError(
                                f"Task family {family!r} already has different policies; "
                                "import into a fresh policy-memory namespace"
                            )
                    await memory._worlds(family)
                for family in families:
                    await memory.import_bundle(staged_bundles[family], task=family)
            finally:
                await store.close()

    data_dir.mkdir(parents=True, exist_ok=True)
    if not file_only:
        _ensure_local_gitignore(data_dir)
    for family, bundle in zip(families, bundles, strict=True):
        _write_json_atomic(bundle_paths[family], bundle)
    metadata = {
        key: value for key, value in document.items() if key not in {"bundle", "bundles"}
    }
    metadata["repository"] = f"{document['author']}/{document['name']}"
    metadata["bundle_files"] = {
        family: str(path.relative_to(package_dir)) for family, path in bundle_paths.items()
    }
    _write_json_atomic(manifest_path, metadata)
    return {
        "repository": f"{document['author']}/{document['name']}",
        "family": families[0] if len(families) == 1 else None,
        "families": families,
        "path": str(bundle_paths[families[0]]) if len(families) == 1 else str(package_dir),
        "database": str(database_path),
        "policies": sum(len(bundle["policies"]) for bundle in bundles),
        "worlds": sum(len(bundle["worlds"]) for bundle in bundles),
        "imported": not file_only,
    }


async def save_local_bundle(
    name: str,
    family: str | list[str],
    *,
    project_dir: Path,
    database: Path | None = None,
    output: Path | None = None,
    namespace: str = "default",
) -> dict[str, Any]:
    """Export one or more saved families into a portable file for ``dreamrsi publish``."""
    if not is_package_slug(name):
        raise PackageError("Package name must be a lowercase hyphenated slug")
    families = [family] if isinstance(family, str) else family
    if not families or any(not isinstance(item, str) or not item for item in families):
        raise PackageError("Task family must not be empty")
    if len(set(families)) != len(families):
        raise PackageError("Do not repeat a task family")
    project_dir = project_dir.resolve()
    database_path = database or project_dir / ".dreamrsi" / "memory.sqlite3"
    if not database_path.is_file():
        raise PackageError(
            f"Policy memory database was not found at {database_path}; use --database "
            "or configure your app to share this SQLiteStore path"
        )
    target = output or project_dir / ".dreamrsi" / "packages" / "exports" / (
        f"{name}.dreamrsi.json"
    )
    if target.exists():
        raise PackageError(f"File already exists: {target}; choose another --output path")
    exported_bundles = []
    store = SQLiteStore(database_path)
    try:
        memory = _memory(store, namespace)
        with tempfile.TemporaryDirectory(prefix="dreamrsi-export-") as temporary_dir:
            for index, family_key in enumerate(families):
                bundle_path = Path(temporary_dir) / f"bundle-{index}.dreamrsi.json"
                await memory.export_bundle(family_key, bundle_path)
                exported_bundles.append(json.loads(bundle_path.read_text(encoding="utf-8")))
    except (ConfigurationError, PolicyError) as exc:
        raise PackageError(str(exc)) from exc
    finally:
        await store.close()

    if len(exported_bundles) == 1:
        bundle_document = exported_bundles[0]
        policy_count = len(bundle_document["policies"])
        world_count = len(bundle_document["worlds"])
        _write_json_atomic(target, bundle_document)
    else:
        collection = make_bundle_collection(exported_bundles)
        policy_count = sum(len(bundle["policies"]) for bundle in exported_bundles)
        world_count = sum(len(bundle["worlds"]) for bundle in exported_bundles)
        _write_json_atomic(target, collection)
    return {
        "path": str(target),
        "families": families,
        "policies": policy_count,
        "worlds": world_count,
    }


def _github_token() -> str:
    if shutil.which("gh") is None:
        raise PackageError(
            "Publishing needs GitHub CLI (gh). Install it from https://cli.github.com/, "
            "then run 'dreamrsi publish' again."
        )
    status = subprocess.run(
        ["gh", "auth", "status", "--hostname", "github.com"],
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        print("GitHub sign-in will open in your browser. Dream-RSI will not store your token.")
        login = subprocess.run(
            [
                "gh",
                "auth",
                "login",
                "--hostname",
                "github.com",
                "--web",
                "--git-protocol",
                "https",
            ],
            check=False,
        )
        if login.returncode != 0:
            raise PackageError("GitHub sign-in did not complete")
    token_result = subprocess.run(
        ["gh", "auth", "token", "--hostname", "github.com"],
        capture_output=True,
        text=True,
        check=False,
    )
    if token_result.returncode != 0 or not token_result.stdout.strip():
        raise PackageError("GitHub CLI is signed out; run 'gh auth login' and retry")
    return token_result.stdout.strip()


def _validate_bundle_file(path: Path) -> tuple[list[dict[str, Any]], int, int]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageError(f"Could not read policy bundle {path}: {exc}") from exc
    bundles = unpack_policy_bundles(document)
    with tempfile.TemporaryDirectory(prefix="dreamrsi-publish-check-") as temporary_dir:
        store = InMemoryStore()
        memory = _memory(store, "default")
        async def validate_all() -> None:
            for index, bundle in enumerate(bundles):
                staged = Path(temporary_dir) / f"bundle-{index}.dreamrsi.json"
                staged.write_text(
                    json.dumps(bundle, ensure_ascii=False, allow_nan=False), encoding="utf-8"
                )

                await memory.import_bundle(staged, task=bundle["family"])

        async def validate_and_close() -> None:
            try:
                await validate_all()
            finally:
                await store.close()

        try:
            asyncio.run(validate_and_close())
        except (ConfigurationError, PolicyError) as exc:
            raise PackageError(f"Bundle validation failed: {exc}") from exc
    return (
        bundles,
        sum(len(bundle["policies"]) for bundle in bundles),
        sum(len(bundle["worlds"]) for bundle in bundles),
    )


def _prompt_available_name(registry: GitHubPackageRegistry, owner: str) -> str:
    while True:
        name = input("Package name (lowercase, hyphens allowed): ").strip()
        if not name:
            continue
        if not re_slug(name):
            print("Use a lowercase slug such as 'my-search-policy'.")
            continue
        if registry.repository(owner, name) is not None:
            print(f"{owner}/{name} already exists. Choose another name.")
            continue
        return name


def re_slug(value: str) -> bool:
    return is_package_slug(value)


def _cmd_list(args: argparse.Namespace) -> int:
    packages = GitHubPackageRegistry().list(args.limit)
    if not packages:
        print(f"No public packages found yet (GitHub topic: {PACKAGE_TOPIC}).")
        return 0
    for index, package in enumerate(packages, 1):
        description = f" - {package.description}" if package.description else ""
        print(f"{index:>2}. {package.reference}  stars={package.stars}{description}")
    print("Popularity is GitHub stars. Install with: dreamrsi install OWNER/REPOSITORY")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    registry = GitHubPackageRegistry()
    owner, name = registry.resolve(args.package)
    document = registry.download(owner, name)
    result = asyncio.run(
        install_document(
            document,
            project_dir=Path.cwd(),
            database=args.database,
            namespace=args.namespace,
            file_only=args.file_only,
        )
    )
    family_label = ", ".join(result["families"])
    noun = "family" if len(result["families"]) == 1 else "families"
    print(f"Downloaded {result['repository']} for task {noun} {family_label}.")
    print(f"Package:  {result['path']}")
    if result["imported"]:
        print(f"Memory:   {result['database']}")
        print(
            f"Imported: {result['policies']} policy versions, "
            f"{result['worlds']} replay trees"
        )
        print("Use SQLiteStore with this same database path in AdaptivePolicyMemory.")
    else:
        print("Saved only; custom codecs or sandbox profiles were not imported.")
        print("Import the bundle from Python with your registered PolicyCodec.")
    return 0


def _cmd_save(args: argparse.Namespace) -> int:
    families = args.family
    database = args.database or (Path.cwd() / ".dreamrsi" / "memory.sqlite3")
    namespace = args.namespace
    if namespace == "auto":
        available = _saved_families_by_namespace(database)
        if len(available) != 1:
            if not available:
                raise PackageError(f"No saved policies or replay trees found in {database}")
            choices = "; ".join(
                f"{item}: {', '.join(families)}" for item, families in sorted(available.items())
            )
            raise PackageError(
                "More than one policy-memory namespace was found; choose one with --namespace. "
                f"Available: {choices}"
            )
        namespace = next(iter(available))
    if args.all_families:
        available = _saved_families_by_namespace(database)
        families = available.get(namespace, [])
        if not families:
            raise PackageError(
                f"No saved policies or replay trees found for namespace {namespace!r} "
                f"in {database}"
            )
    elif families is None:
        if not sys.stdin.isatty():
            raise PackageError("Pass --family or --all in a non-interactive shell")
        families = [input("Task family to export: ").strip()]
    if any(not family for family in families):
        raise PackageError("Task family must not be empty")
    result = asyncio.run(
        save_local_bundle(
            args.name,
            families,
            project_dir=Path.cwd(),
            database=database,
            output=args.output,
            namespace=namespace,
        )
    )
    print(
        f"Saved {result['policies']} policy versions and {result['worlds']} replay trees "
        f"across {len(result['families'])} task families: {', '.join(result['families'])}."
    )
    print(f"Package file: {result['path']}")
    print(f"Publish with: dreamrsi publish \"{result['path']}\"")
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    bundle_path = Path(args.path).expanduser().resolve()
    bundles, policy_count, world_count = _validate_bundle_file(bundle_path)
    token = _github_token()
    registry = GitHubPackageRegistry(GitHubAPI(token))
    user = registry.api.request("GET", "/user")
    owner = user.get("login") if isinstance(user, dict) else None
    if not isinstance(owner, str):
        raise PackageError("Could not determine the authenticated GitHub account")
    name = _prompt_available_name(registry, owner)
    description = input("Short public description (optional): ").strip()
    if len(description) > 350:
        raise PackageError("GitHub package descriptions are limited to 350 characters")
    document = package_document(
        owner=owner,
        name=name,
        description=description,
        bundle=bundles[0] if len(bundles) == 1 else None,
        bundles=bundles if len(bundles) > 1 else None,
    )
    print(
        f"Publishing PUBLIC repository {owner}/{name} with "
        f"{policy_count} policy versions and {world_count} replay trees across "
        f"{len(bundles)} task families."
    )
    print("The package file may contain prompts and task data; the repository will be public.")
    url = registry.publish(name, document)
    print(f"Published: {url}")
    print(f"Install with: dreamrsi install {owner}/{name}")
    print("GitHub may take a short time to include a newly tagged repository in search.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dreamrsi",
        description=(
            "Share Dream-RSI policies and replay trees through public GitHub repositories."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="List public packages by GitHub stars")
    list_parser.add_argument(
        "--limit", type=int, default=20, help="Show 1–100 packages (default 20)"
    )
    list_parser.set_defaults(handler=_cmd_list)

    install_parser = commands.add_parser("install", help="Install a package into this project")
    install_parser.add_argument("package", help="Package name or OWNER/REPOSITORY")
    install_parser.add_argument("--database", type=Path, help="Policy-memory SQLite path")
    install_parser.add_argument("--namespace", default="default", help="Policy-memory namespace")
    install_parser.add_argument(
        "--file-only",
        action="store_true",
        help="Save the bundle without importing it (for custom codecs/sandboxes)",
    )
    install_parser.set_defaults(handler=_cmd_install)

    save_parser = commands.add_parser("save", help="Save local policy versions and replay trees")
    save_parser.add_argument("name", help="Local package slug, e.g. labs-search")
    families = save_parser.add_mutually_exclusive_group()
    families.add_argument(
        "--family",
        action="append",
        help="Task-family key (repeat to combine multiple families)",
    )
    families.add_argument(
        "--all",
        "--all-families",
        dest="all_families",
        action="store_true",
        help="Save every family found in the selected policy-memory namespace",
    )
    save_parser.add_argument("-d", "--database", type=Path, help="Policy-memory SQLite path")
    save_parser.add_argument("--output", type=Path, help="Bundle output path")
    save_parser.add_argument(
        "-n",
        "--namespace",
        default="default",
        help="Policy-memory namespace; use 'auto' when the database contains exactly one",
    )
    save_parser.set_defaults(handler=_cmd_save)

    publish_parser = commands.add_parser(
        "publish", help="Publish a bundle as a public GitHub repo"
    )
    publish_parser.add_argument("path", help="Path to a .dreamrsi.json bundle")
    publish_parser.set_defaults(handler=_cmd_publish)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Legacy Windows consoles cannot encode every public package description.
    # Preserve their encoding and escape unsupported characters instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="backslashreplace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (PackageError, ConfigurationError, PolicyError, OSError, sqlite3.Error) as exc:
        print(f"dreamrsi: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("dreamrsi: cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
