"""Authenticated reserve inheritance for autonomous continuation."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_red_autonomous_collection import _verify_reserve_lineage  # noqa: E402


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
