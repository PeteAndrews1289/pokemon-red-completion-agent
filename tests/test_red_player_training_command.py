import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_goal_resource_quote import _supply_model
from test_paired_red_bounded_player_script import SCRIPT
from test_red_player_training import _plan


@pytest.mark.parametrize("continued", [False, True])
def test_training_runs_one_arm_after_declaration_and_never_compares(monkeypatch, continued):
    module = runpy.run_path(str(SCRIPT))
    run = module["_run"]
    namespace = run.__globals__
    plan = _plan(_supply_model())
    publications, arms, writes = [], [], []
    readiness = SimpleNamespace(
        pair_id="native-training-test",
        training_plan=plan,
        continuation=object() if continued else None,
        continuation_chain=(("old-train-endpoint", "f" * 64),) if continued else (),
        continuation_root_lineage_id=plan.document["root_lineage_id"] if continued else None,
        protected_paths=(),
        rom_path=Path("unused"),
        context_origin="training",
        dashboard_port=None,
        challenger_arm_id=module["CAUSAL_ARM_ID"],
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        rom_sha256="c" * 64,
        model_file_sha256="d" * 64,
        model_sha256=plan.document["model_sha256"],
        decision_limit=4,
        continue_after_progress=True,
        routed_resource_goals=True,
        quote_resource_costs=True,
        save_terminal_checkpoints=False,
        causal_record=None,
        calibration_record=None,
        output_path=Path("unused-result"),
        private_root=SimpleNamespace(
            publish_sealed_record=lambda *args, **kwargs: publications.append((args, kwargs))
        ),
    )
    monkeypatch.setitem(namespace, "_prepare", lambda _: readiness)
    monkeypatch.setitem(namespace, "rom_adjacent_artifacts", lambda _: {})
    monkeypatch.setitem(namespace, "_action_free_preflight", lambda _: {"actions": 0})
    monkeypatch.setitem(namespace, "_challenger_authority", lambda _: object())

    def execute(_readiness, *, arm_id, **_kwargs):
        assert len(publications) == 1
        arms.append(arm_id)
        assert arm_id != module["BASELINE_ARM_ID"]
        return SimpleNamespace(
            trajectory_manifest_sha256="e" * 64,
            episode=SimpleNamespace(public_dict=lambda: {"test_stub": True}),
        )

    monkeypatch.setitem(namespace, "_run_arm", execute)
    monkeypatch.setitem(
        namespace,
        "compare_paired_bounded_player_arms",
        lambda **_: pytest.fail("training ran a comparison"),
    )
    monkeypatch.setitem(
        namespace, "_write_exclusive", lambda _path, document: writes.append(document)
    )
    result = run(SimpleNamespace())
    assert arms == [module["CAUSAL_ARM_ID"]]
    assert result["model_fitted"] is False and result["independent_evaluation"] is False
    assert result["evidence_scope"] == "prospective_correlated_training"
    assert result["schema"] == "pokemon.red.bounded-player-training-result.v1"
    if continued:
        assert result["training_eligible"] is True
        assert result["independent_root"] is False
        assert result["plan_sha256"] == plan.plan_sha256
    assert writes == [result]
