import copy
from types import SimpleNamespace as N

import pytest
from test_player_readiness import records

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import EVENT_FLAG_BYTES
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_native_curriculum import (
    STORY_UNIT_CONTRACT,
    STORY_UNIT_OUTCOME_SCHEMA,
    STORY_UNIT_PLAN_SCHEMA,
    reconstruct_native_curriculum,
)
from pokemon_red_completion.red_player_story_unit import capture_story_unit


def unit_records(tmp_path, kind=GoalKind.ADVANCE_STORY, *, arrival=False):
    assert kind is GoalKind.ADVANCE_STORY
    plan, result = records(tmp_path)
    result["after"] = copy.deepcopy(plan["before"])
    result["after"]["semantic_observation"]["input_ready"] = True
    result["player_lesson"] = copy.deepcopy(plan["player_lesson"]["before"])
    target = (
        dict(kind="arrival", map_id=88, at=[4, 1])
        if arrival
        else dict(kind="events", map_id=88, events=[1360, 1371, 1373])
    )
    opening = dict(map_id=3 if arrival else 88, at=[2, 2], events=[] if arrival else [False] * 3)
    terminal = dict(map_id=88, at=[4, 1], events=[] if arrival else [True] * 3)
    plan.update(
        schema=STORY_UNIT_PLAN_SCHEMA,
        contract=STORY_UNIT_CONTRACT,
        challenge=OptionChallenge(False, False, 0.0, 0.0, 0.0).public_dict(),
        story_unit=dict(target=target, before=opening),
    )
    result.update(
        schema=STORY_UNIT_OUTCOME_SCHEMA,
        story_unit=terminal,
        declaration_sha256=canonical_sha256(plan),
    )
    return plan, result


@pytest.mark.parametrize("arrival", [False, True])
def test_incremental_success_is_not_whole_quest_or_registration_credit(tmp_path, arrival):
    plan, result = unit_records(tmp_path, arrival=arrival)
    row = reconstruct_native_curriculum(plan, result)
    assert row.feature_version == 6 and row.outcome.verified_success
    assert row.outcome.completion_gain == row.outcome.dependency_unlock_gain == 0
    assert row.outcome.action_cost > 0
    assert (
        result["player_lesson"]["completed_objectives"]
        == plan["player_lesson"]["before"]["completed_objectives"]
    )
    assert "map_id" not in str(row.public_dict()) and "objective-" not in str(row.public_dict())


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_event",
        "wrong_map",
        "same_arrival",
        "wrong_at",
        "already_complete",
        "missing_proof",
        "extra_field",
        "bool_event",
        "event_outside_ram",
        "event_integer",
        "unsettled",
        "battle",
        "wrong_kind",
        "lost_prerequisite",
        "substitution",
        "old_schema",
    ],
)
def test_endpoint_falsifiers(tmp_path, mutation):
    plan, result = unit_records(tmp_path, arrival=mutation in {"same_arrival", "wrong_at"})
    target, before = plan["story_unit"]["target"], plan["story_unit"]["before"]
    after = result["story_unit"]
    if mutation == "missing_event":
        after["events"][1] = False
    elif mutation == "wrong_map":
        after["map_id"] = 3
    elif mutation == "same_arrival":
        before.update(copy.deepcopy(after))
    elif mutation == "wrong_at":
        after["at"] = [3, 1]
    elif mutation == "already_complete":
        before["events"] = [True] * 3
    elif mutation == "missing_proof":
        result.pop("story_unit")
    elif mutation == "extra_field":
        target["preferred"] = True
    elif mutation == "bool_event":
        target["events"] = [True]
    elif mutation == "event_outside_ram":
        target["events"] = [EVENT_FLAG_BYTES * 8]
    elif mutation == "event_integer":
        after["events"][0] = 1
    elif mutation == "unsettled":
        result["after"]["semantic_observation"]["input_ready"] = False
    elif mutation == "battle":
        result["player_lesson"]["in_battle"] = True
    elif mutation == "wrong_kind":
        plan["question"]["candidates"][0]["kind"] = GoalKind.RESTORE_TEAM.value
    elif mutation == "lost_prerequisite":
        before["events"][0] = True
        after["events"][0] = False
        result["succeeded"] = False
    elif mutation == "substitution":
        result["player_lesson"]["party"][0]["species_id"] += 1
    else:
        from pokemon_red_completion.red_native_curriculum import (
            CHALLENGE_CONTRACT,
            CHALLENGE_PLAN_SCHEMA,
        )

        plan.update(schema=CHALLENGE_PLAN_SCHEMA, contract=CHALLENGE_CONTRACT)
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises(ValueError):
        reconstruct_native_curriculum(plan, result)


def test_failure_keeps_partial_event_and_cost_not_success(tmp_path):
    plan, result = unit_records(tmp_path)
    result["succeeded"] = False
    result["story_unit"]["events"] = [True, False, False]
    row = reconstruct_native_curriculum(plan, result)
    assert not row.outcome.verified_success and row.outcome.action_cost > 0
    assert row.outcome.dependency_unlock_gain == 0


@pytest.mark.parametrize("fault", [None, "missing", "mutate"])
def test_capture_reads_declared_bits_without_input(fault):
    em = N(frame_count=0, save_state_bytes=lambda: str(em.frame_count).encode())
    flags = bytes([2]) + bytes(EVENT_FLAG_BYTES - 1)

    def read():
        if fault == "mutate":
            em.frame_count += 1
        return N(
            map_id=88, player_y=4, player_x=1, event_flags=None if fault == "missing" else flags
        )

    rt = N(emulator=em, reader=N(read=read))
    target = dict(kind="events", map_id=88, events=[0, 1])
    if fault:
        with pytest.raises(ValueError):
            capture_story_unit(rt, target)
    else:
        assert capture_story_unit(rt, target) == dict(map_id=88, at=[4, 1], events=[False, True])


def test_recorder_publishes_incremental_proof_and_readmits_it(tmp_path, monkeypatch):
    from test_red_player_lesson_runtime import fixture

    import pokemon_red_completion.red_player_lesson_runtime as runtime
    import pokemon_red_completion.red_player_story_unit as unit
    from pokemon_red_completion.red_native_curriculum import (
        NativeCurriculumInput,
        load_native_curriculum,
    )

    store, emulator, kwargs = fixture(tmp_path, monkeypatch, record_factory=unit_records)
    kwargs["observe_challenge"] = lambda *args: OptionChallenge(False, False, 0.0, 0.0, 0.0)
    kwargs["story_unit_target"] = dict(kind="events", map_id=88, events=[1360, 1371, 1373])
    monkeypatch.setattr(
        unit,
        "capture_story_unit",
        lambda rt, target: dict(map_id=88, at=[4, 1], events=[bool(emulator.frame_count)] * 3),
    )
    preflight = runtime.record_native_player_lesson(store, **kwargs, preflight_only=True)
    assert preflight["input_frames"] == 0
    actual = runtime.record_native_player_lesson(store, **kwargs)
    assert actual["admitted"] and actual["succeeded"]
    row = load_native_curriculum(store, NativeCurriculumInput(**actual["outcome"]))
    assert row.outcome.verified_success and row.outcome.dependency_unlock_gain == 0


def test_incremental_rows_fit_and_reauthenticate(tmp_path, monkeypatch):
    import test_red_native_curriculum as original

    def factory(path):
        plan, result = unit_records(path)
        return plan, result, None

    monkeypatch.setattr(original, "records", factory)
    original.test_player_updates_authenticate_and_retain_native_lessons(tmp_path, monkeypatch)
