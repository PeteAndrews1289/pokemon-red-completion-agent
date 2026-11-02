"""ROM-free evidence checks: diagnostic data never replaces a player action."""

import json
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest
from test_living_dex_option_value import _example, _settled
from test_private_artifacts import _make_store
from test_red_acquisition import _RouteOneSurveySimulation
from test_red_autonomous_player import _environment
from test_red_live_option_menu import _mixed, _model
from test_red_player_lesson_runtime import Emulator

from pokemon_red_completion.executor import CountingExecutor, NativeLessonController
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexCurriculumOutcomeExample,
    LivingDexObservedOutcome,
    LivingDexOptionAvailability,
    LivingDexOptionUnavailableReason,
    LivingDexOutcomeStatus,
    fit_living_dex_option_value,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import RedAreaExecutionError, run_red_area_survey
from pokemon_red_completion.red_autonomous_player import run_autonomous_options
from pokemon_red_completion.red_player_lesson_runtime import (
    _RecordedActions,
    player_diagnostic_delta,
    player_diagnostic_state,
)


def test_score_diagnostics_reproduce_clipping_and_economy_without_policy_changes():
    model, menu = _model(), _mixed([]).menu
    before = model.model_sha256, menu.policy_sha256
    receipt = model.diagnose_menu(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY, selected_index=0)
    assert (model.model_sha256, menu.policy_sha256) == before
    scores = model.scores(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY)
    assert [row["score"] for row in receipt["candidates"]] == list(scores)
    acquisition = [row for row in receipt["candidates"] if row["kind"] == "acquire"]
    assert acquisition
    for row in acquisition:
        assert row["raw_predictions"]["verified_success"] == 10
        assert row["bounded_predictions"]["verified_success"] == 1
        assert "verified_success" in row["clipped_outputs"]
        assert row["top_raw_contributions"]["verified_success"][0] == {
            "feature": "kind.acquire",
            "contribution": 10,
        }
    assert not receipt["prediction_is_calibrated_probability"]
    assert not receipt["score_margin_is_confidence"]


def test_masked_candidates_have_inputs_but_no_predictions_or_score():
    model, menu = _model(), _mixed([]).menu
    candidate = replace(
        menu.candidates[0],
        availability=LivingDexOptionAvailability.UNAVAILABLE,
        unavailable_reason=LivingDexOptionUnavailableReason.MISSING_RESOURCE,
    )
    menu = replace(menu, candidates=(candidate, *menu.candidates[1:]))
    receipt = model.diagnose_menu(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY)
    row = receipt["candidates"][0]
    assert row["input_vector"]
    assert not row["available"] and row["score"] is None
    assert "raw_predictions" not in row
    with pytest.raises(ValueError, match="selection is unavailable"):
        model.diagnose_menu(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY, selected_index=0)


def test_collapsed_semantics_identify_only_the_actual_feature_difference():
    model, menu = _model(), _mixed([]).menu
    first = menu.candidates[0]
    second = replace(
        first,
        binding_ref="another-private-source",
        features=replace(first.features, execution_effort=first.features.execution_effort + 0.01),
    )
    menu = replace(menu, candidates=(first, second))
    receipt = model.diagnose_menu(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY, selected_index=0)
    assert receipt["varying_features"] == ["execution_effort"]
    assert [row["feature"] for row in receipt["selected_feature_differences"]] == [
        "execution_effort",
    ]
    assert receipt["best_runner_up_score_margin"] == 0
    assert "another-private-source" not in json.dumps(receipt)


