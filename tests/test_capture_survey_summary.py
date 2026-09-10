from __future__ import annotations

from dataclasses import replace

import pytest
from test_bounded_player_episode import _complete, _Meter, _observer, _trajectory

from pokemon_red_completion.bounded_player_episode import (
    BoundedPlayerStep,
    run_bounded_player_episode,
)
from pokemon_red_completion.capture_survey import (
    ALLOWED_SEARCH_STOP_REASON,
    MAX_SEMANTIC_ACTIONS,
    MAX_SURVEY_COUNT,
    CaptureSurveySummary,
)
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_runtime import CompletionFirstGoalTeacher

VALID_SURVEY: dict[str, object] = {
    "semantic_actions": 42,
    "encounters_seen": 5,
    "captures": 2,
    "flees": 3,
    "search_exhausted": False,
    "safety_stopped": False,
}

VALID_STOP_SURVEY: dict[str, object] = {
    **VALID_SURVEY,
    "search_exhausted": True,
    "safety_stopped": False,
    "search_stop_reason": ALLOWED_SEARCH_STOP_REASON,
}


def test_capture_survey_summary_preserves_valid_fields_and_dict() -> None:
    evidence = {"capture_survey": VALID_SURVEY}
    summary = CaptureSurveySummary.from_evidence(evidence)
    assert summary is not None
    assert summary.semantic_actions == 42
    assert summary.encounters_seen == 5
    assert summary.captures == 2
    assert summary.flees == 3
    assert summary.search_exhausted is False
    assert summary.safety_stopped is False
    assert summary.search_stop_reason is None
    assert summary.public_dict() == VALID_SURVEY

    direct = CaptureSurveySummary(**VALID_SURVEY)  # type: ignore[arg-type]
    assert direct == summary
    assert direct.search_stop_reason is None
    assert direct.public_dict() == VALID_SURVEY


def test_generic_red_exploration_report_stays_none() -> None:
    explore_evidence = {
        "bounded": True,
        "encounters_seen": 5,
        "new_sighting_count": 1,
        "captures": 0,
    }
    assert CaptureSurveySummary.from_evidence(explore_evidence) is None


def test_missing_or_none_marker_returns_none() -> None:
    assert CaptureSurveySummary.from_evidence({}) is None
    assert CaptureSurveySummary.from_evidence({"capture_survey": None}) is None
    assert (
        CaptureSurveySummary.from_evidence(
            {"fail": False, "whole_party_restore": True}
        )
        is None
    )
    assert (
        CaptureSurveySummary.from_evidence(
            {
                "capture_support": {
                    "status_attempts": 1,
                    "verified_status_observations": 1,
                    "party_preparations": 0,
                }
            }
        )
        is None
    )


def test_outer_flat_fields_are_ignored_and_not_merged() -> None:
    evidence = {
        "bounded": True,
        "encounters_seen": 999,
        "captures": 999,
        "search_stop_reason": ALLOWED_SEARCH_STOP_REASON,
        "capture_survey": VALID_SURVEY,
    }
    summary = CaptureSurveySummary.from_evidence(evidence)
    assert summary is not None
    assert summary.encounters_seen == 5
    assert summary.captures == 2
    assert summary.search_stop_reason is None
    assert "search_stop_reason" not in summary.public_dict()


@pytest.mark.parametrize(
    ("search_exhausted", "safety_stopped"),
    [
        (False, False),
        (True, False),
        (False, True),
        (True, True),
    ],
)
def test_flags_distinguish_false_and_true(
    search_exhausted: bool, safety_stopped: bool
) -> None:
    data = {
        **VALID_SURVEY,
        "search_exhausted": search_exhausted,
        "safety_stopped": safety_stopped,
    }
    summary = CaptureSurveySummary.from_evidence({"capture_survey": data})
    assert summary is not None
    assert type(summary.search_exhausted) is bool
    assert type(summary.safety_stopped) is bool
    assert summary.search_exhausted is search_exhausted
    assert summary.safety_stopped is safety_stopped
    assert summary.public_dict()["search_exhausted"] is search_exhausted
    assert summary.public_dict()["safety_stopped"] is safety_stopped


@pytest.mark.parametrize(
    ("actions", "encounters", "captures", "flees"),
    [
        (0, 0, 0, 0),
        (100, 15, 3, 12),
        (0, 5, 0, 2),
        (1, 1, 1, 0),
    ],
)
def test_counters_distinguish_zero_and_positive(
    actions: int, encounters: int, captures: int, flees: int
) -> None:
    data = {
        "semantic_actions": actions,
        "encounters_seen": encounters,
        "captures": captures,
        "flees": flees,
        "search_exhausted": False,
        "safety_stopped": False,
    }
    summary = CaptureSurveySummary.from_evidence({"capture_survey": data})
    assert summary is not None
    assert (
        summary.semantic_actions,
        summary.encounters_seen,
        summary.captures,
        summary.flees,
    ) == (actions, encounters, captures, flees)
    assert summary.public_dict() == data


