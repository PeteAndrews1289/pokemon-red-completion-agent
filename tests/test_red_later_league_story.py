from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_red_lorelei_story import actor, contract

from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.red_learned_league import learned_league_controller
from pokemon_red_completion.red_lorelei_story import (
    FrozenLaterLeagueStoryController,
    FrozenLoreleiStoryController,
    story_league_controller,
)


def controller(tmp_path, objective="defeat_agatha", **changes):
    target = {
        "defeat_agatha": (MapId.AGATHAS_ROOM, EventFlag.BEAT_AGATHA, 246),
        "defeat_lance": (MapId.LANCES_ROOM, EventFlag.BEAT_LANCES_ROOM_TRAINER, 247),
    }[objective]
    battler = actor(tmp_path)
    args = dict(
        battler=battler,
        source_sha256=battler.source_state_sha256,
        contract=replace(
            contract(),
            objective_id=objective,
            map_id=int(target[0]),
            defeated_event=int(target[1]),
            trainer_identity=(target[2], target[2] - 200, 1),
        ),
        admission=(
            Path(__file__).parents[1]
            / "docs/evidence/red-later-league-story-admission-2026-09-23.json"
        ).read_bytes(),
    )
    return FrozenLaterLeagueStoryController(**(args | changes))


@pytest.mark.parametrize("objective", ["defeat_agatha", "defeat_lance"])
def test_explicit_target_reuses_learned_lifecycle_without_income_promotion(tmp_path, objective):
    ctl = controller(tmp_path, objective)
    runtime = NS(league_story_battle_controller=ctl)
    assert story_league_controller(runtime, objective) is ctl
    assert type(ctl).run is FrozenLoreleiStoryController.run
    with pytest.raises(ValueError):
        learned_league_controller(runtime)
    with pytest.raises(ValueError):
        ctl.require_objective(objective, rematch=True)
    for other in {
        "defeat_lorelei",
        "defeat_bruno",
        "defeat_agatha",
        "defeat_lance",
        "defeat_champion",
    } - {objective}:
        with pytest.raises(ValueError):
            ctl.require_objective(other)


@pytest.mark.parametrize("source", ["", "b" * 63, "B" * 64, "z" * 64, "c" * 64, None])
def test_bad_source_binding_refused(tmp_path, source):
    with pytest.raises(ValueError):
        controller(tmp_path, source_sha256=source)


def test_mutated_actor_or_contract_and_wrong_receipt_fail_closed(tmp_path):
    ctl = controller(tmp_path)
    old = ctl.binding_identity
    ctl.source_sha256 = "c" * 64
    assert old != ctl.binding_identity
    with pytest.raises(ValueError):
        ctl.require_identity()
    with pytest.raises(ValueError):
        controller(tmp_path, admission=b"{}")
    with pytest.raises(ValueError):
        controller(tmp_path, contract=contract())
    with pytest.raises(ValueError):
        controller(tmp_path, contract=replace(controller(tmp_path).contract, map_id=246))
    ctl = controller(tmp_path)
    ctl.battler.require_story_identity = lambda: (_ for _ in ()).throw(
        ValueError("changed weights")
    )
    with pytest.raises(ValueError, match="changed weights"):
        ctl.require_identity()


def test_cartridge_target_is_rechecked(tmp_path):
    ctl = controller(tmp_path)
    target = NS(map_id=247, trainer_class=246, trainer_set=1, event_flag=int(EventFlag.BEAT_AGATHA))
    quote = NS(expected_victory_money=ctl.contract.victory_money)
    ctl.require_cartridge_target(target, quote)
    target.trainer_set = 2
    with pytest.raises(ValueError):
        ctl.require_cartridge_target(target, quote)
