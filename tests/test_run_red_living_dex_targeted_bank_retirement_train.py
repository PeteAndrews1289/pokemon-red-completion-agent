from __future__ import annotations

import ast
import json
import runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_freeze_red_living_dex_provider_plan_script import _private_context
from test_living_dex_repeatable_trial_claim import _registry
from test_red_living_dex_provider_plan import _root

from pokemon_red_completion.goal_manager_composition_qualification import (
    root_claim_is_available,
)
from pokemon_red_completion.living_dex_repeatable_trial_claim import (
    LivingDexRepeatableRootReservation,
    ensure_living_dex_repeatable_root_reservation,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_red_living_dex_targeted_bank_retirement_train.py"
RUNNER = runpy.run_path(
    str(SCRIPT),
    run_name="run_red_living_dex_targeted_bank_retirement_train_test",
)


def test_retired_bank_train_command_exposes_no_manual_slot_or_retry() -> None:
    source = SCRIPT.read_text()
    tree = ast.parse(source)

    assert tree is not None
    assert 'add_argument("--ordinal"' not in source
    assert 'add_argument("--retry"' not in source
    assert 'add_argument("--development' not in source
    assert 'add_argument("--reserve' not in source
    assert 'add_argument("--candidate' not in source
    assert "run_red_living_dex_targeted_train_campaign" in source
    assert "authenticate_red_living_dex_targeted_bank_retirement_plan" in source


def test_retired_bank_train_command_has_opt_in_fit_but_no_teacher_or_crystal_entrypoint() -> None:
    source = SCRIPT.read_text().lower()

    for forbidden in (
        "fit_model",
        "model.fit",
        "run_teacher",
        "teacher_policy",
        "run_crystal",
        "pokemon_crystal",
    ):
        assert forbidden not in source
    assert '"development_slots_opened": 0' in source
    assert '"model_fits": 0' in source
    assert '"teacher_queries": 0' in source
    assert 'add_argument("--fit-on-complete", action="store_true")' in source
    assert 'add_argument("--prior-model-record-id", required=true)' in source
    assert "if args.fit_on_complete and readiness.ready:" in source
    assert "prepare_red_living_dex_targeted_fit_basis" in source


def test_retired_bank_train_command_has_an_action_free_preflight() -> None:
    source = SCRIPT.read_text()

    assert 'add_argument("--preflight-only"' in source
    assert '"retired_bank_train_preflight_passed"' in source


def test_retired_bank_train_command_missing_arguments_fail_closed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert RUNNER["main"]([]) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed_closed"
    assert result["stage"] == "arguments"
    assert result["development_slots_opened"] == 0
    assert result["model_fits"] == 0
    assert result["model_predictions"] == 0
    assert result["teacher_queries"] == 0


def _reentry_fixture(tmp_path, monkeypatch, *, partition="train"):
    """Exercise the command's real claim boundary; substitute only observation."""

    private = _private_context(0, partition="validation")
    root = RedLivingDexAuthenticatedSetupRoot(
        root_consumption_sha256=private.root_consumption_sha256,
        state_bytes=private.capture.state_bytes,
        envelope_bytes=(
            json.dumps(private.capture.envelope.to_dict(), sort_keys=True).encode("ascii") + b"\n"
        ),
    )
    lineage = canonical_sha256(
        {
            "root_lineage_id": private.assignment.root_lineage_id,
            "schema": "pokemon.red.private-provider-capacity-lineage.v1",
        }
    )
    # Descriptor validation is covered separately; this unit addresses one root
    # through the same re-entry function used by main, with a real pair ledger.
    schedule = SimpleNamespace(
        schedule_sha256="c" * 64,
        slots=(
            SimpleNamespace(
                physical_root_sha256=root.physical_root_sha256,
                lineage_sha256=lineage,
                partition=partition,
            ),
        ),
    )
    descriptor = SimpleNamespace(schedule_descriptor=SimpleNamespace(schedule=schedule))
    registry = _registry(tmp_path)
    reservation = LivingDexRepeatableRootReservation(
        schedule_sha256=schedule.schedule_sha256,
        logical_root_sha256=root.root_consumption_sha256,
        physical_root_sha256=root.physical_root_sha256,
        runner_sha256=RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256,
        source_commit="a" * 40,
    )
    observed = []

    def observe(value, **kwargs):
        assert value == root
        assert kwargs["cluster_partition"] == "development"
        observed.append(value)
        return replace(
            _root(0),
            root=root,
            observed_state_sha256=root.state_sha256,
            independence_lineage_sha256=lineage,
            cluster_partition="development",
        )

    function = RUNNER["_observe_retired_roots"]
    support = function.__globals__["base"].freezer._PROVIDER_SUPPORT
    monkeypatch.setitem(support, "_observe_root", observe)

    def reenter(**kwargs):
        return function(
            descriptor,
            (private,),
            rom_path=Path("synthetic.gb"),
            rom_bytes=b"synthetic",
            runtime=None,
            claim_registry=registry,
            source_commit="a" * 40,
            **kwargs,
        )

    return private, registry, reservation, observed, reenter


def test_command_reobserves_unused_then_own_reserved_root_without_new_claims(tmp_path, monkeypatch):
    private, registry, reservation, observed, reenter = _reentry_fixture(tmp_path, monkeypatch)
    first = reenter()
    assert root_claim_is_available(registry, reservation.logical_root_sha256)
    ensure_living_dex_repeatable_root_reservation(registry, reservation)
    private.root_available = False  # Fresh inventory after interruption/completion.
    before = {path.name: path.read_bytes() for path in registry.iterdir()}
    assert reenter() == first
    assert len(observed) == 2
    assert {path.name: path.read_bytes() for path in registry.iterdir()} == before


@pytest.mark.parametrize("partition", ["train", "development"])
def test_command_rejects_foreign_claims_before_observation(tmp_path, monkeypatch, partition):
    _private, registry, reservation, observed, reenter = _reentry_fixture(
        tmp_path, monkeypatch, partition=partition
    )
    ensure_living_dex_repeatable_root_reservation(
        registry, replace(reservation, source_commit="b" * 40)
    )
    with pytest.raises(
        RUNNER["RetiredBankTrainCommandError"], match="root_reservation_authentication"
    ):
        reenter()
    assert not observed


def test_command_cannot_recover_a_paired_evaluation_root_as_training(tmp_path, monkeypatch):
    _private, registry, reservation, observed, reenter = _reentry_fixture(
        tmp_path, monkeypatch, partition="development"
    )
    ensure_living_dex_repeatable_root_reservation(registry, reservation)
    with pytest.raises(
        RUNNER["RetiredBankTrainCommandError"], match="root_reservation_authentication"
    ):
        reenter()
    assert not observed


def test_paired_consumer_must_prove_ownership_before_reobserving_a_consumed_root(
    tmp_path, monkeypatch
):
    _private, registry, reservation, observed, reenter = _reentry_fixture(
        tmp_path, monkeypatch, partition="development"
    )
    ensure_living_dex_repeatable_root_reservation(registry, reservation)
    checked = []

    def denied(root, lineage):
        checked.append((root.physical_root_sha256, lineage))
        return False

    with pytest.raises(RUNNER["RetiredBankTrainCommandError"]):
        reenter(owned_development_claim=denied)
    assert len(checked) == 1
    assert observed == []


def test_paired_ownership_callback_cannot_bypass_foreign_train_reservation(tmp_path, monkeypatch):
    _private, registry, reservation, observed, reenter = _reentry_fixture(
        tmp_path, monkeypatch, partition="train"
    )
    ensure_living_dex_repeatable_root_reservation(
        registry, replace(reservation, source_commit="b" * 40)
    )
    with pytest.raises(RUNNER["RetiredBankTrainCommandError"]):
        reenter(owned_development_claim=lambda *_args: True)
    assert observed == []
