from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_development_story_scope import DevelopmentStoryScope
from pokemon_red_completion.red_learned_trainer import FrozenTrainerBattler, qualified_party_limit
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.scenario_lab import ScenarioPartition


def actor(tmp_path):
    model = N(to_dict=lambda: {"test": True})
    scope = DevelopmentStoryScope(
        "a" * 64, "root", "b" * 64, canonical_sha256(model.to_dict()), "c" * 64
    )
    return FrozenTrainerBattler(
        None,
        model,
        tmp_path,
        "d" * 40,
        "root",
        "a" * 64,
        {},
        model_sha256="b" * 64,
        qualification_sha256=scope.identity,
        development_story_scope=scope,
    )


@pytest.mark.parametrize(
    "fault", [None, "source", "root", "model", "receipt", "partition", "mixed"]
)
def test_scope_is_not_global_qualification(tmp_path, fault):
    a = actor(tmp_path)
    if fault == "source":
        a.source_state_sha256 = "e" * 64
    if fault == "root":
        a.root_lineage_id = "other"
    if fault == "model":
        a.model = N(to_dict=lambda: {})
    if fault == "receipt":
        a.qualification_sha256 = "e" * 64
    if fault == "partition":
        a.source_partition = ScenarioPartition.TRAIN
    if fault == "mixed":
        a.train_funding_diagnostic = True
    assert qualified_party_limit(a.model_sha256, a.qualification_sha256) == 0
    if fault:
        with pytest.raises(ValueError):
            a.require_story_identity()
    else:
        assert a.story_limit() == 6
        assert a.story_authority() == "scoped-tower-development"


@pytest.mark.parametrize("fault", [None, "map", "objective", "items", "badge"])
def test_story_contract_stays_inside_tower(tmp_path, fault):
    a = actor(tmp_path)
    c = StoryTrainerContract("rescue_fuji", "channeler", 145, (245, 45, 10), 250, 690)
    if fault == "map":
        c = replace(c, map_id=100)
    if fault == "objective":
        c = replace(c, objective_id="defeat_misty")
    if fault == "items":
        c = replace(c, victory_items=((4, 1),))
    if fault == "badge":
        c = replace(c, victory_badge_bits=16)
    if fault:
        with pytest.raises(ValueError):
            a.require_story_contract(c)
    else:
        a.require_story_contract(c)


def test_assistance_changes_declared_identity(tmp_path):
    a = actor(tmp_path)
    a.development_story_scope = replace(
        a.development_story_scope, diagnostic_stay_when_productive=True
    )
    with pytest.raises(ValueError):
        a.story_limit()


@pytest.mark.parametrize(
    "map_id,battle_state,story", [(65, 2, True), (145, 1, True), (145, 2, False)]
)
def test_scope_rejects_wrong_live_mode_before_any_action(tmp_path, map_id, battle_state, story):
    from pokemon_red_completion.battle_runtime import BattleRuntimeTiming

    a = actor(tmp_path)
    reader = N(read=lambda: N(map_id=map_id, battle_state=battle_state))
    with pytest.raises(ValueError):
        a.continue_battle(
            reader,
            None,
            expected_map=map_id,
            timing=BattleRuntimeTiming(),
            decision_guard=lambda _: None,
            story_authority=story,
        )
    assert a.calls == 0 and not tuple(tmp_path.iterdir())


def exact_actor(tmp_path):
    a = actor(tmp_path)
    contract = StoryTrainerContract(
        "cross_victory_road", "route22-rival-gate", 33, (242, 42, 11), 1318, 3445
    )
    a.development_story_scope = replace(
        a.development_story_scope, contract=contract, diagnostic_stay_when_productive=True
    )
    a.qualification_sha256 = a.development_story_scope.identity
    return a, contract


def test_exact_contract_roundtrip_preserves_identity_and_old_tower_document(tmp_path):
    import json

    old = actor(tmp_path).development_story_scope
    assert "contract" not in old.document()
    assert DevelopmentStoryScope.from_document(old.document()) == old
    a, contract = exact_actor(tmp_path)
    restored = DevelopmentStoryScope.from_document(
        json.loads(json.dumps(a.development_story_scope.document()))
    )
    assert restored == a.development_story_scope
    assert restored.identity == a.qualification_sha256 and restored.contract == contract
    assert a.story_authority() == "scoped-exact-story-development"
    assert qualified_party_limit(a.model_sha256, a.qualification_sha256) == 0


@pytest.mark.parametrize(
    "change",
    [
        None,
        "map_id",
        "objective_id",
        "battle_plan_id",
        "trainer_identity",
        "defeated_event",
        "victory_money",
    ],
)
def test_exact_contract_rejects_every_changed_target(tmp_path, change):
    a, contract = exact_actor(tmp_path)
    changes = dict(
        map_id=145,
        objective_id="rescue_fuji",
        battle_plan_id="other",
        trainer_identity=(242, 42, 10),
        defeated_event=1317,
        victory_money=3000,
    )
    if change is None:
        a.require_story_contract(contract)
    else:
        with pytest.raises(ValueError, match="exact declared contract"):
            a.require_story_contract(replace(contract, **{change: changes[change]}))


