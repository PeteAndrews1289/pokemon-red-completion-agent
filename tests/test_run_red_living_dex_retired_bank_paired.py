from __future__ import annotations

import json
from pathlib import Path

import pytest
import run_red_living_dex_retired_bank_paired as command
from run_product_focus_dashboard import _load_learning_evidence, _training_projection

from pokemon_red_completion.red_living_dex_setup_trust import RedLivingDexSetupEffectMeter


def _args() -> list[str]:
    values = []
    for action in command._parser()._actions:
        if action.required:
            values.extend((action.option_strings[0], "test-input"))
    return values


@pytest.mark.parametrize("flag", ["--fit", "--retry", "--candidate", "--ordinal", "--reserve"])
def test_no_fit_retry_selection_or_reserve_interface(flag: str) -> None:
    with pytest.raises(SystemExit):
        command._parser().parse_args([*_args(), flag, "1"])


def test_changed_source_stops_before_private_reads(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    accessed = []
    monkeypatch.setattr(command, "detect_source_identity", lambda *_args, **_kwargs: "dirty")

    def reject(source):  # type: ignore[no-untyped-def]
        assert source == "dirty"
        raise ValueError("source is dirty")

    monkeypatch.setattr(command, "require_clean_source", reject)
    monkeypatch.setattr(
        command.training_support.base, "_read_schedule", lambda *_: accessed.append("private")
    )
    assert command.main(_args()) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["stage"] == "clean_published_source"
    assert result["model_fits"] == 0
    assert accessed == []


def test_live_feed_uses_real_fitted_identity_and_separates_control() -> None:
    training, component = _training_projection(_load_learning_evidence())
    view = command._LiveView(component.model_sha256, RedLivingDexSetupEffectMeter())
    assert view.snapshot.training == training
    assert not view.snapshot.collection_observed
    assert view.snapshot.model.decisions == 0
    assert json.loads(view.state.status_bytes()[0])["dashboard"]["frame_age_seconds"] is None
    view.event(
        "choices_committed",
        {
            "control_question": {"candidates": [{"kind": "acquire_species"}, {"kind": "resupply"}]},
            "origin_observation": {
                "collection": {
                    "registered": 10,
                    "living": 8,
                    "level_cap": 0,
                    "registered_target": 124,
                    "living_target": 120,
                },
                "capture_item_count": 2,
                "free_storage_slots": 30,
            },
        },
    )
    assert view.snapshot.registered_species == 10
    assert view.snapshot.living_species == 8
    assert view.snapshot.collection_observed
    view.event("arm_started", {"actor": "model", "selected_candidate_index": 0})
    assert view.snapshot.model.mode == "model"
    assert view.snapshot.model.choice == "acquire species"
    assert view.snapshot.model.decisions == 1
    assert view.snapshot.stage == "Model-selected goal"
    view.event("arm_terminal", {"actor": "model", "status": "censored"})
    view.event("arm_started", {"actor": "control", "selected_candidate_index": 1})
    assert view.snapshot.model.mode == "teacher"
    assert view.snapshot.model.decisions == 1
    assert view.snapshot.experiment.adaptation_completed == 1


def test_view_cannot_borrow_training_chart_from_another_model() -> None:
    with pytest.raises(ValueError, match="another fitted model"):
        command._LiveView("f" * 64, RedLivingDexSetupEffectMeter())


def test_bad_frame_disables_only_the_view_and_cannot_abort_play() -> None:
    _, component = _training_projection(_load_learning_evidence())
    meter = RedLivingDexSetupEffectMeter()
    view = command._LiveView(component.model_sha256, meter)
    view.publish_frame(0, 0, b"", 1)
    assert view.viewer_failures == 1
    assert view.frames_disabled
    assert not view.wants_frame(2)
    view.publish_frame(0, 0, b"", 2)
    assert view.viewer_failures == 1
    assert meter.controller_actions == 0
    assert meter.emulator_frames == 0


def test_fixed_game_budget_and_model_record_are_distinct_from_frozen_prior() -> None:
    args = command._parser().parse_args(_args())
    assert isinstance(args.fitted_model, Path)
    assert args.port == 8769
    assert not args.preflight_only
    assert args.fitted_model_sha256 is not None
    assert args.expected_model_sha256 is not None
