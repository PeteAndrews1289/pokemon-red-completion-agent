"""Tests for Fuchsia Mart local resupply profile and real provider affordability."""

from __future__ import annotations

from dataclasses import replace

import pytest
from test_red_goal_skills import _adapter, _MartPort, _raw, _Reader

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
    require_resupply_only_profile_transition,
)
from pokemon_red_completion.red_goal_skills import (
    RedGoalSkillError,
    RedMartPurchase,
    RedMartResupplyGoalProvider,
)


def test_fuchsia_mart_profile_parse_build_and_resupply_transition() -> None:
    base_providers = (
        (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
        (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
        (
            GoalKind.RESUPPLY,
            RedGoalMechanic.MART_RESUPPLY,
            {
                "map_id": int(MapId.VIRIDIAN_MART),
                "player_x": 2,
                "player_y": 5,
                "interaction_direction": "left",
                "purchases": [
                    {
                        "absolute_index": 0,
                        "item_id": int(ItemId.POKE_BALL),
                        "quantity": 10,
                        "unit_price": 200,
                    }
                ],
                "affordable_ball_purchase": True,
            },
        ),
    )
    base_payload = build_red_goal_context_profile_payload(
        profile_id="red-fuchsia-resupply-fixture",
        providers=base_providers,
    )
    base_profile = parse_red_goal_context_profile(base_payload)

    fuchsia_resupply_params = {
        "map_id": 0x98,
        "player_x": 2,
        "player_y": 5,
        "interaction_direction": "left",
        "purchases": [
            {
                "absolute_index": 1,
                "item_id": 3,
                "quantity": 20,
                "unit_price": 600,
            }
        ],
        "affordable_ball_purchase": True,
    }
    fuchsia_providers = (
        (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
        (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
        (GoalKind.RESUPPLY, RedGoalMechanic.MART_RESUPPLY, fuchsia_resupply_params),
    )
    fuchsia_payload = build_red_goal_context_profile_payload(
        profile_id="red-fuchsia-resupply-fixture",
        providers=fuchsia_providers,
    )
    fuchsia_profile = parse_red_goal_context_profile(fuchsia_payload)

    resupply_spec = fuchsia_profile.providers[2]
    assert resupply_spec.kind is GoalKind.RESUPPLY
    assert resupply_spec.mechanic is RedGoalMechanic.MART_RESUPPLY
    assert resupply_spec.parameters["map_id"] == 0x98
    assert resupply_spec.parameters["map_id"] == int(MapId.FUCHSIA_MART)
    assert resupply_spec.parameters["player_x"] == 2
    assert resupply_spec.parameters["player_y"] == 5
    assert resupply_spec.parameters["interaction_direction"] == "left"
    assert resupply_spec.parameters["affordable_ball_purchase"] is True
    assert list(resupply_spec.parameters["purchases"]) == [
        {
            "absolute_index": 1,
            "item_id": 3,
            "quantity": 20,
            "unit_price": 600,
        }
    ]

    require_resupply_only_profile_transition(base_profile, fuchsia_profile)
    require_resupply_only_profile_transition(fuchsia_profile, fuchsia_profile)


def test_resupply_transition_rejects_altered_non_supply_goals() -> None:
    base_providers = (
        (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
        (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
        (
            GoalKind.RESUPPLY,
            RedGoalMechanic.MART_RESUPPLY,
            {
                "map_id": int(MapId.VIRIDIAN_MART),
                "player_x": 2,
                "player_y": 5,
                "interaction_direction": "left",
                "purchases": [
                    {
                        "absolute_index": 0,
                        "item_id": int(ItemId.POKE_BALL),
                        "quantity": 10,
                        "unit_price": 200,
                    }
                ],
                "affordable_ball_purchase": True,
            },
        ),
    )
    base_profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="red-fuchsia-resupply-fixture",
            providers=base_providers,
        )
    )

    fuchsia_resupply_params = {
        "map_id": 0x98,
        "player_x": 2,
        "player_y": 5,
        "interaction_direction": "left",
        "purchases": [
            {
                "absolute_index": 1,
                "item_id": 3,
                "quantity": 20,
                "unit_price": 600,
            }
        ],
        "affordable_ball_purchase": True,
    }

    altered_restore_providers = (
        (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
        (GoalKind.RESTORE_TEAM, RedGoalMechanic.CENTER_RESTORE, {}),
        (GoalKind.RESUPPLY, RedGoalMechanic.MART_RESUPPLY, fuchsia_resupply_params),
    )
    altered_restore_profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="red-fuchsia-resupply-fixture",
            providers=altered_restore_providers,
        )
    )
    with pytest.raises(
        RedGoalContextProfileError, match="resupply transition changes a non-supply skill"
    ):
        require_resupply_only_profile_transition(base_profile, altered_restore_profile)

    changed_inventory = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="red-fuchsia-resupply-fixture",
            providers=(
                (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
                (GoalKind.RESUPPLY, RedGoalMechanic.MART_RESUPPLY, fuchsia_resupply_params),
                (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}),
            ),
        )
    )
    with pytest.raises(RedGoalContextProfileError, match="provider inventory"):
        require_resupply_only_profile_transition(base_profile, changed_inventory)


def test_red_mart_resupply_goal_provider_fuchsia_affordability_and_cash_reduction() -> None:
    reader = _Reader(
        raw=replace(
            _raw(hyper_potions=8, poke_balls=0),
            map_id=MapId.FUCHSIA_MART,
            player_x=2,
            player_y=5,
            player_money=27_503,
        ),
        ready=True,
    )
    port = _MartPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)

    provider = RedMartResupplyGoalProvider(
        map_id=MapId.FUCHSIA_MART,
        player_x=2,
        player_y=5,
        interaction_direction="left",
        purchases=(RedMartPurchase(1, ItemId.GREAT_BALL, 20, 600),),
        actions=actions,
        reader=reader,
        emulator=port,
        adapter=adapter,
        affordable_ball_purchase=True,
    )

    obs = adapter.observe()
    assert obs.raw.player_money == 27_503
    assert int(ItemId.GREAT_BALL) not in dict(obs.raw.bag_items or ())
    assert obs.capture_item_count == 0

    affordable = provider.affordable_provider(obs)
    assert affordable is not None
    assert affordable.affordable_ball_purchase is False
    assert len(affordable.purchases) == 1
    assert affordable.purchases[0].item is ItemId.GREAT_BALL
    assert affordable.purchases[0].quantity == 20
    assert affordable.purchases[0].unit_price == 600

    quote = provider.resource_quote(obs)
    assert quote.available_funds == 27_503
    assert quote.purchase_cost == 12_000
    assert provider.resource_availability(obs).executable is True

    offer = provider.offer(obs)
    assert offer.binding is not None
    assert offer.binding is not None

    reader_reduced = _Reader(
        raw=replace(
            _raw(hyper_potions=8, poke_balls=0),
            map_id=MapId.FUCHSIA_MART,
            player_x=2,
            player_y=5,
            player_money=5_400,
        ),
        ready=True,
    )
    obs_reduced = _adapter(reader_reduced).observe()
    assert int(ItemId.GREAT_BALL) not in dict(obs_reduced.raw.bag_items or ())
    assert obs_reduced.capture_item_count == 0

    affordable_reduced = provider.affordable_provider(obs_reduced)
    assert affordable_reduced is not None
    assert affordable_reduced.purchases[0].quantity == 9
    assert affordable_reduced.purchases[0].unit_price == 600

    quote_reduced = provider.resource_quote(obs_reduced)
    assert quote_reduced.available_funds == 5_400
    assert quote_reduced.purchase_cost == 5_400

    reader_single = _Reader(
        raw=replace(
            _raw(hyper_potions=8, poke_balls=0),
            map_id=MapId.FUCHSIA_MART,
            player_x=2,
            player_y=5,
            player_money=1_000,
        ),
        ready=True,
    )
    obs_single = _adapter(reader_single).observe()
    assert int(ItemId.GREAT_BALL) not in dict(obs_single.raw.bag_items or ())
    affordable_single = provider.affordable_provider(obs_single)
    assert affordable_single is not None
    assert affordable_single.purchases[0].quantity == 1
    assert provider.resource_quote(obs_single).purchase_cost == 600

    reader_broke = _Reader(
        raw=replace(
            _raw(hyper_potions=8, poke_balls=0),
            map_id=MapId.FUCHSIA_MART,
            player_x=2,
            player_y=5,
            player_money=599,
        ),
        ready=True,
    )
    obs_broke = _adapter(reader_broke).observe()
    assert int(ItemId.GREAT_BALL) not in dict(obs_broke.raw.bag_items or ())
    assert provider.affordable_provider(obs_broke) is None
    broke_avail = provider.resource_availability(obs_broke)
    assert broke_avail.executable is False
    assert broke_avail.unavailable_reason is GoalUnavailableReason.MISSING_RESOURCE
    with pytest.raises(RedGoalSkillError, match="no affordable Mart purchase can be quoted"):
        provider.resource_quote(obs_broke)


