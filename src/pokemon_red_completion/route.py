"""High-level, completion-first Pokémon Red quest graph.

This route encodes public game semantics only.  Navigation coordinates,
revision-specific memory observations, and private emulator artifacts belong in
adapters below this planning layer.
"""

from __future__ import annotations

from pokemon_red_completion.quest import Objective, QuestGraph, Specialist

HALL_OF_FAME_FACT = "game:hall_of_fame"

_OBJECTIVE_TARGET_REGIONS: dict[str, str] = {
    "begin_adventure": "pallet",
    "choose_starter": "pallet",
    "receive_pokedex": "pallet",
    "reach_pewter": "pewter",
    "defeat_brock": "pewter",
    "reach_cerulean": "cerulean",
    "help_bill": "cerulean",
    "defeat_misty": "cerulean",
    "reach_vermilion": "vermilion",
    "obtain_cut": "vermilion",
    "defeat_surge": "vermilion",
    "reach_lavender": "lavender",
    "reach_celadon": "celadon",
    "clear_rocket_hideout": "celadon",
    "obtain_silph_scope": "celadon",
    "rescue_fuji": "lavender",
    "reach_fuchsia": "fuchsia",
    "obtain_surf": "fuchsia",
    "obtain_strength": "fuchsia",
    "defeat_koga": "fuchsia",
    "defeat_erika": "celadon",
    "reach_saffron": "saffron",
    "liberate_silph": "saffron",
    "defeat_sabrina": "saffron",
    "reach_cinnabar": "cinnabar",
    "obtain_secret_key": "cinnabar",
    "defeat_blaine": "cinnabar",
    "defeat_giovanni": "viridian",
    "cross_victory_road": "indigo",
    "defeat_lorelei": "league",
    "defeat_bruno": "league",
    "defeat_agatha": "league",
    "defeat_lance": "league",
    "defeat_champion": "league",
    "enter_hall_of_fame": "league",
}


def _objective(
    objective_id: str,
    title: str,
    fact: str,
    specialist: Specialist,
    *prerequisites: str,
    priority: int = 100,
) -> Objective:
    return Objective(
        id=objective_id,
        title=title,
        completion_facts=frozenset({fact}),
        specialist=specialist,
        prerequisites=frozenset(prerequisites),
        priority=priority,
        target_region=_OBJECTIVE_TARGET_REGIONS.get(objective_id),
    )


