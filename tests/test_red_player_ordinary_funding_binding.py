"""Income composition must work before League without replacing scoped actors."""

from dataclasses import fields
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
from pokemon_red_completion.red_learned_trainer import (
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
    FrozenTrainerBattler,
)
from pokemon_red_completion.red_player_configuration import connect_retained_ordinary_funding


def fixture(badges=6):
    actor = object.__new__(FrozenTrainerBattler)
    actor.model_sha256 = FROZEN_K_SHA256
    actor.qualification_sha256 = K_QUALIFICATION_SHA256
    actor.source_partition = ScenarioPartition.DEVELOPMENT
    emulator = N(frame_count=0, pressed_buttons=(), save_state_bytes=lambda: b"original")
    runtime = RedGoalContextRuntime(
        profile=object(), capture=object(), emulator=emulator,
        reader=N(read=lambda: N(badge_bits=(1 << badges) - 1)),
        observer=object(), adapter=object(),
    )
    return runtime, actor


@pytest.mark.parametrize("badges", [0, 3, 6, 8])
def test_qualified_existing_actor_can_earn_before_or_after_league_without_inputs(badges):
    original, actor = fixture(badges)
    bound = connect_retained_ordinary_funding(original, actor)
    assert bound.trainer_battle_runner.__self__ is actor
    assert bound.trainer_battle_model_sha256 == FROZEN_K_SHA256
    assert bound.trainer_battle_qualification_sha256 == K_QUALIFICATION_SHA256
    changes = {
        "trainer_battle_runner", "trainer_battle_model_sha256",
        "trainer_battle_qualification_sha256", "trainer_funding_recovery",
        "trainer_funding_ledges", "trainer_funding_surf", "trainer_funding_indoor_departure",
    }
    for field in fields(original):
        if field.name not in changes:
            assert getattr(bound, field.name) is getattr(original, field.name)
    assert bound.trainer_funding_recovery and bound.trainer_funding_indoor_departure
    assert bound.emulator.save_state_bytes() == b"original"
    assert bound.emulator.frame_count == 0 and bound.emulator.pressed_buttons == ()
    assert original.trainer_battle_runner is None


@pytest.mark.parametrize("fault", ["missing", "model", "qualification", "partition", "train"])
def test_ineligible_actor_keeps_income_unbound(fault):
    runtime, actor = fixture()
    if fault == "missing":
        actor = None
    elif fault == "model":
        actor.model_sha256 = "0" * 64
    elif fault == "qualification":
        actor.qualification_sha256 = "0" * 64
    elif fault == "partition":
        actor.source_partition = "development"
    else:
        actor.source_partition = ScenarioPartition.TRAIN
    assert connect_retained_ordinary_funding(runtime, actor) is runtime


@pytest.mark.parametrize("fault", ["story", "other_runner", "runner_model", "runner_qualification"])
def test_income_never_replaces_an_existing_incompatible_battle_scope(fault):
    runtime, actor = fixture()
    if fault == "story":
        runtime.league_story_battle_controller = object()
    elif fault == "other_runner":
        runtime.trainer_battle_runner = lambda *_a, **_k: None
    else:
        runtime.trainer_battle_runner = actor.run
        runtime.trainer_battle_model_sha256 = FROZEN_K_SHA256
        runtime.trainer_battle_qualification_sha256 = K_QUALIFICATION_SHA256
        if fault == "runner_model":
            runtime.trainer_battle_model_sha256 = "0" * 64
        else:
            runtime.trainer_battle_qualification_sha256 = "0" * 64
    assert connect_retained_ordinary_funding(runtime, actor) is runtime


def test_rebinding_keeps_the_same_owned_actor_and_existing_opt_ins():
    runtime, actor = fixture()
    runtime.collection_dig_departure = True
    once = connect_retained_ordinary_funding(runtime, actor)
    twice = connect_retained_ordinary_funding(once, actor)
    assert twice == once
    assert twice.trainer_battle_runner.__self__ is actor
    assert twice.collection_dig_departure
