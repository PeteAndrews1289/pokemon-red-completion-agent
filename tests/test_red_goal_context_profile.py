from __future__ import annotations

import json

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_goal_context_profile import (
    RED_GOAL_CONTEXT_PROFILE_SCHEMA,
    RedGoalContextProfileError,
    RedGoalMechanic,
    bind_affordable_ball_supply_profile,
    build_acquisition_replanning_profile_payload,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
    require_resupply_only_profile_transition,
)


def _payload(*providers: dict[str, object]) -> bytes:
    value = {
        "schema": RED_GOAL_CONTEXT_PROFILE_SCHEMA,
        "profile_id": "fixture-context",
        "manager_config": {
            "required_party_size": 6,
            "required_team_level": 60,
            "desired_capture_items": 10,
            "desired_recovery_items": 8,
            "desired_storage_headroom": 8,
        },
        "providers": list(providers),
    }
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _provider(
    kind: GoalKind,
    mechanic: RedGoalMechanic,
    parameters: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "kind": kind.value,
        "mechanic": mechanic.value,
        "parameters": parameters or {},
    }


def _supply_transition_profile(map_id=MapId.CINNABAR_MART, item=ItemId.GREAT_BALL):
    return parse_red_goal_context_profile(_payload(
        _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
        _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
        _provider(GoalKind.RESUPPLY, RedGoalMechanic.MART_RESUPPLY, {
            "map_id": int(map_id), "player_x": 2, "player_y": 5,
            "interaction_direction": "left", "purchases": [{
                "absolute_index": 0 if item is ItemId.POKE_BALL else 1,
                "item_id": int(item), "quantity": 10,
                "unit_price": 200 if item is ItemId.POKE_BALL else 600,
            }],
        }),
    ))


def test_resupply_transition_keeps_all_other_skills_and_contract():
    before = _supply_transition_profile()
    after = _supply_transition_profile(MapId.CERULEAN_MART, ItemId.POKE_BALL)
    require_resupply_only_profile_transition(before, after)
    assert before.providers[2].parameters["map_id"] == int(MapId.CINNABAR_MART)
    assert after.providers[2].parameters["purchases"][0]["unit_price"] == 200
    assert before.providers[:2] == after.providers[:2]
    require_resupply_only_profile_transition(after, after)
    affordable = bind_affordable_ball_supply_profile(after)
    require_resupply_only_profile_transition(after, affordable)
    assert affordable.providers[:2] == after.providers[:2]
    assert affordable.providers[2].parameters['affordable_ball_purchase'] is True
    assert 'affordable_ball_purchase' not in after.providers[2].parameters
    assert (
        affordable.providers[2].parameters['purchases']
        == after.providers[2].parameters['purchases']
    )


@pytest.mark.parametrize("damage", ["not_boolean", "non_ball", "mixed", "hidden_sale"])
def test_affordable_supply_profile_rejects_ambiguous_or_hidden_funding(damage):
    parameters = {
        "map_id": int(MapId.CERULEAN_MART), "player_x": 2, "player_y": 5,
        "interaction_direction": "left", "affordable_ball_purchase": True,
        "purchases": [{"absolute_index": 0, "item_id": int(ItemId.POKE_BALL),
                       "quantity": 10, "unit_price": 200}],
    }
    if damage == "not_boolean":
        parameters["affordable_ball_purchase"] = 1
    elif damage == "non_ball":
        parameters["purchases"][0]["item_id"] = int(ItemId.POTION)
    elif damage == "mixed":
        parameters["purchases"].append({
            "absolute_index": 1, "item_id": int(ItemId.POTION),
            "quantity": 1, "unit_price": 300,
        })
    else:
        parameters["funding_sale"] = {
            "item_id": int(ItemId.HYPER_POTION), "quantity": 1, "minimum_remaining": 8,
        }
    with pytest.raises(RedGoalContextProfileError, match="affordable supply"):
        parse_red_goal_context_profile(_payload(
            _provider(GoalKind.RESUPPLY, RedGoalMechanic.MART_RESUPPLY, parameters),
        ))


@pytest.mark.parametrize("damage", ["identity", "inventory", "other_skill"])
def test_resupply_transition_rejects_unrelated_changes(damage):
    from dataclasses import replace
    before = _supply_transition_profile()
    after = _supply_transition_profile(MapId.CERULEAN_MART, ItemId.POKE_BALL)
    if damage == "identity":
        after = replace(after, profile_id="changed")
    elif damage == "inventory":
        after = replace(after, providers=(before.providers[0], before.providers[1],
            parse_red_goal_context_profile(_payload(
                _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
                _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
                _provider(GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY),
            )).providers[2]))
    else:
        other = parse_red_goal_context_profile(_payload(
            _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
            _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.CENTER_RESTORE),
            _provider(GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY),
        ))
        after = replace(after, providers=(
            after.providers[0], other.providers[1], after.providers[2],
        ))
    with pytest.raises(RedGoalContextProfileError, match="resupply transition"):
        require_resupply_only_profile_transition(before, after)


