from __future__ import annotations

import hashlib
import json
import runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.red_party_development_outcome_probe import (
    build_bounded_evolution_venue_question,
)
from pokemon_red_completion.scenario_outcome_adapters import PartyDevelopmentOutcomeTrial
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    TeamTrainingProgress,
)
from pokemon_red_completion.training_venue import TrainingVenue

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_red_party_development_outcome_probe.py")
)
SCRIPT_GLOBALS = SCRIPT["_run"].__globals__
ACTIVE_PLAN_PATH = (
    PROJECT_ROOT / "docs" / "evidence" / "red-party-development-outcome-plan-v2-2026-08-14.json"
)
HISTORICAL_PLAN_PATH = (
    PROJECT_ROOT / "docs" / "evidence" / "red-party-development-outcome-plan-2026-08-14.json"
)
RESULT_PATH = (
    PROJECT_ROOT / "docs" / "evidence" / "red-party-development-outcome-result-2026-08-14.json"
)
RESULT_PATH_V2 = (
    PROJECT_ROOT / "docs" / "evidence" / "red-party-development-outcome-result-v2-2026-08-14.json"
)


def _member(slot: int, species_id: int, level: int, experience: int) -> PartyMemberObservation:
    return PartyMemberObservation(
        slot=slot,
        species_id=species_id,
        level=level,
        hp=80,
        max_hp=80,
        moves=(MoveObservation(1, 25, 35),),
        experience=experience,
    )


def _party() -> PartyObservation:
    return PartyObservation(
        members=(
            _member(1, 9, 48, 100_000),
            _member(2, 64, 20, 8_000),
            _member(3, 59, 22, 10_000),
            _member(4, 132, 30, 27_000),
            _member(5, 104, 25, 15_625),
            _member(6, 43, 30, 27_000),
        )
    )


def _venue(name: str, minimum: int, maximum: int) -> TrainingVenue:
    return TrainingVenue(
        band=GrindingArea(name, minimum, maximum, measured_samples=50),
        map_id=minimum,
        walk_to_grass=lambda *_args: 1,
        heal_and_return=lambda *_args: None,
        is_in_center=lambda _raw: False,
        move_slot=lambda _raw: 1,
    )


def test_public_plan_freezes_one_bounded_non_authority_comparison() -> None:
    payload = json.loads(ACTIVE_PLAN_PATH.read_text(encoding="ascii"))
    encoded = ACTIVE_PLAN_PATH.read_text(encoding="ascii")

    assert payload["schema"] == "pokemon-red-party-development-outcome-plan-v2"
    assert payload["status"] == "prospective_unexecuted"
    assert payload["experiment_id"] == "red-party-development-evolution-venue-v2"
    assert payload["predecessor"]["status"] == "retired_without_training_target"
    assert payload["candidate_construction"]["candidate_count"] == 2
    assert payload["bounded_objective"]["same_trainee_required"] is True
    assert payload["bounded_objective"]["target_experience_measured_exactly"] is True
    assert payload["training_policy"]["retreat_hp_ratio"] == 0.45
    assert payload["training_policy"]["max_healing_trips_runtime_value"] == 50
    assert payload["training_policy"]["maximum_budgeted_center_calls"] == 50
    assert payload["training_policy"]["budgeted_center_call_phases"] == [
        "venue_transition",
        "required_recovery",
        "optional_recovery",
    ]
    assert payload["training_policy"]["required_final_cleanup_calls"] == 1
    assert payload["training_policy"]["optional_heal_selected_by_executor"] is False
    assert payload["execution"]["execute_each_candidate_exactly_once"] is True
    assert payload["interpretation"]["model_fit"] is False
    assert payload["interpretation"]["authority_promotion"] is False
    assert set(payload["protected_access"].values()) == {0}
    assert payload["private_path_fields"] == 0
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_runner_loads_the_exact_v2_plan_and_rejects_center_budget_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, digest = SCRIPT["_load_plan"]()

    assert payload["experiment_id"] == "red-party-development-evolution-venue-v2"
    assert digest == hashlib.sha256(ACTIVE_PLAN_PATH.read_bytes()).hexdigest()

    drifted = json.loads(ACTIVE_PLAN_PATH.read_text(encoding="ascii"))
    drifted["training_policy"]["maximum_budgeted_center_calls"] = 49
    drifted_path = tmp_path / "drifted-plan.json"
    drifted_path.write_text(json.dumps(drifted), encoding="ascii")
    monkeypatch.setitem(SCRIPT_GLOBALS, "PLAN_PATH", drifted_path)

    with pytest.raises(
        SCRIPT_GLOBALS["RedPartyDevelopmentRunError"],
        match="Center-call policy differs",
    ):
        SCRIPT["_load_plan"]()


