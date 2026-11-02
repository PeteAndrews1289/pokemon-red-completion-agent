import hashlib
import json
from pathlib import Path

import pytest
from test_red_story_battle import actor, contract

from pokemon_red_completion import red_learned_trainer as learned
from pokemon_red_completion.red_story_battle import FrozenStoryBattleController


def test_damage_admission_receipt_pins_passed_audits_and_narrow_scope():
    root = Path(__file__).parents[1]
    payload = (root / "docs/evidence/red-damage-story-admission-2026-09-23.json").read_bytes()
    receipt = json.loads(payload)
    assert hashlib.sha256(payload).hexdigest() == learned.DAMAGE_STORY_ADMISSION_SHA256
    assert receipt["model_sha256"] == learned.DAMAGE_STORY_SHA256
    assert receipt["semantic_model_sha256"] == learned.DAMAGE_STORY_MODEL_SHA256
    for key, name in (
        ("damage", "red-interaction-damage-v2"),
        ("composition", "red-damage-composition"),
        ("two_turn", "red-two-turn-compatibility"),
    ):
        evidence = json.loads((root / f"docs/evidence/{name}-2026-09-23.json").read_text())
        assert receipt["qualification_audits"][key] == evidence["audit_sha256"]
    for key in (
        "full_player_promoted",
        "ordinary_funding_authorized",
        "league_authorized",
        "wild_training_authorized",
        "development_fitting_allowed",
        "teacher_fallback_allowed",
    ):
        assert receipt[key] is False
    assert (
        learned.qualified_party_limit(
            learned.DAMAGE_STORY_SHA256, learned.DAMAGE_STORY_ADMISSION_SHA256
        )
        == 0
    )


@pytest.mark.parametrize(
    "model,receipt",
    [
        (learned.DAMAGE_STORY_SHA256, None),
        (learned.DAMAGE_STORY_SHA256, learned.ADDITIVE_STORY_ADMISSION_SHA256),
        (learned.ADDITIVE_STORY_SHA256, learned.DAMAGE_STORY_ADMISSION_SHA256),
        ("0" * 64, learned.DAMAGE_STORY_ADMISSION_SHA256),
    ],
)
def test_damage_binding_rejects_mismatched_pair_before_input(tmp_path, model, receipt):
    battler = actor(tmp_path)
    battler.model_sha256, battler.qualification_sha256 = model, receipt
    with pytest.raises(ValueError):
        FrozenStoryBattleController(battler, (contract(),))
    assert not tuple(tmp_path.iterdir())


def test_claimed_hash_cannot_hide_changed_actual_model(tmp_path):
    battler = actor(tmp_path)
    battler.model_sha256 = learned.DAMAGE_STORY_SHA256
    battler.qualification_sha256 = learned.DAMAGE_STORY_ADMISSION_SHA256
    # Wrong actual object despite correct claimed identities: reject before intro input.
    with pytest.raises(ValueError, match="model object differs"):
        FrozenStoryBattleController(battler, (contract(),))
    assert not tuple(tmp_path.iterdir())


def test_changed_checkpoint_or_receipt_rejected_by_loader():
    receipt = (
        Path(__file__).parents[1] / "docs/evidence/red-damage-story-admission-2026-09-23.json"
    ).read_bytes()
    for changed in (receipt, receipt + b" "):
        with pytest.raises(ValueError, match="exact checkpoint"):
            learned.load_story_trainer_model(b"{}", changed)


@pytest.mark.parametrize(
    "authority", [None, "frozen-additive-story-development", "frozen-k-league-development"]
)
def test_damage_model_cannot_borrow_another_scope(tmp_path, authority):
    battler = actor(tmp_path)
    battler.model_sha256 = learned.DAMAGE_STORY_SHA256
    battler.qualification_sha256 = learned.DAMAGE_STORY_ADMISSION_SHA256
    with pytest.raises(ValueError):
        battler._play(
            None,
            None,
            expected_map=33,
            timing=None,
            label="wrong scope",
            decision_guard=lambda _: None,
            resume=True,
            require_win=False,
            authority=authority,
            allow_immune_switch_recovery=True,
        )
    assert not tuple(tmp_path.iterdir())
