"""Exact earned TRAIN-unit custody. Private fixture bytes; no guest/fit/query."""

import json
import os
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from test_production_train_teacher_prefix import (
    admitted_source as admitted_source,
)
from test_production_train_teacher_prefix import (
    artifacts as artifacts,
)
from test_production_train_teacher_prefix import (
    blaine_scope,
)

from pokemon_red_completion.red_production_train_admission import ProductionTrainAdmission
from pokemon_red_completion.red_production_train_source import (
    SOURCE049_EARNED_UNIT_PINS,
    SOURCE049_GROUP,
    VerifiedEarnedNoncombatTrainSource,
    authenticate_earned_noncombat_train_source,
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture(scope="module")
def unit_artifacts():
    path = os.environ.get("POKEMON_SOURCE049_EARNED_UNIT_ARTIFACT_PATHS")
    if path is None:
        pytest.skip("private immutable earned-unit artifacts not supplied")
    return {k: Path(v).read_bytes() for k, v in json.loads(Path(path).read_bytes()).items()}


@pytest.fixture
def earned(artifacts, unit_artifacts):
    proof = authenticate_earned_noncombat_train_source(
        parent_artifacts=artifacts, unit_artifacts=unit_artifacts, source_commit="a" * 40
    )
    a = ProductionTrainAdmission(
        proof.source_state_sha256,
        proof.source_origin_sha256,
        proof.source_commit,
        "b" * 64,
        sha256(proof.envelope_bytes()).hexdigest(),
        sha256(proof.progress_bytes()).hexdigest(),
        derived_source_proof=proof,
        noncombat_objective_ids=("obtain_strength",),
    )
    plan = encoded(dict(partition="train", production_train_components=a.declaration()))
    a = ProductionTrainAdmission.authenticate(
        source_state=unit_artifacts["state"],
        envelope_bytes=proof.envelope_bytes(),
        progress_bytes=proof.progress_bytes(),
        plan_bytes=plan,
        source_commit=proof.source_commit,
        derived_source_proof=proof,
        context_bytes=unit_artifacts["context"],
        noncombat_objective_ids=("obtain_strength",),
    )
    return a, proof, plan


def test_exact_earned_boundary_retains_native_lineage_without_old_prefix_alias(
    earned, artifacts, unit_artifacts
):
    a, proof, plan = earned
    d = proof.document()
    assert proof.source_state_sha256 == sha256(unit_artifacts["state"]).hexdigest()
    assert proof.source_state_sha256 != sha256(artifacts["prefix_state"]).hexdigest()
    assert a.earned_noncombat and a.source049_family and not a.teacher_prefix
    assert d["source_group_sha256"] == SOURCE049_GROUP
    assert d["cumulative_spent"] == json.loads(unit_artifacts["context"])["spent"]
    assert d["closed_attempt_costs"]["failed"]["physical_loads"] == 1
    assert d["closed_attempt_costs"]["succeeded"]["physical_loads"] == 1
    assert d["costs_are_lower_bounds"] and d["parent_failed_costs_remain_additional"]
    assert (
        d["fit_admission"]
        is d["campaign_eligible"]
        is d["grants_new_budget"]
        is d["continuation_authority"]
        is False
    )
    assert d["independent_origin"] is False
    assert a.objective_id == "defeat_blaine" and a.story_map_id == 166 and a.wild_map_id == 15
    assert a.admitted_story_objective_ids == ("defeat_blaine", "obtain_strength")
    assert a.document()["fit_admission"] is False
    a.require_work_order(plan)
    assert ProductionTrainAdmission.from_document(a.document(), derived_source_proof=proof) == a
    scope, actor = blaine_scope(a)
    a.require_actor(actor, scope, "story")
    scope.contract.objective_id = "defeat_misty"
    with pytest.raises(ValueError):
        a.require_actor(actor, scope, "story")


@pytest.mark.parametrize("name", sorted(SOURCE049_EARNED_UNIT_PINS))
def test_any_changed_unit_artifact_rejected(artifacts, unit_artifacts, name):
    changed = dict(unit_artifacts)
    changed[name] += b" "
    with pytest.raises(ValueError, match="artifact changed"):
        authenticate_earned_noncombat_train_source(
            parent_artifacts=artifacts, unit_artifacts=changed, source_commit="a" * 40
        )


def test_missing_parent_and_direct_constructor_rejected(artifacts, unit_artifacts):
    with pytest.raises(ValueError, match="authenticated"):
        VerifiedEarnedNoncombatTrainSource({})
    changed = dict(artifacts)
    changed.pop("phase_6")
    with pytest.raises(ValueError, match="census"):
        authenticate_earned_noncombat_train_source(
            parent_artifacts=changed, unit_artifacts=unit_artifacts, source_commit="a" * 40
        )
    changed = dict(unit_artifacts)
    changed.pop("failed_closed")
    with pytest.raises(ValueError, match="census"):
        authenticate_earned_noncombat_train_source(
            parent_artifacts=artifacts, unit_artifacts=changed, source_commit="a" * 40
        )


@pytest.mark.parametrize(
    "fault",
    [
        "development",
        "origin",
        "group",
        "independent",
        "costs",
        "envelope",
        "state",
        "context",
        "scope",
        "work_order",
    ],
)
def test_prospective_metadata_context_and_work_order_cannot_be_substituted(
    earned, unit_artifacts, fault
):
    a, proof, plan = earned
    progress = json.loads(proof.progress_bytes())
    envelope = json.loads(proof.envelope_bytes())
    work = json.loads(plan)
    kwargs = dict(
        source_state=unit_artifacts["state"],
        context_bytes=unit_artifacts["context"],
        source_commit=proof.source_commit,
        derived_source_proof=proof,
        noncombat_objective_ids=("obtain_strength",),
    )
    if fault == "development":
        progress["partition"] = "development"
    elif fault == "origin":
        progress["source_origin_sha256"] = "f" * 64
    elif fault == "group":
        progress["source_group_sha256"] = "f" * 64
    elif fault == "independent":
        progress["independent_origin"] = True
    elif fault == "costs":
        progress["failed_unit_costs_retained"] = False
    elif fault == "envelope":
        envelope["state_sha256"] = "f" * 64
    elif fault == "state":
        kwargs["source_state"] += b" "
    elif fault == "context":
        kwargs["context_bytes"] += b" "
    elif fault == "scope":
        kwargs["noncombat_objective_ids"] = ("obtain_surf",)
    else:
        work["partition"] = "development"
    with pytest.raises(ValueError):
        ProductionTrainAdmission.authenticate(
            **kwargs,
            envelope_bytes=encoded(envelope),
            progress_bytes=encoded(progress),
            plan_bytes=encoded(work),
        )


@pytest.mark.parametrize(
    "field",
    [
        "source_state_sha256",
        "source_origin_sha256",
        "source_commit",
        "envelope_sha256",
        "progress_sha256",
    ],
)
def test_direct_typed_admission_still_requires_exact_earned_metadata(earned, field):
    with pytest.raises(ValueError):
        replace(earned[0], **{field: "f" * (40 if field == "source_commit" else 64)})


@pytest.mark.parametrize("scope", [(), ("obtain_surf",), ("obtain_strength", "obtain_surf")])
def test_earned_source_cannot_drop_or_expand_its_noncombat_scope(earned, scope):
    with pytest.raises(ValueError):
        replace(earned[0], noncombat_objective_ids=scope)


def test_original_prefix_document_and_source_checks_remain_unchanged(
    admitted_source, earned, artifacts, unit_artifacts
):
    original, proof, oldplan = admitted_source
    assert original.teacher_prefix and original.source049_family and not original.earned_noncombat
    assert original.declaration() == json.loads(oldplan)["production_train_components"]
    assert (
        ProductionTrainAdmission.from_document(original.document(), derived_source_proof=proof)
        == original
    )
    with pytest.raises(ValueError):
        proof.require_source_context(unit_artifacts["state"], unit_artifacts["context"])
    with pytest.raises(ValueError):
        earned[1].require_source_context(artifacts["prefix_state"], artifacts["prefix_context"])
    with pytest.raises(ValueError):
        earned[0].require_work_order(oldplan)


@pytest.mark.parametrize(
    "artifact,path,value",
    [
        ("closed", ("all_controls_released",), False),
        ("failed_closed", ("prior_costs_retained",), False),
        ("context", ("spent", "actions"), 0),
        ("context", ("lesson", "completed_objectives"), []),
        ("declaration", ("source", "partition"), "development"),
        ("result", ("model_queries",), 1),
        ("pair", ("continuation_authority",), True),
    ],
)
def test_semantic_guards_survive_a_hypothetically_resealed_bad_document(
    artifacts, unit_artifacts, monkeypatch, artifact, path, value
):
    # Test semantic checks separately from the exact fixed-byte boundary.
    from pokemon_red_completion import red_production_train_source as source

    changed = dict(unit_artifacts)
    document = json.loads(changed[artifact])
    node = document
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    changed[artifact] = encoded(document)
    pins = dict(source.SOURCE049_EARNED_UNIT_PINS)
    pins[artifact] = sha256(changed[artifact]).hexdigest()
    monkeypatch.setattr(source, "SOURCE049_EARNED_UNIT_PINS", pins)
    with pytest.raises(ValueError):
        source.authenticate_earned_noncombat_train_source(
            parent_artifacts=artifacts, unit_artifacts=changed, source_commit="a" * 40
        )
