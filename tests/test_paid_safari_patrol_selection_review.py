"""Isolated ROM-free review tests for the paid Safari two-candidate selector.

Only synthetic immutable patrol/terrain fixtures are used. No ROM, state file,
emulator, fitting, runtime teacher or product source mutation is involved.
Root owns integration and execution of this file; this reviewer only AST-parsed it.
"""
from dataclasses import asdict, replace
from pathlib import Path
import builtins
import json
import os
import subprocess

import pytest

from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_paid_safari_patrol import choose_paid_safari_patrol
from pokemon_red_completion.red_safari_acquisition import RedSafariPatrolPlan


def _fixture():
    """Legacy spends alternate steps off grass; nearest two-grass costs one more."""
    shape = tuple(tuple(True for _ in range(4)) for _ in range(3))
    grass = tuple(tuple((y, x) in {(2, 1), (2, 2)} for x in range(4)) for y in range(3))
    terrain = Terrain(
        int(MapId.SAFARI_ZONE_WEST), 0, shape, grass,
        tuple(tuple(False for _ in range(4)) for _ in range(3)),
        tuple(tuple(0 for _ in range(4)) for _ in range(3)),
    )
    legacy = RedSafariPatrolPlan(
        "wild:SafariZoneWest:grass", int(MapId.SAFARI_ZONE_WEST), (0, 0),
        ("down", "down"), (2, 0), (2, 1), 1, "right", "left",
    )
    two_grass = RedSafariPatrolPlan(
        legacy.source_id, legacy.map_id, legacy.start_at,
        ("down", "down", "right"), (2, 1), (2, 2), 2, "right", "left",
    )
    return legacy, two_grass, terrain


def _quote(legacy, two_grass, first=(5, 6), second=(6, 7)):
    def quote(patrol):
        if patrol is legacy:
            return first
        assert patrol is two_grass, "selector invented a third patrol"
        return second
    return quote


def _choose(legacy, two_grass, terrain, remaining, quote):
    selected, evidence = choose_paid_safari_patrol(
        legacy, two_grass, terrain=terrain, steps_after_admission=remaining,
        quote_exit_steps=quote,
    )
    assert isinstance(evidence, dict)
    # Evidence must be persistable before input; no controller/plan object leaks.
    json.dumps(evidence, allow_nan=False)
    return selected, evidence


def test_strict_grass_landing_dominance_keeps_full_approach_and_exit_cost():
    legacy, alternative, terrain = _fixture()
    # Remaining40: legacy40-2-6-18=14 walks/7 grass destinations;
    # alternative40-3-7-18=12 walks/12 grass destinations.
    selected, _ = _choose(legacy, alternative, terrain, 40, _quote(legacy, alternative))
    assert selected is alternative


def test_tie_keeps_exact_legacy_object():
    legacy, alternative, terrain = _fixture()
    # Remaining31: legacy5 walks/3 grass; alternative3 walks/3 grass.
    selected, _ = _choose(legacy, alternative, terrain, 31, _quote(legacy, alternative))
    assert selected is legacy


def test_one_strict_additional_grass_landing_is_enough():
    legacy, alternative, terrain = _fixture()
    # Remaining32: legacy6 walks/3 grass; alternative4 walks/4 grass.
    selected, _ = _choose(legacy, alternative, terrain, 32, _quote(legacy, alternative))
    assert selected is alternative


@pytest.mark.parametrize("remaining", [0, 1, 18, 25, 26, 27, 28, 29, 30])
def test_zero_or_short_budget_never_prefers_expensive_all_grass(remaining):
    legacy, alternative, terrain = _fixture()
    selected, _ = _choose(
        legacy, alternative, terrain, remaining, _quote(legacy, alternative))
    assert selected is legacy


def test_longer_second_endpoint_exit_cannot_be_ignored():
    legacy, alternative, terrain = _fixture()
    # Pricing only its first endpoint would choose the alternative incorrectly.
    quote = _quote(legacy, alternative, first=(5, 6), second=(1, 30))
    selected, _ = _choose(legacy, alternative, terrain, 40, quote)
    assert selected is legacy


def test_farther_all_grass_approach_cannot_consume_search_horizon():
    legacy, alternative, terrain = _fixture()
    # A reversible detour retains the same start/arrival but costs20 extra walks.
    far = replace(alternative, approach_directions=("right", "left") * 10
                  + alternative.approach_directions)
    selected, _ = _choose(legacy, far, terrain, 40, _quote(legacy, far))
    assert selected is legacy


def test_odd_budget_counts_second_endpoint_first():
    legacy, alternative, terrain = _fixture()
    # This legacy starts ON grass, then steps OFF grass first. Five walking
    # steps therefore offer2 grass destinations, not3. Alternative gives3.
    reversed_legacy = replace(
        legacy, approach_directions=alternative.approach_directions,
        first_at=(2, 1), second_at=(2, 0),
        forward_direction="left", backward_direction="right",
    )
    quote = _quote(reversed_legacy, alternative, first=(5, 6), second=(7, 8))
    selected, _ = _choose(reversed_legacy, alternative, terrain, 32, quote)
    assert selected is alternative


