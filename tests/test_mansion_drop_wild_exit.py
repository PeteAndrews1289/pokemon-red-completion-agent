"""A scripted Mansion drop is proved separately; ordinary flee stays strict."""
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_player_mansion as mansion
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.route_1_wild import WildFleeFieldExit, flee_wild
from test_wild_status_recovery import encounter, runtime


def pair():
    before = replace(encounter(), map_id=int(MapId.POKEMON_MANSION_3F),
                     player_y=14, player_x=16)
    after = replace(before, map_id=int(MapId.POKEMON_MANSION_1F),
                    battle_state=0, battle_result=0,
                    first_party_hp=90, party_hp=(90, 92))
    return before, after


def rejected_evidence():
    before, after = pair()
    reader, actions = runtime(before, after)
    with pytest.raises(RuntimeError) as error:
        flee_wild(actions, reader, before, expected_map_id=before.map_id,
                  route_name="strict ordinary caller", stabilization_frames=120,
                  error_type=RuntimeError)
    return before, after, error.value


def test_generic_caller_still_rejects_actual_floor_change():
    before, after, error = rejected_evidence()
    assert type(error.__cause__) is WildFleeFieldExit
    cause = error.__cause__
    assert cause.before is before and cause.after is after
    assert not cause.evidence.verified
    assert cause.evidence.battle_result == 0
    assert cause.evidence.expected_map_id == before.map_id
    assert cause.evidence.map_id == after.map_id


def test_only_scoped_drop_accepts_preserved_party_after_witnessed_run():
    before, after = pair()
    reader, actions = runtime(before, after)
    result = mansion._flee_drop_encounter(actions, reader, before)
    assert result["verified"] and result["battle_result"] == 0
    assert result["source_map"] == 215 and result["terminal_map"] == 165
    assert not result["generic_same_map_evidence"]["verified"]
    assert result["generic_same_map_evidence"]["expected_map"] == 215
    assert sum(a.kind is MacroActionKind.CONFIRM for a in actions.calls) == 1
    assert not any(a.kind is MacroActionKind.MOVE for a in actions.calls)


@pytest.mark.parametrize("change", [
    dict(map_id=214), dict(player_x=17), dict(player_y=15), dict(battle_result=1),
    dict(first_party_hp=94, party_hp=(94, 92)), dict(party_hp=(90, 0)),
    dict(first_party_pp=(24, 20, 30, 0), party_pp=((24, 20, 30, 0), (30, 40, 20, 5))),
    dict(party_status=(0, 8)), dict(party_levels=(28, 32)),
    dict(party_max_hp=(93, 93)), dict(party_species_ids=(41, 43)),
    dict(player_money=549), dict(badge_bits=63), dict(event_flags=b"\x01"),
    dict(bag_items=((4, 5),)),
])
def test_drop_rejects_other_boundary_or_protected_changes(change):
    before, after = pair()
    reader, actions = runtime(before, replace(after, **change))
    with pytest.raises(RuntimeError):
        mansion._flee_drop_encounter(actions, reader, before)


@pytest.mark.parametrize("case", ["no_run", "too_many_runs", "stale", "other_before", "plain"])
def test_drop_does_not_swallow_unauthenticated_failure(monkeypatch, case):
    before, after, original = rejected_evidence()
    cause = original.__cause__
    if case in {"no_run", "too_many_runs"}:
        cause.evidence = replace(cause.evidence, run_attempts=0 if case == "no_run" else 17)
    if case == "other_before":
        cause.before = replace(before)
    reader = NS(read=lambda: replace(after, player_x=17) if case == "stale" else after,
                read_input_readiness=lambda: NS(ready=True))
    def fail(*args, **kwargs):
        if case == "plain":
            raise RuntimeError("unrelated execution error")
        raise original
    monkeypatch.setattr(mansion, "flee_wild", fail)
    with pytest.raises(RuntimeError) as error:
        mansion._flee_drop_encounter(None, reader, before)
    assert error.value is original or case == "plain"
