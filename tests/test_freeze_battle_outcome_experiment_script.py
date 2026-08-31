# ruff: noqa: E402 -- standalone script is loaded after its local path setup.

from __future__ import annotations

import hashlib
import runpy
import stat
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FREEZER = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "freeze_battle_outcome_experiment.py"),
    run_name="freeze_battle_outcome_experiment_test",
)


def _model(*, distinct: bool = True) -> MaskedMLPMoveRanker:
    weights = np.zeros((2, len(FEATURE_NAMES)), dtype=np.float64)
    if distinct:
        weights[0, 0] = 1.0
        weights[1, 1] = 0.5
    return MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=weights,
        hidden_bias=np.zeros(2, dtype=np.float64),
        output_weights=np.asarray((-1.0, 0.25), dtype=np.float64),
        output_bias=0.0,
        training_seed=7,
    )


def _prepared(*, duplicate_vectors: bool = False) -> SimpleNamespace:
    low = [0.0] * len(FEATURE_NAMES)
    high = [0.0] * len(FEATURE_NAMES)
    low[0] = -0.8
    high[0] = -0.8 if duplicate_vectors else 0.8
    return SimpleNamespace(
        initial_observation_sha256=_digest("battle-observation"),
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=(tuple(low), tuple(high)),
            legal_mask=(True, True),
            current_pp=(10.0, 10.0),
            slot_indices=(0, 1),
            schema_id=FEATURE_SCHEMA_ID,
        ),
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class _CatalogEntry:
    slot_id = "red-goal-v1-train-01"
    assignment_id = _digest("assignment")
    capture_id = "red-goal-capture-01"
    state_sha256 = _digest("upstream-state")
    envelope_sha256 = _digest("upstream-envelope")
    context_id = _digest("context")

    def __init__(self) -> None:
        self.authentication_calls = 0

    def authenticated_root_lineage_id(
        self,
        *,
        slot_id: str,
        capture_id: str,
        state_sha256: str,
        envelope_sha256: str,
    ) -> str:
        assert (
            slot_id,
            capture_id,
            state_sha256,
            envelope_sha256,
        ) == (
            self.slot_id,
            self.capture_id,
            self.state_sha256,
            self.envelope_sha256,
        )
        self.authentication_calls += 1
        return f"red-goal-root-{self.assignment_id}"


class _Registry:
    def __init__(
        self,
        entry: _CatalogEntry,
        *,
        partition: str = "train",
        assignment_id: str | None = None,
    ) -> None:
        self.entry = entry
        self.partition = partition
        self.assignment_id = assignment_id or entry.assignment_id
        self.assignment_calls: list[str] = []

    def assignment(self, slot_id: str) -> SimpleNamespace:
        self.assignment_calls.append(slot_id)
        return SimpleNamespace(
            assignment_id=self.assignment_id,
            partition=self.partition,
        )


def _capture(
    entry: _CatalogEntry,
    *,
    partition: ScenarioPartition = ScenarioPartition.TRAIN,
    source_commit: str = "a" * 40,
    source_state_sha256: str | None = None,
    root_lineage_id: str | None = None,
    expected_battle_state: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        manifest=SimpleNamespace(
            partition=partition,
            source_commit=source_commit,
            source_state_sha256=(
                entry.state_sha256
                if source_state_sha256 is None
                else source_state_sha256
            ),
            expected_battle_state=expected_battle_state,
            root_lineage_id=(
                f"red-goal-root-{entry.assignment_id}"
                if root_lineage_id is None
                else root_lineage_id
            ),
            capture_id="battle-train-01",
            state_sha256=_digest("battle-state"),
            initial_observation_sha256=_digest("battle-observation"),
            expected_map=11,
        ),
        manifest_sha256=_digest("battle-manifest"),
    )


def _bind(
    capture: SimpleNamespace,
    entry: _CatalogEntry,
    registry: _Registry,
):  # type: ignore[no-untyped-def]
    return FREEZER["_binding_for_capture"](
        capture,
        prepared=_prepared(),
        base_model=_model(),
        expected_partition=ScenarioPartition.TRAIN,
        expected_catalog_partition="train",
        source_commit="a" * 40,
        catalog=SimpleNamespace(entries=(entry,)),
        registry=registry,
    )


