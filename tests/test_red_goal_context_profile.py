from __future__ import annotations

import json

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_goal_context_profile import (
    RED_GOAL_CONTEXT_PROFILE_SCHEMA,
    RedGoalContextProfileError,
    RedGoalMechanic,
    build_acquisition_replanning_profile_payload,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
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
