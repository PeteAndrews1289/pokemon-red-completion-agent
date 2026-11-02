"""Connect the existing learned story battler to the first native rival gate.

Only approach/intro/dialogue are mechanics. No deterministic combat chapter is
invoked, and winning is not fabricated from the lab's shared resolution event.
"""

from dataclasses import replace

from .gen1_trainer_parties import trainer_party_quote
from .observation import EventFlag, MapId, event_flag_is_set
from .player_option_challenge import OptionChallenge
from .red_player_cerulean_rival import scripted_rival_binding
from .red_story_battle import StoryTrainerContract


def lab_rival_contract(rom, reader):
    raw = reader.read()
    event = int(EventFlag.BATTLED_RIVAL_IN_OAKS_LAB)
    if raw.event_flags is None or event_flag_is_set(raw.event_flags, event):
        raise ValueError("lab rival is resolved or unreadable")
    starter = reader.read_rival_starter()
    matches = [q for n in (1, 2, 3)
        if (q := trainer_party_quote(rom, 225, n)).party
        and len(q.party) == 1 and q.party[0].internal_species == starter]
    if len(matches) != 1:
        raise ValueError("lab rival quote differs from the native starter")
    quote = matches[0]
    return StoryTrainerContract("receive_pokedex", "lab-rival-gate", int(MapId.OAKS_LAB),
        (225, 25, quote.trainer_set), event, quote.expected_victory_money)


def lab_rival_story_option(runtime, actions, observation=None, *, route, battler,
                           battler_for_contract=None):
    if (runtime.reader.read().map_id != int(MapId.OAKS_LAB)
            or runtime.reader.read_oaks_errand_state(runtime.reader.read()).battled_rival):
        return None
    if battler_for_contract is not None:
        if not callable(battler_for_contract):
            raise TypeError("lab story actor selector must be callable")
        battler = battler_for_contract(lab_rival_contract(route.rom, runtime.reader))
    binding = scripted_rival_binding(runtime, actions, route=route, battler=battler,
        objective_id="receive_pokedex", map_id=int(MapId.OAKS_LAB),
        contract_factory=lab_rival_contract,
        already_defeated=lambda: runtime.reader.read_oaks_errand_state(
            runtime.reader.read()).battled_rival,
        entries=(((5, 4), "down"),))
    return None if binding is None else (
        replace(binding, story_objective_ref="receive_pokedex"),
        OptionChallenge(True, False, 0., 0., 0.))