def test_profile_parses_only_finite_path_free_mechanics_in_semantic_order() -> None:
    profile = parse_red_goal_context_profile(
        _payload(
            _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
            _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
            _provider(
                GoalKind.RESUPPLY,
                RedGoalMechanic.MART_RESUPPLY,
                {
                    "map_id": int(MapId.VIRIDIAN_MART),
                    "player_x": 2,
                    "player_y": 4,
                    "interaction_direction": "up",
                    "purchases": [
                        {
                            "absolute_index": 0,
                            "item_id": int(ItemId.POKE_BALL),
                            "quantity": 4,
                            "unit_price": 200,
                        },
                        {
                            "absolute_index": 1,
                            "item_id": int(ItemId.POTION),
                            "quantity": 3,
                            "unit_price": 300,
                        },
                    ],
                },
            ),
        )
    )

    assert tuple(item.kind for item in profile.providers) == (
        GoalKind.ADVANCE_STORY,
        GoalKind.RESTORE_TEAM,
        GoalKind.RESUPPLY,
    )
    assert profile.public_dict()["private_path_fields"] == 0
    with pytest.raises(TypeError):
        profile.providers[-1].parameters["map_id"] = 1  # type: ignore[index]


def test_profile_rejects_callbacks_paths_and_kind_mechanic_mismatches() -> None:
    corridor = {
        "source_id": "wild:Route1:grass",
        "label": "/private/checkpoint.state",
        "map_id": int(MapId.ROUTE_1),
        "player_x": 10,
        "player_y": 20,
        "forward_directions": ["up"],
        "starting_endpoint": "south",
        "maximum_legs": 2,
        "maximum_seek_steps": 20,
        "maximum_encounters": 4,
    }
    with pytest.raises(RedGoalContextProfileError, match="corridor label"):
        parse_red_goal_context_profile(
            _payload(
                _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
                _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
                _provider(
                    GoalKind.EXPLORE,
                    RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
                    corridor,
                ),
            )
        )

    with pytest.raises(RedGoalContextProfileError, match="differ"):
        parse_red_goal_context_profile(
            _payload(
                _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
                _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
                _provider(GoalKind.EXPLORE, RedGoalMechanic.MART_RESUPPLY),
            )
        )


def test_profile_requires_a_positive_fixed_dose_for_corridor_development() -> None:
    corridor = {
        "source_id": "wild:PokemonMansion1F:grass",
        "label": "Mansion source-local development",
        "map_id": int(MapId.POKEMON_MANSION_1F),
        "player_x": 5,
        "player_y": 21,
        "forward_directions": ["up"],
        "starting_endpoint": "south",
        "maximum_legs": 8,
        "maximum_seek_steps": 64,
        "maximum_encounters": 16,
        "completed_battles": 4,
    }
    profile = parse_red_goal_context_profile(
        _payload(
            _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
            _provider(
                GoalKind.DEVELOP_TEAM,
                RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
                corridor,
            ),
            _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
        )
    )

    assert profile.providers[1].parameters["completed_battles"] == 4
    with pytest.raises(RedGoalContextProfileError, match="development battle dose"):
        parse_red_goal_context_profile(
            _payload(
                _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
                _provider(
                    GoalKind.DEVELOP_TEAM,
                    RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
                    {**corridor, "completed_battles": 0},
                ),
                _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
            )
        )


def test_profile_accepts_only_real_targeted_level_and_development_contracts() -> None:
    profile = parse_red_goal_context_profile(
        _payload(
            _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
            _provider(
                GoalKind.DEVELOP_TEAM,
                RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT,
                {
                    "trainee_species_ref": red_species_ref(10),
                    "level_increment": 1,
                },
            ),
            _provider(
                GoalKind.EVOLVE_SPECIES,
                RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
                {
                    "source_species_ref": red_species_ref(11),
                    "target_species_ref": red_species_ref(12),
                    "evolution_level": 10,
                },
            ),
        )
    )

    assert profile.providers[1].parameters == {
        "trainee_species_ref": red_species_ref(10),
        "level_increment": 1,
    }
    assert profile.providers[2].parameters == {
        "source_species_ref": red_species_ref(11),
        "target_species_ref": red_species_ref(12),
        "evolution_level": 10,
    }


