from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_crystal_completion import vertical_slice
from pokemon_crystal_completion.observation import (
    CRYSTAL_BOX_OBSERVATION_BYTES,
    CrystalInventoryObservation,
    CrystalObservationBundle,
    CrystalPokedexProgress,
    CrystalStorageObservation,
    decode_crystal_box,
    derive_crystal_ownership_progress,
)
from pokemon_crystal_completion.source_contract import CRYSTAL_OBSERVATION_SYMBOLS
from pokemon_crystal_completion.vertical_slice import (
    CRYSTAL_FIRST_FLOOR_ARRIVAL_AT,
    CRYSTAL_PLAYERS_HOUSE_1F,
    CRYSTAL_PLAYERS_HOUSE_2F,
    CRYSTAL_STARTING_BEDROOM_AT,
    CrystalStartingVerticalSliceQualification,
    CrystalTraversalPort,
    CrystalVerticalSliceError,
    build_crystal_starting_goal_bindings,
    crystal_map_id,
    execute_crystal_starting_round_trip,
    observe_crystal_starting_goal_state,
    plan_crystal_bedroom_descent,
    plan_crystal_bedroom_return,
    split_crystal_map_id,
)
from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind, GoalManagerQuestion
from pokemon_red_completion.goal_manager_state import CompletionProgress
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.route_executor import RouteExecutionError, execute_route


class _RouteController:
    def __init__(self) -> None:
        self.frame_count = 0
        self.group = 24
        self.number = 7
        self.x, self.y = CRYSTAL_STARTING_BEDROOM_AT
        self.facing = "down"
        self._pressed: set[str] = set()
        self.transitions = {
            (24, 7, 3, 3, "right"): (24, 7, 4, 3),
            (24, 7, 4, 3, "right"): (24, 7, 5, 3),
            (24, 7, 5, 3, "right"): (24, 7, 6, 3),
            (24, 7, 6, 3, "right"): (24, 7, 7, 3),
            (24, 7, 7, 3, "up"): (24, 7, 7, 2),
            (24, 7, 7, 2, "up"): (24, 7, 7, 1),
            (24, 7, 7, 1, "up"): (24, 6, 9, 1),
            (24, 6, 9, 1, "up"): (24, 7, 7, 1),
            (24, 7, 7, 1, "down"): (24, 7, 7, 2),
            (24, 7, 7, 2, "down"): (24, 7, 7, 3),
            (24, 7, 7, 3, "left"): (24, 7, 6, 3),
            (24, 7, 6, 3, "left"): (24, 7, 5, 3),
            (24, 7, 5, 3, "left"): (24, 7, 4, 3),
            (24, 7, 4, 3, "left"): (24, 7, 3, 3),
        }

    @property
    def pressed_buttons(self) -> frozenset[str]:
        return frozenset(self._pressed)

    def press(self, button: str) -> None:
        self._pressed.add(button)

    def release(self, button: str) -> None:
        self._pressed.remove(button)
        if button not in {"up", "right", "down", "left"}:
            return
        if button != self.facing:
            self.facing = button
            return
        before = (self.group, self.number)
        target = self.transitions.get((self.group, self.number, self.x, self.y, button))
        if target is None:
            return
        self.group, self.number, self.x, self.y = target
        if (self.group, self.number) != before:
            self.facing = "down"

    def tick(self, frames: int) -> None:
        self.frame_count += frames

    def read_wram(self, bank: int, address: int, length: int) -> bytes:
        assert length == 1
        name = next(
            name
            for name, symbol in CRYSTAL_OBSERVATION_SYMBOLS.items()
            if (symbol.bank, symbol.address) == (bank, address)
        )
        values = {
            "wJohtoBadges": 0,
            "wKantoBadges": 0,
            "wBattleMode": 0,
            "wMapStatus": 2,
            "wMapEventStatus": 0,
            "wScriptMode": 0,
            "wScriptRunning": 0,
            "wJoypadDisable": 0,
            "wPlayerState": 0,
            "wMapGroup": self.group,
            "wMapNumber": self.number,
            "wXCoord": self.x,
            "wYCoord": self.y,
        }
        return bytes((values[name],))

    def read_cartridge_ram(self, bank: int, address: int, length: int) -> bytes:
        raise AssertionError((bank, address, length))


def _empty_bundle() -> CrystalObservationBundle:
    party = PartyObservation()
    payload = bytearray(CRYSTAL_BOX_OBSERVATION_BYTES)
    payload[1] = 0xFF
    storage = CrystalStorageObservation(
        current_box_number=1,
        boxes=tuple(
            decode_crystal_box(bytes(payload), box_number=number) for number in range(1, 15)
        ),
    )
    return CrystalObservationBundle(
        party=party,
        pokedex=CrystalPokedexProgress(
            registered=CompletionProgress(0, 250),
            seen=CompletionProgress(0, 250),
        ),
        storage=storage,
        inventory=CrystalInventoryObservation(items=(), balls=()),
        ownership=derive_crystal_ownership_progress(party, storage),
    )


def test_crystal_map_identity_round_trips_without_entering_policy_input() -> None:
    assert crystal_map_id(24, 7) == CRYSTAL_PLAYERS_HOUSE_2F
    assert split_crystal_map_id(CRYSTAL_PLAYERS_HOUSE_1F) == (24, 6)
    for invalid in ((0, 1), (1, 0), (True, 1), (1, 256)):
        with pytest.raises(CrystalVerticalSliceError, match="map"):
            crystal_map_id(*invalid)  # type: ignore[arg-type]