def test_invalid_unknown_map_rejections() -> None:
    invalid_map_params = {
        "map_id": 0xFE,
        "player_x": 2,
        "player_y": 5,
        "interaction_direction": "left",
        "purchases": [
            {
                "absolute_index": 1,
                "item_id": 3,
                "quantity": 20,
                "unit_price": 600,
            }
        ],
        "affordable_ball_purchase": True,
    }
    with pytest.raises(RedGoalContextProfileError, match="map identity is unknown"):
        parse_red_goal_context_profile(
            build_red_goal_context_profile_payload(
                profile_id="red-invalid-map-profile",
                providers=(
                    (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
                    (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
                    (GoalKind.RESUPPLY, RedGoalMechanic.MART_RESUPPLY, invalid_map_params),
                ),
            )
        )

    reader = _Reader(
        raw=replace(
            _raw(),
            map_id=MapId.FUCHSIA_MART,
            player_x=2,
            player_y=5,
            player_money=27_503,
        ),
        ready=True,
    )
    port = _MartPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)

    with pytest.raises(TypeError, match="Mart boundary map must be a MapId"):
        RedMartResupplyGoalProvider(
            map_id=0x98,  # type: ignore[arg-type]
            player_x=2,
            player_y=5,
            interaction_direction="left",
            purchases=(RedMartPurchase(1, ItemId.GREAT_BALL, 20, 600),),
            actions=actions,
            reader=reader,
            emulator=port,
            adapter=adapter,
            affordable_ball_purchase=True,
        )

    valid_provider = RedMartResupplyGoalProvider(
        map_id=MapId.FUCHSIA_MART,
        player_x=2,
        player_y=5,
        interaction_direction="left",
        purchases=(RedMartPurchase(1, ItemId.GREAT_BALL, 20, 600),),
        actions=actions,
        reader=reader,
        emulator=port,
        adapter=adapter,
        affordable_ball_purchase=True,
    )
    reader_wrong_map = _Reader(
        raw=replace(
            _raw(),
            map_id=MapId.FUCHSIA_POKECENTER,
            player_x=2,
            player_y=5,
            player_money=27_503,
        ),
        ready=True,
    )
    obs_wrong_map = _adapter(reader_wrong_map).observe()
    offer_wrong_map = valid_provider.offer(obs_wrong_map)
    assert offer_wrong_map.binding is None
    assert offer_wrong_map.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
