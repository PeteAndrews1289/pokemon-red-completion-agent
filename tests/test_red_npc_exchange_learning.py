import copy
from dataclasses import asdict, replace

import pytest
from test_private_artifacts import _make_store
from test_red_native_curriculum import records
from test_red_npc_trade import TRADE
from test_registered_learning_bridge import observations

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_runtime import GoalManagerCompositionError
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import red_species_ref as ref
from pokemon_red_completion.red_native_curriculum import (
    EXCHANGE_CONTRACT,
    EXCHANGE_OUTCOME_SCHEMA,
    EXCHANGE_PLAN_SCHEMA,
    publish_declaration,
    publish_outcome,
    reconstruct_native_curriculum,
    retained_native_curriculum,
)
from pokemon_red_completion.red_npc_exchange_learning import ROM_SHA256, SCHEMA, exchange_snapshot
from pokemon_red_completion.red_player_economy import snapshot_document
from pokemon_red_completion.red_registered_observation import project_registered_observation
from pokemon_red_completion.red_registered_outcome import red_registered_outcome_from_observations
from pokemon_red_completion.red_resource_economy import red_economy_snapshot


def exchange_records(tmp_path, trade=TRADE, *, inherited=()):
    plan, result, _ = records(tmp_path / "template")
    _, before, _, policy = observations(tmp_path / "exchange", inherited=inherited)
    specimen = replace(
        before.collection_observation.specimens[-1],
        species_ref=ref(trade.give),
        level=10,
        slot_index=10,
    )
    before = replace(
        before,
        collection_observation=replace(
            before.collection_observation,
            specimens=(*before.collection_observation.specimens, specimen),
            owned_species=before.collection_observation.owned_species | {ref(trade.give)},
        ),
    )
    before = project_registered_observation(before, policy)
    after = project_registered_observation(
        replace(
            before,
            raw=replace(before.raw, map_id=trade.map_id),
            collection_observation=replace(
                before.collection_observation,
                specimens=(
                    *before.collection_observation.specimens[:-1],
                    replace(specimen, species_ref=ref(trade.receive)),
                ),
                owned_species=before.collection_observation.owned_species | {ref(trade.receive)},
            ),
        ),
        policy,
    )
    offer = asdict(trade)
    offer["at"] = list(offer["at"])
    plan.update(
        schema=EXCHANGE_PLAN_SCHEMA,
        contract=EXCHANGE_CONTRACT,
        before=before.public_dict(),
        npc_exchange=dict(
            schema=SCHEMA,
            rom_sha256=ROM_SHA256,
            offer=offer,
            level=10,
            before=exchange_snapshot(before, {4}),
        ),
    )
    plan["question"]["situation"] = before.situation.policy_dict()
    plan["economy_before"] = snapshot_document(red_economy_snapshot(before.raw))
    result.update(
        schema=EXCHANGE_OUTCOME_SCHEMA,
        declaration_sha256=canonical_sha256(plan),
        after=after.public_dict(),
        npc_exchange=exchange_snapshot(after, {4, trade.index}),
    )
    return plan, result


@pytest.mark.parametrize(
    "trade",
    [
        TRADE,
        replace(
            TRADE,
            index=6,
            give=61,
            receive=124,
            map_id=63,
            picture_id=11,
            at=(2, 1),
            town=3,
            center=64,
        ),
    ],
)
def test_typed_exchange_retains_native_lessons_without_relaxing_capture(tmp_path, trade):
    plan, result = exchange_records(tmp_path / "fixture", trade)
    with pytest.raises(GoalManagerCompositionError, match="undeclared specimen"):
        red_registered_outcome_from_observations(
            plan["before"],
            result["after"],
            selected_kind=GoalKind.ACQUIRE_SPECIES,
            succeeded=True,
            actions=1,
            frames=100,
            maximum_actions=1000,
            maximum_frames=80000,
        )
    row = reconstruct_native_curriculum(plan, result)
    assert row.outcome.verified_success and row.outcome.completion_gain == pytest.approx(1 / 124)
    assert row.outcome.irreversible_loss == 0
    assert row.public_dict()["regression_weight"] == 1
    _, _, store = _make_store(tmp_path)
    item = publish_outcome(store, publish_declaration(store, plan), result)
    items, lessons = retained_native_curriculum(store, {"native_curriculum": [item.public_dict()]})
    assert items == (item,) and lessons == (row,)


def test_inherited_target_is_not_new_shared_credit(tmp_path):
    plan, result = exchange_records(tmp_path, inherited=(122,))
    assert reconstruct_native_curriculum(plan, result).outcome.completion_gain == 0


