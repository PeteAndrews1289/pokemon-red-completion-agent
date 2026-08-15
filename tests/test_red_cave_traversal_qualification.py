from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.red_cave_traversal_qualification import (
    CaveTraversalQualificationError,
    CaveTraversalQualificationPolicy,
    CaveTraversalQualificationResult,
    run_cave_traversal_qualification,
)
from pokemon_red_completion.team_training import GrindingArea
from pokemon_red_completion.training_venue import TrainingVenue, WarpSafeVenueWalker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-traversal-live-qualification-plan-2026-08-14.json"
)
RESULT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-traversal-live-qualification-result-2026-08-14.json"
)
SCRIPT = runpy.run_path(str(PROJECT_ROOT / "scripts" / "run_red_cave_traversal_qualification.py"))
SCRIPT_GLOBALS = SCRIPT["_run"].__globals__


def _party(*, healthy: bool = True) -> PartyObservation:
    return PartyObservation(
        members=tuple(
            PartyMemberObservation(
                slot=slot,
                species_id=slot,
                level=20 + slot,
                hp=80 if healthy else 40,
                max_hp=80,
                moves=(MoveObservation(1, 20, 35),),
                experience=10_000 + slot,
            )
            for slot in range(1, 7)
        )
    )


class _MovementDelegate:
    def __init__(self, raw: SimpleNamespace, *, battle_after: int | None = None) -> None:
        self.raw = raw
        self.moves = 0
        self.battle_after = battle_after

    def execute(self, action: MacroAction) -> None:
        if action.kind is not MacroActionKind.MOVE:
            return
        dx, dy = {
            "up": (0, -1),
            "right": (1, 0),
            "down": (0, 1),
            "left": (-1, 0),
        }[action.value]
        self.raw.player_x += dx
        self.raw.player_y += dy
        self.moves += 1
        if self.battle_after == self.moves:
            self.raw.battle_state = 1


def _venue(raw: SimpleNamespace) -> TrainingVenue:
    def heal_and_return(*_args: object) -> None:
        raw.map_id = int(MapId.DIGLETTS_CAVE)
        raw.player_x = 5
        raw.player_y = 5
        raw.battle_state = 0

    return TrainingVenue(
        band=GrindingArea("fixture", 15, 21, measured_samples=50),
        map_id=int(MapId.DIGLETTS_CAVE),
        walk_to_grass=lambda *_args: 0,
        walk_to_grass_factory=lambda: WarpSafeVenueWalker(
            expected_map_id=int(MapId.DIGLETTS_CAVE),
            excluded_coordinates=frozenset({(5, 5)}),
            move_wait_frames=1,
        ),
        heal_and_return=heal_and_return,
        is_in_center=lambda _raw: False,
        move_slot=lambda _raw: 1,
    )


def test_live_qualification_exercises_the_exit_seam_before_a_battle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = SimpleNamespace(map_id=0, player_x=0, player_y=0, battle_state=0)
    reader = SimpleNamespace(read=lambda: raw)
    monkeypatch.setattr(
        "pokemon_red_completion.red_cave_traversal_qualification.PokemonRedPartyReader",
        lambda _emulator: SimpleNamespace(read=lambda: _party()),
    )
    actions = CountingExecutor(_MovementDelegate(raw, battle_after=2))

    result = run_cave_traversal_qualification(
        actions,
        reader,
        SimpleNamespace(),
        venue=_venue(raw),
        policy=CaveTraversalQualificationPolicy(
            minimum_successful_steps=2,
            maximum_successful_steps=12,
            maximum_movement_attempts=48,
        ),
    )

    assert result.passed is True
    assert result.terminal_reason == "battle_after_minimum"
    assert result.successful_steps == 2
    assert result.movement_attempts == 2
    assert result.excluded_transition_skips == 1
    assert result.public_dict()["map_departures"] == 0


def test_live_qualification_stops_if_a_battle_preempts_the_reversal_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = SimpleNamespace(map_id=0, player_x=0, player_y=0, battle_state=0)
    reader = SimpleNamespace(read=lambda: raw)
    monkeypatch.setattr(
        "pokemon_red_completion.red_cave_traversal_qualification.PokemonRedPartyReader",
        lambda _emulator: SimpleNamespace(read=lambda: _party()),
    )
    actions = CountingExecutor(_MovementDelegate(raw, battle_after=1))

    with pytest.raises(CaveTraversalQualificationError, match="before exercising"):
        run_cave_traversal_qualification(
            actions,
            reader,
            SimpleNamespace(),
            venue=_venue(raw),
            policy=CaveTraversalQualificationPolicy(),
        )


