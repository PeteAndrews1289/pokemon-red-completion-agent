from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_red_lorelei_story import actor, contract

from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.red_lorelei_story import (
    FrozenBrunoCopyStoryController,
    FrozenBrunoStoryController,
    FrozenLoreleiStoryController,
    story_league_controller,
)


def controller(tmp_path, **changes):
    battler = actor(tmp_path)
    battler.source_state_sha256 = "365af4747021049aaeb17d433b9c6696ad056a7a6d78ea6ea93dc333600700f7"
    args = dict(
        battler=battler,
        contract=replace(
            contract(),
            objective_id="defeat_bruno",
            map_id=int(MapId.BRUNOS_ROOM),
            defeated_event=int(EventFlag.BEAT_BRUNO),
            trainer_identity=(233, 33, 1),
        ),
        isolated_copy=True,
        admission=(
            Path(__file__).parents[1] / "docs/evidence/red-bruno-copy-admission-2026-09-23.json"
        ).read_bytes(),
    )
    return FrozenBrunoCopyStoryController(**(args | changes))


def test_copy_requires_own_receipt_source_and_no_campaign_authority(tmp_path):
    ctl = controller(tmp_path)
    assert story_league_controller(NS(league_story_battle_controller=ctl), "defeat_bruno") is ctl
    with pytest.raises(ValueError):
        controller(tmp_path, isolated_copy=False)
    with pytest.raises(ValueError):
        controller(tmp_path, admission=b"{}")
    with pytest.raises(ValueError):
        FrozenLoreleiStoryController(ctl.battler, ctl.contract, ctl.admission)
    ctl.battler.source_state_sha256 = "a" * 64
    with pytest.raises(ValueError):
        ctl.require_identity()


@pytest.mark.parametrize(
    "objective,rematch",
    [
        ("defeat_lorelei", False),
        ("defeat_agatha", False),
        ("defeat_lance", False),
        ("defeat_champion", False),
        ("defeat_bruno", True),
    ],
)
def test_copy_rejects_other_rooms_and_rematch(tmp_path, objective, rematch):
    with pytest.raises(ValueError):
        controller(tmp_path).require_objective(objective, rematch=rematch)


def test_copy_inherits_frozen_lifecycle_and_mutation_breaks_binding(tmp_path):
    ctl = controller(tmp_path)
    assert type(ctl).run is FrozenLoreleiStoryController.run
    bound = ctl.binding_identity
    ctl.isolated_copy = False
    assert ctl.binding_identity != bound
    with pytest.raises(ValueError):
        ctl.require_objective("defeat_bruno")


def earned_controller(tmp_path):
    copy = controller(tmp_path)
    receipt = (
        Path(__file__).parents[1] / "docs/evidence/red-bruno-story-admission-2026-09-23.json"
    ).read_bytes()
    return FrozenBrunoStoryController(copy.battler, copy.contract, receipt)


def test_earned_admission_is_separate_from_copy_and_defaults(tmp_path):
    earned = earned_controller(tmp_path)
    assert (
        story_league_controller(NS(league_story_battle_controller=earned), "defeat_bruno") is earned
    )
    assert type(earned).run is FrozenLoreleiStoryController.run
    copy = controller(tmp_path)
    with pytest.raises(ValueError):
        FrozenBrunoStoryController(copy.battler, copy.contract, copy.admission)
    with pytest.raises(ValueError):
        controller(tmp_path, admission=earned.admission)
    with pytest.raises(ValueError):
        story_league_controller(
            NS(league_story_battle_controller=earned, league_battle_controller=object()),
            "defeat_bruno",
        )
    earned.battler.source_state_sha256 = "a" * 64
    with pytest.raises(ValueError):
        earned.require_identity()


@pytest.mark.parametrize(
    "objective,rematch",
    [
        ("defeat_lorelei", False),
        ("defeat_agatha", False),
        ("defeat_lance", False),
        ("defeat_champion", False),
        ("defeat_bruno", True),
    ],
)
def test_earned_other_rooms_remain_closed(tmp_path, objective, rematch):
    with pytest.raises(ValueError):
        earned_controller(tmp_path).require_objective(objective, rematch=rematch)
