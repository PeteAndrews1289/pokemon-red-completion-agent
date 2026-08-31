from __future__ import annotations

import multiprocessing
import os
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion import claim_first_admission as admission
from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAdmissionError,
    ClaimFirstExecutionIdentity,
    ClaimFirstRootPair,
    claim_first_availability_snapshot_lease,
    claim_first_pair_registry,
    parse_claim_first_availability_snapshot,
    read_root_pair_claim,
    root_pair_claims,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    FreshCompositionQualificationError,
    fixed_account_claim_registry_lease,
    root_claim_is_available,
    write_root_claim,
)
from pokemon_red_completion.provenance import canonical_sha256


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _registry(tmp_path: Path) -> Path:
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    registry.chmod(0o700)
    return registry


def _claim(
    label: str,
    *,
    logical: str | None = None,
    physical: str | None = None,
) -> ClaimFirstRootPair:
    return ClaimFirstRootPair(
        logical_root_sha256=_sha((label, "logical")) if logical is None else logical,
        physical_root_sha256=_sha((label, "physical")) if physical is None else physical,
        stage="setup-capture",
        execution_identity_sha256=_sha((label, "execution")),
        plan_sha256=_sha((label, "plan")),
        slot_sha256=_sha((label, "slot")),
        runner_sha256=_sha((label, "runner")),
        source_commit="a" * 40,
    )


def _execution_identity(label: str = "identity") -> ClaimFirstExecutionIdentity:
    return ClaimFirstExecutionIdentity(
        source_commit="c" * 40,
        source_bundle_sha256=_sha((label, "source")),
        exact_ci_run=1234,
        exact_ci_attempt=1,
        producer_execution_identity_sha256=_sha((label, "producer-execution")),
        producer_plan_sha256=_sha((label, "producer-plan")),
        producer_private_plan_sha256=_sha((label, "private-plan")),
        producer_manifest_sha256=_sha((label, "manifest")),
        slot_sha256=_sha((label, "slot")),
        recipe_sha256=_sha((label, "recipe")),
        logical_root_sha256=_sha((label, "logical")),
        physical_root_sha256=_sha((label, "physical")),
        title_adapter_sha256=_sha((label, "adapter")),
        runtime_factory_sha256=_sha((label, "factory")),
        runner_sha256=_sha((label, "runner")),
    )


def _race_claim(
    registry: str,
    claim: ClaimFirstRootPair,
    start: multiprocessing.synchronize.Event,
    results: multiprocessing.queues.Queue,
) -> None:
    start.wait()
    try:
        with claim_first_pair_registry(Path(registry)) as transaction:
            transaction.claim(claim)
    except BaseException as error:
        results.put(("failed", type(error).__name__))
    else:
        results.put(("claimed", claim.claim_sha256))


def _race_legacy_claim(
    registry: str,
    root_sha256: str,
    start: multiprocessing.synchronize.Event,
    results: multiprocessing.queues.Queue,
) -> None:
    start.wait()
    path = Path(registry)
    try:
        # Historical controller-capable entrypoints share this account lease
        # with the pair ledger.  Holding it across availability and publication
        # is what makes the two on-disk formats one exclusion domain.
        with fixed_account_claim_registry_lease(path, exclusive=True):
            write_root_claim(
                path,
                root_consumption_sha256=root_sha256,
                execution_identity_sha256=_sha("legacy-race-execution"),
                source_commit="b" * 40,
                runner_sha256=_sha("legacy-race-runner"),
            )
    except BaseException as error:
        results.put(("failed", type(error).__name__))
    else:
        results.put(("claimed", root_sha256))