@pytest.mark.parametrize(
    ("encounters", "captures", "flees"),
    [
        (0, 1, 0),
        (0, 0, 1),
        (5, 3, 3),
        (10, 8, 3),
    ],
)
def test_rejects_captures_and_flees_exceeding_encounters(
    encounters: int, captures: int, flees: int
) -> None:
    data = {
        **VALID_SURVEY,
        "encounters_seen": encounters,
        "captures": captures,
        "flees": flees,
    }
    with pytest.raises(ValueError, match="cannot exceed encounters"):
        CaptureSurveySummary(**data)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="cannot exceed encounters"):
        CaptureSurveySummary.from_evidence({"capture_survey": data})


@pytest.mark.parametrize(
    ("search_exhausted", "safety_stopped"),
    [
        (False, False),
        (False, True),
        (True, True),
    ],
)
def test_cause_requires_search_exhausted_and_not_safety_stopped(
    search_exhausted: bool, safety_stopped: bool
) -> None:
    data = {
        **VALID_SURVEY,
        "search_exhausted": search_exhausted,
        "safety_stopped": safety_stopped,
        "search_stop_reason": ALLOWED_SEARCH_STOP_REASON,
    }
    with pytest.raises(ValueError, match="search_stop_reason requires"):
        CaptureSurveySummary(**data)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="search_stop_reason requires"):
        CaptureSurveySummary.from_evidence({"capture_survey": data})


@pytest.mark.parametrize(
    "field",
    ["semantic_actions", "encounters_seen", "captures", "flees"],
)
@pytest.mark.parametrize("bool_val", [True, False])
def test_rejects_bool_as_int(field: str, bool_val: bool) -> None:
    data = {**VALID_SURVEY, field: bool_val}
    with pytest.raises(ValueError):
        CaptureSurveySummary.from_evidence({"capture_survey": data})
    with pytest.raises(ValueError):
        CaptureSurveySummary(**data)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("semantic_actions", -1),
        ("semantic_actions", MAX_SEMANTIC_ACTIONS + 1),
        ("encounters_seen", -1),
        ("encounters_seen", MAX_SURVEY_COUNT + 1),
        ("captures", -1),
        ("captures", MAX_SURVEY_COUNT + 1),
        ("flees", -1),
        ("flees", MAX_SURVEY_COUNT + 1),
    ],
)
def test_rejects_negative_and_oversized_counts(
    field: str, bad_value: int
) -> None:
    data = {**VALID_SURVEY, field: bad_value}
    with pytest.raises(ValueError):
        CaptureSurveySummary.from_evidence({"capture_survey": data})
    with pytest.raises(ValueError):
        CaptureSurveySummary(**data)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["search_exhausted", "safety_stopped"])
@pytest.mark.parametrize("bad_val", [0, 1, "True", "False", None, 1.0])
def test_rejects_non_bool_for_flags(field: str, bad_val: object) -> None:
    data = {**VALID_SURVEY, field: bad_val}
    with pytest.raises(ValueError):
        CaptureSurveySummary.from_evidence({"capture_survey": data})
    with pytest.raises(ValueError):
        CaptureSurveySummary(**data)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "extra_key",
    [
        "private_path",
        "species_ref",
        "source_id",
        "raw_exception",
        "bounded",
        "initial_missing",
    ],
)
def test_rejects_unknown_keys_inside_marked_mapping(extra_key: str) -> None:
    data = {**VALID_SURVEY, extra_key: "disallowed"}
    with pytest.raises(ValueError, match="differ from required contract"):
        CaptureSurveySummary.from_evidence({"capture_survey": data})


@pytest.mark.parametrize(
    "missing_field",
    [
        "semantic_actions",
        "encounters_seen",
        "captures",
        "flees",
        "search_exhausted",
        "safety_stopped",
    ],
)
def test_partial_survey_evidence_fails_closed(missing_field: str) -> None:
    partial = {k: v for k, v in VALID_SURVEY.items() if k != missing_field}
    with pytest.raises(ValueError, match="differ from required contract"):
        CaptureSurveySummary.from_evidence({"capture_survey": partial})


def test_malformed_survey_evidence_fails_closed() -> None:
    with pytest.raises(ValueError):
        CaptureSurveySummary.from_evidence({"capture_survey": {}})
    with pytest.raises(ValueError):
        CaptureSurveySummary.from_evidence({"capture_survey": "not-a-mapping"})
    with pytest.raises(ValueError):
        CaptureSurveySummary.from_evidence({"capture_survey": [1, 2, 3]})
    with pytest.raises(TypeError):
        CaptureSurveySummary.from_evidence("not-a-mapping")  # type: ignore[arg-type]


