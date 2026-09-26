"""GitHub-hosted package discovery and transfer for Dream-RSI bundles."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

GITHUB_API = "https://api.github.com"
PACKAGE_TOPIC = "dreamrsi-package"
PACKAGE_FILE = "dreamrsi-package.json"
PACKAGE_FORMAT = "dreamrsi.github-package"
PACKAGE_SCHEMA_VERSION = 2
LEGACY_PACKAGE_SCHEMA_VERSION = 1
BUNDLE_COLLECTION_FORMAT = "dreamrsi.policy-bundle-collection"
BUNDLE_COLLECTION_SCHEMA_VERSION = 1
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?$")


def is_package_slug(value: str) -> bool:
    return bool(_SLUG_RE.fullmatch(value))


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def verify_bundle_checksum(bundle: Any) -> dict[str, Any]:
    """Check the portable bundle envelope without decoding or executing policies."""
    if not isinstance(bundle, dict):
        raise PackageError("Policy bundle must be a JSON object")
    checksum = bundle.get("sha256")
    payload = {key: value for key, value in bundle.items() if key != "sha256"}
    try:
        actual = _canonical_sha256(payload)
    except (TypeError, ValueError) as exc:
        raise PackageError("Policy bundle contains invalid JSON values") from exc
    if not isinstance(checksum, str) or actual != checksum:
        raise PackageError("Policy bundle checksum failed")
    if (
        bundle.get("format") != "dreamrsi.policy-bundle"
        or bundle.get("schema_version") != 1
        or not isinstance(bundle.get("family"), str)
        or not isinstance(bundle.get("policies"), list)
        or not isinstance(bundle.get("worlds"), list)
    ):
        raise PackageError("Unsupported or incomplete Dream-RSI bundle")
    return bundle


def make_bundle_collection(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap multiple family bundles in one checksummed portable file."""
    if not isinstance(bundles, list) or len(bundles) < 2:
        raise PackageError("A bundle collection must contain at least two task families")
    families: set[str] = set()
    for bundle in bundles:
        verify_bundle_checksum(bundle)
        family = bundle["family"]
        if family in families:
            raise PackageError(f"Bundle collection repeats task family {family!r}")
        families.add(family)
    payload = {
        "format": BUNDLE_COLLECTION_FORMAT,
        "schema_version": BUNDLE_COLLECTION_SCHEMA_VERSION,
        "bundles": bundles,
    }
    return {**payload, "sha256": _canonical_sha256(payload)}


def unpack_policy_bundles(document: Any) -> list[dict[str, Any]]:
    """Validate and return one or more portable family bundles."""
    if isinstance(document, dict) and document.get("format") == "dreamrsi.policy-bundle":
        return [verify_bundle_checksum(document)]
    if not isinstance(document, dict):
        raise PackageError("Policy bundle file must be a JSON object")
    payload = {key: value for key, value in document.items() if key != "sha256"}
    try:
        actual = _canonical_sha256(payload)
    except (TypeError, ValueError) as exc:
        raise PackageError("Bundle collection contains invalid JSON values") from exc
    if (
        document.get("format") != BUNDLE_COLLECTION_FORMAT
        or document.get("schema_version") != BUNDLE_COLLECTION_SCHEMA_VERSION
        or document.get("sha256") != actual
        or not isinstance(document.get("bundles"), list)
        or len(document["bundles"]) < 2
    ):
        raise PackageError("Unsupported or incomplete Dream-RSI bundle collection")
    bundles = [verify_bundle_checksum(bundle) for bundle in document["bundles"]]
    families = [bundle["family"] for bundle in bundles]
    if len(set(families)) != len(families):
        raise PackageError("Bundle collection repeats a task family")
    return bundles


class PackageError(RuntimeError):
    """A package, GitHub API, or local package operation failed."""


class GitHubAPIError(PackageError):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"GitHub API returned HTTP {status}: {message}")


@dataclass(frozen=True)
class PackageListing:
    owner: str
    name: str
    description: str
    stars: int
    url: str

    @property
    def reference(self) -> str:
        return f"{self.owner}/{self.name}"


