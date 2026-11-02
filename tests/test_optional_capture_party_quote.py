"""Actual regional compiler/router admission with an optional no-helper party.

Navigation/cartridge decoding use the existing synthetic route fixture. Party,
cash, balls and current coordinates mirror the paid closed capture-copy shape;
this proves admission composition, not a native route or capture outcome.
"""

from dataclasses import dataclass, replace
from types import SimpleNamespace as N

import pytest
from test_red_goal_skills import _AreaExecutor
from test_red_resource_goal_router import fixture as fixture

import pokemon_red_completion.red_regional_acquisition as regional
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import RedBoxCollectionState, RedCurrentBoxState
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedGoalOpportunityEnumerator
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedGoalSkillAvailability,
)
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridor,
    bind_red_capture_status_profile,
    bind_red_capture_weakening_profile,
    bind_red_optional_capture_status_profile,
    retarget_red_wild_profile,
)


def profile():
    from test_red_living_dex_wild_corridor import _local_discovery_profile

    return _local_discovery_profile()


def current_no_helper_party():
    rows = [
        (113, 8, 25, (40, 81)),
        (165, 20, 42, (33, 39, 98, 158)),
        (150, 22, 60, (16, 28, 98, 18)),
        (179, 25, 66, (33, 61, 145, 55)),
        (5, 15, 42, (64, 45, 43, 31)),
        (108, 13, 36, (35, 43, 40, 91)),
    ]
    return PartyObservation(
        tuple(
            PartyMemberObservation(
                i,
                species,
                level,
                hp,
                hp,
                moves=tuple(MoveObservation(move, 10) for move in moves),
            )
            for i, (species, level, hp, moves) in enumerate(rows, 1)
        )
    )


@dataclass
class Runtime:
    profile: object
    reader: object
    emulator: object
    adapter: object
    provider: object
    registration_policy: object = None

    def provider_for(self, kind, actions):
        assert kind is GoalKind.ACQUIRE_SPECIES
        return self.provider

    def enumerator(self, actions):
        return RedGoalOpportunityEnumerator((self.provider,))


@pytest.mark.parametrize("optional", [False, True])
def test_actual_regional_enumeration_keeps_optional_no_helper_capture_only(
    fixture,
    monkeypatch,
    optional,
):
    f = fixture
    f.reader.raw = replace(
        f.reader.raw,
        map_id=5,
        player_x=23,
        player_y=14,
        player_money=446,
        bag_items=((4, 5),),
        bag_item_ids=(4,),
    )
    f.reader.read_retained_outside_map = lambda: 5
    boxes = tuple(RedCurrentBoxState(i, (), ()) for i in range(12))
    box_reads = []
    f.reader.read_all_box_states = lambda: (
        box_reads.append(True) or RedBoxCollectionState(boxes, 0, True)
    )
    f.reader.read_box_move_members = lambda _: ()
    observation = replace(f.adapter.observe(), party=current_no_helper_party())
    selected_profile = (
        bind_red_optional_capture_status_profile(profile())
        if optional
        else bind_red_capture_status_profile(profile())
    )
    provider = RedAreaSurveyGoalProvider(
        "wild:Route2:grass",
        _AreaExecutor(f.reader, f.actions),
        f.actions,
        f.port,
        f.adapter,
        boundary=lambda _: RedGoalSkillAvailability.available(),
    )
    runtime = Runtime(selected_profile, f.reader, f.port, f.adapter, provider)
    f.world.terrain, f.world.local_graphs = {13: None}, {13: None}
    f.world.object_blockers = {13: frozenset()}
    f.world.macro_graph = N(warp_locations={})
    from pokemon_red_completion.global_router import MacroEdge, MacroPath, MacroTransition
    from pokemon_red_completion.local_router import LocalPath
    from pokemon_red_completion.route_plan import RoutePlan, RouteSegment

    def plan(start, goal_map, *, goal_at):
        approach = LocalPath((start.at,), (), ("land",))
        segment = RouteSegment(
            start.map_id,
            goal_map,
            approach,
            MacroTransition(start.at, goal_at, "right"),
            "connection",
            False,
        )
        return RoutePlan(
            MacroPath((start.map_id, goal_map), (MacroEdge(goal_map),)),
            start.at,
            "land",
            (segment,),
            None,
            goal_at,
            "land",
        )

    f.world.plan_feasible_to_map = plan
    monkeypatch.setattr(regional, "RED_ACQUISITION_CATALOG", N(methods=()))
    monkeypatch.setattr(
        regional, "_rank_regional_sources", lambda *a, **k: (("wild:Route2:grass", 13),)
    )
    monkeypatch.setattr(
        regional,
        "derive_red_living_dex_wild_corridor",
        lambda *a, **k: RedLivingDexWildCorridor("wild:Route2:grass", 13, (4, 2), (3, 2)),
    )
    monkeypatch.setattr(regional, "bind_red_local_discovery_profile", lambda p, *a: p)
    import pokemon_red_completion.red_routed_capture_support as support

    original_preparation = support._capture_party_preparation
    pc_calls = []

    def prepare(*args, **kwargs):
        pc_calls.append(True)
        return original_preparation(*args, **kwargs)

    monkeypatch.setattr(support, "_capture_party_preparation", prepare)
    before, first_frame = f.reader.raw, f.port.frame_count
    rows = regional.enumerate_red_regional_acquisitions(
        runtime, observation, f.actions, f.world, maximum_actions=1000, maximum_frames=100000
    )
    assert len(rows) == int(optional)
    assert bool(pc_calls) is not optional
    assert f.actions.actions_executed == 0 and f.port.frame_count == first_frame
    assert f.reader.raw == before


def test_optional_mode_is_preserved_by_retarget_and_not_by_composite_weakening():
    optional = bind_red_optional_capture_status_profile(profile())
    target = RedLivingDexWildCorridor("wild:Route1:grass", 12, (4, 2), (3, 2))
    moved = retarget_red_wild_profile(optional, target)
    assert moved.providers[0].parameters["capture_party_preparation"] is False
    assert (
        bind_red_capture_weakening_profile(optional)
        .providers[0]
        .parameters["capture_party_preparation"]
        is True
    )
    mandatory = bind_red_capture_weakening_profile(profile())
    assert "capture_party_preparation" not in mandatory.providers[0].parameters
    assert bind_red_optional_capture_status_profile(mandatory) == mandatory


@pytest.mark.parametrize(
    "value,status,weakening",
    [
        (0, True, False),
        (None, True, False),
        ("false", True, False),
        (False, False, False),
        (False, True, True),
    ],
)
def test_optional_party_mode_rejects_implicit_or_contradictory_profiles(value, status, weakening):
    original = profile()
    spec = original.providers[0]
    parameters = dict(
        _thaw(spec.parameters),
        capture_status_support=status,
        capture_party_preparation=value,
        capture_weakening_support=weakening,
    )
    with pytest.raises(RedGoalContextProfileError, match="capture party preparation"):
        parse_red_goal_context_profile(
            build_red_goal_context_profile_payload(
                profile_id=original.profile_id,
                providers=((spec.kind, spec.mechanic, parameters),)
                + tuple((x.kind, x.mechanic, _thaw(x.parameters)) for x in original.providers[1:]),
            )
        )
