"""A native boundary can re-anchor its party guard without changing the game."""

from copy import deepcopy

import pytest
from test_red_sequence_receipts import build_run, project, read, write

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind


@pytest.fixture
def episode(tmp_path, monkeypatch):
    build_run(tmp_path, monkeypatch, None, GoalKind.ADVANCE_STORY, GoalFailureReason.RESOURCE_LOST)
    return tmp_path / "run"


def certificate(digest):
    return dict(
        schema="pokemon.red.retained-party-continuation.v1",
        guard_sha256=digest,
        native_identity_verified=True,
        individuals={
            "retained": dict(species_ref="pokemon:national:008", level=36, experience=40000)
        },
        other_specimen_counts={},
    )


def reanchor(episode, fault=None):
    result = read(episode / "result.json")
    for i, row in enumerate(result["outcomes"]):
        evidence = certificate(("a" if i < 2 else "b") * 64)
        if i == 2:
            if fault == "identity":
                evidence["individuals"]["different"] = evidence["individuals"].pop("retained")
            elif fault == "level":
                evidence["individuals"]["retained"]["level"] += 1
            elif fault == "xp":
                evidence["individuals"]["retained"]["experience"] += 1
            elif fault == "stock":
                evidence["other_specimen_counts"]["pokemon:national:019"] = 1
            elif fault == "unverified":
                evidence["native_identity_verified"] = False
            elif fault == "schema":
                evidence["schema"] = "unknown"
            elif fault == "hash":
                evidence["guard_sha256"] = "invalid"
            elif fault == "new_field":
                evidence["another_certificate"] = True
        row["before"]["retained_party_continuation"] = deepcopy(evidence)
        row["after"]["retained_party_continuation"] = deepcopy(evidence)
        folder = episode / f"step-{i:03d}"
        before = read(folder / "before.json")
        before["facts"] = row["before"]
        write(folder / "before.json", before)
        write(folder / "outcome.json", row)
    write(episode / "result.json", result)


def test_readonly_guard_reanchor_preserves_exact_costs_and_closed_setback(episode):
    baseline = project(episode)
    reanchor(episode)
    original = {p: p.read_bytes() for p in episode.rglob("*") if p.is_file()}
    result = project(episode)
    assert result.choices == baseline.choices
    assert result.support_steps == baseline.support_steps
    assert not result.training_eligible and not result.executor_ownership_verified
    assert original == {p: p.read_bytes() for p in episode.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "fault", ["identity", "level", "xp", "stock", "unverified", "schema", "hash", "new_field"]
)
def test_reanchor_cannot_hide_changed_native_stock_or_unknown_certificate(episode, fault):
    reanchor(episode, fault)
    with pytest.raises(ValueError, match="binding or completion differs"):
        project(episode)


def test_collector_preexecution_failure_preserves_completed_outcomes(tmp_path, monkeypatch):
    from test_red_native_player import setup

    from pokemon_red_completion import red_native_player as native
    from pokemon_red_completion.player_sequence_collector import SequenceTraceCollector

    args, executed = setup(tmp_path, monkeypatch)
    args["sequence_horizon"] = 2
    original = SequenceTraceCollector.before_execution

    def fail_after_one(self, **kw):
        if self.outcomes:
            raise ValueError("injected prospective projection failure")
        return original(self, **kw)

    monkeypatch.setattr(SequenceTraceCollector, "before_execution", fail_after_one)
    native.run_native_continuous_player(**args)
    result = read(args["output"] / "episode/result.json")
    assert result["stop_reason"] == "sequence_collection_unavailable"
    assert result["executed_decisions"] == 1 and len(result["outcomes"]) == 1
    assert result["outcomes"][0]["verification"] == "succeeded"
    assert result["admission_failure"]["failure_phase"] == "sequence_collection"
    assert executed == [2]
    collection = read(args["output"] / "episode/sequence/result.json")
    assert collection["projection_error"] is None and collection["windows"] == 1
    window = read(args["output"] / "episode/sequence/window-000.json")
    assert not window["complete_window"] and window["measurement"]["end"] == "interrupted"


