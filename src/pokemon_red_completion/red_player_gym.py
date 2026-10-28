"""Compose existing observed gym travel/trainers/rewards without a fixed team."""

from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import cut_capabilities, map_object_events
from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import MapId, event_flag_is_set
from .party_preparation import PreparationPurpose
from .player_option_challenge import OptionChallenge
from .red_gym_reward import (
    BLAINE_REWARD,
    BROCK_REWARD,
    ERIKA_REWARD,
    GIOVANNI_REWARD,
    KOGA_REWARD,
    MISTY_REWARD,
    SABRINA_REWARD,
    SURGE_REWARD,
    GymReward,
)
from .red_party_preparation import observe_preparation_members
from .red_player_field_goals import _field_ready
from .red_player_gym_quiz import cinnabar_quiz_option
from .red_player_story_battle import story_battle_binding
from .red_player_story_obstruction import obstructing_story_battle_binding
from .red_player_story_travel import story_travel_binding
from .red_routed_trainer_funding import _face_trainer_boundary
from .red_story_battle import StoryTrainerContract
from .red_story_item_storage import completed_key_storage_binding
from .red_story_map_frontier import story_cut_frontier_target
from .route_plan import RoutePlanningError


def pending_gym_reward_binding(runtime, actions, *, route):
    """Finish an already selected/won local encounter; never choose another fight."""
    raw = runtime.reader.read()
    rewards = tuple(
        r
        for r in (
            BROCK_REWARD,
            MISTY_REWARD,
            SURGE_REWARD,
            ERIKA_REWARD,
            KOGA_REWARD,
            SABRINA_REWARD,
            BLAINE_REWARD,
            GIOVANNI_REWARD,
        )
        if r.pending(raw)
    )
    if not rewards or not runtime.reader.read_input_readiness().ready:
        return None
    if len(rewards) != 1:
        raise ValueError("pending gym reward is ambiguous")
    reward = rewards[0]
    source, used, terminal = runtime.emulator.save_state_bytes(), False, None

    def execute():
        nonlocal used, terminal
        if (
            used
            or runtime.emulator.save_state_bytes() != source
            or not reward.pending(runtime.reader.read())
        ):
            raise ValueError("pending reward is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        # Movement flags are ready while multi-page reward text still waits.
        # CANCEL advances only the existing text; A can reopen the NPC.
        for _ in range(32):
            if _field_ready(runtime):
                break
            current = runtime.reader.read()
            if (
                current.battle_state
                or current.map_id != raw.map_id
                or (current.player_y, current.player_x) != (raw.player_y, raw.player_x)
                or current.bag_items != raw.bag_items
                or current.player_money != raw.player_money
            ):
                raise RuntimeError("pending gym dialogue changed its retained boundary")
            actions.execute(MacroAction(MacroActionKind.CANCEL))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
        if not _field_ready(runtime):
            raise RuntimeError("pending gym dialogue did not release field control")
        stored = []
        if not reward.capacity_available(runtime.reader.read()):
            storage = completed_key_storage_binding(runtime, actions, route=route, reserved_slots=1)
            if storage is None:
                raise RuntimeError("pending reward has no legal completed-key capacity recovery")
            report = storage.execute()
            if storage.verify(report).status is not GoalDecisionOutcome.SUCCEEDED:
                raise RuntimeError("pending reward key deposit did not verify")
            stored = report.evidence["stored_items"]
            replace(
                route, destination_map=reward.map_id, destination_at=(raw.player_y, raw.player_x)
            )(
                actions,
                runtime.reader,
                runtime.emulator,
            )
        (leader,) = [
            o for o in map_object_events(route.rom, {reward.map_id}) if o.object_index == 1
        ]
        facing = {(1, 0): "up", (0, -1): "right", (0, 1): "left", (-1, 0): "down"}.get(
            (raw.player_y - leader.y, raw.player_x - leader.x)
        )
        if facing is None:
            raise RuntimeError("pending reward lost its original leader interaction boundary")
        _face_trainer_boundary(actions, runtime.reader, facing)
        before = runtime.reader.read()
        evidence = reward.settle(runtime.reader, actions, before=before, victory_money=0)
        if not reward.received(runtime.reader.read()) or not _field_ready(runtime):
            raise RuntimeError("pending gym reward did not independently settle")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="pending_earned_gym_reward",
                reward=evidence,
                stored_items=stored,
                prior_victory_preserved=True,
                model_queries=0,
                new_battles=0,
                sales=0,
            ),
        )

    def verify(_):
        return (
            GoalVerification.succeeded()
            if terminal is not None
            and runtime.emulator.save_state_bytes() == terminal
            and reward.received(runtime.reader.read())
            and _field_ready(runtime)
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:pending-gym-reward:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL,
        0.1,
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
    )