@pytest.mark.parametrize(
    ("mechanic", "parameters", "message"),
    (
        (
            RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT,
            {
                "trainee_species_ref": red_species_ref(10),
                "level_increment": 2,
            },
            "one level",
        ),
        (
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
            {
                "source_species_ref": red_species_ref(10),
                "target_species_ref": red_species_ref(12),
                "evolution_level": 10,
            },
            "canonical Red level evolution",
        ),
        (
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
            {
                "source_species_ref": red_species_ref(35),
                "target_species_ref": red_species_ref(36),
                "evolution_level": 10,
            },
            "canonical Red level evolution",
        ),
    ),
)
def test_profile_rejects_synthetic_targeted_team_families(
    mechanic: RedGoalMechanic,
    parameters: dict[str, object],
    message: str,
) -> None:
    kind = (
        GoalKind.DEVELOP_TEAM
        if mechanic is RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT
        else GoalKind.EVOLVE_SPECIES
    )
    with pytest.raises(RedGoalContextProfileError, match=message):
        parse_red_goal_context_profile(
            _payload(
                _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
                _provider(kind, mechanic, parameters),
                _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
            )
        )


def test_acquisition_replanning_profile_reuses_the_exact_wild_source() -> None:
    corridor = {
        "source_id": "wild:PokemonMansion1F:grass",
        "label": "Mansion source-local development",
        "map_id": int(MapId.POKEMON_MANSION_1F),
        "player_x": 5,
        "player_y": 21,
        "forward_directions": ["up"],
        "starting_endpoint": "south",
        "maximum_legs": 8,
        "maximum_seek_steps": 64,
        "maximum_encounters": 16,
    }
    original = parse_red_goal_context_profile(
        _payload(
            _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
            _provider(
                GoalKind.ACQUIRE_SPECIES,
                RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                corridor,
            ),
            _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
            _provider(GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY),
            _provider(
                GoalKind.EXPLORE,
                RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
                corridor,
            ),
        )
    )

    extended = parse_red_goal_context_profile(
        build_acquisition_replanning_profile_payload(original)
    )
    providers = {provider.kind: provider for provider in extended.providers}

    assert tuple(providers) == (
        GoalKind.ADVANCE_STORY,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.DEVELOP_TEAM,
        GoalKind.RESTORE_TEAM,
        GoalKind.RECOVER_CONTROL,
        GoalKind.EXPLORE,
    )
    development = dict(providers[GoalKind.DEVELOP_TEAM].parameters)
    assert development.pop("completed_battles") == 4
    assert development == dict(providers[GoalKind.ACQUIRE_SPECIES].parameters)
    assert development == dict(providers[GoalKind.EXPLORE].parameters)
    with pytest.raises(RedGoalContextProfileError, match="four-battle"):
        build_acquisition_replanning_profile_payload(original, completed_battles=3)


def test_acquisition_replanning_profile_rejects_different_sources() -> None:
    corridor = {
        "source_id": "wild:PokemonMansion1F:grass",
        "label": "Mansion source-local development",
        "map_id": int(MapId.POKEMON_MANSION_1F),
        "player_x": 5,
        "player_y": 21,
        "forward_directions": ["up"],
        "starting_endpoint": "south",
        "maximum_legs": 8,
        "maximum_seek_steps": 64,
        "maximum_encounters": 16,
    }
    mismatched = parse_red_goal_context_profile(
        _payload(
            _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
            _provider(
                GoalKind.ACQUIRE_SPECIES,
                RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                corridor,
            ),
            _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
            _provider(
                GoalKind.EXPLORE,
                RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
                {**corridor, "source_id": "wild:Route1:grass"},
            ),
        )
    )

    with pytest.raises(RedGoalContextProfileError, match="different sources"):
        build_acquisition_replanning_profile_payload(mismatched)

    unsupported = parse_red_goal_context_profile(
        _payload(
            _provider(
                GoalKind.ACQUIRE_SPECIES,
                RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                {**corridor, "map_id": int(MapId.ROUTE_1)},
            ),
            _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
            _provider(
                GoalKind.EXPLORE,
                RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
                {**corridor, "map_id": int(MapId.ROUTE_1)},
            ),
        )
    )
    with pytest.raises(RedGoalContextProfileError, match="measured Mansion"):
        build_acquisition_replanning_profile_payload(unsupported)


def test_profile_rejects_duplicate_goal_kinds_and_noncanonical_json() -> None:
    with pytest.raises(RedGoalContextProfileError, match="duplicates"):
        parse_red_goal_context_profile(
            _payload(
                _provider(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
                _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
                _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.CENTER_RESTORE),
            )
        )

    with pytest.raises(RedGoalContextProfileError, match="canonical"):
        parse_red_goal_context_profile(b'{"schema": "wrong"}\n')


def test_profile_builder_fixes_normalization_contract_before_collection() -> None:
    providers = (
        (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
        (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
        (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}),
    )

    parsed = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="built-context",
            providers=providers,
        )
    )

    assert parsed.manager_config.required_party_size == 6
    assert parsed.manager_config.required_team_level == 60

    value = json.loads(_payload(*(_provider(kind, mechanic) for kind, mechanic, _ in providers)))
    value["manager_config"]["required_team_level"] = 59
    with pytest.raises(RedGoalContextProfileError, match="fixed Red contract"):
        parse_red_goal_context_profile(
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"
        )
