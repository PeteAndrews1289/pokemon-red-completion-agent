"""Current-feature continuation contracts; all fixtures here are synthetic."""

import json
from dataclasses import replace

import pytest
from test_red_native_player import setup
from test_story_unit_v16 import candidate, context

from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionMenu,
    option_feature_names,
    upgrade_option_value_model_for_story_unit,
)
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit
from pokemon_red_completion.player_sequence_policy import SequenceChoiceContext
from pokemon_red_completion.player_sequence_reconstruction import reconstruct_sequence_candidates
from pokemon_red_completion.player_sequence_value import (
    SequenceRegressionRow,
    SequenceValueHead,
    fit_sequence_value,
    sequence_feature_width,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.recorded_branch_history import RecordedBranchHistory
from pokemon_red_completion.red_native_player import run_native_continuous_player
from pokemon_red_completion.red_sequence_native_audit import audit_native_sequence_trace


def read(path):
    return json.loads(path.read_bytes())


def test_v16_scope_reaches_continuation_features_and_head_roundtrips():
    menu = LivingDexOptionMenu(
        context(),
        (
            replace(candidate(), story_unit=OptionStoryUnit("movement", True)),
            replace(
                candidate(), binding_ref="other", story_unit=OptionStoryUnit("interaction", False)
            ),
        ),
    )
    zero = RecordedBranchHistory(0, 0, 0, 0, 0, 0, 0, 0)
    ctx = SequenceChoiceContext(menu.policy_sha256, "a" * 64, (zero, zero), feature_version=16)
    vectors = ctx.vectors(menu)
    assert len(vectors[0]) == len(option_feature_names(16)) + 8
    assert vectors[0][-12:-8] == (1.0, 1.0, 0.0, 1.0)
    assert vectors[1][-12:-8] == (1.0, 0.0, 1.0, 0.0)
    rows = tuple(
        SequenceRegressionRow(
            f"{i:064x}", v, (float(i),) + (None,) * 6, "train", feature_version=16
        )
        for i, v in enumerate(vectors)
    )
    head = fit_sequence_value(rows, ridge=1.0, horizon=2, behavior_model_sha256="b" * 64)
    assert head.feature_version == 16 and head.predict(vectors[1])[0] > head.predict(vectors[0])[0]
    assert head.predict(vectors[0])[-1] is None
    doc = head.document()
    assert doc["schema"].endswith(".v2") and doc["feature_version"] == 16
    assert SequenceValueHead.from_document(doc, expected_sha256=head.model_sha256) == head
    assert SequenceChoiceContext.from_document(ctx.document()) == ctx
    with pytest.raises(ValueError):
        replace(ctx, feature_version=6).vectors(menu)
    with pytest.raises(ValueError):
        head.score(vectors[0], utility=(0.0,) * 6 + (1.0,))


@pytest.mark.parametrize("version", [True, 0, 7, 15, 17])
def test_unsupported_or_boolean_sequence_versions_fail_closed(version):
    with pytest.raises(ValueError):
        sequence_feature_width(version)


def test_mixed_versions_cannot_be_pooled_in_a_fit():
    rows = tuple(
        SequenceRegressionRow(
            f"{i:064x}",
            (0.0,) * sequence_feature_width(v),
            (float(i),) + (None,) * 6,
            "train",
            feature_version=v,
        )
        for i, v in enumerate((6, 16))
    )
    with pytest.raises(ValueError):
        fit_sequence_value(rows, ridge=1.0, horizon=2, behavior_model_sha256="b" * 64)


def test_v16_passive_native_path_collects_and_reconstructs_without_changing_authority(
    tmp_path, monkeypatch
):
    args, executed = setup(tmp_path, monkeypatch)
    args.update(
        model=upgrade_option_value_model_for_story_unit(args["model"]),
        sequence_horizon=2,
        limits=replace(args["limits"], decisions=6, actions=6),
    )
    result = run_native_continuous_player(**args)
    root = args["output"]
    episode = root / "episode"
    assert executed and result["model_sha256"] == args["model"].model_sha256
    declaration = read(episode / "sequence/declaration.json")
    assert declaration["schema"].endswith(".v2") and declaration["feature_version"] == 16
    assert declaration["scoring_changed"] is False and declaration["training_eligible"] is False
    audit = audit_native_sequence_trace(
        root,
        store=args["store"],
        model=args["model"],
        expected_native_plan_sha256=canonical_sha256(read(root / "native-plan.json")),
        expected_actor_result_sha256=canonical_sha256(read(episode / "result.json")),
        source_sha256=args["source"]["state_sha256"],
    )
    windows = reconstruct_sequence_candidates(
        episode,
        source_sha256=args["source"]["state_sha256"],
        partition=args["source"]["partition"],
        expected_plan_sha256=canonical_sha256(read(episode / "plan.json")),
        expected_result_sha256=canonical_sha256(read(episode / "result.json")),
        expected_declaration_sha256=canonical_sha256(declaration),
    )
    assert windows and audit.recorded_selector_and_binding_replayed == 6
    assert all(len(w.features) == sequence_feature_width(16) for w in windows)
    assert all(not w.training_eligible and not any(w.targets.known) for w in windows)
