from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_setup_identity import (
    RedLivingDexSetupIdentityError,
    compose_red_living_dex_setup_execution_identity,
    red_living_dex_provider_registry_sha256,
)
from pokemon_red_completion.runtime_identity import RuntimeFileIdentity, RuntimeIdentity


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _runtime(*, file_sha256: str = "b" * 64) -> RuntimeIdentity:
    files = (
        RuntimeFileIdentity(
            name="pyboy/__init__.py",
            size=17,
            sha256=file_sha256,
        ),
    )
    inventory = {
        "schema": "python-distribution-file-inventory-v1",
        "distribution_name": "pyboy",
        "distribution_version": "2.6.0",
        "files": [file.public_dict() for file in files],
    }
    inventory_sha256 = hashlib.sha256(
        (
            json.dumps(
                inventory,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii")
    ).hexdigest()
    return RuntimeIdentity(
        python_implementation="CPython",
        python_version="3.14.3",
        python_executable_sha256="a" * 64,
        pyboy_distribution_name="pyboy",
        pyboy_distribution_version="2.6.0",
        pyboy_files=files,
        pyboy_inventory_sha256=inventory_sha256,
    )


def _identity(*, runtime: RuntimeIdentity | None = None):
    return compose_red_living_dex_setup_execution_identity(
        source_commit="1" * 40,
        source_bundle_sha256=_sha("source"),
        route_registry_sha256=_sha("routes"),
        runtime_identity=_runtime() if runtime is None else runtime,
    )


def test_composer_binds_exact_red_and_remains_path_free() -> None:
    identity = _identity()

    assert identity == _identity()
    assert identity.game_id == "pokemon-red"
    assert identity.rom_sha1 == POKEMON_RED_US_REV_0.sha1
    assert identity.rom_sha256 == POKEMON_RED_US_REV_0.sha256
    assert identity.source_published is True
    assert identity.worktree_dirty is False
    encoded = json.dumps(identity.private_dict(), sort_keys=True)
    assert "/" not in encoded
    assert "\\" not in encoded


def test_runtime_change_rebinds_runtime_dependent_components_only() -> None:
    before = _identity()
    after = _identity(runtime=_runtime(file_sha256="c" * 64))

    assert after.adapter_version_sha256 != before.adapter_version_sha256
    assert after.state_schema_sha256 != before.state_schema_sha256
    assert after.runtime_contract_sha256 != before.runtime_contract_sha256
    assert after.observation_schema_sha256 == before.observation_schema_sha256
    assert after.provider_registry_sha256 == before.provider_registry_sha256
    assert after.route_registry_sha256 == before.route_registry_sha256


def test_provider_registry_covers_the_mechanics_derived_curriculum() -> None:
    digest = red_living_dex_provider_registry_sha256()

    assert digest == red_living_dex_provider_registry_sha256()
    assert len(digest) == 64


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_commit", "1" * 39),
        ("source_bundle_sha256", "g" * 64),
        ("route_registry_sha256", "2" * 63),
    ),
)
def test_composer_rejects_malformed_source_bindings(field: str, value: str) -> None:
    arguments = {
        "source_commit": "1" * 40,
        "source_bundle_sha256": _sha("source"),
        "route_registry_sha256": _sha("routes"),
        "runtime_identity": _runtime(),
    }
    arguments[field] = value

    with pytest.raises(RedLivingDexSetupIdentityError):
        compose_red_living_dex_setup_execution_identity(**arguments)  # type: ignore[arg-type]


def test_composer_rejects_malformed_runtime_identity() -> None:
    malformed = replace(_runtime(), pyboy_inventory_sha256="0" * 64)

    with pytest.raises(RedLivingDexSetupIdentityError, match="runtime differs"):
        _identity(runtime=malformed)


def test_composer_requires_concrete_runtime_type() -> None:
    with pytest.raises(TypeError, match="RuntimeIdentity"):
        compose_red_living_dex_setup_execution_identity(
            source_commit="1" * 40,
            source_bundle_sha256=_sha("source"),
            route_registry_sha256=_sha("routes"),
            runtime_identity=object(),  # type: ignore[arg-type]
        )