def test_public_result_reproduces_trials_but_rejects_ambiguous_recovery() -> None:
    payload = json.loads(RESULT_PATH.read_text(encoding="ascii"))
    encoded = RESULT_PATH.read_text(encoding="ascii")
    collection = payload["outcome_collection"]
    recovery = payload["recovery_accounting"]
    trials = collection["trials"]

    assert payload["status"] == "complete_rejected_accounting_ambiguity"
    assert (
        payload["prospective_bindings"]["public_plan_sha256"]
        == hashlib.sha256(HISTORICAL_PLAN_PATH.read_bytes()).hexdigest()
    )
    assert payload["source"]["exact_commit_ci_conclusion"] == "success"
    assert collection["candidate_outcomes"] == 2
    assert collection["runner_reported_fully_measured"] is True
    assert collection["runner_reported_learner_update_eligible"] is True
    assert collection["publication_learner_update_eligible"] is False
    assert collection["runner_best_candidate_indices"] == [1]
    assert collection["runner_target_distribution"] == [0.0, 1.0]
    assert [trial["candidate_index"] for trial in trials] == [0, 1]
    assert all(trial["evolution_completed"] for trial in trials)
    assert all(trial["initial_target_level"] == 22 for trial in trials)
    assert all(trial["final_target_level"] == 26 for trial in trials)
    assert all(trial["faints"] == 0 for trial in trials)
    for trial in trials:
        assert trial["target_experience_per_1000_frames"] == pytest.approx(
            trial["target_experience_gained"] * 1_000 / trial["frames_executed"],
            abs=0.000001,
        )
        assert trial["total_experience_per_1000_frames"] == pytest.approx(
            trial["total_experience_gained"] * 1_000 / trial["frames_executed"],
            abs=0.000001,
        )
    assert (
        trials[1]["target_experience_per_1000_frames"]
        > trials[0]["target_experience_per_1000_frames"]
    )
    assert recovery["configured_max_healing_trips"] == 40
    assert recovery["observed_total_counted_center_routes"] == [13, 42]
    assert recovery["phase_breakdown_retained"] is False
    assert recovery["policy_conformance_proven"] is False
    assert recovery["training_target_rejected"] is True
    assert payload["decision"]["training_target_accepted"] is False
    assert payload["decision"]["model_fit"] is False
    assert payload["decision"]["authority_promoted"] is False
    assert set(payload["protected_access"].values()) == {0}
    assert payload["private_path_fields"] == 0
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_public_v2_result_accepts_only_the_phase_reconciled_target() -> None:
    payload = json.loads(RESULT_PATH_V2.read_text(encoding="ascii"))
    encoded = RESULT_PATH_V2.read_text(encoding="ascii")
    collection = payload["outcome_collection"]
    accounting = payload["center_call_accounting"]
    representation = payload["representation_audit"]
    trials = collection["trials"]

    assert payload["status"] == "complete_learner_target_accepted"
    assert (
        payload["prospective_bindings"]["public_plan_sha256"]
        == hashlib.sha256(ACTIVE_PLAN_PATH.read_bytes()).hexdigest()
    )
    assert payload["source"]["git_commit"] == "00499bc68b099ffcd0125a6777bc3b836a84ff0b"
    assert payload["source"]["exact_commit_ci_run"] == 31858937755
    assert payload["source"]["exact_commit_ci_conclusion"] == "success"
    assert collection["candidate_outcomes"] == 2
    assert collection["fully_measured"] is True
    assert collection["learner_update_eligible"] is True
    assert collection["best_candidate_indices"] == [0]
    assert collection["target_distribution"] == [1.0, 0.0]
    assert [trial["candidate_index"] for trial in trials] == [0, 1]
    assert all(trial["evolution_completed"] for trial in trials)
    assert all(trial["initial_target_level"] == 22 for trial in trials)
    assert all(trial["final_target_level"] == 26 for trial in trials)
    assert all(trial["faints"] == 0 for trial in trials)
    for trial in trials:
        assert trial["target_experience_per_1000_frames"] == pytest.approx(
            trial["target_experience_gained"] * 1_000 / trial["frames_executed"],
            abs=0.000001,
        )
        budgeted = (
            trial["venue_transition_trips"]
            + trial["required_recovery_trips"]
            + trial["optional_recovery_trips"]
        )
        assert budgeted == trial["budgeted_center_calls"]
        assert budgeted <= accounting["configured_maximum_budgeted_center_calls"]
        assert trial["cleanup_trips"] == 1
        assert budgeted + trial["cleanup_trips"] == trial["total_counted_center_routes"]
    assert (
        trials[0]["target_experience_per_1000_frames"]
        > trials[1]["target_experience_per_1000_frames"]
    )
    assert accounting["observed_budgeted_center_calls"] == [10, 40]
    assert accounting["observed_cleanup_calls"] == [1, 1]
    assert accounting["phase_sum_equals_total_for_every_trial"] is True
    assert accounting["budget_conformance_proven"] is True
    assert representation["higher_band_venue_transition_trips"] == 39
    assert representation["intrinsic_lower_band_superiority_demonstrated"] is False
    assert payload["decision"]["training_target_accepted"] is True
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
            public_dict=lambda: {
                "artifact_id": "red-party-outcome-test",
                "status": "complete",
            }
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
        assert artifact_id.startswith("red-party-outcome-")
        assert kind == "party_development_outcome_probe"
        return self.writer