def test_no_second_candidate_retains_legacy():
    legacy, _, terrain = _fixture()
    selected, _ = _choose(legacy, None, terrain, 40, lambda _: (5, 6))
    assert selected is legacy


@pytest.mark.parametrize("unknown_for", ["legacy", "alternative", "both"])
def test_unknown_route_cost_cannot_justify_change(unknown_for):
    legacy, alternative, terrain = _fixture()
    def quote(patrol):
        if unknown_for == "both":
            return None
        if patrol is legacy:
            return None if unknown_for == "legacy" else (5, 6)
        assert patrol is alternative
        return None if unknown_for == "alternative" else (6, 7)
    selected, _ = _choose(legacy, alternative, terrain, 40, quote)
    assert selected is legacy


def test_legally_denied_capability_is_not_fabricated_by_selector():
    legacy, alternative, terrain = _fixture()
    observed_capabilities = frozenset()  # Healthy Surf holder without Soul.
    observed_before = observed_capabilities
    calls = []
    def quote(patrol):
        calls.append(patrol)
        if patrol is legacy:
            return (5, 6)  # Existing lawful walking exit.
        assert patrol is alternative
        # Caller refuses an exit that needs a capability absent from live proof.
        return (1, 1) if "move:surf" in observed_capabilities else None
    selected, _ = _choose(legacy, alternative, terrain, 40, quote)
    assert selected is legacy
    assert observed_capabilities is observed_before
    assert all(p is legacy or p is alternative for p in calls)


@pytest.mark.parametrize("bad_quote", [
    (6.0, 7), (6, 7.0), (True, 7), (6, False), (-1, 7), (6, -1),
    (), (6,), (6, 7, 8), "6,7", {"first": 6, "second": 7},
])
@pytest.mark.parametrize("bad_for", ["legacy", "alternative"])
def test_malformed_quote_is_unknown_not_optimistic(bad_quote, bad_for):
    legacy, alternative, terrain = _fixture()
    def quote(patrol):
        if (patrol is legacy) == (bad_for == "legacy"):
            return bad_quote
        return (5, 6) if patrol is legacy else (6, 7)
    selected, _ = _choose(legacy, alternative, terrain, 40, quote)
    assert selected is legacy


@pytest.mark.parametrize("raise_for", ["legacy", "alternative"])
@pytest.mark.parametrize("error", [ValueError, RuntimeError, OSError])
def test_quote_exception_falls_back_without_an_execution_attempt(raise_for, error):
    legacy, alternative, terrain = _fixture()
    def quote(patrol):
        if (patrol is legacy) == (raise_for == "legacy"):
            raise error("unavailable lawful return")
        return (5, 6) if patrol is legacy else (6, 7)
    selected, _ = _choose(legacy, alternative, terrain, 40, quote)
    assert selected is legacy


@pytest.mark.parametrize("remaining", [True, False, -1, 40.0, None, "40"])
def test_budget_requires_nonnegative_plain_integer(remaining):
    legacy, alternative, terrain = _fixture()
    with pytest.raises((TypeError, ValueError)):
        _choose(legacy, alternative, terrain, remaining, _quote(legacy, alternative))


def test_quote_cannot_smuggle_non_grass_alternative_into_choice():
    legacy, alternative, terrain = _fixture()
    # The dataclass says2, but actual observed terrain makes one endpoint bare.
    grass = tuple(tuple((y, x) == (2, 1) for x in range(4)) for y in range(3))
    changed = replace(terrain, grass=grass)
    try:
        selected, _ = _choose(
            legacy, alternative, changed, 40, _quote(legacy, alternative))
    except (TypeError, ValueError):
        return  # An explicit invalid-input rejection is also fail-closed.
    assert selected is legacy


def test_selector_is_read_only_and_uses_only_two_supplied_candidates(monkeypatch):
    legacy, alternative, terrain = _fixture()
    before = (asdict(legacy), asdict(alternative), asdict(terrain))
    calls = []
    def quote(patrol):
        calls.append(patrol)
        assert patrol is legacy or patrol is alternative
        return (5, 6) if patrol is legacy else (6, 7)
    def forbidden(*args, **kwargs):
        raise AssertionError("pure selector attempted external IO or process execution")
    # All fixtures and imports already exist; selection has no file/native port.
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(os, "system", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(subprocess, "run", forbidden)
        selected, evidence = _choose(legacy, alternative, terrain, 40, quote)
    assert selected is alternative
    assert calls == [legacy, alternative]
    assert (asdict(legacy), asdict(alternative), asdict(terrain)) == before
    assert isinstance(evidence, dict)
