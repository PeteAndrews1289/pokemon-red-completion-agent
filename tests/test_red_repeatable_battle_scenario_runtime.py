from __future__ import annotations

import hashlib
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_repeatable_battle_scenario_runtime as runtime
from pokemon_red_completion.repeatable_battle_scenario_factory import (
    RepeatableBattlePartyOption,
    RepeatableBattleScenarioAssignment,
    RepeatableBattleScenarioKind,
    RepeatableBattleSourceKind,
    RepeatableBattleSourceObservation,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

STATE_BYTES = b"authenticated source state"
STATE_SHA256 = hashlib.sha256(STATE_BYTES).hexdigest()
MENU_SHA256 = "a" * 64
SOURCE_COMMIT = "b" * 40
MATERIALIZER_COMMIT = "c" * 40


def _source(
    *,
    kind: RepeatableBattleSourceKind = RepeatableBattleSourceKind.FIELD,
    partition: ScenarioPartition = ScenarioPartition.TRAIN,
) -> RepeatableBattleSourceObservation:
    return RepeatableBattleSourceObservation(
        source_id="source-a",
        source_lineage_id=(
            "train-lineage" if partition is ScenarioPartition.TRAIN else "dev-lineage"
        ),
        partition=partition,
        state_sha256=STATE_SHA256,
        source_commit=SOURCE_COMMIT,
        expected_map=22,
        source_kind=kind,
        active_party_index=(None if kind is RepeatableBattleSourceKind.FIELD else 0),
        reachable_venue_ids=(
            ("route_11",) if kind is RepeatableBattleSourceKind.FIELD else ()
        ),
        party_options=(
            RepeatableBattlePartyOption(
                party_index=0,
                menu_semantic_sha256=MENU_SHA256,
                supported_move_count=3,
                hp_ratio=1.0,
            ),
            RepeatableBattlePartyOption(
                party_index=1,
                menu_semantic_sha256="d" * 64,
                supported_move_count=2,
                hp_ratio=0.75,
            ),
        ),
    )


def _assignment(
    source: RepeatableBattleSourceObservation,
    *,
    source_id: str | None = None,
    party_index: int = 0,
    wait: int = 0,
) -> RepeatableBattleScenarioAssignment:
    option = next(item for item in source.party_options if item.party_index == party_index)
    wild = source.source_kind is RepeatableBattleSourceKind.FIELD
    return RepeatableBattleScenarioAssignment(
        scenario_id="repeatable-scenario-a",
        source_id=source_id or source.source_id,
        source_lineage_id=source.source_lineage_id,
        partition=source.partition,
        source_state_sha256=source.state_sha256,
        source_commit=source.source_commit,
        scenario_kind=(
            RepeatableBattleScenarioKind.WILD
            if wild
            else RepeatableBattleScenarioKind.TRAINER
        ),
        party_index=party_index,
        menu_semantic_sha256=option.menu_semantic_sha256,
        venue_id="route_11" if wild else None,
        pre_encounter_wait_frames=wait,
    )


class _Session:
    def __init__(self) -> None:
        self.loaded: list[bytes] = []

    def load_state_bytes(self, payload: bytes) -> None:
        self.loaded.append(payload)

    def save_state_bytes(self) -> bytes:
        return b"naturally materialized state"

    def read_u8(self, address: int) -> int:
        del address
        return 4

    def press(self, button: str) -> None:
        del button

    def release(self, button: str) -> None:
        del button

    def tick(self, frames: int) -> None:
        del frames


class _Reader:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def read(self) -> SimpleNamespace:
        return SimpleNamespace(map_id=22, battle_state=0)

    def read_last_blackout_map(self) -> int:
        return 5


def _session_factory(session: _Session):  # type: ignore[no-untyped-def]
    @contextmanager
    def factory():  # type: ignore[no-untyped-def]
        yield session

    return factory


def test_field_materialization_preserves_lineage_and_emits_no_model_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    assignment = _assignment(source)
    session = _Session()
    prepared = SimpleNamespace(initial_observation_sha256="e" * 64)
    monkeypatch.setattr(runtime, "PokemonRedStateReader", _Reader)
    monkeypatch.setattr(runtime, "_adapt_loaded_source", lambda *args, **kwargs: source)
    monkeypatch.setattr(
        runtime,
        "_selected_venue",
        lambda *args, **kwargs: (
            SimpleNamespace(source_location="route_11"),
            SimpleNamespace(map_id=22),
        ),
    )
    monkeypatch.setattr(runtime, "_prepare_source_venue", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runtime,
        "_materialize_wild_boundary",
        lambda *args, **kwargs: (prepared, 2, 48, 3, 7),
    )

    result = runtime.materialize_repeatable_red_battle_scenario(
        source,
        assignment,
        STATE_BYTES,
        rom_bytes=b"red-rom",
        materializer_source_commit=MATERIALIZER_COMMIT,
        session_factory=_session_factory(session),
    )

    assert session.loaded == [STATE_BYTES]
    assert result.expected_battle_state == 1
    assert result.expected_map == 22
    assert result.encounter_steps == 7
    assert result.public_dict()["source_lineage_id"] == "train-lineage"
    assert result.public_dict()["memory_edits"] == 0
    assert result.public_dict()["move_choices"] == 0
    assert result.public_dict()["teacher_queries"] == 0
    assert b'"root_lineage_id":"train-lineage"' in result.manifest_payload
    assert b'"source_state_sha256":"' + STATE_SHA256.encode("ascii") in result.manifest_payload


def test_trainer_materialization_switches_only_to_the_frozen_party_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(kind=RepeatableBattleSourceKind.TRAINER_BATTLE)
    assignment = _assignment(source, party_index=1, wait=37)
    session = _Session()
    prepared = SimpleNamespace(initial_observation_sha256="f" * 64)
    selected: list[int] = []
    monkeypatch.setattr(runtime, "PokemonRedStateReader", _Reader)
    monkeypatch.setattr(runtime, "_adapt_loaded_source", lambda *args, **kwargs: source)
    monkeypatch.setattr(
        runtime,
        "switch_active_battler",
        lambda actions, reader, emulator, party_index, **kwargs: selected.append(party_index),
    )
    monkeypatch.setattr(
        runtime,
        "_prepare_capture_boundary",
        lambda *args, **kwargs: prepared,
    )

    result = runtime.materialize_repeatable_red_battle_scenario(
        source,
        assignment,
        STATE_BYTES,
        rom_bytes=b"red-rom",
        materializer_source_commit=MATERIALIZER_COMMIT,
        session_factory=_session_factory(session),
    )

    assert selected == [1]
    assert result.expected_battle_state == 2
    assert result.expected_map == source.expected_map
    assert result.controller_actions == 1
    assert result.public_dict()["pre_encounter_wait_frames"] == 37


@pytest.mark.parametrize(
    ("state_bytes", "source_id", "error"),
    (
        (b"wrong state", None, "digest"),
        (STATE_BYTES, "different-source", "authenticated source"),
    ),
)
def test_materializer_rejects_provenance_drift_before_opening_emulator(
    state_bytes: bytes,
    source_id: str | None,
    error: str,
) -> None:
    source = _source()
    assignment = _assignment(source, source_id=source_id)
    entered = False

    @contextmanager
    def forbidden_session():  # type: ignore[no-untyped-def]
        nonlocal entered
        entered = True
        yield _Session()

    with pytest.raises(runtime.RepeatableRedBattleScenarioRuntimeError, match=error):
        runtime.materialize_repeatable_red_battle_scenario(
            source,
            assignment,
            state_bytes,
            rom_bytes=b"red-rom",
            materializer_source_commit=MATERIALIZER_COMMIT,
            session_factory=forbidden_session,
        )
    assert not entered


def test_active_trainer_timing_variant_is_rejected_before_input() -> None:
    source = _source(kind=RepeatableBattleSourceKind.TRAINER_BATTLE)
    assignment = _assignment(source, party_index=0, wait=37)

    with pytest.raises(
        runtime.RepeatableRedBattleScenarioRuntimeError,
        match="trainer assignment",
    ):
        runtime.materialize_repeatable_red_battle_scenario(
            source,
            assignment,
            STATE_BYTES,
            rom_bytes=b"red-rom",
            materializer_source_commit=MATERIALIZER_COMMIT,
            session_factory=_session_factory(_Session()),
        )
