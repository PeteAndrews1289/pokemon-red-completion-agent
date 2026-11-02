from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
import test_red_scoped_lorelei as lorelei

from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.red_lorelei_story import (
    ScopedAssistedChampionController,
    story_league_controller,
)


def controller(tmp_path, variant=2):
    old = lorelei.controller(tmp_path)
    contract = replace(
        old.contract,
        objective_id="defeat_champion",
        battle_plan_id="cartridge-final-story",
        map_id=int(MapId.CHAMPIONS_ROOM),
        trainer_identity=(243, 43, variant),
        defeated_event=int(EventFlag.BEAT_CHAMPION_RIVAL),
        victory_money=6435,
    )
    actor = old.battler
    actor.development_story_scope = replace(actor.development_story_scope, contract=contract)
    actor.qualification_sha256 = actor.development_story_scope.identity
    return ScopedAssistedChampionController(actor, contract, old.admission, 80)


@pytest.mark.parametrize("variant", [1, 2, 3])
@pytest.mark.parametrize("rematch", [False, True])
def test_live_script_binds_all_native_champion_variants(tmp_path, variant, rematch):
    ctl = controller(tmp_path, variant)
    assert (
        story_league_controller(
            NS(league_story_battle_controller=ctl), "defeat_champion", rematch=rematch
        )
        is ctl
    )
    ctl.require_champion_target(
        NS(active_identity=(243, 43, variant), event_flag=2305), NS(expected_victory_money=6435)
    )
    ctl.require_party_hp(NS(party_count=2, party_hp=(1, 0)))
    assert ctl.battler.calls == 0


@pytest.mark.parametrize(
    "fault",
    [
        "source",
        "model",
        "work",
        "assistance",
        "contract",
        "partition",
        "budget",
    ],
)
def test_champion_preserves_source_model_and_support_guards(tmp_path, monkeypatch, fault):
    ctl = controller(tmp_path)
    monkeypatch.setattr(lorelei, "controller", lambda _: ctl)
    lorelei.test_scoped_lorelei_rejects_changed_authority(tmp_path, fault)


@pytest.mark.parametrize(
    "changes",
    [
        {"trainer_identity": (243, 43, 4)},
        {"trainer_identity": (247, 47, 1)},
        {"map_id": int(MapId.LANCES_ROOM)},
        {"defeated_event": 2297},
        {"battle_plan_id": "cartridge-trainer-story"},
        {"objective_id": "defeat_lance"},
    ],
)
def test_rehashed_scope_cannot_redirect_final_target(tmp_path, changes):
    ctl = controller(tmp_path)
    ctl.contract = replace(ctl.contract, **changes)
    ctl.battler.development_story_scope = replace(
        ctl.battler.development_story_scope, contract=ctl.contract
    )
    ctl.battler.qualification_sha256 = ctl.battler.development_story_scope.identity
    with pytest.raises(ValueError):
        ctl.require_identity()
    assert ctl.battler.calls == 0


@pytest.mark.parametrize(
    "identity,event,payout",
    [
        ((243, 43, 1), 2305, 6435),
        ((243, 43, 2), 2304, 6435),
        ((243, 43, 2), 2305, 1),
    ],
)
def test_wrong_live_roster_event_or_payout_rejected(tmp_path, identity, event, payout):
    ctl = controller(tmp_path)
    with pytest.raises(ValueError):
        ctl.require_champion_target(
            NS(active_identity=identity, event_flag=event), NS(expected_victory_money=payout)
        )
    assert ctl.battler.calls == 0


@pytest.mark.parametrize("objective,rematch", [("defeat_lance", True), ("defeat_champion", 1)])
def test_wrong_objective_and_untyped_rematch_rejected(tmp_path, objective, rematch):
    ctl = controller(tmp_path)
    with pytest.raises(ValueError):
        story_league_controller(NS(league_story_battle_controller=ctl), objective, rematch=rematch)


@pytest.mark.parametrize(
    "deficit,mode,allowed",
    [
        (5, "critical-inclusive", True),
        (7, "scoped-assisted-champion-development", True),
        (7, "critical-inclusive", False),
        (8, "scoped-assisted-champion-development", False),
        (True, "scoped-assisted-champion-development", False),
    ],
)
def test_scoped_level_allowance_preserves_default(deficit, mode, allowed):
    from pokemon_red_completion.red_champion_story import (
        RedCartridgeChampionSkill,
        RedChampionStoryError,
    )

    if allowed:
        RedCartridgeChampionSkill(
            None, None, None, recovery_controller=mode, maximum_level_deficit=deficit
        )
    else:
        with pytest.raises(RedChampionStoryError, match="level-screen"):
            RedCartridgeChampionSkill(
                None, None, None, recovery_controller=mode, maximum_level_deficit=deficit
            )
    assert RedCartridgeChampionSkill.__dataclass_fields__["maximum_level_deficit"].default == 5


def test_allowance_mutation_after_preparation_fails_before_input(monkeypatch):
    from test_red_champion_story import fixture

    from pokemon_red_completion.red_champion_story import RedChampionStoryError

    skill, _, inputs, _ = fixture(monkeypatch)
    skill.maximum_level_deficit = 7
    with pytest.raises(RedChampionStoryError, match="origin or authority"):
        skill.execute()
    assert not inputs


def test_allowance_mutation_before_availability_is_revalidated():
    from pokemon_red_completion.red_champion_story import RedCartridgeChampionSkill

    skill = RedCartridgeChampionSkill(
        None,
        None,
        None,
        recovery_controller="scoped-assisted-champion-development",
        maximum_level_deficit=7,
    )
    skill.maximum_level_deficit = 100
    assert not skill.availability(None).executable


def test_prospective_champion_deficit_requires_exact_current_development_scope(tmp_path):
    from pokemon_red_completion.red_champion_story import (
        RedCartridgeChampionSkill,
        RedChampionStoryError,
    )
    from pokemon_red_completion.scenario_lab import ScenarioPartition

    ctl = controller(tmp_path)
    ctl.declared_level_deficit = 30
    runtime = NS(league_story_battle_controller=ctl)
    options = dict(recovery_controller=ctl.controller_name, maximum_level_deficit=30)
    RedCartridgeChampionSkill(runtime, None, None, **options)
    with pytest.raises(RedChampionStoryError):
        RedCartridgeChampionSkill(runtime, None, None, **(options | {"maximum_level_deficit": 29}))
    ctl.battler.source_partition = ScenarioPartition.TRAIN
    with pytest.raises(ValueError):
        RedCartridgeChampionSkill(runtime, None, None, **options)
    assert ctl.battler.calls == 0
