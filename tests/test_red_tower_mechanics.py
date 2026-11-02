"""The existing mechanics boundary is opt-in, K-only and Tower-story-only."""

from dataclasses import replace

import pytest

from pokemon_red_completion.red_learned_trainer import (
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
    FrozenTrainerBattler,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def actor(tmp_path, **changes):
    result = FrozenTrainerBattler(
        None,
        None,
        tmp_path,
        "a" * 40,
        "root",
        "b" * 64,
        {},
        model_sha256=FROZEN_K_SHA256,
        qualification_sha256=K_QUALIFICATION_SHA256,
    )
    return replace(result, **changes)


def test_disabled_by_default(tmp_path):
    assert not actor(tmp_path).tower_mechanics_active(145, "frozen-k-story-development")


@pytest.mark.parametrize("map_id", range(143, 149))
def test_only_exact_tower_story(tmp_path, map_id):
    value = actor(tmp_path, mechanics_aware_tower_choices=True)
    assert value.tower_mechanics_active(map_id, "frozen-k-story-development")
    assert not value.tower_mechanics_active(map_id, "frozen-k-wild-training-development")


@pytest.mark.parametrize("map_id", [142, 149, 134, None, True])
def test_other_maps_unchanged(tmp_path, map_id):
    assert not actor(tmp_path, mechanics_aware_tower_choices=True).tower_mechanics_active(
        map_id, "frozen-k-story-development"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"mechanics_aware_tower_choices": 1},
        {"mechanics_aware_tower_choices": "yes"},
        {"source_partition": ScenarioPartition.TRAIN},
        {"model_sha256": "c" * 64},
        {"qualification_sha256": "d" * 64},
        {"train_funding_diagnostic": True},
        {"train_story_contract": object()},
        {"development_story_scope": object()},
        {"development_preparation_scope": object()},
        {"evaluation_story_scope": object()},
        {"train_risk_story_scope": object()},
        {"story_chain_scope": object()},
    ],
)
def test_wrong_authority_rejected_without_input(tmp_path, changes):
    value = actor(tmp_path, **({"mechanics_aware_tower_choices": True} | changes))
    with pytest.raises(ValueError, match="Tower mechanics"):
        value.tower_mechanics_active(145, "frozen-k-story-development")
    assert value.calls == 0 and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "changes",
    [
        {"source_partition": ScenarioPartition.TRAIN},
        {"model_sha256": "c" * 64},
        {"qualification_sha256": "d" * 64},
        {"mechanics_aware_tower_choices": 1},
    ],
)
def test_live_entry_rejects_wrong_scope_before_reader_or_output(tmp_path, changes):
    from pokemon_red_completion.battle_runtime import BattleRuntimeTiming

    value = actor(tmp_path, **({"mechanics_aware_tower_choices": True} | changes))
    with pytest.raises(ValueError, match="Tower mechanics"):
        value._play(
            None,
            None,
            expected_map=145,
            timing=BattleRuntimeTiming(),
            label="test",
            decision_guard=lambda _: None,
            resume=True,
            require_win=False,
            authority="frozen-k-story-development",
        )
    assert value.calls == 0 and not list(tmp_path.iterdir())


def test_existing_pp_screen_can_coexist(tmp_path):
    assert actor(
        tmp_path, pp_depleted_switch_screen=True, mechanics_aware_tower_choices=True
    ).tower_mechanics_active(145, "frozen-k-story-development")


@pytest.mark.parametrize(
    "changes",
    [
        {"diagnostic_tower_productive_stay": 1},
        {"diagnostic_tower_productive_stay": "yes"},
        {"diagnostic_tower_productive_stay": True},
    ],
)
def test_diagnostic_stay_cannot_enable_implicit_or_wrong_tower_scope(tmp_path, changes):
    with pytest.raises(ValueError, match="diagnostic stay"):
        actor(tmp_path, **changes).tower_mechanics_active(145, "frozen-k-story-development")


def test_diagnostic_is_explicit_and_tower_only(tmp_path):
    value = actor(
        tmp_path, mechanics_aware_tower_choices=True, diagnostic_tower_productive_stay=True
    )
    assert value.tower_mechanics_active(145, "frozen-k-story-development")
    assert not value.tower_mechanics_active(24, "frozen-k-story-development")
    assert not value.tower_mechanics_active(145, "frozen-k-wild-training-development")