def test_binding_authenticates_the_exact_catalog_root_and_physical_bytes() -> None:
    entry = _CatalogEntry()
    registry = _Registry(entry)

    binding = _bind(_capture(entry), entry, registry)

    assert entry.authentication_calls == 1
    assert registry.assignment_calls == [entry.slot_id]
    assert binding.partition is ScenarioPartition.TRAIN
    assert binding.source_slot_id == entry.slot_id
    assert binding.source_assignment_id == entry.assignment_id
    assert binding.source_context_id == entry.context_id
    assert binding.root_lineage_id == f"red-goal-root-{entry.assignment_id}"
    assert binding.root_consumption_sha256 == root_consumption_sha256(
        state_sha256=entry.state_sha256,
        envelope_sha256=entry.envelope_sha256,
    )


@pytest.mark.parametrize(
    ("attribute", "value", "error"),
    (
        ("partition", ScenarioPartition.DEVELOPMENT, "binding differs"),
        ("source_commit", "b" * 40, "binding differs"),
        ("source_state_sha256", None, "binding differs"),
        ("source_state_sha256", _digest("unregistered"), "unique upstream"),
        ("expected_battle_state", 2, "binding differs"),
        ("root_lineage_id", "red-goal-root-forged", "lineage differs"),
    ),
)
def test_binding_rejects_capture_or_lineage_drift(
    attribute: str,
    value: object,
    error: str,
) -> None:
    entry = _CatalogEntry()
    registry = _Registry(entry)
    capture = _capture(entry)
    setattr(capture.manifest, attribute, value)

    with pytest.raises(FREEZER["BattleOutcomeExperimentFreezeError"], match=error):
        _bind(capture, entry, registry)


def test_binding_rejects_ambiguous_catalog_bytes() -> None:
    entry = _CatalogEntry()
    capture = _capture(entry)
    registry = _Registry(entry)

    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="unique upstream",
    ):
        FREEZER["_binding_for_capture"](
            capture,
            prepared=_prepared(),
            base_model=_model(),
            expected_partition=ScenarioPartition.TRAIN,
            expected_catalog_partition="train",
            source_commit="a" * 40,
            catalog=SimpleNamespace(entries=(entry, entry)),
            registry=registry,
        )


def test_binding_rejects_a_runtime_menu_without_two_distinct_candidates() -> None:
    entry = _CatalogEntry()
    registry = _Registry(entry)

    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="two distinct candidate",
    ):
        FREEZER["_binding_for_capture"](
            _capture(entry),
            prepared=_prepared(duplicate_vectors=True),
            base_model=_model(),
            expected_partition=ScenarioPartition.TRAIN,
            expected_catalog_partition="train",
            source_commit="a" * 40,
            catalog=SimpleNamespace(entries=(entry,)),
            registry=registry,
        )


def test_binding_rejects_a_menu_collapsed_by_the_frozen_prior() -> None:
    entry = _CatalogEntry()
    registry = _Registry(entry)

    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="two distinct hidden",
    ):
        FREEZER["_binding_for_capture"](
            _capture(entry),
            prepared=_prepared(),
            base_model=_model(distinct=False),
            expected_partition=ScenarioPartition.TRAIN,
            expected_catalog_partition="train",
            source_commit="a" * 40,
            catalog=SimpleNamespace(entries=(entry,)),
            registry=registry,
        )


@pytest.mark.parametrize(
    ("partition", "assignment_id"),
    (
        ("validation", None),
        ("train", _digest("different-assignment")),
    ),
)
def test_binding_rejects_registry_assignment_drift(
    partition: str,
    assignment_id: str | None,
) -> None:
    entry = _CatalogEntry()
    registry = _Registry(
        entry,
        partition=partition,
        assignment_id=assignment_id,
    )

    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="partition or lineage differs",
    ):
        _bind(_capture(entry), entry, registry)