@pytest.mark.parametrize(
    "damage",
    [
        "rom",
        "offer",
        "offer_bool",
        "level",
        "level_bool",
        "stock",
        "extra_stock",
        "stock_level",
        "stock_count_bool",
        "missing_flag",
        "extra_flag",
        "flag_bool",
        "used_flag",
        "cash",
        "bag",
        "battle",
        "ready",
        "map",
        "binding",
        "scope",
        "development",
        "source_development",
        "legacy_schema",
        "legacy_plan",
        "unexecuted",
        "intervention",
        "audit",
        "failed",
        "before_stock",
        "extra_receipt",
        "extra_declaration",
    ],
)
def test_counterfeit_exchange_fails_closed(tmp_path, damage):
    plan, result = exchange_records(tmp_path)
    declaration, witness = plan["npc_exchange"], result["npc_exchange"]
    if damage == "rom":
        declaration["rom_sha256"] = "0" * 64
    elif damage == "offer":
        declaration["offer"]["receive"] = 150
    elif damage == "offer_bool":
        declaration["offer"]["index"] = True
    elif damage == "level":
        declaration["level"] = 11
    elif damage == "level_bool":
        declaration["level"] = True
    elif damage == "stock":
        witness["stock"] = declaration["before"]["stock"]
    elif damage == "extra_stock":
        witness["stock"].append(witness["stock"][-1])
    elif damage == "stock_level":
        witness["stock"][-1][1] += 1
    elif damage == "stock_count_bool":
        witness["stock"][-1][2] = True
    elif damage == "missing_flag":
        witness["flags"] = [4]
    elif damage == "extra_flag":
        witness["flags"] = [1, 4, 6]
    elif damage == "flag_bool":
        witness["flags"] = [True, 4]
    elif damage == "used_flag":
        declaration["before"]["flags"] = [1, 4]
    elif damage == "cash":
        witness["cash"] += 1
    elif damage == "bag":
        witness["bag"] = [[1, 99]]
    elif damage == "battle":
        witness["battle"] = 1
    elif damage == "ready":
        witness["ready"] = False
    elif damage == "map":
        witness["map_id"] = 1
    elif damage == "binding":
        result["after"]["registration"]["binding_sha256"] = "0" * 64
    elif damage == "scope":
        plan["contract"] = "registered-native-teacher-unit-outcome-v1"
    elif damage == "development":
        plan["partition"] = "development"
    elif damage == "source_development":
        plan["source"]["partition"] = "development"
    elif damage == "legacy_schema":
        result["schema"] = "pokemon.red.native-curriculum-outcome.v1"
    elif damage == "legacy_plan":
        plan["schema"] = "pokemon.red.native-curriculum-declaration.v1"
    elif damage == "unexecuted":
        result["trace"] = []
    elif damage == "intervention":
        result["interventions_during_execution"] = ["money"]
    elif damage == "audit":
        result["native_audit"]["passed"] = False
    elif damage == "failed":
        result["succeeded"] = False
    elif damage == "before_stock":
        declaration["before"]["stock"] = []
    elif damage == "extra_receipt":
        witness["cheat"] = True
    elif damage == "extra_declaration":
        declaration["cheat"] = True
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises((ValueError, GoalManagerCompositionError)):
        reconstruct_native_curriculum(plan, result)


def test_exchange_receipt_is_not_a_policy_feature(tmp_path):
    from pokemon_red_completion.red_native_curriculum import curriculum_projection

    plan, _ = exchange_records(tmp_path)
    old_context, old_candidate = curriculum_projection(plan)
    modified = copy.deepcopy(plan)
    modified["npc_exchange"]["before"]["flags"] = [3]
    context, candidate = curriculum_projection(modified)
    assert old_context == context and old_candidate == candidate


def test_exchange_lessons_survive_incremental_fit_and_reauthentication(tmp_path, monkeypatch):
    import test_red_native_curriculum as native_tests

    monkeypatch.setattr(native_tests, "records", lambda path: (*exchange_records(path), None))
    native_tests.test_player_updates_authenticate_and_retain_native_lessons(tmp_path, monkeypatch)


def test_protected_source_and_conflicting_economy_are_rejected(tmp_path):
    plan, result = exchange_records(tmp_path)
    plan["economy_before"]["cash"] += 1
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises(ValueError, match="economy differs"):
        reconstruct_native_curriculum(plan, result)
    plan["economy_before"]["cash"] -= 1
    plan["before"]["registration"]["protected_counts"].append([ref(63), 1])
    plan["before"]["registration"]["protected_counts"].sort()
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises(ValueError, match="source, target or unused flag"):
        reconstruct_native_curriculum(plan, result)
