"""Authenticated reserve inheritance for autonomous continuation."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fit_red_autonomous_collection import _require_unassisted_goal_fit  # noqa: E402
from run_red_autonomous_collection import (  # noqa: E402
    _apply_assisted_training_money,
    _verify_goal_continuation,
    _verify_reserve_lineage,
)

from pokemon_red_completion.observation import RamAddress


class _TrainingEmulator:
    def __init__(self, money_bytes=(0x00, 0x01, 0x98)):
        self.frame_count = 0
        self.pressed_buttons = frozenset()
        self.memory = {
            int(RamAddress.PLAYER_MONEY) + index: value
            for index, value in enumerate(money_bytes)
        }

    def read_u8(self, address):
        return self.memory[address]

    def _require_backend(self):
        return self


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
    _verify_reserve_lineage(plan, {
        **payloads,
        "prior_plan": json.dumps(parent).encode(),
    })


def test_reserve_origin_requires_authenticated_parent_documents():
    plan, _, _ = _fixture()
    with pytest.raises(ValueError, match="authenticated parent evidence"):
        _verify_reserve_lineage(plan, {})


def test_goal_continuation_requires_consumed_model_evolution_and_exact_terminal():
    plan, parent, outcome = _fixture()
    outcome.update({
        "selected_kind": "evolve_species", "learning_eligible": True,
        "error_type": "CompositionActionBudgetExhausted",
        "choice": {
            "mode": "model_exploration", "menu_sha256": "c" * 64,
            "model_sha256": "f" * 64,
        },
    })
    parent["model_sha256"] = "f" * 64
    started = {
        "selected_kind": "evolve_species", "state_sha256": "a" * 64,
        "menu_sha256": "c" * 64, "selected_binding_ref": f"old:{'d' * 64}",
    }
    payloads = {
        "prior_plan": json.dumps(parent).encode(),
        "prior_outcome": json.dumps(outcome).encode(),
        "prior_execution_started": json.dumps(started).encode(),
    }
    assert _verify_goal_continuation(plan, payloads) == started["selected_binding_ref"]
    started["menu_sha256"] = "e" * 64
    with pytest.raises(ValueError, match="consumed model goal"):
        _verify_goal_continuation(plan, {
            **payloads, "prior_execution_started": json.dumps(started).encode(),
        })


def test_pending_continuation_can_authenticate_next_chunk_without_new_model_choice():
    plan, parent, outcome = _fixture()
    original_ref = f"first-origin:{'d' * 64}"
    rebound_ref = f"second-origin:{'d' * 64}"
    parent.update({
        "schema": "pokemon.red.autonomous-goal-continuation.v1",
        "prior_binding_ref": original_ref,
    })
    outcome.update({"model_queries": 0, "learning_eligible": False})
    started = {
        "selected_kind": "evolve_species", "state_sha256": "a" * 64,
        "selected_binding_ref": rebound_ref, "prior_binding_ref": original_ref,
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
        _verify_goal_continuation(plan, {
            **payloads, "prior_result": json.dumps(result).encode(),
        })
