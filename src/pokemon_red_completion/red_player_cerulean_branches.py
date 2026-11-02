"""Fresh independent Cerulean story capabilities and immediate-action previews.

No priority or desired winner is supplied. The outer mixed menu retains all
real nonstory alternatives and chooses the actual executor. A travel preview
does not purport to predict the eventual boss battle after entering a building.
"""

from dataclasses import dataclass, replace

from .gen1_trainer_parties import trainer_party_quote
from .gen1_traversal import map_object_events
from .goal_manager_runtime import ExecutableGoalBinding
from .observation import EventFlag, MapId, event_flag_is_set
from .player_option_challenge import OptionChallenge
from .red_gym_reward import MISTY_REWARD
from .red_player_bill import bill_interaction_binding
from .red_player_cerulean_rival import cerulean_rival_binding, cerulean_rival_contract
from .red_player_field_goals import _field_ready
from .red_player_story_battle import story_battle_binding
from .red_player_story_obstruction import obstructing_story_battle_binding
from .red_player_story_travel import story_travel_binding


@dataclass(frozen=True)
class CeruleanStoryOption:
    objective_id: str
    binding: ExecutableGoalBinding
    challenge: OptionChallenge


def cerulean_story_options(
    runtime, actions, *, route, battler, combat_levels, battler_for_objective=None
):
    if battler_for_objective is not None and not callable(battler_for_objective):
        raise TypeError("story actor dispatch must be callable")

    def actor(objective):
        return battler if battler_for_objective is None else battler_for_objective(objective)

    if not _field_ready(runtime):
        return ()
    before = runtime.adapter.observe()
    available = {o.id for o in runtime.adapter.graph.available_objectives(before.game_state)}
    raw = before.raw
    result = []

    def add(objective, binding, *, contract=None, combat=False):
        if binding is None:
            return
        challenge = OptionChallenge(combat, False, 0.0, 0.0, 0.0)
        if contract is not None:
            quote = trainer_party_quote(
                route.rom, contract.trainer_identity[0], contract.trainer_identity[2]
            )
            challenge = OptionChallenge.from_levels(
                combat_levels=combat_levels, opponent_levels=tuple(m.level for m in quote.party)
            )
        result.append(
            CeruleanStoryOption(
                objective,
                replace(binding, story_objective_ref=objective),
                challenge,
            )
        )

    if "defeat_misty" in available:
        if raw.map_id == int(MapId.CERULEAN_GYM):
            contract = MISTY_REWARD.contract(route.rom, raw)
            binding = story_battle_binding(
                runtime,
                actions,
                contract=contract,
                route=route,
                battler=actor("defeat_misty"),
                reward=MISTY_REWARD,
            )
            if binding is not None:
                add("defeat_misty", binding, contract=contract)
            else:
                # Offer only an obstruction of an actual leader interaction
                # square, not arbitrary nearby trainers or a fixed battle list.
                leader = next(
                    o for o in map_object_events(route.rom, {raw.map_id}) if o.object_index == 1
                )
                for dy, dx in ((1, 0), (0, -1), (0, 1), (-1, 0)):
                    at = leader.y + dy, leader.x + dx
                    if min(at) < 0:
                        continue
                    binding = obstructing_story_battle_binding(
                        runtime,
                        actions,
                        objective_id="defeat_misty",
                        route=route,
                        battler=actor("defeat_misty"),
                        destination_at=at,
                        allow_sequence=True,
                    )
                    if binding is not None:
                        add("defeat_misty", binding, combat=True)
                        break
        else:
            add(
                "defeat_misty",
                story_travel_binding(
                    runtime,
                    actions,
                    objective_id="defeat_misty",
                    route=route,
                    frontier=True,
                    stop_at_map_boundary=True,
                ),
            )

    if "help_bill" in available:
        if raw.map_id == int(MapId.BILLS_HOUSE):
            add("help_bill", bill_interaction_binding(runtime, actions, route=route))
        elif raw.map_id == int(MapId.CERULEAN_CITY) and not event_flag_is_set(
            raw.event_flags, int(EventFlag.BEAT_CERULEAN_RIVAL)
        ):
            binding = cerulean_rival_binding(
                runtime, actions, route=route, battler=actor("help_bill")
            )
            if binding is not None:
                add(
                    "help_bill",
                    binding,
                    contract=cerulean_rival_contract(route.rom, runtime.reader),
                )
        else:
            binding = story_travel_binding(
                runtime,
                actions,
                objective_id="help_bill",
                route=route,
                frontier=True,
                stop_at_map_boundary=True,
            )
            if binding is not None:
                add("help_bill", binding)
            else:
                add(
                    "help_bill",
                    obstructing_story_battle_binding(
                        runtime,
                        actions,
                        objective_id="help_bill",
                        route=route,
                        battler=actor("help_bill"),
                        frontier=True,
                        allow_sequence=True,
                    ),
                    combat=True,
                )
    return tuple(result)
