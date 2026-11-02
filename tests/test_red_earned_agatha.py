"""Exact earned admission; no private model or emulator needed for guard tests."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_red_trainer_practice_fit import _target

from pokemon_red_completion import red_learned_trainer as learned
from pokemon_red_completion.red_lorelei_story import (
    FrozenEarnedAgathaStoryController,
    story_league_controller,
)
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.red_trainer_practice_fit import fit_trainer_practice_three_heads


@pytest.fixture
def setup(tmp_path, monkeypatch):
    model = fit_trainer_practice_three_heads(
        [_target()], seed=1, epochs=1, require_corpus_floor=False
    )
    monkeypatch.setattr(
        learned, "AGATHA_STORY_MODEL_SHA256", learned.canonical_sha256(model.to_dict())
    )
    actor = learned.FrozenTrainerBattler(
        None,
        model,
        tmp_path,
        "a" * 40,
        "root",
        learned.AGATHA_STORY_SOURCE_SHA256,
        {},
        model_sha256=learned.AGATHA_STORY_SHA256,
        qualification_sha256=learned.AGATHA_STORY_ADMISSION_SHA256,
    )
    contract = StoryTrainerContract(
        "defeat_agatha", "cartridge-trainer-story", 247, (246, 46, 1), 2289, 5940
    )
    admission = (
        Path(__file__).parents[1] / "docs/evidence/red-earned-agatha-admission-2026-09-25.json"
    ).read_bytes()
    return actor, contract, admission


def test_exact_admission_is_not_ordinary_funding(setup):
    actor, contract, admission = setup
    assert sha256(admission).hexdigest() == learned.AGATHA_STORY_ADMISSION_SHA256
    ctl = FrozenEarnedAgathaStoryController(actor, contract, admission)
    assert story_league_controller(NS(league_story_battle_controller=ctl), "defeat_agatha") is ctl
    assert learned.qualified_party_limit(actor.model_sha256, actor.qualification_sha256) == 0
    with pytest.raises(ValueError):
        learned.load_frozen_trainer_model(b"{}", actor.model_sha256, qualification=admission)


@pytest.mark.parametrize(
    "change",
    [
        {"objective_id": "defeat_lance"},
        {"battle_plan_id": "ordinary-trainer-funding"},
        {"map_id": 248},
        {"trainer_identity": (246, 46, 2)},
        {"defeated_event": 8},
        {"victory_money": 1},
        {"victory_items": ((1, 1),)},
        {"victory_badge_bits": 1},
    ],
)
def test_other_contracts_rejected_before_input(setup, change):
    actor, contract, admission = setup
    with pytest.raises(ValueError):
        FrozenEarnedAgathaStoryController(actor, replace(contract, **change), admission)
    assert not list(actor.output.iterdir())


@pytest.mark.parametrize("fault", ["source", "weights", "receipt", "model_label", "calls", "claim"])
def test_mutation_and_replay_rejected(setup, fault):
    actor, contract, admission = setup
    ctl = FrozenEarnedAgathaStoryController(actor, contract, admission)
    if fault == "source":
        actor.source_state_sha256 = "0" * 64
    elif fault == "weights":
        actor.model = None
    elif fault == "receipt":
        ctl.admission += b" "
    elif fault == "model_label":
        actor.model_sha256 = learned.DAMAGE_STORY_SHA256
    elif fault == "calls":
        actor.calls = 1
    else:
        (actor.output / "battle-0001").mkdir()
    with pytest.raises(ValueError):
        ctl.require_identity()


@pytest.mark.parametrize("objective,rematch", [("defeat_lance", False), ("defeat_agatha", True)])
def test_no_next_room_or_rematch(setup, objective, rematch):
    ctl = FrozenEarnedAgathaStoryController(*setup)
    with pytest.raises(ValueError):
        story_league_controller(NS(league_story_battle_controller=ctl), objective, rematch=rematch)


@pytest.mark.parametrize("fault", ["authority", "map", "identity", "resume", "win", "wild"])
def test_direct_runtime_cannot_bypass_scope(setup, fault):
    actor, _, _ = setup
    raw = NS(map_id=247, battle_state=2)
    reader = NS(
        read=lambda: raw,
        read_active_trainer_identity=lambda: (246, 46, 2) if fault == "identity" else (246, 46, 1),
    )
    with pytest.raises(ValueError):
        actor._play(
            reader,
            None,
            expected_map=248 if fault == "map" else 247,
            timing=None,
            label="test",
            decision_guard=lambda _: None,
            resume=fault != "resume",
            require_win=fault == "win",
            wild_training=fault == "wild",
            authority=None if fault == "authority" else "frozen-risk-cost-agatha-development",
        )
    assert actor.calls == 0 and not list(actor.output.iterdir())
