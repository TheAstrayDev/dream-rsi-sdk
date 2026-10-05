import ast
from dataclasses import replace

import pytest

from dreamrsi import (
    PolicyArtifact,
    PolicyCodec,
    PolicySandbox,
    ProcessPolicySandbox,
    SandboxConfig,
)
from dreamrsi.artifacts import SourcePolicy
from dreamrsi.errors import SandboxError
from dreamrsi.models.policy import PolicyView

VIEW = PolicyView([], None, 0, 0, 0, 0)
STOP = 'def decide(view):\n    return {"expand": [], "stop": True}'


@pytest.mark.parametrize("name", ["small", "balanced", "large"])
def test_presets_keep_supported_language_and_roundtrip(name, tmp_path):
    config = SandboxConfig.preset(name)
    assert config.allow_math and config.allow_helpers and config.allow_methods
    assert config.allow_comprehensions and config.allowed_builtins is None
    path = config.save(tmp_path / "sandbox.json")
    assert path.is_absolute()
    assert SandboxConfig.from_json(config.to_json()) == SandboxConfig.load(path) == config
    assert PolicySandbox.from_file(path).config == config
    assert ProcessPolicySandbox.from_file(path).config == config
    with pytest.raises(FileExistsError):
        config.save(path)
    with pytest.raises(ValueError, match="overwrite"):
        config.save(path, overwrite="false")
    updated = replace(config, max_steps=config.max_steps + 1)
    updated.save(path, overwrite=True)
    assert SandboxConfig.load(path) == updated


def test_presets_and_file_constructors_allow_explicit_overrides(tmp_path):
    assert SandboxConfig.preset("balanced") == SandboxConfig()
    large = PolicySandbox.from_preset("large", max_steps=42, cache_size=0)
    assert large.config.max_steps == 42
    assert large.config.max_units > SandboxConfig().max_units
    path = large.config.save(tmp_path / "sandbox.json")
    restored = ProcessPolicySandbox.from_file(path, max_steps=100, cache_size=2)
    assert restored.config.max_steps == 100
    assert restored.cache_info()["capacity"] == 2


@pytest.mark.parametrize("text", ['[]', 'null', '{"open": true}', '{"max_steps": 0}'])
def test_invalid_json_profiles_fail_before_execution(text):
    with pytest.raises(ValueError):
        SandboxConfig.from_json(text)


def test_unknown_presets_and_invalid_cache_limits_are_rejected():
    with pytest.raises(ValueError, match="preset"):
        SandboxConfig.preset("unrestricted")
    for value in (-1, True, 1.5, "16"):
        with pytest.raises(ValueError, match="cache_size"):
            PolicySandbox(cache_size=value)


async def test_cache_skips_only_repeated_parsing_and_never_leaks_execution_state(monkeypatch):
    sandbox = PolicySandbox(cache_size=2)
    parse = sandbox.parse
    parses = []

    def count(source):
        parses.append(source)
        return parse(source)

    monkeypatch.setattr(sandbox, "parse", count)
    source = '''memory = [0]
def decide(view):
    memory.append(1)
    view["observations"]["state"].append(2)
    return {"expand": [str(len(memory)), str(len(view["observations"]["state"]))]}
'''
    view = PolicyView([], None, 0, 0, 0, 0, observations={"state": [0]})
    sandbox.validate(source)
    for _ in range(4):
        assert (await sandbox.execute(source, view)).expand == ["2", "2"]
    assert parses == [source]
    assert view.observations == {"state": [0]}
    assert sandbox.cache_info() == {"capacity": 2, "entries": 1, "hits": 4, "misses": 1}


async def test_public_parse_cannot_mutate_private_cached_program():
    sandbox = PolicySandbox()
    digest = sandbox.validate(STOP)
    exposed_tree = sandbox.parse(STOP)
    for node in ast.walk(exposed_tree):
        if isinstance(node, ast.Constant) and node.value is True:
            node.value = False
    assert (await sandbox.execute(STOP, VIEW)).stop is True
    assert sandbox.validate(STOP) == digest


async def test_lru_is_bounded_and_clear_or_disable_force_fresh_validation(monkeypatch):
    sandbox = PolicySandbox(cache_size=2)
    parse = sandbox.parse
    parses = []

    def count(source):
        parses.append(source)
        return parse(source)

    monkeypatch.setattr(sandbox, "parse", count)
    sources = [STOP + f"\n# policy {i}" for i in range(3)]
    for index in (0, 1, 0, 2, 1):
        await sandbox.execute(sources[index], VIEW)
    assert parses == [sources[i] for i in (0, 1, 2, 1)]
    assert sandbox.cache_info()["entries"] == 2
    sandbox.clear_cache()
    assert sandbox.cache_info() == {"capacity": 2, "entries": 0, "hits": 0, "misses": 0}
    await sandbox.execute(STOP, VIEW)
    assert len(parses) == 5
    disabled = PolicySandbox(cache_size=0)
    await disabled.execute(STOP, VIEW)
    await disabled.execute(STOP, VIEW)
    assert disabled.cache_info() == {"capacity": 0, "entries": 0, "hits": 0, "misses": 2}


async def test_profile_changes_and_invalid_sources_do_not_reuse_stale_validation():
    sandbox = PolicySandbox()
    sandbox.validate(STOP)
    sandbox.config = replace(sandbox.config, max_ast_nodes=1)
    with pytest.raises(SandboxError, match="AST node"):
        await sandbox.execute(STOP, VIEW)
    assert sandbox.cache_info()["entries"] == 1
    fresh = PolicySandbox()
    for _ in range(2):
        with pytest.raises(SandboxError):
            await fresh.execute("import os\n" + STOP, VIEW)
    assert fresh.cache_info()["entries"] == 0


async def test_warm_cache_does_not_bypass_steps_or_language_restrictions():
    sandbox = PolicySandbox(max_steps=50)
    source = "def decide(view):\n    while True:\n        pass"
    sandbox.validate(source)
    for _ in range(2):
        with pytest.raises(SandboxError, match="operation/time"):
            await sandbox.execute(source, VIEW)
    assert sandbox.cache_info()["hits"] == 2
    restricted = PolicySandbox.from_preset("large", allowed_builtins=())
    bad = 'def decide(view):\n    return {"expand": [str(1)]}'
    restricted.validate(bad)
    with pytest.raises(SandboxError, match="Builtin disabled"):
        await restricted.execute(bad, VIEW)


async def test_cache_settings_do_not_change_portable_policy_capabilities():
    cached = PolicySandbox(cache_size=4)
    uncached = PolicySandbox(cache_size=0)
    assert cached.capabilities() == uncached.capabilities()
    encoded = PolicyCodec(cached).encode(SourcePolicy(PolicyArtifact(STOP), cached))
    restored = PolicyCodec(uncached).decode(encoded)
    assert (await restored.decide(VIEW)).stop


async def test_named_process_profile_retains_killable_worker_semantics():
    worker = ProcessPolicySandbox.from_preset("small", max_steps=1000)
    assert worker.capabilities()["execution"] == "fresh_process"
    assert await worker.execute(STOP, VIEW) == await PolicySandbox.from_preset("small").execute(
        STOP, VIEW
    )
    assert worker.cache_info()["entries"] == 0