class _Emulator:
    def __enter__(self) -> _Emulator:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def load_state(self, path: Path) -> None:
        assert path.name == "capture.state"


def test_stable_party_requires_the_exact_center_nurse_boundary(monkeypatch) -> None:
    raw = SimpleNamespace(
        game_started=True,
        map_id=MapId.CINNABAR_POKECENTER,
        player_x=3,
        player_y=3,
        battle_state=0,
    )
    reader = SimpleNamespace(
        read=lambda: raw,
        read_input_readiness=lambda: SimpleNamespace(ready=True),
    )
    party = _party()
    monkeypatch.setitem(SCRIPT_GLOBALS, "PokemonRedStateReader", lambda emulator: reader)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "PokemonRedPartyReader",
        lambda emulator: SimpleNamespace(read=lambda: party),
    )

    observed_reader, observed_party = SCRIPT["_stable_party"](_Emulator())

    assert observed_reader is reader
    assert observed_party is party

    raw.player_x = 4
    with pytest.raises(SCRIPT_GLOBALS["RedPartyDevelopmentRunError"], match="nurse boundary"):
        SCRIPT["_stable_party"](_Emulator())


def test_runner_opens_catalog_before_two_one_shot_trials(
    tmp_path: Path,
    monkeypatch,
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
    before = _party()
    venues = (_venue("lower", 9, 15), _venue("higher", 15, 21))
    policy = BalancedTeamPolicy(
        minimum_level=55,
        maximum_level_spread=40,
        required_size=6,
        minimum_direct_level_advantage=5,
    )
    question = build_bounded_evolution_venue_question(
        before,
        policy,
        venues,
        source_species_id=59,
        final_species_id=118,
        initial_state_sha256=state_sha256,
    )
    plan = {
        "authenticated_root": {
            "state_sha256": state_sha256,
            "capture_envelope_sha256": envelope_sha256,
            "rom_sha256": rom_sha256,
        },
        "candidate_construction": {
            "ordered_policy_input_sha256": question.ordered_policy_input_sha256,
            "candidate_count": 2,
            "ordered_minimum_encounter_levels": [
                venue.band.minimum_encounter_level for venue in question.venue_bindings
            ],
            "ordered_maximum_encounter_levels": [
                venue.band.maximum_encounter_level for venue in question.venue_bindings
            ],
        },
        "bounded_objective": {
            "initial_target_slot": 3,
            "initial_target_level": 22,
        },
    }
    capture = CapturedProgressEnvelope(
        state_sha256=state_sha256,
        checkpoint_id=SCRIPT_GLOBALS["SOURCE_CHECKPOINT_ID"],
        checkpoint_label="party fixture",
        checkpoints_completed=1,
        checkpoints_total=1,
        verified_objective_ids=(),
    )
    source = SimpleNamespace(
        git_commit="a" * 40,
        public_dict=lambda: {"git_commit": "a" * 40},
    )
    execution = SimpleNamespace(source_commit="a" * 40, source_bundle_sha256="b" * 64)
    registry = SimpleNamespace(execution=execution)
    store = _Store()
    calls: list[int] = []

    def execute_candidate(**kwargs):
        index = kwargs["candidate_index"]
        assert store.writer.opened
        assert [stream for stream, _record in store.writer.records] == ["catalog"] + [
            "trials"
        ] * index
        calls.append(index)
        target = before.members[2]
        after = PartyObservation(
            members=(
                before.members[0],
                before.members[1],
                replace(target, species_id=118, level=26, experience=12_000 + index * 100),
                *before.members[3:],
            )
        )
        trial = PartyDevelopmentOutcomeTrial(
            candidate=question.candidate_set.candidates[index],
            target_slot=3,
            before_party=before,
            after_party=after,
            progress_before=TeamTrainingProgress(),
            progress_after=TeamTrainingProgress(
                battles_completed=10 + index,
                steps_taken=100 + index,
                healing_trips=2,
            ),
            frames_executed=1_000 + index * 100,
            rotations_executed=10 + index,
            evolution_completed=True,
        )
        return trial, {
            "candidate_index": index,
            "execution": {
                "venue_transition_trips": 1,
                "required_recovery_trips": 0,
                "optional_recovery_trips": 0,
                "cleanup_trips": 1,
                "budgeted_center_calls": 1,
            },
        }

    monkeypatch.setitem(SCRIPT_GLOBALS, "detect_source_identity", lambda *a, **k: source)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_clean_source", lambda value: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_published_source", lambda *a: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_load_plan", lambda: (plan, "c" * 64))
    monkeypatch.setitem(SCRIPT_GLOBALS, "load_captured_progress", lambda *a, **k: capture)
    monkeypatch.setitem(
        SCRIPT_GLOBALS, "load_committed_goal_manager_registry", lambda root: registry
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "working_source_bundle_sha256", lambda root: "b" * 64)
    monkeypatch.setitem(SCRIPT_GLOBALS, "resolve_rom_path", lambda path: rom_path)
    monkeypatch.setitem(
        SCRIPT_GLOBALS, "verify_rom", lambda path: SimpleNamespace(sha256=rom_sha256)
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "rom_adjacent_artifacts", lambda path: ())
    monkeypatch.setitem(SCRIPT_GLOBALS, "PyBoyAdapter", lambda path: _Emulator())
    monkeypatch.setitem(SCRIPT_GLOBALS, "_stable_party", lambda emulator: (object(), before))
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "build_bounded_evolution_venue_question",
        lambda *a, **k: question,
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "open_private_root", lambda *a, **k: store)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_execute_candidate", execute_candidate)

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

    assert calls == [0, 1]
    assert [stream for stream, _record in store.writer.records] == [
        "catalog",
        "trials",
        "trials",
        "outcomes",
    ]
    assert result["status"] == "complete"
    assert result["fully_measured"] is True
    assert result["learner_update_eligible"] is True
    assert result["trials"][0]["venue_transition_trips"] == 1
    assert result["trials"][0]["required_recovery_trips"] == 0
    assert result["trials"][0]["optional_recovery_trips"] == 0
    assert result["trials"][0]["cleanup_trips"] == 1
    assert result["trials"][0]["budgeted_center_calls"] == 1
    assert result["model_fit"] is False
    assert result["authority_promoted"] is False
    assert result["teacher_queries"] == 0
    assert result["teacher_choice_targets"] == 0