def test_train_coverage_preserves_failures_and_censored_attempts_without_fitting():
    rows = (
        _example(
            0,
            selected=0,
            outcome=_settled(success=True, completion=0.3, unlock=0.1, action_cost=0.2),
        ),
        _example(
            1, selected=1, outcome=_settled(success=False, completion=0, unlock=0, action_cost=0.5)
        ),
        _example(
            2,
            selected=0,
            outcome=LivingDexObservedOutcome(
                LivingDexOutcomeStatus.CENSORED,
                censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
            ),
        ),
    )
    model = fit_living_dex_option_value(rows).model
    before = model.model_sha256
    report = model.diagnose_training_coverage(rows)
    assert model.model_sha256 == before and report["matches_model_train_dataset"]
    assert report["settled_examples"] == 2 and report["censored_examples"] == 1
    assert report["successful_examples"] == report["unsuccessful_examples"] == 1
    assert not report["automatic_fit"]
    assert any(row["variance"] == 0 for row in report["features"])
    assert report["comparative_outcomes_by_kind"]["acquire"]["censored"] == 1
    with pytest.raises(ValueError, match="partition"):
        model.diagnose_training_coverage((replace(rows[0], partition="development"), rows[1]))
    # In-sample errors are not a claim of unseen native performance.
    assert report["in_sample_errors_are_not_unseen_performance"]


def test_coverage_accounts_for_executed_unit_lessons_without_inventing_choices():
    row = _example(
        0, selected=0, outcome=_settled(success=True, completion=0.3, unlock=0.1, action_cost=0.2)
    )
    unit = LivingDexCurriculumOutcomeExample(
        decision_sha256="e" * 64,
        partition="train",
        feature_version=1,
        features=row.menu.candidate_vector(0, feature_version=1),
        outcome=_settled(success=False, completion=0, unlock=0, action_cost=0.5),
    )
    model = fit_living_dex_option_value((row,), curriculum_examples=(unit,)).model
    report = model.diagnose_training_coverage((row,), curriculum_examples=(unit,))
    assert report["matches_model_train_dataset"]
    assert report["comparative_attempts"] == report["unit_curriculum_attempts"] == 1
    assert report["unit_curriculum_outcomes_by_kind"]["acquire"] == dict(
        attempts=1, successes=0, failures=1, censored=0
    )


def test_unknown_resources_are_not_zero_and_serialization_preserves_exact_state():
    observation = NS(
        raw=NS(party_hp=(0, 12), repel_remaining_steps=0, enemy_party_hp=(44,)),
        input_ready=True,
        collection_observation=NS(owned_species=frozenset({"one"})),
    )
    result = player_diagnostic_state(observation)
    assert result == json.loads(json.dumps(result))
    assert result["party_hp"] == [0, 12] and result["bag_items"] is None
    assert "bag_items" in result["unknown_fields"]
    assert "repel_remaining_steps" not in result["unknown_fields"]
    assert "enemy_party_hp" not in result  # Hidden reserve roster is not actor data.
    assert result["battle_fields_are_live"] is None
    observation.raw.battle_state = 0
    assert player_diagnostic_state(observation)["battle_fields_are_live"] is False


def test_resource_deltas_count_spending_and_do_not_invent_a_cause():
    before = dict(
        diagnostics=dict(player_money=1000, bag_items=[[4, 3], [20, 1]]), owned_species=["old"]
    )
    after = dict(
        diagnostics=dict(player_money=800, bag_items=[[4, 1], [20, 1]]),
        owned_species=["old", "new"],
    )
    result = player_diagnostic_delta(before, after)
    assert result["player_money"] == -200
    assert result["bag_item_quantity_changes"] == [
        dict(item_id=4, before=3, after=1, change=-2),
    ]
    assert result["new_owned_species"] == ["new"]
    assert result["cause_not_inferred"]
    assert player_diagnostic_delta({}, {})["bag_item_quantity_changes"] is None


def test_diagnostic_journal_is_durable_and_never_counts_as_input(tmp_path):
    _, _, store = _make_store(tmp_path)
    emulator = Emulator()
    controller = NativeLessonController(emulator, maximum_frames=10)
    recorder = _RecordedActions(controller, store, "a" * 64, 1)
    limiter = HardCompositionActionLimiter(
        CountingExecutor(recorder), maximum_actions_per_decision=1, maximum_episode_actions=1
    )
    actions = CountingExecutor(limiter)
    payload = dict(reason="already registered", value=None)
    actions.record_diagnostic_event("candidate_excluded", payload)
    payload["reason"] = "mutated later"
    assert emulator.frame_count == actions.actions_executed == len(recorder.trace) == 0
    assert not controller.input_enabled
    assert limiter.attempted_actions == limiter.completed_actions == 0
    record_id = "rnp-diagnostic-" + canonical_sha256(dict(declaration="a" * 64, ordinal=0))
    saved = store.find_sealed_record(record_id, expected_kind="red_native_player_diagnostic").read()
    assert saved == recorder.diagnostic_events[0]
    assert saved["payload"]["reason"] == "already registered"
    assert saved["diagnostic_only"] and not saved["automatic_fit"]


