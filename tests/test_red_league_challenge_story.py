from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_red_lorelei_story import actor

from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.red_learned_league import learned_league_controller
from pokemon_red_completion.red_lorelei_story import (
    FrozenLeagueChallengeStoryController,
    FrozenLoreleiStoryController,
    story_league_controller,
)
from pokemon_red_completion.red_story_battle import StoryTrainerContract

TARGETS = [
    ("lorelei", MapId.LORELEIS_ROOM, EventFlag.BEAT_LORELEI, 244),
    ("bruno", MapId.BRUNOS_ROOM, EventFlag.BEAT_BRUNO, 233),
    ("agatha", MapId.AGATHAS_ROOM, EventFlag.BEAT_AGATHA, 246),
    ("lance", MapId.LANCES_ROOM, EventFlag.BEAT_LANCES_ROOM_TRAINER, 247),
    ("champion", MapId.CHAMPIONS_ROOM, EventFlag.BEAT_CHAMPION_RIVAL, 243),
]


def controller(tmp_path, target="champion", rechallenge=False, **changes):
    _, mp, event, cl = next(row for row in TARGETS if row[0] == target)
    battler = actor(tmp_path)
    args = dict(
        battler=battler,
        source_sha256=battler.source_state_sha256,
        rechallenge=rechallenge,
        contract=StoryTrainerContract(
            "defeat_" + target,
            "cartridge-final-story" if target == "champion" else "cartridge-trainer-story",
            int(mp),
            (cl, cl - 200, 2 if target == "champion" else 1),
            int(event),
            5400,
        ),
        admission=(
            Path(__file__).parents[1]
            / "docs/evidence/red-league-challenge-admission-2026-09-23.json"
        ).read_bytes(),
    )
    return FrozenLeagueChallengeStoryController(**(args | changes))


@pytest.mark.parametrize("target", [r[0] for r in TARGETS])
@pytest.mark.parametrize("rechallenge", [False, True])
def test_exact_room_and_explicit_rechallenge_are_separate_from_income(
    tmp_path, target, rechallenge
):
    ctl = controller(tmp_path, target, rechallenge)
    runtime = NS(league_story_battle_controller=ctl)
    assert story_league_controller(runtime, "defeat_" + target, rematch=rechallenge) is ctl
    assert type(ctl).run is FrozenLoreleiStoryController.run
    with pytest.raises(ValueError):
        story_league_controller(runtime, "defeat_" + target, rematch=not rechallenge)
    with pytest.raises(ValueError):
        learned_league_controller(runtime)
    with pytest.raises(ValueError):
        ctl.require_objective("defeat_brock")
    with pytest.raises(ValueError):
        ctl.require_objective("defeat_" + target, rematch=1)


@pytest.mark.parametrize(
    "change",
    [
        {"rechallenge": 1},
        {"source_sha256": "c" * 64},
        {"admission": b"{}"},
        {"maximum_decisions": 81},
    ],
)
def test_bad_binding_refuses(tmp_path, change):
    with pytest.raises(ValueError):
        controller(tmp_path, **change)


def test_champion_target_uses_actual_starter_set_and_price(tmp_path):
    ctl = controller(tmp_path)
    script = NS(active_identity=(243, 43, 2), event_flag=int(EventFlag.BEAT_CHAMPION_RIVAL))
    quote = NS(expected_victory_money=5400)
    ctl.require_champion_target(script, quote)
    script.active_identity = (243, 43, 1)
    with pytest.raises(ValueError):
        ctl.require_champion_target(script, quote)
    with pytest.raises(ValueError):
        controller(
            tmp_path, contract=replace(ctl.contract, battle_plan_id="cartridge-trainer-story")
        )


def test_champion_prepared_binding_detects_in_place_mutation_before_inputs(tmp_path, monkeypatch):
    from test_red_champion_story import fixture

    skill, reader, inputs, scene = fixture(monkeypatch)
    ctl = controller(tmp_path)
    skill.runtime.league_story_battle_controller = ctl
    skill.recovery_controller = skill._prepared_controller = ctl.controller_name
    skill._prepared_learned_controller = ctl
    skill._prepared_story_binding = ctl.binding_identity
    ctl.maximum_decisions = 79
    with pytest.raises(RuntimeError, match="origin or authority"):
        skill.execute()
    assert not inputs and scene["entry"] == 0


def test_champion_outer_scene_preserves_learned_authority_and_completion(tmp_path, monkeypatch):
    from test_red_champion_story import fixture

    from pokemon_red_completion import red_champion_story as module

    skill, reader, inputs, scene = fixture(monkeypatch)
    ctl = controller(tmp_path)
    # Native scene mock tests outer routing/evidence, not battler competence.
    ctl.run = module.RedTrainerPartyController(reader, skill.runtime.emulator).run
    skill.runtime.league_story_battle_controller = ctl
    skill.recovery_controller = skill._prepared_controller = ctl.controller_name
    skill._prepared_learned_controller = ctl
    skill._prepared_story_binding = ctl.binding_identity
    result = skill.execute()
    assert result.evidence["learned_battle_authority"]
    assert result.evidence["battle_controller"] == ctl.controller_name
    assert result.evidence["concurrent_champion_and_hall_of_fame"]
    assert scene["battle_calls"] == 1 and reader.raw.map_id == 118