def gym_story_option(
    runtime,
    actions,
    *,
    reward,
    route,
    battler,
    preparation_plan,
    continuous_travel=False,
    allow_surf=False,
    trainer_battler_for_contract=None,
    observe_matchup_binding=None,
    observe_leader_binding: (
        Callable[[StoryTrainerContract, ExecutableGoalBinding], None] | None
    ) = None,
):
    """Return an executable option and its actual next-component challenge.

    A route to the gym does not pretend to be a leader battle. Combat previews
    describe only the exact leader or ordinary obstruction currently executable.
    The optional private leader observer distinguishes those execution scopes;
    known opposition alone does not identify a leader.
    An optional exact-contract resolver affects ordinary obstructions only;
    it cannot replace the leader's separately supplied battle actor.
    Opt-in continuous travel uses the existing guarded multi-map executor until
    the selected gym, rather than asking the model to pick a new destination at
    every border. Actual obstructions still become separate combat choices.
    """
    if observe_matchup_binding is not None and not callable(observe_matchup_binding):
        raise TypeError("gym matchup binding observer must be callable")
    if observe_leader_binding is not None and not callable(observe_leader_binding):
        raise TypeError("gym leader binding observer must be callable")
    if type(continuous_travel) is not bool:
        raise TypeError("continuous gym travel must be an explicit boolean")
    if trainer_battler_for_contract is not None and not callable(trainer_battler_for_contract):
        raise TypeError("gym obstruction battler resolver must be callable")
    if type(allow_surf) is not bool:
        raise TypeError("gym Surf transport scope must be boolean")
    if allow_surf and getattr(route, "allow_surf", False) is not True:
        raise ValueError("gym Surf quote requires a Surf-enabled native executor")
    if not isinstance(reward, GymReward):
        raise TypeError("gym composition requires a declared native reward contract")
    if not _field_ready(runtime):
        return None
    observation = runtime.adapter.observe()
    if reward.objective_id not in {
        o.id for o in runtime.adapter.graph.available_objectives(observation.game_state)
    }:
        return None
    objective, raw = reward.objective_id, runtime.reader.read()
    matchup_source = (
        runtime.emulator.save_state_bytes() if observe_matchup_binding is not None else None
    )
    if not reward.capacity_available(raw):
        return None
    combat, leader_contract, binding = False, None, None
    obstruction_quote = None

    def observe_obstruction(contract, quoted_binding):
        nonlocal obstruction_quote
        if (
            obstruction_quote is not None
            or not isinstance(contract, StoryTrainerContract)
            or contract.objective_id != objective
            or contract.map_id != raw.map_id
            or contract.battle_plan_id != "observed-story-obstruction"
            or contract.defeated_event is None
            or event_flag_is_set(raw.event_flags, contract.defeated_event)
            or contract.victory_items
            or contract.victory_badge_bits
        ):
            raise ValueError("gym obstruction witness differs from its current component")
        obstruction_quote = contract, quoted_binding

    if raw.map_id == reward.map_id:
        leader_contract = reward.contract(route.rom, raw)
        binding = story_battle_binding(
            runtime, actions, contract=leader_contract, route=route, battler=battler, reward=reward
        )
        combat = binding is not None
        if binding is None:
            leader_contract = None
            if objective == "defeat_blaine":
                quiz = cinnabar_quiz_option(runtime, actions, route=route)
                if quiz is not None:
                    return quiz
            (leader,) = [
                o for o in map_object_events(route.rom, {raw.map_id}) if o.object_index == 1
            ]
            for dy, dx in ((1, 0), (0, -1), (0, 1), (-1, 0)):
                at = leader.y + dy, leader.x + dx
                if min(at) < 0:
                    continue
                obstruction_quote = None
                binding = obstructing_story_battle_binding(
                    runtime,
                    actions,
                    objective_id=objective,
                    route=route,
                    battler=battler,
                    destination_at=at,
                    allow_sequence=True,
                    trainer_battler_for_contract=trainer_battler_for_contract,
                    allow_surf=allow_surf,
                    observe_binding=observe_obstruction,
                )
                if binding is not None:
                    combat = True
                    break
            if binding is None:
                start = Gen1TraversalObserver(
                    runtime.reader,
                    capability_projector=cut_capabilities,
                    hazard_projector=Gen1TrainerSightProjector(
                        route.rom, runtime.reader, full_event_offsets=True
                    ),
                ).observe()
                try:
                    at = story_cut_frontier_target(
                        route.route_world, start, (leader.y + 1, leader.x)
                    )
                    binding = story_travel_binding(
                        runtime, actions, objective_id=objective, route=route, destination_at=at
                    )
                except RoutePlanningError:
                    pass
    else:
        # A statue changes doors in multiple Mansion rooms. Observe the next
        # room before quoting beyond it; an old off-screen grid is not a
        # current exit witness. This limits navigation, not the chosen gym.
        continuous_route = continuous_travel and raw.map_id not in {
            int(MapId.POKEMON_MANSION_1F), int(MapId.POKEMON_MANSION_2F),
            int(MapId.POKEMON_MANSION_3F), int(MapId.POKEMON_MANSION_B1F),
        }
        binding = story_travel_binding(
            runtime,
            actions,
            objective_id=objective,
            route=route,
            frontier=not continuous_route,
            stop_at_map_boundary=not continuous_route,
            allow_surf=allow_surf,
        )
        if binding is None and continuous_route:
            # A bounded complete quote can miss a longer feasible approach.
            # Reuse the existing real next-boundary quote before declaring the
            # selected gym unreachable. Never execute its object-free preview.
            binding = story_travel_binding(
                runtime, actions, objective_id=objective, route=route,
                frontier=True, stop_at_map_boundary=True, allow_surf=allow_surf,
            )
        if binding is None:
            binding = obstructing_story_battle_binding(
                runtime,
                actions,
                objective_id=objective,
                route=route,
                battler=battler,
                frontier=True,
                allow_sequence=True,
                trainer_battler_for_contract=trainer_battler_for_contract,
                allow_surf=allow_surf,
                observe_binding=observe_obstruction,
            )
            combat = binding is not None
    if binding is None:
        return None
    challenge = OptionChallenge(combat, False, 0.0, 0.0, 0.0)
    if obstruction_quote is not None and obstruction_quote[1] is not binding:
        raise ValueError("gym obstruction witness does not belong to the admitted binding")
    exact_contract = leader_contract if leader_contract is not None else (
        obstruction_quote[0] if obstruction_quote is not None else None
    )
    quote = None
    if exact_contract is not None:
        members = observe_preparation_members(runtime.emulator, preparation_plan)
        levels = tuple(
            m.observation.level for m in members if m.purpose is PreparationPurpose.COMBAT
        )
        # No utility or undecided member is invented as a combat reference.
        if levels or observe_matchup_binding is not None:
            trainer_class, trainer_set = reward.trainer_class, reward.trainer_set
            if obstruction_quote is not None:
                contract = obstruction_quote[0]
                trainer_class, _, trainer_set = contract.trainer_identity
            quote = trainer_party_quote(route.rom, trainer_class, trainer_set)
            if levels:
                challenge = OptionChallenge.from_levels(
                    combat_levels=levels, opponent_levels=tuple(m.level for m in quote.party)
                )
    result = replace(binding, story_objective_ref=objective)
    if leader_contract is not None and observe_leader_binding is not None:
        observe_leader_binding(leader_contract, result)
    if observe_matchup_binding is not None and exact_contract is not None:
        from .red_player_matchup import ExactTrainerMatchupWitness

        if not combat or runtime.emulator.save_state_bytes() != matchup_source:
            raise ValueError("gym matchup witness changed its current native boundary")
        witness = ExactTrainerMatchupWitness(
            source_sha256=sha256(matchup_source).hexdigest(),
            binding_ref=result.binding_ref,
            contract=exact_contract,
            quote=quote,
        )
        observe_matchup_binding(witness)
        if runtime.emulator.save_state_bytes() != matchup_source:
            raise ValueError("gym matchup observer changed native state")
    return result, challenge
