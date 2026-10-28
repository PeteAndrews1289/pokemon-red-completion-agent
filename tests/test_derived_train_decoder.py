"""Derived capability decoding only; synthetic proof is never native admission.

The public source proof loader and sealed evidence are separate integration
gates. This test deliberately uses the module-private token to isolate nested
scope codec behavior, and performs no emulation or fitting.
"""
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
from test_production_train_pool import components
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_development_story_scope import DevelopmentStoryScope
from pokemon_red_completion.red_production_train_admission import ProductionTrainAdmission
from pokemon_red_completion.red_production_train_source import VerifiedDerivedTrainSource,_TOKEN
from pokemon_red_completion.red_production_train_readback import read_production_train_pool
from pokemon_red_completion.red_scoped_training_battlers import ScopedTrainingBattlers


def derived(c):
    payload=b"synthetic unit decoder source, never a native checkpoint"
    document=dict(source_state_sha256=sha256(payload).hexdigest(),
        source_origin_sha256=c.admission.source_origin_sha256,
        source_commit=c.admission.source_commit,context_content_sha256=sha256(b"synthetic context").hexdigest())
    with pytest.raises(ValueError):VerifiedDerivedTrainSource(document)
    proof=VerifiedDerivedTrainSource(document,_token=_TOKEN)
    admission=replace(c.admission,source_state_sha256=proof.source_state_sha256,
        envelope_sha256="e"*64,progress_sha256="f"*64,derived_source_proof=proof)
    return admission,payload


def test_derived_story_document_needs_exact_preverified_capability(components):
    c=components;admission,payload=derived(c)
    scope=replace(c.story.development_story_scope,source_state_sha256=admission.source_state_sha256,
        train_admission=admission)
    with pytest.raises(ValueError):DevelopmentStoryScope.from_document(scope.document())
    restored=DevelopmentStoryScope.from_document(scope.document(),train_admission=admission)
    assert restored==scope and restored.identity==scope.identity
    with pytest.raises(ValueError):
        DevelopmentStoryScope.from_document(scope.document(),train_admission=c.admission)
    with pytest.raises(ValueError):ProductionTrainAdmission.from_document(admission.document())


def test_both_derived_actor_scope_documents_roundtrip_through_pool_reader(components):
    c=components;admission,payload=derived(c)
    wild_scope=replace(c.wild.development_preparation_scope,
        source_state_sha256=admission.source_state_sha256,train_admission=admission)
    story_scope=replace(c.story.development_story_scope,
        source_state_sha256=admission.source_state_sha256,train_admission=admission)
    c.delegate.save_state_bytes=lambda:payload
    c.wild=replace(c.wild,source_state_sha256=admission.source_state_sha256,
        development_preparation_scope=wild_scope,qualification_sha256=wild_scope.identity)
    c.story=replace(c.story,source_state_sha256=admission.source_state_sha256,
        development_story_scope=story_scope,qualification_sha256=story_scope.identity)
    source=dict(c.source,state_sha256=admission.source_state_sha256)
    pool=ScopedTrainingBattlers.for_production_source(c.wild,c.story,admission=admission,
        source=source,output=c.tmp/"derived-pool",reader=c.reader)
    checked=read_production_train_pool(pool.output,expected_declaration_sha256=pool.declaration_sha256,
        expected_admission=admission,source=source,expected_story_calls=0)
    assert checked.episodes==() and checked.invocations==()
    assert checked.declaration["production_admission"]["derived_source_proof_sha256"]==admission.derived_source_proof.identity
    assert c.delegate.frame_count==0