def test_search_stop_reason_allowlist() -> None:
    summary = CaptureSurveySummary.from_evidence(
        {"capture_survey": VALID_STOP_SURVEY}
    )
    assert summary is not None
    assert summary.search_stop_reason == ALLOWED_SEARCH_STOP_REASON
    assert (
        summary.public_dict()["search_stop_reason"]
        == ALLOWED_SEARCH_STOP_REASON
    )

    # Absent search_stop_reason is omitted from public_dict
    without_stop = CaptureSurveySummary.from_evidence(
        {"capture_survey": VALID_SURVEY}
    )
    assert without_stop is not None
    assert without_stop.search_stop_reason is None
    assert "search_stop_reason" not in without_stop.public_dict()

    # search_exhausted=True does NOT infer search_stop_reason
    exhausted_no_reason = {
        **VALID_SURVEY,
        "search_exhausted": True,
        "safety_stopped": False,
    }
    exhausted_summary = CaptureSurveySummary.from_evidence(
        {"capture_survey": exhausted_no_reason}
    )
    assert exhausted_summary is not None
    assert exhausted_summary.search_exhausted is True
    assert exhausted_summary.search_stop_reason is None
    assert "search_stop_reason" not in exhausted_summary.public_dict()


@pytest.mark.parametrize(
    "bad_reason",
    [
        "search_exhausted",
        "timeout",
        "survey_leg_limit",
        "leg_limit_exceeded",
        123,
        True,
    ],
)
def test_rejects_unallowlisted_search_stop_reason(bad_reason: object) -> None:
    data = {
        **VALID_SURVEY,
        "search_exhausted": True,
        "safety_stopped": False,
        "search_stop_reason": bad_reason,
    }
    with pytest.raises(ValueError):
        CaptureSurveySummary.from_evidence({"capture_survey": data})
    with pytest.raises(ValueError):
        CaptureSurveySummary(**data)  # type: ignore[arg-type]


def test_search_stop_reason_explicit_none_in_evidence_is_rejected() -> None:
    data = {
        **VALID_SURVEY,
        "search_exhausted": True,
        "safety_stopped": False,
        "search_stop_reason": None,
    }
    with pytest.raises(ValueError):
        CaptureSurveySummary.from_evidence({"capture_survey": data})
    # Constructor accepts documented None default (means omitted)
    direct = CaptureSurveySummary(**data)  # type: ignore[arg-type]
    assert direct.search_stop_reason is None


def test_bounded_player_step_public_dict_preserves_optional_capture_survey() -> None:
    observe, _, _ = _observer(fail_first=False)
    obs = observe()
    step_without = BoundedPlayerStep(
        decision_ordinal=1,
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        status=GoalDecisionOutcome.SUCCEEDED,
        failure_reason=None,
        recovery_attempt=False,
        available_goal_count=2,
        actions_executed=5,
        frames_executed=50,
        semantic_state_changed=True,
        policy_context_sha256="a" * 64,
        available_menu_sha256="b" * 64,
        collection_before=obs.collection,
        collection_after=obs.collection,
        capture_survey=None,
    )
    assert "capture_survey" not in step_without.public_dict()

    survey_summary = CaptureSurveySummary.from_evidence(
        {"capture_survey": VALID_SURVEY}
    )
    step_with = replace(step_without, capture_survey=survey_summary)
    assert step_with.public_dict()["capture_survey"] == VALID_SURVEY


def test_bounded_player_episode_populates_capture_survey_from_execution_report() -> None:
    observe, meter, state = _observer(fail_first=False)

    def enriched() -> object:
        observation = observe()
        bindings = []
        for binding in observation.binding_set.bindings:

            def execute(original=binding.execute):
                report = original()
                return replace(
                    report,
                    evidence={
                        **report.evidence,
                        "capture_survey": VALID_STOP_SURVEY,
                        "capture_support": {
                            "status_attempts": 1, "verified_status_observations": 1,
                            "party_preparations": 0, "prepared_throws": 3,
                            "prepared_asleep": 0, "prepared_paralyzed": 0,
                            "prepared_full_hp": 3,
                        },
                        "unrelated_extra": "should_be_ignored",
                    },
                )

            bindings.append(replace(binding, execute=execute))
        return replace(
            observation,
            binding_set=replace(observation.binding_set, bindings=tuple(bindings)),
        )

    trajectory, _ = _trajectory()
    result = run_bounded_player_episode(
        authority=CompletionFirstGoalTeacher(),
        authority_id="survey-diagnostic-test",
        observe=enriched,  # type: ignore[arg-type]
        budget_meter=_Meter(state),
        trajectory=trajectory,
        completion_satisfied=_complete,
    )

    assert len(result.steps) == 2
    for step in result.steps:
        assert step.capture_survey is not None
        assert step.capture_survey.public_dict() == VALID_STOP_SURVEY
        assert step.public_dict()["capture_survey"] == VALID_STOP_SURVEY
        assert step.public_dict()['capture_support']['prepared_throws'] == 3
        assert step.public_dict()['capture_support']['prepared_asleep'] == 0
        assert step.public_dict()['capture_support']['verified_status_observations'] == 1

    # Plain run without survey evidence leaves capture_survey as None
    plain_trajectory, _ = _trajectory()
    plain_observe, plain_meter, plain_state = _observer(fail_first=False)
    plain_result = run_bounded_player_episode(
        authority=CompletionFirstGoalTeacher(),
        authority_id="survey-diagnostic-plain-test",
        observe=plain_observe,
        budget_meter=_Meter(plain_state),
        trajectory=plain_trajectory,
        completion_satisfied=_complete,
    )
    for step in plain_result.steps:
        assert step.capture_survey is None
        assert "capture_survey" not in step.public_dict()