def test_source_derived_two_room_plans_are_semantic_not_button_retries() -> None:
    outbound = plan_crystal_bedroom_descent()
    returning = plan_crystal_bedroom_return()

    assert outbound.actions == ("right",) * 4 + ("up",) * 3
    assert outbound.terminal_map == CRYSTAL_PLAYERS_HOUSE_1F
    assert outbound.terminal_at == CRYSTAL_FIRST_FLOOR_ARRIVAL_AT
    assert returning.actions == ("up",) + ("down",) * 2 + ("left",) * 4
    assert returning.terminal_map == CRYSTAL_PLAYERS_HOUSE_2F
    assert returning.terminal_at == CRYSTAL_STARTING_BEDROOM_AT


def test_shared_executor_retries_turns_and_qualifies_the_round_trip() -> None:
    controller = _RouteController()

    report = execute_crystal_starting_round_trip(controller)

    assert report.semantic_steps == 14
    assert report.movement_requests == 18
    assert controller.pressed_buttons == frozenset()
    assert (controller.group, controller.number, controller.x, controller.y) == (24, 7, 3, 3)
    document = report.public_dict()
    assert document["returned_to_start"] is True
    assert document["private_location_identity_fields"] == 0
    assert "24" not in json.dumps(document, sort_keys=True)


def test_shared_executor_fails_closed_on_an_unplanned_coordinate() -> None:
    controller = _RouteController()
    controller.transitions[(24, 7, 3, 3, "right")] = (24, 7, 4, 4)
    port = CrystalTraversalPort(controller)

    with pytest.raises(RouteExecutionError, match="drifted") as caught:
        execute_route(
            plan_crystal_bedroom_descent(),
            port,
            port,
            limits=vertical_slice.CRYSTAL_ROUTE_LIMITS,
        )

    assert caught.value.failure is not None
    assert caught.value.failure.movement_requests == 2
    assert controller.pressed_buttons == frozenset()


def test_fresh_boundary_exposes_two_real_goals_without_model_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _RouteController()
    monkeypatch.setattr(
        vertical_slice,
        "read_crystal_observation_bundle",
        lambda _controller: _empty_bundle(),
    )

    observation = observe_crystal_starting_goal_state(controller)
    binding_set = build_crystal_starting_goal_bindings(observation, controller)
    question = GoalManagerQuestion(observation.situation, binding_set.opportunities)

    assert observation.snapshot.world_knowledge == CompletionProgress(1, 388)
    assert tuple(
        opportunity.kind
        for opportunity in question.opportunities
        if opportunity.availability is GoalAvailability.AVAILABLE
    ) == (GoalKind.ADVANCE_STORY, GoalKind.EXPLORE)
    policy = json.dumps(
        {
            "state": observation.policy_dict(),
            "candidates": [item.policy_dict() for item in question.opportunities],
        },
        sort_keys=True,
    )
    for forbidden in ("pokemon.crystal", "starting-story", "24", "7, 0", "binding_ref"):
        assert forbidden not in policy

    explore = next(binding for binding in binding_set.bindings if binding.kind is GoalKind.EXPLORE)
    exploration_report = explore.execute()
    assert explore.verify(exploration_report).status.value == "succeeded"
    assert (controller.group, controller.number, controller.x, controller.y) == (24, 7, 3, 3)

    story = next(
        binding for binding in binding_set.bindings if binding.kind is GoalKind.ADVANCE_STORY
    )
    story_report = story.execute()
    assert story.verify(story_report).status.value == "succeeded"
    assert (controller.group, controller.number, controller.x, controller.y) == (24, 6, 9, 1)


def test_vertical_slice_receipt_is_path_free_and_preserves_zero_counters() -> None:
    receipt = CrystalStartingVerticalSliceQualification(
        source_commit="1" * 40,
        plan_sha256="2" * 64,
        rom_sha1="3" * 40,
        rom_sha256="4" * 64,
        setup_transcript_sha256="5" * 64,
        policy_question_sha256="6" * 64,
        setup_actions=46,
        menu_close_actions=2,
        exploration_actions=18,
        exploration_frames=3_684,
        exploration_semantic_steps=14,
        story_actions=9,
        story_frames=1_842,
        story_semantic_steps=7,
        available_goal_kinds=(GoalKind.ADVANCE_STORY, GoalKind.EXPLORE),
        exploration_verified=True,
        story_verified=True,
        controller_released=True,
        rom_unchanged=True,
    )

    document = receipt.public_dict()

    assert document["total_controller_actions"] == 75
    assert document["experiment"] == {
        "context_opened": False,
        "teacher_executed": False,
        "prediction_computed": False,
        "zero_shot_opened": 0,
        "adaptation_opened": 0,
        "sealed_test_opened": 0,
    }
    assert "/Users/" not in json.dumps(document, sort_keys=True)
    assert document["private_location_identity_fields"] == 0
    with pytest.raises(CrystalVerticalSliceError, match="menu-close"):
        replace(receipt, menu_close_actions=1)
    with pytest.raises(CrystalVerticalSliceError, match="controller_released"):
        replace(receipt, controller_released=1)  # type: ignore[arg-type]
    with pytest.raises(CrystalVerticalSliceError, match="did not qualify"):
        replace(receipt, story_verified=False)