@pytest.mark.parametrize("fault", [None, "map", "trainer", "wild"])
def test_exact_scope_checks_live_trainer_before_inputs(tmp_path, fault):
    a, contract = exact_actor(tmp_path)
    reader = N(
        read=lambda: N(
            map_id=145 if fault == "map" else 33, battle_state=1 if fault == "wild" else 2
        ),
        read_active_trainer_identity=lambda: (
            (242, 42, 10) if fault == "trainer" else contract.trainer_identity
        ),
    )
    if fault:
        with pytest.raises(ValueError, match="live target differs"):
            a.development_story_scope.require_live(reader, 33)
    else:
        a.development_story_scope.require_live(reader, 33)
    assert a.calls == 0 and not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("kind", ["items", "badge", "dict"])
def test_exact_scope_cannot_smuggle_rewards_or_untyped_contract(tmp_path, kind):
    a, contract = exact_actor(tmp_path)
    bad = (
        replace(contract, victory_items=((4, 1),))
        if kind == "items"
        else (replace(contract, victory_badge_bits=1) if kind == "badge" else {"map_id": 33})
    )
    with pytest.raises(ValueError):
        replace(a.development_story_scope, contract=bad)


def gym_actor(tmp_path):
    from pokemon_red_completion.red_gym_reward import MISTY_REWARD as reward

    a = actor(tmp_path)
    contract = StoryTrainerContract(
        reward.objective_id,
        reward.objective_id,
        reward.map_id,
        (reward.trainer_class, reward.trainer_class - 200, reward.trainer_set),
        reward.defeated_event,
        2100,
        ((reward.item, 1),),
        reward.badge,
    )
    a.development_story_scope = replace(
        a.development_story_scope,
        contract=contract,
        gym_reward=reward,
    )
    a.qualification_sha256 = a.development_story_scope.identity
    return a, contract


def test_declared_gym_supports_ordinary_rematch_without_global_promotion(tmp_path):
    a, contract = gym_actor(tmp_path)
    a.calls = 2
    a.require_story_contract(contract)
    assert a.story_limit() == 6
    assert qualified_party_limit(a.model_sha256, a.qualification_sha256) == 0
    assert DevelopmentStoryScope.from_document(a.development_story_scope.document()) == (
        a.development_story_scope
    )
    assert "gym_reward" not in actor(tmp_path).development_story_scope.document()


def test_sabrina_exact_rewards_round_trip_without_global_qualification(tmp_path):
    from pokemon_red_completion.red_gym_reward import SABRINA_REWARD as reward

    a = actor(tmp_path)
    contract = StoryTrainerContract(
        reward.objective_id,
        "sabrina",
        reward.map_id,
        (240, 40, 1),
        reward.defeated_event,
        4257,
        ((reward.item, 1),),
        reward.badge,
    )
    scope = replace(a.development_story_scope, contract=contract, gym_reward=reward)
    a.development_story_scope = scope
    a.qualification_sha256 = scope.identity
    a.require_story_contract(contract)
    assert DevelopmentStoryScope.from_document(scope.document()) == scope
    assert qualified_party_limit(a.model_sha256, scope.identity) == 0
    with pytest.raises(ValueError, match="gym contract/reward"):
        replace(scope, contract=replace(contract, victory_items=((1, 1),)))


@pytest.mark.parametrize("fault", ["no_contract", "profile", "items", "badge", "map", "trainer"])
def test_gym_scope_cannot_smuggle_rewards_or_different_trainer(tmp_path, fault):
    from pokemon_red_completion.red_gym_reward import MISTY_REWARD, SURGE_REWARD

    a, contract = gym_actor(tmp_path)
    changes = dict(
        no_contract=dict(contract=None),
        profile=dict(gym_reward=SURGE_REWARD),
        items=dict(contract=replace(contract, victory_items=((4, 1),))),
        badge=dict(contract=replace(contract, victory_badge_bits=16)),
        map=dict(contract=replace(contract, map_id=33)),
        trainer=dict(gym_reward=replace(MISTY_REWARD, trainer_set=2)),
    )
    with pytest.raises(ValueError, match="gym contract/reward"):
        replace(a.development_story_scope, **changes[fault])


def test_changed_gym_live_target_and_contract_still_refuse_before_input(tmp_path):
    a, contract = gym_actor(tmp_path)
    with pytest.raises(ValueError, match="exact declared contract"):
        a.require_story_contract(replace(contract, victory_money=999999))
    reader = N(
        read=lambda: N(map_id=contract.map_id, battle_state=2),
        read_active_trainer_identity=lambda: (235, 35, 2),
    )
    with pytest.raises(ValueError, match="live target differs"):
        a.development_story_scope.require_live(reader, contract.map_id)
    assert a.calls == 0
