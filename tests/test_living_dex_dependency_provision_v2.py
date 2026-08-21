from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pokemon_red_completion import living_dex_dependency_provision_v2 as provision
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
    ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT,
    ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT,
    require_fresh_development_opening_set_v2,
)
from pokemon_red_completion.private_artifacts import initialize_private_root


def _store(tmp_path: Path):
    repository = tmp_path / "repository"
    private = tmp_path / "private"
    repository.mkdir()
    private.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == private.resolve() else 1

    return initialize_private_root(
        private,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda path: False,
    )


def test_generator_uses_full_domain_and_csprng_nonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span = (
        ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT
        - ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT
        + 1
    )
    values = iter((0, 0, span - 1, span - 1))
    counter = 0

    def token_hex(byte_count: int) -> str:
        nonlocal counter
        counter += 1
        return hashlib.sha256(f"token-{counter}".encode("ascii")).hexdigest()[: byte_count * 2]

    monkeypatch.setattr(provision.secrets, "randbelow", lambda limit: next(values))
    monkeypatch.setattr(provision.secrets, "token_hex", token_hex)

    openings = provision.generate_v2_development_openings()

    require_fresh_development_opening_set_v2(openings)
    structures = {row.structure for row in openings}
    assert {row.required_precursor_count for row in structures} == {
        ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT,
        ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT,
    }
    assert {row.required_evolved_count for row in structures} == {
        ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT,
        ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT,
    }
    assert all(len(row.nonce) == 64 for row in openings)
    assert len({row.nonce for row in openings}) == 4
    assert all(row.nonce in row.canonical_private_bytes().decode("ascii") for row in openings)


def test_provision_publishes_real_manifests_and_resumes_same_plan(tmp_path: Path) -> None:
    store = _store(tmp_path)

    first = provision.provision_v2_development_commitments(store)
    second = provision.provision_v2_development_commitments(store)

    assert second == first
    assert len(first.openings) == len(first.roster.rows) == 4
    for opening, commitment in zip(first.openings, first.roster.rows, strict=True):
        metadata = store.inspect_sealed_record_metadata(
            opening.scenario_id,
            expected_kind=ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
        )
        assert metadata is not None
        assert commitment.manifest_sha256 == metadata.manifest_sha256
        assert commitment.declared_record_sha256 == metadata.declared_record_sha256
        assert commitment.declared_total_bytes == metadata.declared_total_bytes
        assert metadata.public_dict()["payload_opened"] is False


def test_resume_never_calls_generator_or_replaces_openings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    first = provision.provision_v2_development_commitments(store)

    def forbidden_generator():
        raise AssertionError("resume attempted to substitute fresh openings")

    monkeypatch.setattr(provision, "generate_v2_development_openings", forbidden_generator)
    resumed = provision.provision_v2_development_commitments(store)

    assert resumed == first


def test_strict_opening_parser_rejects_outcome_injection() -> None:
    opening = provision.generate_v2_development_openings()[0]
    document = opening.private_dict()
    document["reward"] = 1

    with pytest.raises(provision.LivingDexDependencyProvisionV2Error, match="fields differ"):
        provision.parse_v2_development_opening(document)