def build_completion_quest_graph() -> QuestGraph:
    """Build the power-on-to-Hall-of-Fame completion contract.

    The graph intentionally permits legal midgame work in parallel.  For
    example, the Celadon Gym, Rocket Hideout, and Saffron access branches can be
    completed in any order compatible with their own prerequisites.
    """

    objectives = (
        _objective(
            "power_on",
            "Verify a clean power-on",
            "system:clean_power_on",
            Specialist.BOOTSTRAP,
            priority=0,
        ),
        _objective(
            "begin_adventure",
            "Complete the opening sequence",
            "story:adventure_begun",
            Specialist.INTERACTION,
            "power_on",
        ),
        _objective(
            "choose_starter",
            "Choose and verify a starter Pokémon",
            "party:starter_obtained",
            Specialist.MENU,
            "begin_adventure",
        ),
        _objective(
            "receive_pokedex",
            "Deliver Oak's Parcel and receive the Pokédex",
            "story:pokedex_received",
            Specialist.INTERACTION,
            "choose_starter",
        ),
        _objective(
            "reach_pewter",
            "Reach Pewter City",
            "location:pewter_city",
            Specialist.NAVIGATION,
            "receive_pokedex",
        ),
        _objective(
            "defeat_brock",
            "Defeat Brock",
            "badge:boulder",
            Specialist.BATTLE,
            "reach_pewter",
        ),
        _objective(
            "reach_cerulean",
            "Reach Cerulean City",
            "location:cerulean_city",
            Specialist.NAVIGATION,
            "defeat_brock",
        ),
        _objective(
            "help_bill",
            "Help Bill and obtain the S.S. Ticket",
            "item:ss_ticket",
            Specialist.INTERACTION,
            "reach_cerulean",
            priority=10,
        ),
        _objective(
            "defeat_misty",
            "Defeat Misty",
            "badge:cascade",
            Specialist.BATTLE,
            "reach_cerulean",
            priority=20,
        ),
        _objective(
            "reach_vermilion",
            "Reach Vermilion City",
            "location:vermilion_city",
            Specialist.NAVIGATION,
            "help_bill",
            priority=10,
        ),
        _objective(
            "obtain_cut",
            "Obtain HM01 Cut aboard the S.S. Anne",
            "move:cut_available",
            Specialist.INTERACTION,
            "reach_vermilion",
            priority=10,
        ),
        _objective(
            "defeat_surge",
            "Defeat Lt. Surge",
            "badge:thunder",
            Specialist.BATTLE,
            "obtain_cut",
            "defeat_misty",
        ),
        _objective(
            "reach_lavender",
            "Traverse Rock Tunnel and reach Lavender Town",
            "location:lavender_town",
            Specialist.NAVIGATION,
            "defeat_surge",
        ),
        _objective(
            "reach_celadon",
            "Reach Celadon City",
            "location:celadon_city",
            Specialist.NAVIGATION,
            "reach_lavender",
        ),
        _objective(
            "clear_rocket_hideout",
            "Clear the Rocket Hideout",
            "story:rocket_hideout_cleared",
            Specialist.BATTLE,
            "reach_celadon",
            priority=10,
        ),
        _objective(
            "obtain_silph_scope",
            "Secure the Silph Scope",
            "item:silph_scope",
            Specialist.INTERACTION,
            "clear_rocket_hideout",
            priority=10,
        ),
        _objective(
            "rescue_fuji",
            "Resolve Pokémon Tower and rescue Mr. Fuji",
            "item:poke_flute",
            Specialist.BATTLE,
            "obtain_silph_scope",
            "reach_lavender",
            priority=10,
        ),
        _objective(
            "reach_fuchsia",
            "Wake Snorlax and reach Fuchsia City",
            "location:fuchsia_city",
            Specialist.NAVIGATION,
            "rescue_fuji",
            priority=10,
        ),
        _objective(
            "obtain_surf",
            "Obtain HM03 Surf in the Safari Zone",
            "move:surf_available",
            Specialist.NAVIGATION,
            "reach_fuchsia",
            priority=10,
        ),
        _objective(
            "obtain_strength",
            "Return the Gold Teeth and obtain HM04 Strength",
            "move:strength_available",
            Specialist.INTERACTION,
            "reach_fuchsia",
            priority=20,
        ),
        _objective(
            "defeat_koga",
            "Defeat Koga",
            "badge:soul",
            Specialist.BATTLE,
            "reach_fuchsia",
            priority=30,
        ),
        _objective(
            "defeat_erika",
            "Defeat Erika",
            "badge:rainbow",
            Specialist.BATTLE,
            "reach_celadon",
            priority=20,
        ),
        _objective(
            "reach_saffron",
            "Gain access to Saffron City",
            "location:saffron_city",
            Specialist.NAVIGATION,
            "reach_celadon",
            priority=20,
        ),
        _objective(
            "liberate_silph",
            "Liberate Silph Co.",
            "story:silph_co_liberated",
            Specialist.BATTLE,
            "clear_rocket_hideout",
            "reach_saffron",
            priority=20,
        ),
        _objective(
            "defeat_sabrina",
            "Defeat Sabrina",
            "badge:marsh",
            Specialist.BATTLE,
            "liberate_silph",
            priority=20,
        ),
        _objective(
            "reach_cinnabar",
            "Surf to Cinnabar Island",
            "location:cinnabar_island",
            Specialist.NAVIGATION,
            "obtain_surf",
            "defeat_koga",
        ),
        _objective(
            "obtain_secret_key",
            "Recover the Secret Key from Pokémon Mansion",
            "item:secret_key",
            Specialist.NAVIGATION,
            "reach_cinnabar",
        ),
        _objective(
            "defeat_blaine",
            "Defeat Blaine",
            "badge:volcano",
            Specialist.BATTLE,
            "obtain_secret_key",
        ),
        _objective(
            "defeat_giovanni",
            "Defeat Giovanni and earn the eighth badge",
            "badge:earth",
            Specialist.BATTLE,
            "defeat_brock",
            "defeat_misty",
            "defeat_surge",
            "defeat_erika",
            "defeat_koga",
            "defeat_sabrina",
            "defeat_blaine",
        ),
        _objective(
            "cross_victory_road",
            "Cross Victory Road",
            "story:victory_road_cleared",
            Specialist.NAVIGATION,
            "defeat_giovanni",
            "obtain_strength",
        ),
        _objective(
            "defeat_lorelei",
            "Defeat Elite Four Lorelei",
            "league:lorelei_defeated",
            Specialist.BATTLE,
            "cross_victory_road",
        ),
        _objective(
            "defeat_bruno",
            "Defeat Elite Four Bruno",
            "league:bruno_defeated",
            Specialist.BATTLE,
            "defeat_lorelei",
        ),
        _objective(
            "defeat_agatha",
            "Defeat Elite Four Agatha",
            "league:agatha_defeated",
            Specialist.BATTLE,
            "defeat_bruno",
        ),
        _objective(
            "defeat_lance",
            "Defeat Elite Four Lance",
            "league:lance_defeated",
            Specialist.BATTLE,
            "defeat_agatha",
        ),
        _objective(
            "defeat_champion",
            "Defeat the Champion",
            "league:champion_defeated",
            Specialist.BATTLE,
            "defeat_lance",
        ),
        _objective(
            "enter_hall_of_fame",
            "Verify Hall of Fame completion",
            HALL_OF_FAME_FACT,
            Specialist.VERIFICATION,
            "defeat_champion",
        ),
    )
    return QuestGraph(objectives)


COMPLETION_QUEST = build_completion_quest_graph()


def completion_route_payload() -> list[dict[str, object]]:
    """Return the canonical public projection of the completion objective graph."""

    return [
        {
            "id": objective.id,
            "title": objective.title,
            "specialist": objective.specialist.value,
            "prerequisites": sorted(objective.prerequisites),
            "completion_facts": sorted(objective.completion_facts),
            "target_region": objective.target_region,
        }
        for objective in COMPLETION_QUEST.topological_order()
    ]
