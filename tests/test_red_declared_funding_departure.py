"""Independent ROM-free tests for declared Mart funding departure.

Verifies declared_mart_funding_exit pure helper behavior under matching
opt-in parameters, missing/disabled flags, invalid maps, unready state,
and terrain/interruption mismatches.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_declared_funding_departure import (
    declared_mart_funding_exit,
)
from pokemon_red_completion.red_goal_context_profile import (
    RED_GOAL_MANAGER_CONFIG,
    RedGoalContextProfile,
    RedGoalMechanic,
    RedGoalProviderSpec,
    _document_sha256,
    _thaw,
)
from pokemon_red_completion.route_executor import TraversalSnapshot


def _spec(
    kind: GoalKind,
    mechanic: RedGoalMechanic,
    parameters: Mapping[str, object] | None = None,
) -> RedGoalProviderSpec:
    params = MappingProxyType(dict(parameters or {}))
    digest = _document_sha256(
        {
            "kind": kind.value,
            "mechanic": mechanic.value,
            "parameters": _thaw(params),
        }
    )
    return RedGoalProviderSpec(
        kind=kind,
        mechanic=mechanic,
        parameters=params,
        configuration_sha256=digest,
    )


def _profile(
    mart_parameters: Mapping[str, object] | None = None,
) -> RedGoalContextProfile:
    providers = (
        _spec(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
        _spec(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
        _spec(GoalKind.RESUPPLY, RedGoalMechanic.MART_RESUPPLY, mart_parameters),
    )
    return RedGoalContextProfile(
        profile_id="test-fuchsia-mart-funding-profile",
        profile_sha256="0" * 64,
        manager_config=RED_GOAL_MANAGER_CONFIG,
        providers=providers,
    )


def _profile_without_resupply() -> RedGoalContextProfile:
    providers = (
        _spec(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY),
        _spec(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE),
        _spec(GoalKind.MANAGE_STORAGE, RedGoalMechanic.BOX_SWITCH),
    )
    return RedGoalContextProfile(
        profile_id="test-no-resupply-profile",
        profile_sha256="0" * 64,
        manager_config=RED_GOAL_MANAGER_CONFIG,
        providers=providers,
    )


def _start(
    *,
    map_id: object = int(MapId.FUCHSIA_MART),
    at: tuple[int, int] = (3, 3),
    ready: bool = True,
    mode: str | None = "land",
    interruption: str | None = None,
    last_outside_map: object = int(MapId.FUCHSIA_CITY),
) -> TraversalSnapshot:
    return TraversalSnapshot(
        map_id=map_id,  # type: ignore[arg-type]
        at=at,
        ready=ready,
        mode=mode,
        interruption=interruption,
        last_outside_map=last_outside_map,  # type: ignore[arg-type]
    )


def _matching_mart_params(
    *,
    map_id: object = int(MapId.FUCHSIA_MART),
    mart_funding_departure: object = True,
    indoor_funding_departure: object = True,
    affordable_ball_purchase: object = True,
) -> dict[str, object]:
    params: dict[str, object] = {
        "map_id": map_id,
        "player_x": 2,
        "player_y": 5,
        "interaction_direction": "left",
        "purchases": [
            {
                "absolute_index": 1,
                "item_id": int(ItemId.GREAT_BALL),
                "quantity": 10,
                "unit_price": 600,
            }
        ],
    }
    if mart_funding_departure is not None:
        params["mart_funding_departure"] = mart_funding_departure
    if indoor_funding_departure is not None:
        params["indoor_funding_departure"] = indoor_funding_departure
    if affordable_ball_purchase is not None:
        params["affordable_ball_purchase"] = affordable_ball_purchase
    return params


def test_matching_indoor_profile_and_observed_outside_succeeds() -> None:
    profile = _profile(_matching_mart_params())
    start = _start()

    exit_map = declared_mart_funding_exit(profile, start)

    assert exit_map == int(MapId.FUCHSIA_CITY)
    assert type(exit_map) is int
    assert type(exit_map) is not bool


def test_missing_mart_funding_departure_flag_returns_none() -> None:
    params = _matching_mart_params(mart_funding_departure=None)
    profile = _profile(params)
    start = _start()

    assert declared_mart_funding_exit(profile, start) is None


def test_false_mart_funding_departure_flag_returns_none() -> None:
    params = _matching_mart_params(mart_funding_departure=False)
    profile = _profile(params)
    start = _start()

    assert declared_mart_funding_exit(profile, start) is None


@pytest.mark.parametrize("invalid_flag", [1, 0, "true", "True", [True], (True,), {"val": True}])
def test_nonboolean_mart_funding_departure_flag_returns_none(invalid_flag: object) -> None:
    params = _matching_mart_params(mart_funding_departure=invalid_flag)
    profile = _profile(params)
    start = _start()

    assert declared_mart_funding_exit(profile, start) is None


@pytest.mark.parametrize(
    "indoor_funding,affordable_purchase",
    [
        (False, True),
        (True, False),
        (False, False),
        (None, True),
        (True, None),
        (1, True),
        (True, 1),
        ("true", True),
    ],
)
def test_disabled_or_missing_existing_options_return_none(
    indoor_funding: object, affordable_purchase: object,
) -> None:
    params = _matching_mart_params(
        indoor_funding_departure=indoor_funding,
        affordable_ball_purchase=affordable_purchase,
    )
    profile = _profile(params)
    start = _start()

    assert declared_mart_funding_exit(profile, start) is None


def test_different_shop_mismatch_returns_none() -> None:
    # Profile declared for Cerulean Mart, but player is in Fuchsia Mart
    params = _matching_mart_params(map_id=int(MapId.CERULEAN_MART))
    profile = _profile(params)
    start = _start(map_id=int(MapId.FUCHSIA_MART))

    assert declared_mart_funding_exit(profile, start) is None


def test_current_map_mismatch_returns_none() -> None:
    # Profile declared for Fuchsia Mart, but player is in Celadon Mart 1F
    params = _matching_mart_params(map_id=int(MapId.FUCHSIA_MART))
    profile = _profile(params)
    start = _start(map_id=int(MapId.CELADON_MART_1F))

    assert declared_mart_funding_exit(profile, start) is None


def test_outdoor_current_map_returns_none() -> None:
    # Fuchsia City is 0x07 (< 0x25, outdoor)
    params = _matching_mart_params(map_id=int(MapId.FUCHSIA_CITY))
    profile = _profile(params)
    start = _start(map_id=int(MapId.FUCHSIA_CITY))

    assert declared_mart_funding_exit(profile, start) is None

    # Route 25 is 0x24 (< 0x25, highest outdoor map)
    params_r25 = _matching_mart_params(map_id=int(MapId.ROUTE_25))
    profile_r25 = _profile(params_r25)
    start_r25 = _start(map_id=int(MapId.ROUTE_25))

    assert declared_mart_funding_exit(profile_r25, start_r25) is None


@pytest.mark.parametrize(
    "invalid_outside",
    [
        None,
        -1,
        0x25,  # Reds House 1F (indoor)
        0x98,  # Fuchsia Mart (indoor)
        100,
        "7",
        (7,),
    ],
)
def test_missing_or_invalid_outside_returns_none(invalid_outside: object) -> None:
    profile = _profile(_matching_mart_params())
    start = _start(last_outside_map=invalid_outside)

    assert declared_mart_funding_exit(profile, start) is None


@pytest.mark.parametrize("bool_val", [True, False])
def test_boolean_outside_does_not_masquerade_as_integer_map(bool_val: bool) -> None:
    profile = _profile(_matching_mart_params())
    start = _start(last_outside_map=bool_val)

    assert declared_mart_funding_exit(profile, start) is None


@pytest.mark.parametrize("bool_val", [True, False])
def test_boolean_map_id_does_not_masquerade_as_integer_map(bool_val: bool) -> None:
    profile = _profile(_matching_mart_params(map_id=bool_val))
    start = _start(map_id=bool_val)

    assert declared_mart_funding_exit(profile, start) is None


def test_water_mode_returns_none() -> None:
    profile = _profile(_matching_mart_params())
    start = _start(mode="water")

    assert declared_mart_funding_exit(profile, start) is None

    start_none = _start(mode=None)
    assert declared_mart_funding_exit(profile, start_none) is None


def test_unready_state_returns_none() -> None:
    profile = _profile(_matching_mart_params())
    start = _start(ready=False)

    assert declared_mart_funding_exit(profile, start) is None


@pytest.mark.parametrize("interruption", ["wild_battle", "trainer_battle", "text_box"])
def test_interruption_not_none_returns_none(interruption: str) -> None:
    profile = _profile(_matching_mart_params())
    start = _start(interruption=interruption)

    assert declared_mart_funding_exit(profile, start) is None


def test_profile_without_resupply_returns_none() -> None:
    profile = _profile_without_resupply()
    start = _start()

    assert declared_mart_funding_exit(profile, start) is None


@pytest.mark.parametrize(
    "bad_profile,bad_start",
    [
        (None, _start()),
        (_profile(_matching_mart_params()), None),
        ("not_a_profile", _start()),
        (_profile(_matching_mart_params()), "not_a_start"),
    ],
)
def test_malformed_or_none_inputs_return_none(
    bad_profile: object, bad_start: object,
) -> None:
    assert declared_mart_funding_exit(bad_profile, bad_start) is None  # type: ignore[arg-type]
