import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_native_curriculum import records

from pokemon_red_completion.goal_manager import GoalKind, GoalManagerQuestion
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_native_curriculum import (
    PLAYER_CONTRACT,
    PLAYER_OUTCOME_SCHEMA,
    PLAYER_PLAN_SCHEMA,
    curriculum_projection,
    reconstruct_native_curriculum,
)
from pokemon_red_completion.red_player_lesson import (
    SNAPSHOT_SCHEMA,
    capture_player_lesson_snapshot,
    validate_snapshot,
)


def player_records(tmp_path, kind=GoalKind.ADVANCE_STORY):
    plan, result, question = records(tmp_path)
    question = replace(
        question, opportunities=(replace(question.opportunities[0], kind=kind),
                                 question.opportunities[1]),
    )
    plan.update(schema=PLAYER_PLAN_SCHEMA, contract=PLAYER_CONTRACT, question=_question(question))
    facts = plan["before"]["semantic_observation"]
    count = facts["story"]["target"]
    completed = facts["story"]["completed"]
    catalog = [f"objective-{i:03}" for i in range(count)]
    snapshot = dict(
        schema=SNAPSHOT_SCHEMA, objective_catalog=catalog,
        completed_objectives=catalog[:completed], in_battle=False,
        party=[dict(
            specimen_ref="red-preparation:" + f"{i:064x}", species_id=i + 1,
            level=20, experience=8000, hp=20, max_hp=60, status="paralysis",
            moves=[[1, 5], [2, 3], [0, 0], [0, 0]],
        ) for i in range(facts["party_size"])],
    )
    facts["situation"]["need_pressures"]["safety"] = 1.0
    plan["question"]["situation"]["need_pressures"]["safety"] = 1.0
    target = (
        {"objective": catalog[completed]} if kind is GoalKind.ADVANCE_STORY
        else {"specimen_ref": snapshot["party"][0]["specimen_ref"], "level": 22}
        if kind is GoalKind.DEVELOP_TEAM else {"restoration": "improve_without_regression"}
    )
    plan["player_lesson"] = {"before": snapshot, "target": target}
    terminal = copy.deepcopy(snapshot)
    result.update(schema=PLAYER_OUTCOME_SCHEMA, after=copy.deepcopy(plan["before"]),
                  player_lesson=terminal)
    result["after"]["semantic_observation"]["input_ready"] = True
    if kind is GoalKind.ADVANCE_STORY:
        terminal["completed_objectives"] = catalog[:completed + 1]
        result["after"]["semantic_observation"]["story"]["completed"] += 1
    elif kind is GoalKind.DEVELOP_TEAM:
        terminal["party"][0].update(level=22, experience=10648)
    else:
        terminal["party"][0].update(hp=60, status="healthy")
        result["after"]["semantic_observation"]["situation"]["need_pressures"]["safety"] = (
            1 - 1 / facts["party_size"]
        )
    result["declaration_sha256"] = canonical_sha256(plan)
    return plan, result


def _question(question):
    return dict(schema=question.policy_input["schema"], situation=question.situation.policy_dict(),
                candidates=[o.policy_dict() for o in question.opportunities])


@pytest.mark.parametrize("kind", [GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM,
                                  GoalKind.RESTORE_TEAM])
def test_three_native_lesson_families_reuse_inference_projection(tmp_path, kind):
    plan, result = player_records(tmp_path, kind)
    context, candidate = curriculum_projection(plan)
    row = reconstruct_native_curriculum(plan, result)
    assert row.features == candidate.vector(context, feature_version=4)
    assert row.outcome.verified_success
    assert row.outcome.completion_gain == 0
    assert row.outcome.action_cost > 0
    assert row.public_dict()["comparative_choice"] is False
    assert row.public_dict()["regression_weight"] == 1
    if kind is GoalKind.ADVANCE_STORY:
        assert row.outcome.dependency_unlock_gain > 0
    assert "objective-" not in str(row.public_dict())
    assert "red-preparation:" not in str(row.public_dict())


@pytest.mark.parametrize("kind", [GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM,
                                  GoalKind.RESTORE_TEAM])
def test_failed_lessons_keep_cost_without_inventing_success(tmp_path, kind):
    plan, result = player_records(tmp_path, kind)
    result.update(succeeded=False, after=copy.deepcopy(plan["before"]),
                  player_lesson=copy.deepcopy(plan["player_lesson"]["before"]))
    row = reconstruct_native_curriculum(plan, result)
    assert not row.outcome.verified_success and row.outcome.completion_gain == 0
    assert row.outcome.action_cost > 0
    result["succeeded"] = True
    with pytest.raises(ValueError, match="selected-goal progress"):
        reconstruct_native_curriculum(plan, result)


