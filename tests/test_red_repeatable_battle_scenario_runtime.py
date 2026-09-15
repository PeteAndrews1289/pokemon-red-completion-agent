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
        reachable_venue_ids=(("route_11",) if kind is RepeatableBattleSourceKind.FIELD else ()),
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
            RepeatableBattleScenarioKind.WILD if wild else RepeatableBattleScenarioKind.TRAINER
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


@pytest.mark.parametrize(
    "failure_stage",
    [
        "source_inspection",
        "relocation",
        "encounter_setup",
        "battle",
        "terminal",
        "success",
    ],
)
def test_integrated_qualification_journals_materializer_and_battle(
    monkeypatch,
    tmp_path,
    failure_stage,
):
    import pokemon_red_completion.red_battle_cartridge_qualification as qualification
    from pokemon_red_completion.actions import MacroAction, MacroActionKind
    from pokemon_red_completion.battle_runtime_diagnostics import diagnose_battle_runtime
    from pokemon_red_completion.cartridge_qualification import (
        QualificationCampaign,
        QualificationLimits,
    )
    from pokemon_red_completion.private_artifacts import initialize_private_root

    root, repository = tmp_path / "private", tmp_path / "repository"
    root.mkdir()
    repository.mkdir()
    store = initialize_private_root(
        root,
        repository_root=repository,
        device_id=lambda path: 2 if path == root.resolve() else 1,
        git_worktree_probe=lambda _: False,
    )
    source = _source()
    sessions = []
    phases = []

    class Session(_Session):
        def __init__(self):
            super().__init__()
            self.frame_count = 700 if not sessions else 9
            self.start = self.frame_count

        def tick(self, frames):
            self.frame_count += frames

    @contextmanager
    def factory():
        session = Session()
        sessions.append(session)
        yield session

    class Reader(_Reader):
        def read_input_readiness(self):
            if failure_stage == "terminal":
                raise ValueError("terminal sentinel")
            return SimpleNamespace(ready=True)

    def adapt(*args, **kwargs):
        phases.append("source_inspection")
        if failure_stage == "source_inspection":
            raise ValueError("source sentinel")
        return source

    def relocation(edge, venue, actions, reader, session):
        phases.append("relocation")
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=3))
        if failure_stage == "relocation":
            raise runtime.RepeatableRedBattleScenarioRuntimeError(
                "source did not reach its selected encounter venue"
            )

    def boundary(assignment, venue, actions, controller, reader, session, **kwargs):
        phases.append("encounter_setup")
        # This direct controller path bypassed the old setup CountingExecutor.
        controller.execute(MacroAction(MacroActionKind.WAIT, repeat=4))
        if failure_stage == "encounter_setup":
            raise runtime.RepeatableRedBattleScenarioRuntimeError(
                "wild encounter exceeded its step bound"
            )
        return SimpleNamespace(initial_observation_sha256="e" * 64), 1, 4, 0, 1

    @diagnose_battle_runtime
    def battle(reader, executor, policy, **kwargs):
        phases.append("battle")
        executor.execute(MacroAction(MacroActionKind.WAIT, repeat=5))
        if failure_stage == "battle":
            raise ValueError("battle sentinel")
        policy(
            SimpleNamespace(
                active_party_index=0,
                battler_moves=(1,),
                battler_pp=(4,),
                battler_status=0,
                enemy_hp=10,
            )
        )
        return SimpleNamespace(battle_state=0)

    monkeypatch.setattr(runtime, "PokemonRedStateReader", Reader)
    monkeypatch.setattr(qualification, "PokemonRedStateReader", Reader)
    monkeypatch.setattr(runtime, "_adapt_loaded_source", adapt)
    monkeypatch.setattr(
        runtime,
        "_selected_venue",
        lambda *a, **kw: (
            SimpleNamespace(source_location="route_11"),
            SimpleNamespace(map_id=22),
        ),
    )
    monkeypatch.setattr(runtime, "_prepare_source_venue", relocation)
    monkeypatch.setattr(runtime, "_materialize_wild_boundary", boundary)
    monkeypatch.setattr(qualification, "run_adaptive_wild_battle", battle)
    monkeypatch.setattr(qualification, "strongest_usable_move_slot", lambda _: 1)
    limits = QualificationLimits(20, 1000)
    budget = QualificationCampaign(limits, maximum_cases=1)

    def run():
        return qualification.qualify_repeatable_red_wild_battle(
            store,
            "integrated-v2",
            source,
            _assignment(source),
            STATE_BYTES,
            rom_bytes=b"red-rom",
            materializer_source_commit=MATERIALIZER_COMMIT,
            session_factory=factory,
            limits=limits,
            campaign=budget,
        )

    if failure_stage == "success":
        result = run()
        assert result["actions_completed"] == result["actions_attempted"] == 3
        assert len(sessions) == 2
        assert phases == ["source_inspection", "relocation", "encounter_setup", "battle"]
    else:
        with pytest.raises((ValueError, runtime.RepeatableRedBattleScenarioRuntimeError)):
            run()
        result = store.read_failed_episode_diagnostic("integrated-v2").failure_diagnostic
        assert result["phase"] == failure_stage
        expected_actions = {
            "source_inspection": 0,
            "relocation": 1,
            "encounter_setup": 2,
            "battle": 3,
            "terminal": 3,
        }
        assert result["actions_completed"] == expected_actions[failure_stage]
        if failure_stage == "battle":
            assert result["diagnostic"]["exception_chain"][0]["error_type"] == "ValueError"
        if failure_stage == "relocation":
            assert result["reason"] == "relocation_destination_mismatch"
        if failure_stage == "encounter_setup":
            assert result["reason"] == "encounter_step_limit"
    assert result["emulator_frames"] == sum(s.frame_count - s.start for s in sessions)
    assert result["cost_known"] is True


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
