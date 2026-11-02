"""Exact teacher-prefix noncombat permission; no guest, prediction or fitting."""
import ast
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from test_production_train_admission import admitted, scope_and_actor
from test_production_train_teacher_prefix import (
    artifacts, admitted_source, blaine_scope, helper_hook,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_production_train_admission import (
    ADMISSION_NONCOMBAT_SCHEMA, ADMISSION_TEACHER_SCHEMA, ProductionTrainAdmission,
)


@pytest.fixture
def noncombat_source(admitted_source, artifacts):
    old, proof, _ = admitted_source
    requested = replace(old, noncombat_objective_ids=("obtain_strength",))
    plan = json.dumps(dict(partition="train", production_train_components=requested.declaration()),
                      sort_keys=True).encode()
    result = ProductionTrainAdmission.authenticate(
        source_state=artifacts["prefix_state"], envelope_bytes=artifacts["prefix_envelope"],
        progress_bytes=proof.progress_bytes(), plan_bytes=plan, source_commit=proof.source_commit,
        derived_source_proof=proof, context_bytes=artifacts["prefix_context"],
        noncombat_objective_ids=("obtain_strength",),
    )
    return result, proof, plan


def test_explicit_noncombat_scope_roundtrips_without_changing_combat(noncombat_source, admitted_source):
    a, proof, plan = noncombat_source
    old, _, old_plan = admitted_source
    assert a.admission_schema == ADMISSION_NONCOMBAT_SCHEMA
    assert a.admitted_story_objective_ids == ("defeat_blaine", "obtain_strength")
    assert a.objective_id == old.objective_id == "defeat_blaine"
    assert a.story_reward is old.story_reward and a.story_map_id == 166
    assert a.wild_map_id == 15 and a.wild_model_sha256 == old.wild_model_sha256
    assert a.source_state_sha256 == old.source_state_sha256
    assert a.source_origin_sha256 == old.source_origin_sha256
    assert a.work_order_sha256 == sha256(plan).hexdigest() != sha256(old_plan).hexdigest()
    a.require_work_order(plan)
    restored = ProductionTrainAdmission.from_document(a.document(), derived_source_proof=proof)
    assert restored == a and restored.identity == a.identity
    assert a.document()["fit_admission"] is False
    scope, actor = blaine_scope(a)
    a.require_actor(actor, scope, "story")
    scope.contract.objective_id = "obtain_strength"
    with pytest.raises(ValueError):
        a.require_actor(actor, scope, "story")
    with pytest.raises(ValueError):
        a.require_scope(scope, "noncombat")


def test_noncombat_does_not_broaden_wild_map(noncombat_source):
    a, _, _ = noncombat_source
    _, scope, actor = scope_and_actor("wild")
    scope.source_state_sha256 = actor.source_state_sha256 = a.source_state_sha256
    scope.root_lineage_id = actor.root_lineage_id = a.root_lineage_id
    scope.work_order_sha256 = a.work_order_sha256
    a.require_actor(actor, scope, "wild")
    scope.map_id = 22
    with pytest.raises(ValueError):
        a.require_actor(actor, scope, "wild")


@pytest.mark.parametrize("value", [None, "obtain_strength", ["obtain_strength"],
    ("obtain_surf",), ("defeat_blaine",), ("obtain_strength", "obtain_surf"),
    ("obtain_strength", "obtain_strength"), (True,)])
def test_wrong_or_untyped_scope_rejected(admitted_source, value):
    with pytest.raises(ValueError):
        replace(admitted_source[0], noncombat_objective_ids=value)


def test_legacy_source_cannot_claim_noncombat_scope():
    with pytest.raises(ValueError, match="teacher-prefix"):
        replace(admitted(), noncombat_objective_ids=("obtain_strength",))


def test_scope_must_be_committed_in_exact_work_order(admitted_source, noncombat_source, artifacts):
    old, proof, old_plan = admitted_source
    a, _, plan = noncombat_source
    uncommitted = replace(old, noncombat_objective_ids=("obtain_strength",))
    with pytest.raises(ValueError, match="exact TRAIN work order"):
        uncommitted.require_work_order(old_plan)
    kwargs = dict(source_state=artifacts["prefix_state"], envelope_bytes=artifacts["prefix_envelope"],
        progress_bytes=proof.progress_bytes(), source_commit=proof.source_commit,
        derived_source_proof=proof, context_bytes=artifacts["prefix_context"])
    with pytest.raises(ValueError):
        ProductionTrainAdmission.authenticate(**kwargs, plan_bytes=old_plan,
                                               noncombat_objective_ids=("obtain_strength",))
    with pytest.raises(ValueError):
        ProductionTrainAdmission.authenticate(**kwargs, plan_bytes=plan)
    with pytest.raises(ValueError):
        a.require_work_order(old_plan)


@pytest.mark.parametrize("fault", ["state", "context", "origin", "goal", "schema", "field_type"])
def test_noncombat_scope_retains_source_and_document_guards(noncombat_source, artifacts, fault):
    a, proof, plan = noncombat_source
    if fault in ("state", "context"):
        kwargs = dict(source_state=artifacts["prefix_state"], envelope_bytes=artifacts["prefix_envelope"],
            progress_bytes=proof.progress_bytes(), plan_bytes=plan, source_commit=proof.source_commit,
            derived_source_proof=proof, context_bytes=artifacts["prefix_context"],
            noncombat_objective_ids=("obtain_strength",))
        kwargs["source_state" if fault == "state" else "context_bytes"] += b" "
        with pytest.raises(ValueError):
            ProductionTrainAdmission.authenticate(**kwargs)
    else:
        d = a.document()
        if fault == "origin": d["source_origin_sha256"] = "f" * 64
        elif fault == "goal": d["noncombat_objective_ids"] = ["obtain_surf"]
        elif fault == "schema": d["schema"] = ADMISSION_TEACHER_SCHEMA
        else: d["noncombat_objective_ids"] = "obtain_strength"
        with pytest.raises(ValueError):
            ProductionTrainAdmission.from_document(d, derived_source_proof=proof)


def test_opt_out_keeps_exact_legacy_declaration_document_and_identity(admitted_source):
    a, proof, plan = admitted_source
    declared = json.loads(plan)["production_train_components"]
    assert a.declaration() == declared and declared["schema"] == ADMISSION_TEACHER_SCHEMA
    assert "noncombat_objective_ids" not in declared
    original = a.document()
    assert "noncombat_objective_ids" not in original
    opted_out = replace(a, noncombat_objective_ids=())
    assert opted_out.document() == original and opted_out.identity == canonical_sha256(original)
    assert ProductionTrainAdmission.from_document(original, derived_source_proof=proof) == a
    assert a.admitted_story_objective_ids == ("defeat_blaine",)
    with pytest.raises(ValueError):
        ProductionTrainAdmission.from_document(dict(original, noncombat_objective_ids=[]),
                                               derived_source_proof=proof)


def test_actual_helper_filters_only_declared_observers_without_calling_them(noncombat_source, admitted_source):
    path, hook = helper_hook("branches")
    node = next(n for n in hook.body if isinstance(n, ast.If)
                and "admitted_story_objective_ids" in ast.dump(n))
    def forbidden(*args):
        raise AssertionError("observer execution is not admission")
    original = {key: forbidden for key in ("defeat_blaine", "obtain_strength", "obtain_surf", "defeat_giovanni")}
    for a, expected in ((admitted_source[0], {"defeat_blaine"}),
                        (noncombat_source[0], {"defeat_blaine", "obtain_strength"})):
        ns = dict(training_admission=a, observers=dict(original))
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
        assert set(ns["observers"]) == expected
        assert all(callback is forbidden for callback in ns["observers"].values())
    ns = dict(training_admission=noncombat_source[0], observers={"defeat_blaine": forbidden})
    with pytest.raises(KeyError):
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
