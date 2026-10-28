import copy
from dataclasses import replace

import pytest
from test_red_player_lesson import player_records

from pokemon_red_completion.goal_manager import GoalKind, GoalManagerQuestion
from pokemon_red_completion.goal_manager_composition_runtime import GoalManagerCompositionError
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote, GoalResourceReserve
from pokemon_red_completion.player_readiness import PlayerReadiness
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_native_curriculum import (
    READINESS_CONTRACT,
    READINESS_PLAN_SCHEMA,
    RESOURCE_CONTRACT,
    RESOURCE_OUTCOME_SCHEMA,
    RESOURCE_PLAN_SCHEMA,
    curriculum_projection,
    reconstruct_native_curriculum,
)
from pokemon_red_completion.red_player_economy import snapshot_document
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def records(tmp_path, kind=GoalKind.RESUPPLY, *, earn=False):
    from test_party_preparation import team
    from test_post_battle_strategy import aftermath

    from pokemon_red_completion.post_battle_strategy import context_after_recovery

    plan, result = player_records(tmp_path, GoalKind.RESUPPLY)
    quote = (GoalResourceQuote(3000, 0, (), expected_income=200) if earn else
             GoalResourceQuote(3000, 1000, (GoalResourceReserve("capture", 0, 5, 5),)))
    q = GoalManagerQuestion.from_policy_input(plan["question"])
    q = replace(q, opportunities=(replace(q.opportunities[0], kind=kind,
        resource_quote=quote if kind is GoalKind.RESUPPLY else None), *q.opportunities[1:]))
    plan.update(schema=RESOURCE_PLAN_SCHEMA, contract=RESOURCE_CONTRACT,
        question=dict(schema=q.policy_input["schema"], situation=q.situation.policy_dict(),
                      candidates=[o.policy_dict() for o in q.opportunities]),
        readiness=PlayerReadiness.from_context(
            context_after_recovery(aftermath(), team(20)), (1.,)*5).public_dict())
    plan["player_lesson"]["target"] = {"resource": (
        "native_acquisition" if kind is GoalKind.ACQUIRE_SPECIES else
        "earn_cash" if earn else "purchase_stock")}
    plan["before"]["semantic_observation"]["capture_item_count"] = 0
    plan["before"]["semantic_observation"]["recovery_item_count"] = 0
    result.update(schema=RESOURCE_OUTCOME_SCHEMA, after=copy.deepcopy(plan["before"]),
                  player_lesson=copy.deepcopy(plan["player_lesson"]["before"]))
    result["after"]["semantic_observation"]["input_ready"] = True
    if kind is GoalKind.ACQUIRE_SPECIES:
        from test_red_native_curriculum import records as acquisition_records

        _, acquisition, _ = acquisition_records(tmp_path / "acquisition")
        result["after"]["registration"] = acquisition["after"]["registration"]
        result["after"]["semantic_observation"]["collection"] = (
            acquisition["after"]["semantic_observation"]["collection"])
        terminal = EconomySnapshot(3000, ())
    else:
        terminal = (EconomySnapshot(3200, ()) if earn
                    else EconomySnapshot(2000, (("red-item-004", 5),)))
        result["after"]["semantic_observation"]["capture_item_count"] = 0 if earn else 5
    result["economy_after"] = snapshot_document(terminal)
    result["declaration_sha256"] = canonical_sha256(plan)
    return plan, result


@pytest.mark.parametrize("earn", [False, True])
def test_native_resource_rows_include_only_measured_economy(tmp_path, earn):
    plan, result = records(tmp_path, earn=earn)
    row = reconstruct_native_curriculum(plan, result)
    assert row.feature_version == 5 and row.outcome.verified_success
    assert row.outcome.economy.cash_delta == (200 if earn else -1000)
    assert row.outcome.economy.net_item_increase == (0 if earn else 5)
    assert row.public_dict()["comparative_choice"] is False
    assert row.outcome.action_cost > 0


def test_acquisition_readiness_and_economy_use_existing_registration_proof(tmp_path):
    plan, result = records(tmp_path, GoalKind.ACQUIRE_SPECIES)
    row = reconstruct_native_curriculum(plan, result)
    assert row.outcome.verified_success and row.outcome.completion_gain > 0
    assert row.outcome.economy.cash_delta == 0
    result["after"] = copy.deepcopy(plan["before"])
    with pytest.raises(GoalManagerCompositionError):
        reconstruct_native_curriculum(plan, result)


@pytest.mark.parametrize("mutation", ["cash", "stock", "kind", "target", "quote", "party"])
def test_resource_success_cannot_be_fabricated(tmp_path, mutation):
    plan, result = records(tmp_path)
    if mutation == "cash":
        result["economy_after"]["cash"] += 1
    elif mutation == "stock":
        result["economy_after"]["inventory"][0][1] = 4
    elif mutation == "kind":
        result["after"]["semantic_observation"]["capture_item_count"] = 0
    elif mutation == "target":
        plan["player_lesson"]["target"] = {"resource": "earn_cash"}
    elif mutation == "quote":
        plan["economy_before"]["cash"] = 2999
    else:
        result["player_lesson"]["party"][0]["experience"] -= 1
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises(ValueError):
        reconstruct_native_curriculum(plan, result)


def test_failed_settled_purchase_keeps_actual_cash_loss(tmp_path):
    plan, result = records(tmp_path)
    result["succeeded"] = False
    result["economy_after"] = snapshot_document(EconomySnapshot(2500, ()))
    result["after"] = copy.deepcopy(plan["before"])
    row = reconstruct_native_curriculum(plan, result)
    assert not row.outcome.verified_success and row.outcome.economy.cash_delta == -500


def test_old_readiness_contract_still_refuses_resource_kind(tmp_path):
    plan, _ = records(tmp_path)
    plan.update(schema=READINESS_PLAN_SCHEMA, contract=READINESS_CONTRACT)
    with pytest.raises(ValueError, match="declaration scope"):
        curriculum_projection(plan)