def test_live_qualification_can_finish_at_its_step_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = SimpleNamespace(map_id=0, player_x=0, player_y=0, battle_state=0)
    reader = SimpleNamespace(read=lambda: raw)
    monkeypatch.setattr(
        "pokemon_red_completion.red_cave_traversal_qualification.PokemonRedPartyReader",
        lambda _emulator: SimpleNamespace(read=lambda: _party()),
    )
    actions = CountingExecutor(_MovementDelegate(raw))

    result = run_cave_traversal_qualification(
        actions,
        reader,
        SimpleNamespace(),
        venue=_venue(raw),
        policy=CaveTraversalQualificationPolicy(
            minimum_successful_steps=2,
            maximum_successful_steps=3,
            maximum_movement_attempts=12,
        ),
    )

    assert result.terminal_reason == "step_ceiling"
    assert result.successful_steps == 3
    assert result.excluded_transition_skips == 1


def test_qualification_result_rejects_incomplete_movement_accounting() -> None:
    with pytest.raises(CaveTraversalQualificationError, match="accounting"):
        CaveTraversalQualificationResult(
            recovery_completed=True,
            entered_on_declared_transition=True,
            terminal_reason="step_ceiling",
            battle_started=False,
            movement_attempts=3,
            successful_steps=2,
            blocked_attempts=0,
            excluded_transition_skips=1,
            no_progress_cycles=0,
        )


def test_public_plan_is_path_free_and_collects_no_learner_target() -> None:
    payload = json.loads(PLAN_PATH.read_text(encoding="ascii"))
    encoded = PLAN_PATH.read_text(encoding="ascii")

    assert payload["status"] == "prospective_unexecuted"
    assert payload["experiment_id"] == "red-cave-traversal-live-qualification-v1"
    assert payload["authenticated_root"]["partition"] == "train"
    assert payload["authenticated_root"]["sealed_test"] is False
    assert payload["qualification_policy"]["minimum_successful_steps"] == 2
    assert payload["qualification_policy"]["battle_commands_allowed"] == 0
    assert payload["execution"]["execute_exactly_once"] is True
    assert payload["execution"]["retry_after_observation"] is False
    assert payload["interpretation"]["training_example_added"] is False
    assert payload["interpretation"]["model_fit"] is False
    assert payload["interpretation"]["authority_promotion"] is False
    assert set(payload["protected_access"].values()) == {0}
    assert payload["private_path_fields"] == 0
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_runner_loads_the_exact_plan_and_rejects_policy_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, digest = SCRIPT["_load_plan"]()
    assert payload["experiment_id"] == "red-cave-traversal-live-qualification-v1"
    assert digest == hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()

    drifted = json.loads(PLAN_PATH.read_text(encoding="ascii"))
    drifted["qualification_policy"]["maximum_movement_attempts"] = 49
    path = tmp_path / "drifted.json"
    path.write_text(json.dumps(drifted), encoding="ascii")
    monkeypatch.setitem(SCRIPT_GLOBALS, "PLAN_PATH", path)

    with pytest.raises(
        SCRIPT_GLOBALS["RedCaveTraversalRunError"],
        match="policy differs",
    ):
        SCRIPT["_load_plan"]()


def test_public_result_reports_only_the_one_live_qualification() -> None:
    payload = json.loads(RESULT_PATH.read_text(encoding="ascii"))
    encoded = RESULT_PATH.read_text(encoding="ascii")
    result = payload["qualification"]

    assert payload["status"] == "complete_live_qualified"
    assert (
        payload["prospective_bindings"]["public_plan_sha256"]
        == hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()
    )
    assert payload["prospective_bindings"]["runner_executions"] == 1
    assert payload["prospective_bindings"]["retries"] == 0
    assert payload["source"]["git_commit"] == "66ed6eef1e72c34fac2079f5db3671c51041eccd"
    assert payload["source"]["exact_commit_ci_run"] == 31861829598
    assert payload["source"]["exact_commit_ci_conclusion"] == "success"
    assert result["recovery_completed"] is True
    assert result["entered_on_declared_transition"] is True
    assert result["movement_attempts"] == 14
    assert result["successful_steps"] == 12
    assert result["blocked_attempts"] == 2
    assert result["excluded_transition_skips"] == 1
    assert result["no_progress_cycles"] == 0
    assert result["map_departures"] == 0
    assert result["battle_commands_executed"] == 0
    assert payload["decision"]["repair_live_qualified"] is True
    assert payload["decision"]["training_example_added"] is False
    assert payload["decision"]["model_fit"] is False
    assert payload["decision"]["authority_promoted"] is False
    assert set(payload["protected_access"].values()) == {0}
    assert payload["private_path_fields"] == 0
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


class _Writer:
    def __init__(self) -> None:
        self.opened = False
        self.records: list[tuple[str, dict[str, object]]] = []
        self.summary = SimpleNamespace(
            public_dict=lambda: {"artifact_id": "cave-test", "status": "complete"}
        )

    def __enter__(self) -> _Writer:
        self.opened = True
        return self

    def __exit__(self, *args: object) -> None:
        del args
        self.opened = False

    def append(self, stream: str, record: dict[str, object]) -> None:
        assert self.opened
        self.records.append((stream, record))


