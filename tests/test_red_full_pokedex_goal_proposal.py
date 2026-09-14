"""Real registry/router composition with only cartridge/IO seams substituted."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_resource_goal_router import _World
from test_registered_runtime_binding import bound_fixture

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.global_router import MacroEdge, MacroPath, MacroTransition
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetCheckpoint,
)
from pokemon_red_completion.goal_manager_runtime import (
    CompletionFirstGoalTeacher,
    GoalExecutionReport,
)
from pokemon_red_completion.local_router import LocalPath
from pokemon_red_completion.red_acquisition import RedAcquisitionKind
from pokemon_red_completion.red_bounded_player import preflight_red_bounded_player
from pokemon_red_completion.red_collection import red_internal_species_id, red_species_ref
from pokemon_red_completion.red_full_pokedex_goal_proposal import (
    RedFullPokedexGoalProposalError,
    RedFullPokedexPlayerAttempt,
    build_red_full_pokedex_player_observer,
    propose_red_full_pokedex_goals,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution
from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RouteSegment


class _CrossMapWorld(_World):
    def plan_feasible_to_map(self, start, goal_map, *, goal_at):
        if self.fail or start.map_id == goal_map:
            return super().plan_feasible_to_map(start, goal_map, goal_at=goal_at)
        self.plans.append((start, goal_map, goal_at))
        transition = MacroTransition(start.at, goal_at, "right")
        return RoutePlan(
            macro_path=MacroPath((start.map_id, goal_map), (MacroEdge(goal_map),)),
            start_at=start.at, start_mode="land",
            segments=(RouteSegment(start.map_id, goal_map,
                                   LocalPath((start.at,), (), ("land",)), transition,
                                   "connection", False),),
            terminal_approach=None, terminal_at=goal_at, terminal_mode="land",
        )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    runtime, reader, owned = bound_fixture(tmp_path, inherited=(78,))
    # The route is deliberately off-Center. Synthetic geometry does not prove
    # cartridge travel; the native providers/availability tests are not mocked.
    parameters = {
        "source_id": "wild:Route1:grass", "label": "test capture",
        "map_id": 12, "player_x": 4, "player_y": 3,
        "forward_directions": ["right", "left"], "starting_endpoint": "south",
        "maximum_legs": 8, "maximum_seek_steps": 32, "maximum_encounters": 8,
    }
    profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="shared-departure-test",
        providers=tuple(sorted(tuple((s.kind, s.mechanic, dict(s.parameters))
                                     for s in runtime.profile.providers
                        if s.kind is not GoalKind.ACQUIRE_SPECIES) + (
            (GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE, parameters),
        ), key=lambda s: tuple(GoalKind).index(s[0]))),
    ))
    runtime = replace(runtime, profile=profile,
                      registration_policy=replace(runtime.registration_policy,
                                                  completion_scope="local_red"))
    actions = CountingExecutor(SimpleNamespace(execute=lambda _: pytest.fail("unexpected input")))
    world = _CrossMapWorld()
    monkeypatch.setattr("pokemon_red_completion.red_native_boxed_evolution.wild_tables",
                        lambda _: {22: [(10, 0x21), (15, 0x6C)]})
    monkeypatch.setattr("pokemon_red_completion.red_resource_goal_router.Gen1TrainerSightProjector",
                        lambda *_: None)
    monkeypatch.setattr("pokemon_red_completion.red_resource_goal_router.Gen1TraversalObserver",
                        lambda *_a, **_k: SimpleNamespace(observe=lambda: TraversalSnapshot(
                            int(reader.raw.map_id),
                            (reader.raw.player_y, reader.raw.player_x), True,
                            mode="land")))
    native = bind_native_boxed_evolution(runtime, world)
    router = RedResourceGoalRouter(native, actions, world)
    return SimpleNamespace(runtime=runtime, native=native, router=router, actions=actions,
                           reader=reader, world=world, owned=owned, parameters=parameters)


@pytest.mark.nonconsuming_direct_rehearsal
def test_shared_departure_uses_real_travel_capture_and_native_evolution(setup):
    observed = setup.native.adapter.observe()
    local = setup.native.enumerator(setup.actions).enumerate(observed)
    assert GoalKind.ACQUIRE_SPECIES not in {b.kind for b in local.bindings}
    proposal = propose_red_full_pokedex_goals(setup.router, observed)
    assert proposal.acquisition_family_count == 2
    capture, evolution = proposal.candidates
    assert capture.acquisition_kind is RedAcquisitionKind.WILD
    assert capture.target_numbers == (16, 19)
    assert capture.binding.binding_ref.startswith("red-resource-goal:")
    assert evolution.target_numbers == (78,)
    assert red_species_ref(78) in setup.native.registration_policy.registered(
        observed.collection_observation)
    assert setup.actions.actions_executed == setup.native.emulator.frame_count == 0


def test_public_menu_hides_identity_and_is_the_same_player_binding_set(setup):
    proposal = propose_red_full_pokedex_goals(setup.router, setup.native.adapter.observe())
    assert all(any(c.binding is b for b in proposal.binding_set.bindings)
               for c in proposal.candidates)
    public = proposal.public_dict()
    assert public["candidate_count"] == public["acquisition_family_count"] == 2
    assert public["controller_actions"] == public["emulator_frames"] == 0
    encoded = json.dumps(public)
    for secret in (setup.runtime.profile.profile_sha256, "wild:Route1:grass",
                   "pokemon:national:", "red-resource-goal:"):
        assert secret not in encoded


@pytest.mark.nonconsuming_direct_rehearsal
def test_existing_player_bridge_consumes_full_local_checkpoint_and_same_menu(setup):
    observer = build_red_full_pokedex_player_observer(setup.runtime, setup.actions, setup.world)
    result = observer()
    assert {b.kind for b in result.binding_set.bindings} >= {
        GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
    assert len(result.binding_set.opportunities) == len(GoalKind)
    assert len(result.collection.target_species) == 151
    assert result.collection.completion_scope == "local_red"
    assert result.collection.registered_species == len(setup.owned)
    assert red_species_ref(78) in result.collection.global_species
    assert red_species_ref(78) not in result.collection.local_species


@pytest.mark.nonconsuming_direct_rehearsal
def test_action_free_preflight_qualifies_real_two_family_menu(setup):
    observer = build_red_full_pokedex_player_observer(
        setup.runtime,
        setup.actions,
        setup.world,
        maximum_quanta=128,
        maximum_controller_actions=30_000,
        maximum_emulator_frames=3_000_000,
        quote_resource_costs=True,
    )

    class Meter:
        @staticmethod
        def checkpoint():
            return CompositionBudgetCheckpoint(
                setup.actions.actions_executed,
                setup.native.emulator.frame_count,
            )

    result = preflight_red_bounded_player(
        observe=observer,
        budget_meter=Meter(),
        assignment_id="nonconsuming-direct-rehearsal",
        authorities=(
            ("rehearsal-challenger", CompletionFirstGoalTeacher()),
            ("rehearsal-baseline", CompletionFirstGoalTeacher()),
        ),
    )
    assert set(result.available_goal_kinds) >= {
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.EVOLVE_SPECIES,
    }
    assert len(result.choices) == 2
    assert result.public_dict()["status"] == "ready"
    assert setup.actions.actions_executed == 0
    assert setup.native.emulator.frame_count == 0


@pytest.mark.parametrize("failure", ["route", "precursor", "reserve", "local_complete", "balls"])
def test_one_family_or_unready_state_stops_before_input(setup, failure):
    if failure == "route":
        setup.world.fail = True
    elif failure == "precursor":
        setup.reader.boxes = replace(setup.reader.boxes, boxes=tuple(
            replace(box, species_ids=(), levels=()) for box in setup.reader.boxes.boxes))
    elif failure == "reserve":
        setup.native = bind_native_boxed_evolution(
            replace(setup.runtime, registration_policy=replace(
                setup.runtime.registration_policy, protected_counts={red_species_ref(77): 1})),
            setup.world,
        )
        setup.router.runtime = setup.native
    elif failure == "local_complete":
        setup.owned.add(78)
    else:
        setup.reader.raw = replace(setup.reader.raw, bag_items=(), bag_item_ids=())
    with pytest.raises(RedFullPokedexGoalProposalError, match="at least two"):
        propose_red_full_pokedex_goals(setup.router, setup.native.adapter.observe())
    assert setup.actions.actions_executed == 0


def test_allowlist_uses_actual_capture_provider_not_entire_canonical_source(setup):
    profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="allowlist-test", providers=tuple(
            (s.kind, s.mechanic, {**dict(s.parameters), "capture_species_numbers": [19]}
             if s.kind is GoalKind.ACQUIRE_SPECIES else dict(s.parameters))
            for s in setup.native.profile.providers),
    ))
    setup.native.profile = profile
    proposal = propose_red_full_pokedex_goals(setup.router, setup.native.adapter.observe())
    assert proposal.candidates[0].target_numbers == (19,)


@pytest.mark.parametrize("change", ["position", "money", "flags", "policy", "frame"])
def test_selected_binding_rejects_changed_departure_before_controller_input(setup, change):
    proposal = propose_red_full_pokedex_goals(setup.router, setup.native.adapter.observe())
    if change == "position":
        setup.reader.raw = replace(setup.reader.raw, player_x=4)
    elif change == "money":
        setup.reader.raw = replace(setup.reader.raw, player_money=1)
    elif change == "flags":
        setup.owned.add(78)
    elif change == "policy":
        setup.native.registration_policy = replace(setup.native.registration_policy,
                                                   completion_scope="shared")
    else:
        setup.native.emulator.frame_count += 1
    with pytest.raises(RedFullPokedexGoalProposalError, match="changed"):
        proposal.candidates[0].binding.execute()
    with pytest.raises(RedFullPokedexGoalProposalError, match="consumed"):
        proposal.candidates[1].binding.execute()
    assert setup.actions.actions_executed == 0


def test_stale_caller_observation_is_rejected(setup):
    old = setup.native.adapter.observe()
    setup.reader.raw = replace(setup.reader.raw, player_x=4)
    with pytest.raises(RedFullPokedexGoalProposalError, match="changed"):
        propose_red_full_pokedex_goals(setup.router, old)


def test_arbitrary_bindings_and_legacy_policy_are_not_admitted(setup):
    observation = setup.native.adapter.observe()
    bindings = setup.native.enumerator(setup.actions).enumerate(observation)
    with pytest.raises(TypeError, match="live Red resource router"):
        propose_red_full_pokedex_goals(bindings, observation)
    setup.native.registration_policy = replace(setup.native.registration_policy,
                                               completion_scope="shared")
    with pytest.raises(RedFullPokedexGoalProposalError, match="explicit full-local"):
        propose_red_full_pokedex_goals(setup.router, observation)


def test_only_selected_skill_is_dispatched_once_even_when_it_fails(setup):
    calls = []

    def native_failure(request, actions):
        calls.append("evolution")
        return GoalExecutionReport(0, 0, {"test_only": True})

    # Substitute only the final IO execution in this dispatch test. Its zero-cost
    # report is not verified success and is never admitted to learning.
    setup.native.boxed_level_evolution_executor = native_failure
    proposal = propose_red_full_pokedex_goals(setup.router, setup.native.adapter.observe())
    proposal.candidates[1].binding.execute()
    assert calls == ["evolution"]
    for binding in proposal.binding_set.bindings:
        with pytest.raises(RedFullPokedexGoalProposalError, match="consumed"):
            binding.execute()
    assert calls == ["evolution"]


def test_attempt_authority_survives_fresh_action_gates(setup):
    attempt = RedFullPokedexPlayerAttempt()
    first_observer = build_red_full_pokedex_player_observer(
        setup.runtime, setup.actions, setup.world, attempt=attempt,
    )
    first_observer.runtime.boxed_level_evolution_executor = (
        lambda _request, _actions: GoalExecutionReport(0, 0, {"test_only": True})
    )
    first = first_observer()
    second_observer = build_red_full_pokedex_player_observer(
        setup.runtime, setup.actions, setup.world, attempt=attempt,
    )
    second = second_observer()
    next(b for b in first.binding_set.bindings if b.kind is GoalKind.EVOLVE_SPECIES).execute()
    with pytest.raises(RedFullPokedexGoalProposalError, match="already attempted"):
        next(b for b in second.binding_set.bindings if b.kind is GoalKind.EVOLVE_SPECIES).execute()


@pytest.mark.parametrize("failed", [False, True])
def test_terminal_observation_survives_lost_diversity_and_has_no_second_authority(setup, failed):
    observer = build_red_full_pokedex_player_observer(setup.runtime, setup.actions, setup.world)

    def final_io(request, actions):
        setup.owned.add(78)
        setup.reader.boxes = replace(setup.reader.boxes, boxes=tuple(
            replace(box, species_ids=tuple(red_internal_species_id(78)
                                          if s == red_internal_species_id(77) else s
                                          for s in box.species_ids))
            for box in setup.reader.boxes.boxes))
        if failed:
            raise RuntimeError("test execution failed after partial progress")
        return GoalExecutionReport(0, 0, {"test_only": True})

    observer.runtime.boxed_level_evolution_executor = final_io
    first = observer()
    # A second read before selection must not create a second execution allowance.
    second = observer()
    chosen = next(b for b in first.binding_set.bindings if b.kind is GoalKind.EVOLVE_SPECIES)
    if failed:
        with pytest.raises(RuntimeError, match="partial progress"):
            chosen.execute()
    else:
        chosen.execute()
    terminal = observer()
    assert terminal.collection.registered_species == first.collection.registered_species + 1
    assert terminal.binding_set.bindings == ()
    assert len(terminal.binding_set.opportunities) == len(GoalKind)
    for binding in second.binding_set.bindings:
        with pytest.raises(RedFullPokedexGoalProposalError, match="already attempted"):
            binding.execute()