def test_pair_claim_round_trips_once_and_blocks_every_identity_overlap(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    first = _claim("first")
    with claim_first_pair_registry(registry) as transaction:
        assert transaction.available(
            first.logical_root_sha256,
            first.physical_root_sha256,
        )
        assert transaction.claim(first) == first

    assert read_root_pair_claim(registry, first.claim_sha256) == first
    assert root_pair_claims(registry) == (first,)
    for candidate in (
        first,
        _claim("logical-overlap", logical=first.logical_root_sha256),
        _claim("physical-overlap", physical=first.physical_root_sha256),
        _claim("cross-overlap", logical=first.physical_root_sha256),
    ):
        with claim_first_pair_registry(registry) as transaction:
            assert not transaction.available(
                candidate.logical_root_sha256,
                candidate.physical_root_sha256,
            )
            with pytest.raises(ClaimFirstAdmissionError, match="already consumed"):
                transaction.claim(candidate)


def test_shared_snapshot_binds_the_relevant_ledger_and_sorted_availability(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    first = _claim("snapshot-first")
    second = _claim("snapshot-second")

    with claim_first_availability_snapshot_lease(registry) as lease:
        empty = lease.observe(
            (
                (second.logical_root_sha256, second.physical_root_sha256),
                (first.logical_root_sha256, first.physical_root_sha256),
            )
        )

    assert tuple(item.identity_sha256 for item in empty.observations) == tuple(
        item.identity_sha256
        for item in sorted(
            empty.observations,
            key=lambda item: (
                item.logical_root_sha256,
                item.physical_root_sha256,
            ),
        )
    )
    assert all(item.available for item in empty.observations)
    assert empty.public_dict()["root_claims_created"] == 0
    assert empty.public_dict()["private_path_fields"] == 0
    assert parse_claim_first_availability_snapshot(empty.canonical_bytes()) == empty

    with claim_first_pair_registry(registry) as transaction:
        transaction.claim(first)
    with claim_first_availability_snapshot_lease(registry) as lease:
        consumed = lease.observe(
            (
                (first.logical_root_sha256, first.physical_root_sha256),
                (second.logical_root_sha256, second.physical_root_sha256),
            )
        )

    assert consumed.snapshot_sha256 != empty.snapshot_sha256
    assert not consumed.availability_for(
        first.logical_root_sha256,
        first.physical_root_sha256,
    )
    assert consumed.availability_for(
        second.logical_root_sha256,
        second.physical_root_sha256,
    )


def test_availability_snapshot_parser_rejects_duplicates_and_noncanonical_json(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    candidate = _claim("snapshot-parser")
    with claim_first_availability_snapshot_lease(registry) as lease:
        snapshot = lease.observe(
            ((candidate.logical_root_sha256, candidate.physical_root_sha256),)
        )
    payload = snapshot.canonical_bytes()

    with pytest.raises(ClaimFirstAdmissionError, match="not canonical"):
        parse_claim_first_availability_snapshot(payload.replace(b'\n', b' \n'))
    duplicate = payload.replace(
        b'{"observations":',
        b'{"observations":[],"observations":',
        1,
    )
    with pytest.raises(ClaimFirstAdmissionError, match="not canonical"):
        parse_claim_first_availability_snapshot(duplicate)


def test_shared_snapshot_includes_legacy_root_claims(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    candidate = _claim("snapshot-legacy")
    with claim_first_availability_snapshot_lease(registry) as lease:
        before = lease.observe(
            ((candidate.logical_root_sha256, candidate.physical_root_sha256),)
        )
    write_root_claim(
        registry,
        root_consumption_sha256=candidate.logical_root_sha256,
        execution_identity_sha256=_sha("snapshot-legacy-execution"),
        source_commit="b" * 40,
        runner_sha256=_sha("snapshot-legacy-runner"),
    )

    with claim_first_availability_snapshot_lease(registry) as lease:
        after = lease.observe(
            ((candidate.logical_root_sha256, candidate.physical_root_sha256),)
        )

    assert before.registry_state_sha256 != after.registry_state_sha256
    assert after.observations[0].available is False


def test_availability_snapshot_requires_one_open_lease_and_unique_pairs(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    candidate = _claim("snapshot-contract")
    lease = claim_first_availability_snapshot_lease(registry)
    pair = (candidate.logical_root_sha256, candidate.physical_root_sha256)

    with pytest.raises(ClaimFirstAdmissionError, match="lease is not open"):
        lease.observe((pair,))
    with lease:
        with pytest.raises(ClaimFirstAdmissionError, match="pairs differ"):
            lease.observe((pair, pair))
        snapshot = lease.observe((pair,))
        assert snapshot.availability_for(*pair)
    with pytest.raises(ClaimFirstAdmissionError, match="lease is not open"):
        lease.observe((pair,))


def test_outer_identity_binds_current_consumer_and_immutable_producer() -> None:
    identity = _execution_identity()
    assert identity.public_dict() == {
        "current_consumer_bound": True,
        "exact_ci_bound": True,
        "immutable_producer_bound": True,
        "logical_and_physical_root_bound": True,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "runtime_factory_bound": True,
        "schema": "pokemon.core.claim-first-execution-identity.v1",
        "source_published": True,
        "worktree_dirty": False,
    }
    pair = identity.root_pair(stage="setup-capture")
    assert pair.execution_identity_sha256 == identity.identity_sha256
    assert pair.plan_sha256 == identity.execution_plan_sha256
    assert pair.identities == frozenset(
        (identity.logical_root_sha256, identity.physical_root_sha256)
    )
    for field in identity.__dataclass_fields__:
        if field in {"exact_ci_run", "exact_ci_attempt", "source_published", "worktree_dirty"}:
            continue
        changed = "d" * 40 if field == "source_commit" else _sha(("changed", field))
        assert replace(identity, **{field: changed}).identity_sha256 != identity.identity_sha256


def test_legacy_single_marker_blocks_either_member_of_a_new_pair(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    candidate = _claim("candidate")
    write_root_claim(
        registry,
        root_consumption_sha256=candidate.logical_root_sha256,
        execution_identity_sha256=_sha("legacy-execution"),
        source_commit="b" * 40,
        runner_sha256=_sha("legacy-runner"),
    )

    with claim_first_pair_registry(registry) as transaction:
        assert not transaction.available(
            candidate.logical_root_sha256,
            candidate.physical_root_sha256,
        )


def test_pair_marker_blocks_every_legacy_single_root_admission(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    claim = _claim("pair-first")
    with claim_first_pair_registry(registry) as transaction:
        transaction.claim(claim)

    for identity in claim.identities:
        assert not root_claim_is_available(registry, identity)
        with pytest.raises(FreshCompositionQualificationError, match="already consumed"):
            write_root_claim(
                registry,
                root_consumption_sha256=identity,
                execution_identity_sha256=_sha("legacy-execution"),
                source_commit="b" * 40,
                runner_sha256=_sha("legacy-runner"),
            )


@pytest.mark.parametrize("overlap", ("identical", "logical", "physical"))
def test_subprocess_race_has_exactly_one_atomic_winner(
    tmp_path: Path,
    overlap: str,
) -> None:
    registry = _registry(tmp_path)
    first = _claim("first")
    second = {
        "identical": first,
        "logical": _claim("second", logical=first.logical_root_sha256),
        "physical": _claim("second", physical=first.physical_root_sha256),
    }[overlap]
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    processes = tuple(
        context.Process(
            target=_race_claim,
            args=(str(registry), claim, start, results),
        )
        for claim in (first, second)
    )
    for process in processes:
        process.start()
    start.set()
    outcomes = tuple(results.get(timeout=20) for _ in processes)
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0

    assert [item[0] for item in outcomes].count("claimed") == 1
    assert [item[0] for item in outcomes].count("failed") == 1
    retained = root_pair_claims(registry)
    assert len(retained) == 1
    assert retained[0] in {first, second}


@pytest.mark.parametrize("legacy_member", ("logical", "physical"))
def test_legacy_and_pair_subprocess_race_has_one_cross_ledger_winner(
    tmp_path: Path,
    legacy_member: str,
) -> None:
    registry = _registry(tmp_path)
    pair = _claim(f"mixed-{legacy_member}")
    legacy_root = {
        "logical": pair.logical_root_sha256,
        "physical": pair.physical_root_sha256,
    }[legacy_member]
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    processes = (
        context.Process(
            target=_race_claim,
            args=(str(registry), pair, start, results),
        ),
        context.Process(
            target=_race_legacy_claim,
            args=(str(registry), legacy_root, start, results),
        ),
    )
    for process in processes:
        process.start()
    start.set()
    outcomes = tuple(results.get(timeout=20) for _ in processes)
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0

    assert [item[0] for item in outcomes].count("claimed") == 1
    assert [item[0] for item in outcomes].count("failed") == 1
    retained_pairs = root_pair_claims(registry)
    if retained_pairs:
        assert retained_pairs == (pair,)
        assert not root_claim_is_available(registry, legacy_root)
    else:
        assert not root_claim_is_available(registry, legacy_root)
        with claim_first_pair_registry(registry) as transaction:
            assert not transaction.available(
                pair.logical_root_sha256,
                pair.physical_root_sha256,
            )


def test_failure_before_atomic_rename_leaves_the_pair_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path)
    claim = _claim("before-rename")

    def fail_rename(_source: Path, _destination: Path) -> None:
        raise OSError("injected rename failure")

    monkeypatch.setattr(admission, "atomic_no_replace_rename", fail_rename)
    with (
        claim_first_pair_registry(registry) as transaction,
        pytest.raises(ClaimFirstAdmissionError, match="could not be retained"),
    ):
        transaction.claim(claim)
    assert root_pair_claims(registry) == ()


def test_file_fsync_failure_before_atomic_rename_leaves_pair_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path)
    claim = _claim("before-file-fsync")

    def fail_file_fsync(_descriptor: int) -> None:
        raise OSError("injected file fsync failure")

    monkeypatch.setattr(admission.os, "fsync", fail_file_fsync)
    with (
        claim_first_pair_registry(registry) as transaction,
        pytest.raises(ClaimFirstAdmissionError, match="could not be retained"),
    ):
        transaction.claim(claim)

    assert root_pair_claims(registry) == ()
    assert not tuple(registry.glob(".*.pending-*"))


def test_uncertain_directory_fsync_retains_a_nonretryable_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path)
    claim = _claim("after-rename")
    real_fsync = os.fsync
    calls = 0

    def fail_directory_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected directory fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(admission.os, "fsync", fail_directory_fsync)
    with (
        claim_first_pair_registry(registry) as transaction,
        pytest.raises(ClaimFirstAdmissionError, match="could not be retained"),
    ):
        transaction.claim(claim)

    assert read_root_pair_claim(registry, claim.claim_sha256) == claim
    with claim_first_pair_registry(registry) as transaction:
        assert not transaction.available(
            claim.logical_root_sha256,
            claim.physical_root_sha256,
        )


def test_reader_rejects_noncanonical_symlink_hardlink_and_rehashed_mutation(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    claim = _claim("unsafe")
    with claim_first_pair_registry(registry) as transaction:
        transaction.claim(claim)
    marker = registry / f"claim-pair-v1-{claim.claim_sha256}.json"

    original = marker.read_bytes()
    marker.unlink()
    target = tmp_path / "target"
    target.write_bytes(original)
    target.chmod(0o600)
    marker.symlink_to(target)
    with pytest.raises(ClaimFirstAdmissionError, match="cannot be authenticated"):
        read_root_pair_claim(registry, claim.claim_sha256)

    marker.unlink()
    os.link(target, marker)
    with pytest.raises(ClaimFirstAdmissionError, match="cannot be authenticated"):
        read_root_pair_claim(registry, claim.claim_sha256)

    marker.unlink()
    changed = replace(claim, stage="selected-outcome")
    marker.write_bytes(admission._canonical_payload(changed.private_dict()))
    marker.chmod(0o600)
    with pytest.raises(ClaimFirstAdmissionError, match="identity differs"):
        read_root_pair_claim(registry, claim.claim_sha256)


def test_contract_is_title_neutral_and_rejects_collapsed_or_invalid_identity() -> None:
    source = Path(admission.__file__).read_text(encoding="utf-8").lower()
    assert "pokemon_red_completion.red" not in source
    assert "pokemon_red_completion.crystal" not in source
    assert "rom" not in ClaimFirstRootPair.__dataclass_fields__
    shared = _sha("shared")
    with pytest.raises(ClaimFirstAdmissionError, match="collapse"):
        _claim("collapsed", logical=shared, physical=shared)
    with pytest.raises(ClaimFirstAdmissionError, match="stage"):
        replace(_claim("bad-stage"), stage="Pokemon Red")


def test_pair_registry_rejects_an_unsafe_container(tmp_path: Path) -> None:
    real = _registry(tmp_path)
    alias = tmp_path / "claim-alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(ClaimFirstAdmissionError, match="registry is invalid"):
        claim_first_pair_registry(alias)


@pytest.mark.parametrize(
    "title_shape",
    (
        {
            "adapter": "red",
            "species": 151,
            "boxes": 12,
            "time": "none",
            "mechanics": ("trade", "stone", "level"),
        },
        {
            "adapter": "crystal",
            "species": 251,
            "boxes": 14,
            "time": "night",
            "mechanics": ("trade", "stone", "level", "held-item", "breeding"),
        },
    ),
)
def test_red_and_crystal_shaped_fixtures_use_the_same_rom_free_claim_sequence(
    tmp_path: Path,
    title_shape: dict[str, object],
) -> None:
    registry = _registry(tmp_path)
    base = _execution_identity(str(title_shape["adapter"]))
    identity = replace(
        base,
        title_adapter_sha256=_sha(title_shape),
    )
    claim = identity.root_pair(stage="setup-capture")

    with claim_first_pair_registry(registry) as transaction:
        assert transaction.available(
            claim.logical_root_sha256,
            claim.physical_root_sha256,
        )
        transaction.claim(claim)

    assert read_root_pair_claim(registry, claim.claim_sha256) == claim
    assert not root_claim_is_available(registry, claim.logical_root_sha256)
    assert not root_claim_is_available(registry, claim.physical_root_sha256)


def test_cross_title_relabelling_cannot_reclaim_the_same_physical_state(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    shared_physical = _sha("shared-physical-state")
    red = replace(
        _execution_identity("red-shape"),
        physical_root_sha256=shared_physical,
    ).root_pair(stage="setup-capture")
    crystal = replace(
        _execution_identity("crystal-shape"),
        physical_root_sha256=shared_physical,
    ).root_pair(stage="setup-capture")

    with claim_first_pair_registry(registry) as transaction:
        transaction.claim(red)
    with claim_first_pair_registry(registry) as transaction:
        assert not transaction.available(
            crystal.logical_root_sha256,
            crystal.physical_root_sha256,
        )
        with pytest.raises(ClaimFirstAdmissionError, match="already consumed"):
            transaction.claim(crystal)