def test_prospective_twelve_choice_budget_does_not_hit_legacy_ten_receipt_cap(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    from test_red_native_player import setup

    from pokemon_red_completion import red_native_player as native

    args, executed = setup(tmp_path, monkeypatch)
    args["sequence_horizon"] = 4
    args["limits"] = replace(args["limits"], decisions=12, actions=12, frames=100)
    native.run_native_continuous_player(**args)
    result = read(args["output"] / "episode/result.json")
    assert result["stop_reason"] == "decision_budget" and result["executed_decisions"] == 12
    assert len(executed) == 12
    collection = read(args["output"] / "episode/sequence/result.json")
    assert collection["projection_error"] is None and collection["windows"] == 3

    # Final readers must accept the same prospectively declared budget as the
    # live prefix reader. Native input/selector audits depend on this projection.
    from pokemon_red_completion.red_sequence_receipts import read_sequence_receipts
    from pokemon_red_completion.provenance import canonical_sha256
    root = args["output"] / "episode"
    projection = read_sequence_receipts(
        root, expected_plan_sha256=canonical_sha256(read(root / "plan.json")),
        expected_result_sha256=canonical_sha256(result),
        source_sha256=args["source"]["state_sha256"],
    )
    assert len(projection.choices) == 12 and not projection.training_eligible


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "unknown_ref",
        "changed_xp",
        "wrong_species",
        "missing_old",
        "invented_stock",
        "not_all_party",
    ],
)
def test_newly_covered_party_member_requires_exact_unchanged_native_census(episode, fault):
    result = read(episode / "result.json")
    party = [
        dict(specimen_ref="retained", species_id=179, level=36, experience=40000),
        dict(specimen_ref="new-catch", species_id=112, level=3, experience=27),
    ]
    for i, row in enumerate(result["outcomes"]):
        evidence = certificate(("a" if i < 2 else "b") * 64)
        evidence["other_specimen_counts"] = {"pokemon:national:013": 1}
        if i == 2:
            evidence["individuals"]["new-catch"] = dict(
                species_ref="pokemon:national:013", level=3, experience=27
            )
            evidence["other_specimen_counts"] = {}
            if fault == "unknown_ref":
                evidence["individuals"]["invented"] = evidence["individuals"].pop("new-catch")
            elif fault == "changed_xp":
                evidence["individuals"]["new-catch"]["experience"] = 28
            elif fault == "wrong_species":
                evidence["individuals"]["new-catch"]["species_ref"] = "pokemon:national:014"
            elif fault == "missing_old":
                evidence["individuals"].pop("retained")
                evidence["other_specimen_counts"]["pokemon:national:008"] = 1
            elif fault == "invented_stock":
                evidence["other_specimen_counts"]["pokemon:national:019"] = 1
            elif fault == "not_all_party":
                evidence["individuals"].pop("new-catch")
                evidence["other_specimen_counts"]["pokemon:national:013"] = 1
                evidence["individuals"]["other"] = dict(
                    species_ref="pokemon:national:019", level=3, experience=27
                )
        for when in ("before", "after"):
            row[when]["retained_party_continuation"] = deepcopy(evidence)
            row[when]["player_lesson"] = dict(party=deepcopy(party))
            row[when]["specimen_counts"] = {"pokemon:national:008": 1, "pokemon:national:013": 1}
        folder = episode / f"step-{i:03d}"
        before = read(folder / "before.json")
        before["facts"] = row["before"]
        write(folder / "before.json", before)
        write(folder / "outcome.json", row)
    write(episode / "result.json", result)
    if fault:
        with pytest.raises(ValueError, match="binding or completion differs"):
            project(episode)
    else:
        projected = project(episode)
        assert len(projected.choices) == 2 and not projected.training_eligible


@pytest.mark.parametrize("prior", ["absent", "null"])
def test_new_guard_certificate_requires_exact_party_and_complete_stock(prior):
    from pokemon_red_completion.red_sequence_receipts import _same_boundary_facts
    old = dict(player_lesson=dict(party=[dict(specimen_ref="retained", species_id=179, level=36, experience=40000)]), specimen_counts={"pokemon:national:008": 1, "pokemon:national:019": 2}, cash=123, actions=7, frames=84)
    if prior == "null":
        old["retained_party_continuation"] = None
    new = deepcopy(old)
    new["retained_party_continuation"] = certificate("b" * 64)
    new["retained_party_continuation"]["other_specimen_counts"] = {"pokemon:national:019": 2}
    assert _same_boundary_facts(old, new)
    assert not _same_boundary_facts(new, old)


@pytest.mark.parametrize("fault", ["stock", "xp", "unknown_ref", "unverified", "cash", "duplicate", "incomplete_party", "bad_hash"])
def test_new_guard_installation_cannot_hide_changed_world_or_invent_protection(fault):
    from pokemon_red_completion.red_sequence_receipts import _same_boundary_facts
    old = dict(player_lesson=dict(party=[dict(specimen_ref="retained", species_id=179, level=36, experience=40000)]), specimen_counts={"pokemon:national:008": 1}, cash=123)
    new = deepcopy(old)
    evidence = certificate("b" * 64)
    new["retained_party_continuation"] = evidence
    if fault == "stock":
        evidence["other_specimen_counts"]["pokemon:national:019"] = 1
    elif fault == "xp":
        evidence["individuals"]["retained"]["experience"] += 1
    elif fault == "unknown_ref":
        evidence["individuals"]["invented"] = evidence["individuals"].pop("retained")
    elif fault == "unverified":
        evidence["native_identity_verified"] = False
    elif fault == "cash":
        new["cash"] += 1
    elif fault == "duplicate":
        old["player_lesson"]["party"] *= 2
        new["player_lesson"]["party"] *= 2
    elif fault == "incomplete_party":
        for facts in (old, new):
            facts["player_lesson"]["party"].append(dict(specimen_ref="other", species_id=165, level=3, experience=27))
            facts["specimen_counts"]["pokemon:national:019"] = 1
        evidence["other_specimen_counts"]["pokemon:national:019"] = 1
    elif fault == "bad_hash":
        evidence["guard_sha256"] = "invalid"
    assert not _same_boundary_facts(old, new)
