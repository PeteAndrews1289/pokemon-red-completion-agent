"""Copy-only final-scene admission; no private emulator or model artifacts."""

from dataclasses import fields, replace
from types import SimpleNamespace as NS

import pytest
from test_red_champion_story import fixture as champion_fixture
from test_red_story_copy import setup as _shared_setup

from pokemon_red_completion import red_champion_story as champion
from pokemon_red_completion import red_story_copy as copy
from pokemon_red_completion.gen1_champion_script import ChampionScriptBinding
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember, TrainerPartyQuote

setup = _shared_setup  # pytest discovers this imported fixture by module attribute.


def bind(setup, money=6435):
    scope, battler, _ = setup
    battler.scope = replace(
        scope,
        contract=copy.StoryTrainerContract(
            "defeat_champion", "cartridge-final-story", 120, (243, 43, 2), 2305, money
        ),
    )
    return copy.StoryCopyController(battler)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "objective",
        "plan",
        "map",
        "event",
        "identity",
        "money",
        "quote",
        "source",
        "model",
        "claimed",
        "calls",
    ],
)
def test_exact_champion_script_contract_is_required(setup, fault):
    actor = bind(setup)
    script = ChampionScriptBinding(243, 43, 2, 2305, (), (), ())
    quote = TrainerPartyQuote(243, 2, (TrainerPartyMember(151, 18, 61),), 99, 6435)
    changes = {
        "objective": {"objective_id": "defeat_lance"},
        "plan": {"battle_plan_id": "cartridge-trainer-story"},
        "map": {"map_id": 113},
        "event": {"defeated_event": 2297},
        "identity": {"trainer_identity": (243, 43, 1)},
        "money": {"victory_money": 6436},
    }
    if fault in changes:
        actor.battler.scope = replace(
            actor.battler.scope, contract=replace(actor.battler.scope.contract, **changes[fault])
        )
    elif fault == "quote":
        quote = replace(quote, trainer_set=1)
    elif fault == "source":
        actor.battler.scope.source.write_bytes(b"changed")
    elif fault == "model":
        actor.battler.model = None
    elif fault == "claimed":
        (actor.battler.scope.output / "battle").mkdir()
    elif fault == "calls":
        actor.battler.calls = 1
    if fault:
        with pytest.raises(ValueError):
            actor.require_champion_target(script, quote)
    else:
        actor.require_champion_target(script, quote)
        with pytest.raises(ValueError):
            actor.require_objective("defeat_champion", rematch=True)


@pytest.mark.parametrize(
    "hp,maximum,valid",
    [
        ((0, 20), (30, 30), True),
        ((0, 0), (30, 30), False),
        ((-1, 20), (30, 30), False),
        ((31, 20), (30, 30), False),
        ((20,), (30, 30), False),
        ((True, 20), (30, 30), False),
    ],
)
def test_final_scene_accepts_recoverable_faints_not_corrupt_party(setup, hp, maximum, valid):
    actor = bind(setup)
    raw = NS(party_count=2, party_hp=hp, party_max_hp=maximum)
    if valid:
        actor.require_party_hp(raw)
    else:
        with pytest.raises(ValueError):
            actor.require_party_hp(raw)


@pytest.mark.parametrize("fault", [None, "bag", "payout", "missing_champion", "held_terminal"])
def test_copy_binding_preserves_champion_epilogue_checks(setup, monkeypatch, fault):
    skill, reader, inputs, scene = champion_fixture(monkeypatch, fault)
    changes = {
        f.name: getattr(reader.raw, f.name) * 2
        for f in fields(reader.raw)
        if f.name.startswith("party_")
        and isinstance(getattr(reader.raw, f.name), tuple)
        and len(getattr(reader.raw, f.name)) == 1
    }
    reader.raw = replace(reader.raw, **changes, party_count=2)
    skill._prepared = replace(skill._prepared, before=skill.runtime.adapter.observe())
    actor = bind(setup, money=5400)
    skill.runtime.league_story_battle_controller = actor
    skill.recovery_controller = skill._prepared_controller = actor.controller_name
    skill._prepared_learned_controller = actor
    skill._prepared_story_binding = actor.binding_identity
    # The fixture owns only cartridge response; no deterministic policy is forwarded.
    ordinary = champion.RedTrainerPartyController(reader, skill.runtime.emulator)

    def run(actual_reader, actions, unused_teacher, **kwargs):
        assert kwargs["intent"].battle_plan_id == "cartridge-final-story"
        assert skill._learned_controller() is actor
        # Recoverable faint exercises the real outer party guard throughout epilogue.
        reader.raw = replace(reader.raw, party_hp=(0,) + reader.raw.party_hp[1:])
        return ordinary.run(actual_reader, actions, lambda *_: pytest.fail("teacher"), **kwargs)

    monkeypatch.setattr(actor, "run", run)
    if fault:
        with pytest.raises(champion.RedChampionStoryError):
            skill.execute()
    else:
        result = skill.execute()
        assert result.evidence["concurrent_champion_and_hall_of_fame"]
        assert result.evidence["authority"] == actor.controller_name
        assert reader.raw.map_id == 118
    assert scene["battle_calls"] == 1


def test_changed_copy_binding_refuses_before_champion_entry(setup, monkeypatch):
    skill, reader, inputs, scene = champion_fixture(monkeypatch)
    actor = bind(setup, money=5400)
    skill.runtime.league_story_battle_controller = actor
    skill.recovery_controller = skill._prepared_controller = actor.controller_name
    skill._prepared_learned_controller = actor
    skill._prepared_story_binding = actor.binding_identity
    actor.battler.scope = replace(actor.battler.scope, maximum_decisions=79)
    with pytest.raises(champion.RedChampionStoryError, match="origin"):
        skill.execute()
    assert not inputs and scene["entry"] == 0


@pytest.mark.parametrize("fault", [None, "missing_champion", "payout", "held_terminal"])
def test_copy_escort_already_finished_at_combat_return(setup, monkeypatch, fault):
    skill, reader, inputs, scene = champion_fixture(monkeypatch, fault)
    actor = bind(setup, money=5400)
    skill.runtime.league_story_battle_controller = actor
    skill.recovery_controller = skill._prepared_controller = actor.controller_name
    skill._prepared_learned_controller = actor
    skill._prepared_story_binding = actor.binding_identity

    def run(actual_reader, actions, unused_teacher, **kwargs):
        scene["battle_calls"] += 1
        scene["won"] = True
        flags = bytearray(reader.raw.event_flags)
        if fault != "missing_champion":
            flags[2305 // 8] |= 1 << (2305 % 8)
        reader.raw = replace(
            reader.raw,
            map_id=118,
            battle_state=0,
            battle_result=0,
            event_flags=bytes(flags),
            player_money=29382 if fault == "payout" else 29383,
        )
        if fault == "held_terminal":
            skill.runtime.emulator.pressed_buttons = frozenset({"a"})
        kwargs["battle_exit_guard"](reader.raw)
        return reader.raw

    monkeypatch.setattr(actor, "run", run)
    if fault:
        with pytest.raises(champion.RedChampionStoryError):
            skill.execute()
    else:
        assert skill.execute().evidence["concurrent_champion_and_hall_of_fame"]
    assert scene["battle_calls"] == 1