def test_a_safety_stop_is_recorded_even_before_any_encounter_or_input():
    survey = _RouteOneSurveySimulation((16, 19))
    seen = []
    result = run_red_area_survey(
        "wild:Route1:grass",
        survey,
        safety_check=lambda: False,
        record_diagnostic_event=lambda kind, row: seen.append((kind, row)),
    )
    assert result.safety_stopped and result.actions_executed == result.encounters_seen == 0
    assert seen[0][0] == "survey_stopped"
    assert seen[0][1]["reason"] == "safety_check_failed"
    assert result.diagnostic_events[0]["source_id"] == "wild:Route1:grass"


def test_capture_receipts_separate_rejection_failed_attempt_and_verified_capture():
    class Survey(_RouteOneSurveySimulation):
        failed_once = False

        def capture_encounter(self, species_ref):
            if not self.failed_once:
                self.failed_once = True
                self.current_encounter = None
                return False
            return super().capture_encounter(species_ref)

    seen = []
    report = run_red_area_survey(
        "wild:Route1:grass",
        Survey((21, 16, 16, 19)),
        record_diagnostic_event=lambda kind, row: seen.append((kind, row)),
    )
    assert report.passed and report.captures == 2
    assert report.capture_attempts == 3 and report.failed_capture_attempts == 1
    assert report.direct_flees == 1 and report.flees == 2  # Legacy accounting stays unchanged.
    rejected = [
        row
        for kind, row in seen
        if kind == "survey_decision" and row["directive"] == "flee_encounter"
    ]
    assert len(rejected) == 1 and "does not advance" in rejected[0]["reason"]
    assert len([row for kind, row in seen if kind == "capture_verified"]) == 2
    assert len([row for kind, row in seen if kind == "capture_not_retained"]) == 1
    assert len(seen) == len(report.diagnostic_events)


def test_failure_event_survives_missing_survey_report():
    class Broken(_RouteOneSurveySimulation):
        def capture_encounter(self, species_ref):
            raise RedAreaExecutionError("native control failed", reason_code="control_failed")

    events = []
    with pytest.raises(RedAreaExecutionError, match="native control failed"):
        run_red_area_survey(
            "wild:Route1:grass",
            Broken((16,)),
            record_diagnostic_event=lambda kind, row: events.append((kind, row)),
        )
    assert events[-1][0] == "survey_action_failed"
    assert events[-1][1]["operation"] == "capture_encounter"
    assert events[-1][1]["reason_code"] == "control_failed"
    assert events[-1][1]["error_type"] == "RedAreaExecutionError"


@pytest.mark.parametrize("failure", [None, "execute", "verify"])
def test_player_retains_selection_and_timing_even_when_goal_fails(tmp_path, failure):
    output = tmp_path / "run"
    state, snapshot, observe = _environment(
        output, fail=failure == "execute", verify_fails=failure == "verify"
    )
    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=snapshot,
        observe=observe,
        seed=17,
        provenance={},
        maximum_decisions=1,
    )
    diagnostics = json.loads((output / "step-000/selection-diagnostics.json").read_bytes())
    decision = json.loads((output / "step-000/decision.json").read_bytes())
    outcome = result["outcomes"][0]
    assert diagnostics["actual_selection_scores"] == decision["scores"]
    assert state["selected"] == [decision["selected_candidate_index"]]
    assert diagnostics["baseline_head_used_for_selection"]
    assert not diagnostics["training_admission"]
    assert (
        outcome["failure_phase"]
        == {None: None, "execute": "execution", "verify": "verification"}[failure]
    )
    assert all(value is None or value >= 0 for value in outcome["phase_seconds"].values())
    assert (output / "step-000/terminal.state").read_bytes() == b"1"
    np.testing.assert_allclose(
        [row["score"] for row in diagnostics["candidates"] if row["available"]],
        [score for score in decision["scores"] if score is not None],
    )