class GitHubAPI:
    """Small stdlib-only GitHub REST client; tokens are never persisted here."""

    def __init__(self, token: str | None = None, timeout: float = 20) -> None:
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict | None = None) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub API paths must start with '/'")
        body = None
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "dreamrsi-sdk",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(f"{GITHUB_API}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("message", exc.reason)
            except (UnicodeError, json.JSONDecodeError, AttributeError):
                detail = exc.reason
            raise GitHubAPIError(exc.code, str(detail)) from exc
        except (URLError, OSError) as exc:
            raise PackageError(f"Could not reach GitHub: {getattr(exc, 'reason', exc)}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise PackageError("GitHub returned an invalid JSON response") from exc

    def raw_file(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "github.com",
            "raw.githubusercontent.com",
        }:
            raise PackageError("GitHub returned an unexpected package download URL")
        request = Request(url, headers={"User-Agent": "dreamrsi-sdk"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except (HTTPError, URLError, OSError) as exc:
            raise PackageError(f"Could not download the package file from GitHub: {exc}") from exc

    def upload_asset(self, upload_url: str, name: str, content: bytes) -> Any:
        upload_url = upload_url.split("{", 1)[0]
        parsed = urlparse(upload_url)
        if parsed.scheme != "https" or parsed.hostname != "uploads.github.com":
            raise PackageError("GitHub returned an unexpected release-asset upload URL")
        separator = "&" if parsed.query else "?"
        upload_url = f"{upload_url}{separator}{urlencode({'name': name})}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/octet-stream",
            "User-Agent": "dreamrsi-sdk",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(upload_url, data=content, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("message", exc.reason)
            except (UnicodeError, json.JSONDecodeError, AttributeError):
                detail = exc.reason
            raise GitHubAPIError(exc.code, str(detail)) from exc
        except (URLError, OSError) as exc:
            raise PackageError(f"Could not upload the GitHub release asset: {exc}") from exc
        try:
            return json.loads(raw) if raw else {}
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise PackageError("GitHub returned an invalid release-asset response") from exc


class GitHubPackageRegistry:
    """Discover, fetch, and publish package repositories tagged with one topic."""

    def __init__(self, api: GitHubAPI | None = None) -> None:
        self.api = api or GitHubAPI()

    def list(self, limit: int = 20) -> list[PackageListing]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise PackageError("Package list limit must be between 1 and 100")
        query = urlencode(
            {
                "q": f"topic:{PACKAGE_TOPIC}",
                "sort": "stars",
                "order": "desc",
                "per_page": "100",
            }
        )
        result = self.api.request("GET", f"/search/repositories?{query}")
        items = result.get("items") if isinstance(result, dict) else None
        if not isinstance(items, list):
            raise PackageError("GitHub returned an invalid package search result")
        packages = [
            PackageListing(
                owner=item["owner"]["login"],
                name=item["name"],
                description=item.get("description") or "",
                stars=int(item.get("stargazers_count", 0)),
                url=item["html_url"],
            )
            for item in items
            if isinstance(item, dict)
            and isinstance(item.get("owner"), dict)
            and isinstance(item.get("owner", {}).get("login"), str)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("html_url"), str)
        ]
        packages.sort(key=lambda package: (-package.stars, package.reference.casefold()))
        return packages[:limit]

    @staticmethod
    def split_reference(reference: str) -> tuple[str | None, str]:
        value = reference.strip()
        if value.count("/") > 1:
            raise PackageError("Use a package name or GitHub reference OWNER/REPOSITORY")
        if "/" in value:
            owner, name = value.split("/", 1)
            if (
                not _OWNER_RE.fullmatch(owner)
                or not _REPO_RE.fullmatch(name)
                or name in (".", "..")
            ):
                raise PackageError("Invalid GitHub package reference")
            return owner, name
        if not _REPO_RE.fullmatch(value):
            raise PackageError("Invalid package name")
        return None, value

    def resolve(self, reference: str) -> tuple[str, str]:
        owner, name = self.split_reference(reference)
        if owner is not None:
            return owner, name
        query = urlencode(
            {
                "q": f"topic:{PACKAGE_TOPIC} {name} in:name",
                "sort": "stars",
                "order": "desc",
                "per_page": "100",
            }
        )
        result = self.api.request("GET", f"/search/repositories?{query}")
        items = result.get("items") if isinstance(result, dict) else None
        matches = [
            item
            for item in (items if isinstance(items, list) else [])
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item["name"].casefold() == name.casefold()
            and isinstance(item.get("owner"), dict)
            and isinstance(item["owner"].get("login"), str)
        ]
        if not matches:
            raise PackageError(f"No published Dream-RSI package named {name!r} was found")
        if len(matches) > 1:
            choices = ", ".join(
                f"{item['owner']['login']}/{item['name']}" for item in matches[:8]
            )
            raise PackageError(f"Package name is ambiguous; install one of: {choices}")
        return matches[0]["owner"]["login"], matches[0]["name"]

    def download(self, owner: str, name: str) -> dict[str, Any]:
        parsed_owner, name = self.split_reference(f"{owner}/{name}")
        if parsed_owner is None:
            raise PackageError("A GitHub package owner is required")
        owner = parsed_owner
        repo_path = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
        try:
            release = self.api.request("GET", f"{repo_path}/releases/latest")
        except GitHubAPIError as exc:
            if exc.status == 404:
                raise PackageError(
                    f"{owner}/{name} has no published Dream-RSI package release"
                ) from exc
            raise
        assets = release.get("assets") if isinstance(release, dict) else None
        asset = next(
            (
                item
                for item in (assets if isinstance(assets, list) else [])
                if isinstance(item, dict) and item.get("name") == PACKAGE_FILE
            ),
            None,
        )
        if not isinstance(asset, dict) or not isinstance(asset.get("browser_download_url"), str):
            raise PackageError(f"{owner}/{name}'s latest release has no {PACKAGE_FILE} asset")
        raw = self.api.raw_file(asset["browser_download_url"])
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise PackageError("Package repository contains invalid JSON") from exc
        validate_package_document(document, owner=owner, name=name)
        return document

    def repository(self, owner: str, name: str) -> dict | None:
        parsed_owner, name = self.split_reference(f"{owner}/{name}")
        if parsed_owner is None:
            raise PackageError("A GitHub package owner is required")
        owner = parsed_owner
        try:
            value = self.api.request(
                "GET", f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
            )
        except GitHubAPIError as exc:
            if exc.status == 404:
                return None
            raise
        return value if isinstance(value, dict) else None

    def publish(self, name: str, document: dict[str, Any]) -> str:
        if not is_package_slug(name):
            raise PackageError("Package repository name must be a lowercase hyphenated slug")
        user = self.api.request("GET", "/user")
        owner = user.get("login") if isinstance(user, dict) else None
        if not isinstance(owner, str) or not _OWNER_RE.fullmatch(owner):
            raise PackageError("Could not determine the authenticated GitHub account")
        if self.repository(owner, name) is not None:
            raise PackageError(f"Repository {owner}/{name} already exists")
        validate_package_document(document, owner=owner, name=name)
        repo = self.api.request(
            "POST",
            "/user/repos",
            {
                "name": name,
                "description": document.get("description", "Dream-RSI policy bundle"),
                "private": False,
                "auto_init": True,
            },
        )
        url = repo.get("html_url") if isinstance(repo, dict) else None
        if not isinstance(url, str):
            raise PackageError("GitHub created a repository but returned no repository URL")
        try:
            package_bytes = json.dumps(
                document, ensure_ascii=False, indent=2, allow_nan=False
            ).encode("utf-8")
            if len(package_bytes) >= 2 * 1024**3:
                raise PackageError("GitHub release assets must be smaller than 2 GiB")
            release = self.api.request(
                "POST",
                f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/releases",
                {
                    "tag_name": f"v{document['version']}",
                    "name": f"Dream-RSI package v{document['version']}",
                    "body": "Dream-RSI policy and replay package.",
                    "draft": False,
                    "prerelease": False,
                },
            )
            upload_url = release.get("upload_url") if isinstance(release, dict) else None
            if not isinstance(upload_url, str):
                raise PackageError("GitHub created a release but returned no asset upload URL")
            self.api.upload_asset(upload_url, PACKAGE_FILE, package_bytes)
            self.api.request(
                "PUT",
                f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/topics",
                {"names": ["dreamrsi", PACKAGE_TOPIC]},
            )
        except PackageError as exc:
            raise PackageError(
                f"Repository {url} was created, but package publishing did not finish: {exc}"
            ) from exc
        return url


def validate_package_document(
    document: Any, *, owner: str | None = None, name: str | None = None
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise PackageError("Dream-RSI package manifest must be a JSON object")
    if document.get("format") != PACKAGE_FORMAT:
        raise PackageError("Unsupported Dream-RSI GitHub package format")
    package_name = document.get("name")
    author = document.get("author")
    schema_version = document.get("schema_version")
    if not isinstance(package_name, str) or not is_package_slug(package_name):
        raise PackageError("Package manifest has an invalid name")
    version = document.get("version")
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise PackageError("Package manifest has an invalid version")
    if not isinstance(author, str) or not _OWNER_RE.fullmatch(author):
        raise PackageError("Package manifest has an invalid GitHub author")
    if schema_version == LEGACY_PACKAGE_SCHEMA_VERSION:
        family = document.get("family")
        bundle = document.get("bundle")
        if not isinstance(family, str) or not family:
            raise PackageError("Package manifest has an invalid task family")
        if not isinstance(bundle, dict) or bundle.get("family") != family:
            raise PackageError("Package manifest family does not match its policy bundle")
        verify_bundle_checksum(bundle)
    elif schema_version == PACKAGE_SCHEMA_VERSION:
        bundles = document.get("bundles")
        families = document.get("families")
        if not isinstance(bundles, list) or len(bundles) < 2:
            raise PackageError("Multi-family package must contain at least two bundles")
        if not isinstance(families, list) or len(families) != len(bundles):
            raise PackageError("Package family list does not match its bundles")
        for bundle in bundles:
            verify_bundle_checksum(bundle)
        bundle_families = [bundle["family"] for bundle in bundles]
        if families != bundle_families or len(set(bundle_families)) != len(bundle_families):
            raise PackageError("Package family list is invalid or contains duplicates")
    else:
        raise PackageError("Unsupported Dream-RSI GitHub package schema version")
    description = document.get("description", "")
    if not isinstance(description, str) or len(description) > 350:
        raise PackageError("Package description must be a string of at most 350 characters")
    if owner is not None and author.casefold() != owner.casefold():
        raise PackageError("Package author does not match the GitHub repository owner")
    if name is not None and package_name.casefold() != name.casefold():
        raise PackageError("Package name does not match the GitHub repository name")
    return document


def package_document(
    *,
    owner: str,
    name: str,
    description: str,
    bundle: dict[str, Any] | None = None,
    bundles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    common = {
        "format": PACKAGE_FORMAT,
        "name": name,
        "version": "0.1.0",
        "author": owner,
        "description": description,
    }
    if bundles is not None:
        if len(bundles) < 2:
            raise PackageError("Pass one bundle or at least two bundles")
        for item in bundles:
            verify_bundle_checksum(item)
        families = [item["family"] for item in bundles]
        if len(set(families)) != len(families):
            raise PackageError("Package cannot repeat a task family")
        document = {
            **common,
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "families": families,
            "bundles": bundles,
        }
    elif bundle is not None:
        verify_bundle_checksum(bundle)
        document = {
            **common,
            "schema_version": LEGACY_PACKAGE_SCHEMA_VERSION,
            "family": bundle.get("family"),
            "bundle": bundle,
        }
    else:
        raise PackageError("Pass a policy bundle or multiple family bundles")
    return validate_package_document(document, owner=owner, name=name)
