"""ROM-free live-port budget and already-satisfied arrival integration."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_executor import RecordingController
from test_red_travel_capture import Harness

import pokemon_red_completion.red_travel_capture_runtime as travel
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameSafeExecutor,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    RedGoalMechanic,
    bind_travel_capture_profile,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_skills import RedAreaSurveyGoalProvider
from pokemon_red_completion.red_travel_capture import RedTravelCaptureError


@pytest.mark.parametrize(
    "child_actions,child_frames,outer_actions,outer_frames,expected",
    [
        (2, 20, 20, 20, 2),
        (20, 3, 20, 20, 3),
        (20, 20, 1, 20, 1),
        (20, 20, 20, 2, 2),
    ],
)
def test_capture_port_keeps_original_recording_and_hard_limits(
    monkeypatch,
    child_actions,
    child_frames,
    outer_actions,
    outer_frames,
    expected,
):
    raw = RecordingController()
    frames = WindowedFrameBudgetController(
        raw,
        maximum_frames_per_window=outer_frames,
        maximum_total_frames=outer_frames,
    )
    dispatched = []
    compiler = FrameSafeExecutor(frames)

    def record(action):
        dispatched.append(action)
        return compiler.execute(action)

    actions = CountingExecutor(
        HardCompositionActionLimiter(
            SimpleNamespace(execute=record),
            maximum_actions_per_decision=outer_actions,
            maximum_episode_actions=outer_actions,
        )
    )

    class Capture:
        def __init__(self, emulator, executor, reader, timing, **kwargs):
            assert emulator is frames and kwargs["capture_status_support"] is True
            self.executor = executor

        def capture_encounter(self, species):
            for _ in range(30):
                self.executor.execute(MacroAction(MacroActionKind.WAIT))
            pytest.fail("capture bypassed hard budget")

    monkeypatch.setattr(travel, "LiveWildEncounterExecutor", Capture)
    runtime = SimpleNamespace(emulator=frames, reader=object())
    port = travel.BoundedTravelCapturePort(
        runtime,
        actions,
        True,
        maximum_actions=child_actions,
        maximum_frames=child_frames,
    )
    with pytest.raises(RuntimeError):
        port.capture_encounter("pokemon:109")
    assert raw.frame_count == expected
    assert actions.actions_executed == expected
    assert len(dispatched) >= expected  # An interrupted attempted dispatch is never hidden.
    previous = len(dispatched)
    with pytest.raises(RedTravelCaptureError, match="consumed"):
        port.capture_encounter("pokemon:109")
    assert len(dispatched) == previous


def profile(parameters=None):
    values = {
        "source_id": "wild:PokemonMansion1F:grass",
        "label": "test wild source",
        "map_id": 165,
        "player_x": 20,
        "player_y": 16,
        "forward_directions": ["up"],
        "starting_endpoint": "south",
        "maximum_legs": 2,
        "maximum_seek_steps": 10,
        "maximum_encounters": 2,
    }
    values.update(parameters or {})
    return parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="travel-capture-test",
            providers=(
                (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
                (
                    GoalKind.ACQUIRE_SPECIES,
                    RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                    values,
                ),
                (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
            ),
        )
    )


def test_travel_capture_is_explicit_and_preserves_historical_profile():
    original = profile()
    updated = bind_travel_capture_profile(original)
    assert "travel_capture" not in original.providers[1].parameters
    assert updated.providers[1].parameters["travel_capture"] is True
    assert updated.profile_sha256 != original.profile_sha256
    fallback = object()
    assert travel.bind_travel_capture_handler(None, original.providers[1], fallback) is fallback
    with pytest.raises(RedTravelCaptureError, match="registration"):
        travel.bind_travel_capture_handler(
            SimpleNamespace(runtime=SimpleNamespace(registration_policy=None)),
            updated.providers[1],
            fallback,
        )


def test_travel_capture_opt_in_survives_source_retarget_without_leaking_to_other_goals():
    from test_red_living_dex_wild_corridor import _graph, _local_discovery_profile, _terrain

    from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        derive_red_living_dex_wild_corridor,
        retarget_red_wild_profile,
    )

    original = _local_discovery_profile()
    updated = bind_travel_capture_profile(original)
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"),
        _terrain(),
        _graph(),
    )
    moved = retarget_red_wild_profile(updated, corridor)
    assert all("travel_capture" not in spec.parameters for spec in original.providers)
    assert (
        next(s for s in moved.providers if s.kind is GoalKind.ACQUIRE_SPECIES).parameters[
            "travel_capture"
        ]
        is True
    )
    assert all(
        "travel_capture" not in spec.parameters
        for spec in moved.providers
        if spec.kind is not GoalKind.ACQUIRE_SPECIES
    )


@pytest.mark.parametrize("value", ["true", 1, None, []])
def test_travel_capture_profile_rejects_non_boolean(value):
    with pytest.raises(RedGoalContextProfileError, match="travel capture"):
        profile({"travel_capture": value})


def arrival_fixture():
    h = Harness()
    source = "wild:PokemonMansion1F:grass"
    catalog = replace(
        RED_ACQUISITION_CATALOG,
        remaining_demand=True,
        registered_species=h.collection.owned_species,
        wild_source_species=((source, (h.target,)),),
    )

    def observe():
        return SimpleNamespace(
            raw=h.raw,
            collection_observation=h.collection,
            party=SimpleNamespace(fainted_count=0),
            input_ready=True,
        )

    runtime = SimpleNamespace(
        adapter=SimpleNamespace(observe=observe), emulator=SimpleNamespace(frame_count=0)
    )
    actions = SimpleNamespace(actions_executed=0)
    survey = RedAreaSurveyGoalProvider(
        source, h, actions, runtime.emulator, runtime.adapter, catalog=catalog
    )
    fallback = SimpleNamespace(kind=GoalKind.ACQUIRE_SPECIES, offer=lambda _: "fallback")
    provider = travel.TravelSatisfiedCaptureProvider(
        fallback,
        survey,
        runtime,
        frozenset({h.target}),
        [h.handler],
        actions,
    )
    return h, runtime, provider


def test_verified_travel_catch_can_satisfy_arrival_without_second_capture_or_label():
    h, runtime, provider = arrival_fixture()
    h.handler.handle(h.start)
    offered = provider.offer(runtime.adapter.observe())
    assert offered.binding is not None
    report = offered.binding.execute()
    assert report.actions_executed == report.frames_executed == 0
    assert report.evidence["new_learning_labels"] == 0
    assert report.evidence["capture_survey"]["captures"] == 0
    assert offered.binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert h.calls == 1
    with pytest.raises(RedTravelCaptureError, match="consumed"):
        offered.binding.execute()


@pytest.mark.parametrize("reason", ["no_receipt", "wrong_species", "lost_credit", "still_missing"])
def test_satisfied_arrival_needs_actual_source_gain_and_verified_receipt(reason):
    h, runtime, provider = arrival_fixture()
    h.handler.handle(h.start)
    if reason == "no_receipt":
        h.handler.receipts.clear()
    elif reason == "wrong_species":
        provider.initial_missing = frozenset({"pokemon:001"})
    elif reason == "lost_credit":
        h.collection = replace(h.collection, owned_species=h.collection.owned_species - {h.target})
    else:
        h.collection = replace(
            h.collection, specimens=h.collection.specimens[:-1], box_counts=(0, 0)
        )
    if reason in {"lost_credit", "still_missing"}:
        with pytest.raises(RedTravelCaptureError, match="lost"):
            provider.offer(runtime.adapter.observe())
    else:
        assert provider.offer(runtime.adapter.observe()) == "fallback"


def test_satisfied_arrival_rejects_changed_observation_before_execute():
    h, runtime, provider = arrival_fixture()
    h.handler.handle(h.start)
    binding = provider.offer(runtime.adapter.observe()).binding
    h.raw = replace(h.raw, player_x=19)
    with pytest.raises(RedTravelCaptureError, match="changed"):
        binding.execute()