class _Store:
    def __init__(self) -> None:
        self.writer = _Writer()

    def begin_artifact(self, artifact_id: str, *, kind: str) -> _Writer:
        assert artifact_id.startswith("red-cave-traversal-")
        assert kind == "cave_traversal_live_qualification"
        return self.writer


class _Emulator:
    def __init__(self) -> None:
        self.frame_count = 0

    def __enter__(self) -> _Emulator:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def load_state(self, path: Path) -> None:
        assert path.name == "capture.state"


def test_execute_opens_private_catalog_before_controller_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "capture.state"
    envelope_path = tmp_path / "capture.state.json"
    rom_path = tmp_path / "red.gb"
    state_path.write_bytes(b"state")
    envelope_path.write_bytes(b"envelope")
    rom_path.write_bytes(b"rom")
    state_sha256 = hashlib.sha256(b"state").hexdigest()
    envelope_sha256 = hashlib.sha256(b"envelope").hexdigest()
    rom_sha256 = hashlib.sha256(b"rom").hexdigest()
    party = _party()
    raw = SimpleNamespace(map_id=int(MapId.DIGLETTS_CAVE), player_x=4, player_y=4)
    reader = SimpleNamespace(read=lambda: raw)
    plan = {
        "authenticated_root": {
            "state_sha256": state_sha256,
            "capture_envelope_sha256": envelope_sha256,
            "rom_sha256": rom_sha256,
            "initial_party_size": 6,
            "initial_fainted_members": 0,
            "initial_damaged_members": 0,
            "initial_statused_members": 0,
        }
    }
    capture = CapturedProgressEnvelope(
        state_sha256=state_sha256,
        checkpoint_id=SCRIPT_GLOBALS["SOURCE_CHECKPOINT_ID"],
        checkpoint_label="fixture",
        checkpoints_completed=1,
        checkpoints_total=1,
        verified_objective_ids=(),
    )
    source = SimpleNamespace(
        git_commit="a" * 40,
        public_dict=lambda: {"git_commit": "a" * 40},
    )
    registry = SimpleNamespace(
        execution=SimpleNamespace(source_commit="a" * 40, source_bundle_sha256="b" * 64)
    )
    store = _Store()

    def qualify(controller, observed_reader, emulator, **kwargs):
        del controller, kwargs
        assert observed_reader is reader
        assert store.writer.opened
        assert [stream for stream, _record in store.writer.records] == ["catalog"]
        emulator.frame_count = 120
        return CaveTraversalQualificationResult(
            recovery_completed=True,
            entered_on_declared_transition=True,
            terminal_reason="step_ceiling",
            battle_started=False,
            movement_attempts=3,
            successful_steps=2,
            blocked_attempts=1,
            excluded_transition_skips=1,
            no_progress_cycles=0,
        )

    monkeypatch.setitem(SCRIPT_GLOBALS, "detect_source_identity", lambda *a, **k: source)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_clean_source", lambda _value: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_published_source", lambda *a: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_load_plan", lambda: (plan, "c" * 64))
    monkeypatch.setitem(SCRIPT_GLOBALS, "load_captured_progress", lambda *a, **k: capture)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "load_committed_goal_manager_registry",
        lambda _root: registry,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "working_source_bundle_sha256",
        lambda _root: "b" * 64,
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "resolve_rom_path", lambda _path: rom_path)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "verify_rom",
        lambda _path: SimpleNamespace(sha256=rom_sha256),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "rom_adjacent_artifacts", lambda _path: ())
    monkeypatch.setitem(SCRIPT_GLOBALS, "PyBoyAdapter", lambda _path: _Emulator())
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_stable_boundary",
        lambda _emulator: (reader, party),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "open_private_root", lambda *a, **k: store)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "FrameSafeExecutor",
        lambda *_args: SimpleNamespace(execute=lambda _action: None),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "run_cave_traversal_qualification", qualify)

    result = SCRIPT["_run"](
        SimpleNamespace(
            state=state_path,
            envelope=envelope_path,
            rom=rom_path,
            private_root=tmp_path,
            exact_ci_run=123,
            execute=True,
        )
    )

    assert [stream for stream, _record in store.writer.records] == [
        "catalog",
        "qualifications",
    ]
    assert result["status"] == "complete_live_qualified"
    assert result["qualification"]["passed"] is True
    assert result["battle_commands_executed"] == 0
    assert result["training_example_added"] is False
    assert result["model_fit"] is False
    assert result["authority_promoted"] is False
    assert result["teacher_queries"] == 0
    assert result["red_sealed_test_cases_opened"] == 0