def test_freezer_observes_both_logical_and_physical_root_pairs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / "claims"
    bindings = (
        SimpleNamespace(
            logical_root_sha256=_digest("train-logical"),
            physical_root_sha256=_digest("train-physical"),
        ),
        SimpleNamespace(
            logical_root_sha256=_digest("development-logical"),
            physical_root_sha256=_digest("development-physical"),
        ),
    )
    calls: list[tuple[Path, str, str]] = []

    def available(path: Path, logical: str, physical: str) -> bool:
        calls.append((path, logical, physical))
        return True

    monkeypatch.setitem(
        FREEZER["_require_available_root_pairs"].__globals__,
        "observe_claim_first_pair_availability",
        available,
    )

    FREEZER["_require_available_root_pairs"](
        bindings,
        registry_path=registry,
    )

    assert calls == [
        (
            registry,
            bindings[0].logical_root_sha256,
            bindings[0].physical_root_sha256,
        ),
        (
            registry,
            bindings[1].logical_root_sha256,
            bindings[1].physical_root_sha256,
        ),
    ]


def test_freezer_fails_closed_when_a_root_pair_is_consumed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = SimpleNamespace(
        logical_root_sha256=_digest("logical"),
        physical_root_sha256=_digest("physical"),
    )
    monkeypatch.setitem(
        FREEZER["_require_available_root_pairs"].__globals__,
        "observe_claim_first_pair_availability",
        lambda *_args: False,
    )

    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="already consumed",
    ):
        FREEZER["_require_available_root_pairs"](
            (binding, binding),
            registry_path=tmp_path,
        )


def test_freezer_normalizes_an_unauthenticatable_pair_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = SimpleNamespace(
        logical_root_sha256=_digest("logical"),
        physical_root_sha256=_digest("physical"),
    )

    def unavailable(*_args: object) -> bool:
        raise FREEZER["ClaimFirstAdmissionError"]("malformed ledger")

    monkeypatch.setitem(
        FREEZER["_require_available_root_pairs"].__globals__,
        "observe_claim_first_pair_availability",
        unavailable,
    )

    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="cannot be authenticated",
    ):
        FREEZER["_require_available_root_pairs"](
            (binding, binding),
            registry_path=tmp_path,
        )


def test_plan_output_must_be_new_private_and_away_from_the_rom(
    tmp_path: Path,
) -> None:
    rom_dir = tmp_path / "roms"
    plan_dir = tmp_path / "plans"
    rom_dir.mkdir()
    plan_dir.mkdir()
    rom = rom_dir / "red.gb"
    rom.write_bytes(b"rom")
    accepted = plan_dir / "battle-plan.json"

    assert FREEZER["_private_new_plan"](
        accepted,
        rom_path=rom,
    ) == accepted.resolve()

    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="beside the ROM",
    ):
        FREEZER["_private_new_plan"](rom_dir / "battle-plan.json", rom_path=rom)

    accepted.write_bytes(b"existing")
    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="already exists",
    ):
        FREEZER["_private_new_plan"](accepted, rom_path=rom)

    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="remain private",
    ):
        FREEZER["_private_new_plan"](
            PROJECT_ROOT / ".forbidden-battle-plan.json",
            rom_path=rom,
        )


def test_plan_writer_is_exclusive_owner_only_and_non_overwriting(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "battle-plan.json"
    payload = b'{"schema":"test"}\n'

    FREEZER["_write_exclusive"](destination, payload)

    assert destination.read_bytes() == payload
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="could not be retained",
    ):
        FREEZER["_write_exclusive"](destination, b"replacement")
    assert destination.read_bytes() == payload


def test_plan_writer_fsyncs_the_file_and_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "battle-plan.json"
    real_fsync = FREEZER["os"].fsync
    synced_kinds: list[str] = []

    def observe_fsync(descriptor: int) -> None:
        mode = FREEZER["os"].fstat(descriptor).st_mode
        synced_kinds.append("directory" if stat.S_ISDIR(mode) else "file")
        real_fsync(descriptor)

    monkeypatch.setattr(FREEZER["os"], "fsync", observe_fsync)

    FREEZER["_write_exclusive"](destination, b"prospective-plan")

    assert synced_kinds == ["file", "directory"]


def test_plan_writer_removes_a_partial_file_after_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "battle-plan.json"
    real_write = FREEZER["os"].write
    calls = 0

    def fail_after_prefix(descriptor: int, payload: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(descriptor, payload[:4])
        return 0

    monkeypatch.setattr(FREEZER["os"], "write", fail_after_prefix)

    with pytest.raises(
        FREEZER["BattleOutcomeExperimentFreezeError"],
        match="could not be retained",
    ):
        FREEZER["_write_exclusive"](destination, b"prospective-plan")

    assert not destination.exists()
