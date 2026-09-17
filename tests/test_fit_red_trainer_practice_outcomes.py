from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from pokemon_red_completion.battle_scenario_capture import BattleScenarioCaptureManifest
from pokemon_red_completion.scenario_lab import ScenarioPartition
from scripts.fit_red_trainer_practice_outcomes import (
    _root_source_from_parent,
    _validate_exploratory_supply,
    _validate_root_source_provenance,
)


def _receipt(root: str, source: str) -> dict[str, object]:
    return {"root_lineage_id": root, "source_state_sha256": source}


def test_fit_corpus_requires_consistent_distinct_upstream_states() -> None:
    first = _receipt("root-a", "a" * 64)
    second = _receipt("root-b", "b" * 64)
    _validate_root_source_provenance([first, deepcopy(first), second])
    with pytest.raises(ValueError, match="relabeled"):
        _validate_root_source_provenance([first, _receipt("root-b", "a" * 64)])
    with pytest.raises(ValueError, match="multiple upstream"):
        _validate_root_source_provenance([first, _receipt("root-a", "b" * 64)])
    with pytest.raises(ValueError, match="missing"):
        _validate_root_source_provenance([first, _receipt("root-b", "not-a-hash")])


def test_fit_rejects_unresolved_celadon_slot_aliases_as_independent_roots() -> None:
    with pytest.raises(ValueError, match="unresolved shared Celadon ancestry"):
        _validate_root_source_provenance([
            _receipt("red-lab-rival-train-20260917-offset137", "a" * 64),
            _receipt("red-goal-v1-001-advance_story-train-01", "b" * 64),
        ])


def test_derived_prompt_or_forced_capture_rejoins_authenticated_upstream_source() -> None:
    parent = BattleScenarioCaptureManifest(
        capture_id="assisted-parent",
        root_lineage_id="one-root",
        partition=ScenarioPartition.TRAIN,
        state_sha256="a" * 64,
        source_state_sha256="b" * 64,
        initial_observation_sha256="c" * 64,
        source_commit="d" * 40,
        expected_map=40,
        expected_battle_state=2,
    )
    child = BattleScenarioCaptureManifest(
        capture_id="forced-child",
        root_lineage_id="one-root",
        partition=ScenarioPartition.TRAIN,
        state_sha256="e" * 64,
        source_state_sha256="a" * 64,
        initial_observation_sha256="f" * 64,
        source_commit="d" * 40,
        expected_map=40,
        expected_battle_state=2,
    )
    assert _root_source_from_parent(child, parent) == "b" * 64
    assert _root_source_from_parent(parent, None) == "b" * 64
    with pytest.raises(ValueError, match="parent chain differs"):
        _root_source_from_parent(child, replace(parent, root_lineage_id="other-root"))
    with pytest.raises(ValueError, match="unresolved shared Celadon ancestry"):
        _validate_root_source_provenance([
            _receipt("red-goal-v1-002-advance_story-train-02", "a" * 64),
            _receipt("red-goal-v1-003-advance_story-train-03", "b" * 64),
        ])


def test_exploratory_fit_discloses_one_root_and_requires_four_or_eight_varied_scenarios() -> None:
    receipts = [
        {"root_lineage_id": "one-root", "capture_id": f"capture-{index}"}
        for index in range(4)
    ]
    targets = [
        {
            "observation": {
                "features": {
                    "party": {"lead": {"species_ref": f"actor-{index % 3}"}},
                    "battle": {"opponent_species_ref": f"opponent-{index % 3}"},
                }
            }
        }
        for index in range(4)
    ]
    _validate_exploratory_supply(targets, receipts)
    with pytest.raises(ValueError, match="exactly four"):
        _validate_exploratory_supply(targets[:3], receipts[:3])
    duplicated = deepcopy(receipts)
    duplicated[3]["capture_id"] = "capture-0"
    with pytest.raises(ValueError, match="distinct captures"):
        _validate_exploratory_supply(targets, duplicated)
    mixed = deepcopy(receipts)
    mixed[3]["root_lineage_id"] = "another-root"
    with pytest.raises(ValueError, match="one disclosed"):
        _validate_exploratory_supply(targets, mixed)
    repeated = deepcopy(targets)
    repeated[2]["observation"] = repeated[0]["observation"]
    repeated[3]["observation"] = repeated[1]["observation"]
    with pytest.raises(ValueError, match="3 prospective matchup"):
        _validate_exploratory_supply(repeated, receipts)
    extension_receipts = receipts + [
        {"root_lineage_id": "one-root", "capture_id": f"capture-{index}"}
        for index in range(4, 8)
    ]
    extension_targets = targets + [
        {
            "observation": {
                "features": {
                    "party": {"lead": {"species_ref": f"actor-{index}"}},
                    "battle": {"opponent_species_ref": f"opponent-{index}"},
                }
            }
        }
        for index in range(4, 8)
    ]
    _validate_exploratory_supply(extension_targets, extension_receipts)
    with pytest.raises(ValueError, match="6 prospective matchup"):
        _validate_exploratory_supply(targets * 2, extension_receipts)
    with pytest.raises(ValueError, match="exactly four or eight"):
        _validate_exploratory_supply(extension_targets[:7], extension_receipts[:7])