@pytest.mark.parametrize("mutation", [
    "wrong_objective", "catalog_changed", "already_completed", "bad_counts",
    "substitute", "duplicate_identity", "xp_only", "level_without_xp", "wrong_member",
    "party_count", "heal_with_pp_loss", "new_status", "heal_after_levelup", "battle",
    "unsettled", "intervention", "development", "zero_input", "bool_xp", "extra_field",
])
def test_native_evidence_rejects_false_success(tmp_path, mutation):
    development = {"xp_only", "level_without_xp", "wrong_member", "bool_xp"}
    recovery = {"heal_with_pp_loss", "new_status", "heal_after_levelup"}
    kind = (GoalKind.DEVELOP_TEAM if mutation in development else
            GoalKind.RESTORE_TEAM if mutation in recovery else GoalKind.ADVANCE_STORY)
    plan, result = player_records(tmp_path, kind)
    before = plan["player_lesson"]["before"]
    after = result["player_lesson"]
    if mutation == "wrong_objective":
        # Correct completed count but the selected story objective never happened.
        after["completed_objectives"][-1] = before["objective_catalog"][-1]
    elif mutation == "catalog_changed":
        after["objective_catalog"][-1] = "zzz"
    elif mutation == "already_completed":
        plan["player_lesson"]["target"]["objective"] = before["completed_objectives"][0]
    elif mutation == "bad_counts":
        result["after"]["semantic_observation"]["story"]["completed"] += 1
    elif mutation == "substitute":
        after["party"][0]["specimen_ref"] = "red-preparation:" + "f" * 64
    elif mutation == "duplicate_identity":
        after["party"][1]["specimen_ref"] = after["party"][0]["specimen_ref"]
    elif mutation == "xp_only":
        after["party"][0]["level"] = 20
    elif mutation == "level_without_xp":
        after["party"][0]["experience"] = 8000
    elif mutation == "wrong_member":
        after["party"][0].update(level=20, experience=8000)
        after["party"][1].update(level=22, experience=10648)
    elif mutation == "party_count":
        after["party"].pop()
    elif mutation == "heal_with_pp_loss":
        after["party"][1]["moves"][0][1] -= 1
    elif mutation == "new_status":
        after["party"][1]["status"] = "poison"
    elif mutation == "heal_after_levelup":
        after["party"][0].update(level=21, experience=9261)
    elif mutation == "battle":
        after["in_battle"] = True
    elif mutation == "unsettled":
        result["after"]["semantic_observation"]["input_ready"] = False
    elif mutation == "intervention":
        result["interventions_during_execution"] = ["money"]
    elif mutation == "development":
        plan["source"]["partition"] = "development"
    elif mutation == "zero_input":
        result["trace"] = []
    elif mutation == "bool_xp":
        after["party"][0]["experience"] = True
    else:
        after["cheat"] = True
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises(ValueError):
        reconstruct_native_curriculum(plan, result)


def test_partial_development_and_faint_are_retained_not_promoted(tmp_path):
    plan, result = player_records(tmp_path, GoalKind.DEVELOP_TEAM)
    result["succeeded"] = False
    result["player_lesson"]["party"][0].update(level=21, experience=9261, hp=0)
    row = reconstruct_native_curriculum(plan, result)
    assert not row.outcome.verified_success
    assert row.outcome.action_cost > 0


def test_party_order_is_not_specimen_identity(tmp_path):
    plan, result = player_records(tmp_path, GoalKind.DEVELOP_TEAM)
    result["player_lesson"]["party"].reverse()
    assert reconstruct_native_curriculum(plan, result).outcome.verified_success


def test_live_snapshot_uses_existing_read_only_adapter_and_checks_frame(tmp_path, monkeypatch):
    from test_registered_learning_bridge import observations

    import pokemon_red_completion.red_player_lesson as module
    from pokemon_red_completion.red_registered_observation import project_registered_observation

    runtime, observation, _, policy = observations(tmp_path)
    observation = project_registered_observation(observation, policy)
    party = replace(observation.party, members=tuple(
        replace(m, experience=1000) for m in observation.party.members))
    emulator = SimpleNamespace(frame_count=4)
    refs = tuple("red-preparation:" + f"{i:064x}" for i in range(party.size))
    reader = SimpleNamespace(read=lambda: party, preparation_specimen_refs=lambda: refs)
    monkeypatch.setattr(module, "PokemonRedPartyReader", lambda _: reader)
    adapter = SimpleNamespace(observe=lambda: observation, graph=runtime.adapter.graph)
    harness = SimpleNamespace(emulator=emulator, adapter=adapter)
    returned, snapshot = capture_player_lesson_snapshot(harness)
    assert returned is observation
    assert len(validate_snapshot(snapshot, returned.public_dict())) == party.size

    def changing_read():
        emulator.frame_count += 1
        return party

    reader.read = changing_read
    with pytest.raises(ValueError, match="advanced"):
        capture_player_lesson_snapshot(harness)


def test_wrong_family_cannot_use_new_contract(tmp_path):
    plan, result = player_records(tmp_path)
    q = GoalManagerQuestion.from_policy_input(plan["question"])
    q = replace(q, opportunities=(replace(q.opportunities[0], kind=GoalKind.ACQUIRE_SPECIES),
                                   q.opportunities[1]))
    plan["question"] = _question(q)
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises(ValueError, match="declaration scope"):
        reconstruct_native_curriculum(plan, result)


@pytest.mark.parametrize("kind", [GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM,
                                  GoalKind.RESTORE_TEAM])
def test_new_lessons_fit_and_survive_incremental_reauthentication(tmp_path, monkeypatch, kind):
    import test_red_native_curriculum as original

    def factory(path):
        plan, result = player_records(path, kind)
        return plan, result, None

    monkeypatch.setattr(original, "records", factory)
    original.test_player_updates_authenticate_and_retain_native_lessons(tmp_path, monkeypatch)
