"""Authenticated reserve inheritance for autonomous continuation."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fit_red_autonomous_collection import _require_unassisted_goal_fit  # noqa: E402
from run_red_autonomous_collection import (  # noqa: E402
    _apply_assisted_training_money,
    _validate_paid_exit_budget,
    _verify_goal_continuation,
    _verify_reserve_lineage,
)

from pokemon_red_completion.observation import RamAddress


@pytest.mark.parametrize("change", [None, "reserve", "state", "prior_state", "missing", "mode"])
def test_paid_attachment_still_requires_original_reserve_chain(change):
    from test_red_paid_safari_lineage import encode, fixture

    from pokemon_red_completion.red_paid_safari_lineage import PAID_RECORDS

    plan, docs = fixture()
    plan.update({key: {} for key in PAID_RECORDS})
    plan.update(prior_plan={}, prior_outcome={}, reserve_origin={"sha256": "a" * 64})
    docs["prior_plan"]["provenance"].update(
        parent_state_sha256="b" * 64, reserve_origin_state_sha256="a" * 64,
    )
    if change == "reserve":
        plan["reserve_origin"]["sha256"] = "wrong"
    elif change == "state":
        plan["state"]["sha256"] = "wrong"
    elif change == "prior_state":
        docs["prior_plan"]["provenance"]["parent_state_sha256"] = "wrong"
    elif change == "missing":
        del plan["reserve_origin"]
    elif change == "mode":
        plan["mode"] = "continue_selected_goal"
    if change is None:
        _verify_reserve_lineage(plan, encode(docs))
    else:
        with pytest.raises(ValueError):
            _verify_reserve_lineage(plan, encode(docs))


@pytest.mark.parametrize("actions,frames,accepted", [
    (2000, 240000, True), (2001, 240000, False), (2000, 240001, False),
    (0, 1000, False), (True, 1000, False), (100, 40000, False),
])
def test_paid_exit_keeps_original_remaining_allowance(actions, frames, accepted):
    from test_red_paid_safari_lineage import encode, fixture

    plan, docs = fixture()
    # Frame allowance below the fixed ceiling is still binding.
    docs["paid_safari_plan"]["remaining_original_frames"] = 242000 if accepted else 30000
    plan.update(maximum_actions=actions, maximum_frames=frames)
    if accepted:
        _validate_paid_exit_budget(plan, encode(docs))
    else:
        with pytest.raises(ValueError):
            _validate_paid_exit_budget(plan, encode(docs))


class _TrainingEmulator:
    def __init__(self, money_bytes=(0x00, 0x01, 0x98)):
        self.frame_count = 0
        self.pressed_buttons = frozenset()
        self.memory = {
            int(RamAddress.PLAYER_MONEY) + index: value for index, value in enumerate(money_bytes)
        }

    def read_u8(self, address):
        return self.memory[address]

    def _require_backend(self):
        return self


@pytest.mark.parametrize("limit", [0, 513, True, 1.5, "512", None])
def test_invalid_evolution_budget_rejected_before_private_inputs(tmp_path, monkeypatch, limit):
    import run_red_autonomous_collection as module

    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"maximum_evolution_quanta": limit}))
    monkeypatch.setattr(sys, "argv", ["run", "--plan", str(plan)])
    with pytest.raises(ValueError, match="quantum limit"):
        module.main()


@pytest.mark.parametrize("value", [0, 1, "true", [], None])
def test_npc_trade_scope_requires_boolean_before_private_inputs(tmp_path, monkeypatch, value):
    import run_red_autonomous_collection as module
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"npc_trades": value}))
    monkeypatch.setattr(sys, "argv", ["run", "--plan", str(plan)])
    with pytest.raises(ValueError, match="NPC trade scope"):
        module.main()


@pytest.mark.parametrize("change", [
    {"integrated_play": "true"}, {"maximum_cash_spent": True},
    {"maximum_cash_spent": -1}, {"safari_complete_paid_session": False},
    {"include_league_funding": True}, {"mode": "continue_selected_goal"},
    {"assisted_training_money": 10000},
])
def test_integrated_scope_rejected_before_private_inputs(tmp_path, monkeypatch, change):
    import run_red_autonomous_collection as module
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(dict({"integrated_play": True, "maximum_cash_spent": 4000,
                                    "safari_complete_paid_session": True,
                                    "include_league_funding": False}, **change)))
    monkeypatch.setattr(sys, "argv", ["run", "--plan", str(plan)])
    with pytest.raises(ValueError, match="integrated play"):
        module.main()


def test_assisted_money_changes_only_three_loaded_bcd_bytes():
    emulator = _TrainingEmulator()
    emulator.memory[0xD350] = 0xAA
    assert _apply_assisted_training_money(emulator, 500) == (198, 500)
    assert emulator.memory == {
        int(RamAddress.PLAYER_MONEY): 0x00,
        int(RamAddress.PLAYER_MONEY) + 1: 0x05,
        int(RamAddress.PLAYER_MONEY) + 2: 0x00,
        0xD350: 0xAA,
    }


@pytest.mark.parametrize("amount", [-1, True, 1_000_000])
def test_assisted_money_rejects_invalid_amount_without_writes(amount):
    emulator = _TrainingEmulator()
    before = dict(emulator.memory)
    with pytest.raises(ValueError, match="six-digit BCD"):
        _apply_assisted_training_money(emulator, amount)
    assert emulator.memory == before


def test_assisted_money_rejects_live_or_invalid_origin_without_writes():
    for emulator in (_TrainingEmulator((0xFA, 0, 0)), _TrainingEmulator()):
        if emulator.memory[int(RamAddress.PLAYER_MONEY)] != 0xFA:
            emulator.frame_count = 1
        before = dict(emulator.memory)
        with pytest.raises(ValueError):
            _apply_assisted_training_money(emulator, 500)
        assert emulator.memory == before


def test_ordinary_goal_fit_rejects_assisted_state_and_provenance():
    _require_unassisted_goal_fit({}, {})
    with pytest.raises(ValueError, match="assisted training"):
        _require_unassisted_goal_fit({"assisted_training_money": 500}, {})
    with pytest.raises(ValueError, match="assisted training"):
        _require_unassisted_goal_fit({}, {"training_assistance": {"kind": "money_override"}})
    for plan, provenance in (({"integrated_play": True}, {}), ({}, {"integrated_play": True})):
        with pytest.raises(ValueError, match="integrated DEVELOPMENT"):
            _require_unassisted_goal_fit(plan, provenance)


def _fixture():
    origin, terminal = "a" * 64, "b" * 64
    plan = {
        "reserve_origin": {"sha256": origin},
        "state": {"sha256": terminal},
    }
    parent = {
        "schema": "pokemon.red.autonomous-option-run.v1",
        "provenance": {"parent_state_sha256": origin},
    }
    outcome = {
        "before_state_sha256": origin,
        "terminal_state_sha256": terminal,
        "safe_terminal": True,
    }
    return plan, parent, outcome


@pytest.mark.parametrize(
    "change",
    ("reserve", "terminal", "unsafe", "broken_parent", "broken_lineage"),
)
def test_inherited_reserves_require_exact_safe_parent_lineage(change):
    plan, parent, outcome = _fixture()
    if change == "reserve":
        plan["reserve_origin"]["sha256"] = "c" * 64
    elif change == "terminal":
        plan["state"]["sha256"] = "c" * 64
    elif change == "unsafe":
        outcome["safe_terminal"] = False
    elif change == "broken_parent":
        parent["provenance"]["parent_state_sha256"] = "c" * 64
    else:
        parent["provenance"]["reserve_origin_state_sha256"] = "c" * 64
    payloads = {
        "prior_plan": json.dumps(parent).encode(),
        "prior_outcome": json.dumps(outcome).encode(),
    }
    with pytest.raises(ValueError, match="inherited reserves do not match"):
        _verify_reserve_lineage(plan, payloads)


def test_inherited_reserves_accept_parent_and_preserve_multistep_origin():
    plan, parent, outcome = _fixture()
    payloads = {
        "prior_plan": json.dumps(parent).encode(),
        "prior_outcome": json.dumps(outcome).encode(),
    }
    _verify_reserve_lineage(plan, payloads)
    parent["provenance"]["reserve_origin_state_sha256"] = "c" * 64
    plan["reserve_origin"]["sha256"] = "c" * 64
    _verify_reserve_lineage(
        plan,
        {
            **payloads,
            "prior_plan": json.dumps(parent).encode(),
        },
    )


def test_reserve_origin_requires_authenticated_parent_documents():
    plan, _, _ = _fixture()
    with pytest.raises(ValueError, match="authenticated parent evidence"):
        _verify_reserve_lineage(plan, {})


def test_incomplete_field_recovery_is_separate_from_ordinary_resume():
    plan, parent, outcome = _fixture()
    outcome.update(
        safe_terminal=False,
        error_type="ControllerFrameBudgetExhausted",
        after={"battle_state": 0, "input_ready": False},
    )
    payloads = {
        "prior_plan": json.dumps(parent).encode(),
        "prior_outcome": json.dumps(outcome).encode(),
    }
    with pytest.raises(ValueError, match="inherited reserves"):
        _verify_reserve_lineage(plan, payloads)
    _verify_reserve_lineage(plan, payloads, field_settlement=True)
    outcome["after"]["battle_state"] = 1
    payloads["prior_outcome"] = json.dumps(outcome).encode()
    with pytest.raises(ValueError, match="inherited reserves"):
        _verify_reserve_lineage(plan, payloads, field_settlement=True)


def test_failed_settlement_is_only_eligible_for_explicit_neutral_recovery():
    plan, parent, outcome = _fixture()
    parent["schema"] = "pokemon.red.field-settlement.v1"
    outcome.update(
        safe_terminal=False,
        model_queries=0,
        neutral_frames=61,
        preserved_resources=False,
        error={"type": "ValueError"},
    )
    payloads = {
        "prior_plan": json.dumps(parent).encode(),
        "prior_outcome": json.dumps(outcome).encode(),
    }
    with pytest.raises(ValueError, match="inherited reserves"):
        _verify_reserve_lineage(plan, payloads)
    _verify_reserve_lineage(plan, payloads, field_settlement=True)


@pytest.mark.parametrize(
    "change", [None, "verification", "model_queries", "neutral_frames", "preserved_resources"]
)
def test_resume_from_field_settlement_requires_resource_preserving_neutral_receipt(change):
    plan, parent, outcome = _fixture()
    parent["schema"] = "pokemon.red.field-settlement.v1"
    outcome.update(
        verification="field_ready", model_queries=0, neutral_frames=5, preserved_resources=True
    )
    if change:
        outcome[change] = {
            "verification": "succeeded",
            "model_queries": 1,
            "neutral_frames": 65,
            "preserved_resources": False,
        }[change]
    payloads = {
        "prior_plan": json.dumps(parent).encode(),
        "prior_outcome": json.dumps(outcome).encode(),
    }
    if change:
        with pytest.raises(ValueError, match="field settlement"):
            _verify_reserve_lineage(plan, payloads)
    else:
        _verify_reserve_lineage(plan, payloads)


@pytest.mark.parametrize("change", [None, "missing", "gap", "unsafe", "ordinal", "model", "tail"])
def test_later_goal_reserve_inheritance_requires_complete_authenticated_chain(change):
    plan, parent, first = _fixture()
    parent["model_sha256"] = "f" * 64
    first["ordinal"] = 0
    last = {
        **first,
        "ordinal": 1,
        "before_state_sha256": "b" * 64,
        "terminal_state_sha256": "c" * 64,
    }
    plan["state"]["sha256"] = "c" * 64
    result = {
        "schema": "pokemon.red.autonomous-option-result.v1",
        "model_sha256": "f" * 64,
        "outcomes": [first, dict(last)],
    }
    if change == "gap":
        result["outcomes"][0]["terminal_state_sha256"] = "d" * 64
    elif change == "unsafe":
        result["outcomes"][0]["safe_terminal"] = False
    elif change == "ordinal":
        result["outcomes"][0]["ordinal"] = 2
    elif change == "model":
        result["model_sha256"] = "e" * 64
    elif change == "tail":
        result["outcomes"].append(dict(last))
    payloads = {
        "prior_plan": json.dumps(parent).encode(),
        "prior_outcome": json.dumps(last).encode(),
    }
    if change != "missing":
        payloads["prior_result"] = json.dumps(result).encode()
    if change is None:
        _verify_reserve_lineage(plan, payloads)
    else:
        with pytest.raises(ValueError, match="inherited reserves do not match"):
            _verify_reserve_lineage(plan, payloads)


def test_goal_continuation_requires_consumed_model_evolution_and_exact_terminal():
    plan, parent, outcome = _fixture()
    outcome.update(
        {
            "selected_kind": "evolve_species",
            "learning_eligible": True,
            "error_type": "CompositionActionBudgetExhausted",
            "choice": {
                "mode": "model_exploration",
                "menu_sha256": "c" * 64,
                "model_sha256": "f" * 64,
            },
        }
    )
    parent["model_sha256"] = "f" * 64
    started = {
        "selected_kind": "evolve_species",
        "state_sha256": "a" * 64,
        "menu_sha256": "c" * 64,
        "selected_binding_ref": f"old:{'d' * 64}",
    }
    payloads = {
        "prior_plan": json.dumps(parent).encode(),
        "prior_outcome": json.dumps(outcome).encode(),
        "prior_execution_started": json.dumps(started).encode(),
    }
    assert _verify_goal_continuation(plan, payloads) == started["selected_binding_ref"]
    started["menu_sha256"] = "e" * 64
    with pytest.raises(ValueError, match="consumed model goal"):
        _verify_goal_continuation(
            plan,
            {
                **payloads,
                "prior_execution_started": json.dumps(started).encode(),
            },
        )


def test_pending_continuation_can_authenticate_next_chunk_without_new_model_choice():
    plan, parent, outcome = _fixture()
    original_ref = f"first-origin:{'d' * 64}"
    rebound_ref = f"second-origin:{'d' * 64}"
    parent.update(
        {
            "schema": "pokemon.red.autonomous-goal-continuation.v1",
            "prior_binding_ref": original_ref,
        }
    )
    outcome.update({"model_queries": 0, "learning_eligible": False})
    started = {
        "selected_kind": "evolve_species",
        "state_sha256": "a" * 64,
        "selected_binding_ref": rebound_ref,
        "prior_binding_ref": original_ref,
    }
    result = {"status": "pending", "model_queries": 0, "outcome": outcome}
    payloads = {
        "prior_plan": json.dumps(parent).encode(),
        "prior_outcome": json.dumps(outcome).encode(),
        "prior_execution_started": json.dumps(started).encode(),
        "prior_result": json.dumps(result).encode(),
    }
    assert _verify_goal_continuation(plan, payloads) == rebound_ref
    result["status"] = "stopped"
    with pytest.raises(ValueError, match="consumed model goal"):
        _verify_goal_continuation(
            plan,
            {
                **payloads,
                "prior_result": json.dumps(result).encode(),
            },
        )
