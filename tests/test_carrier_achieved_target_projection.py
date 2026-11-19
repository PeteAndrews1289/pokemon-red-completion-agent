"""Achieved targets are archived, never rebased into higher training targets."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json

import pytest
import run_configured_red_player as driver
import test_carrier_abort_driver_handoff as prior
from pokemon_red_completion.provenance import canonical_sha256


def target_case(monkeypatch,tmp_path,level):
    original_case=prior.case
    original_configured=prior.configured_pending
    def setup(*args,**kwargs):
        c=original_case(*args,**kwargs)
        primary=c.refs[0]
        c.mons[primary].level=5;c.mons[primary].xp=125
        c.guard=replace(c.guard,before=c.guard.reader.read())
        c.runtime.adapter.party_guard=c.guard
        roster=tuple(replace(m,observation=replace(m.observation,level=5,experience=125))if m.specimen_ref==primary else m for m in c.plan.roster)
        c.plan=replace(c.plan,roster=roster,opposition_level=14,observed_opponents=1,targets=((primary,6),))
        return c
    monkeypatch.setattr(prior,'case',setup)
    def configured(*args,**kwargs):
        x=original_configured(*args,**kwargs)
        primary=x.c.refs[0];x.c.mons[primary].level=level;x.c.mons[primary].xp=max(125,level**3)
        return x
    monkeypatch.setattr(prior,'configured_pending',configured)
    return prior.handoff_case(monkeypatch,tmp_path)


@pytest.mark.parametrize('level,remaining,achieved',[(5,True,0),(6,False,1),(54,False,1)])
def test_archived_target6_with_current_native54_reconciles_only_if_achieved(monkeypatch,tmp_path,level,remaining,achieved):
    h=target_case(monkeypatch,tmp_path,level)
    primary=h.x.c.refs[0];guard=h.x.c.runtime.adapter.party_guard
    archive=guard.field_carrier.preparation_before
    assert dict(archive.targets)=={primary:6}
    assert next(m for m in archive.roster if m.specimen_ref==primary).observation.level==5
    assert (tmp_path/'CONTEXT.json').read_bytes()==h.x.source_bytes
    plan=h.x.holder['plan'];members={m.specimen_ref:m for m in plan.roster}
    assert members[primary].observation.level==level
    assert dict(plan.targets)==({primary:6}if remaining else {})
    assert members[guard.field_carrier.carrier_ref].purpose.value=='field_utility'
    certificate=driver._qualified_zero_input_carrier_abort_handoff(h.result,**h.kwargs)
    assert certificate is not None
    assert certificate['physically_achieved_target_count']==achieved
    assert certificate['archived_targets_preserved']is True
    assert certificate['native_progress']is certificate['quest_progress']is False


@pytest.mark.parametrize('fault',['remove_unmet','retain_achieved','new_higher_target','source_target_erased','archive_rewritten'])
def test_driver_independently_refuses_unproved_target_reconciliation(monkeypatch,tmp_path,fault):
    h=target_case(monkeypatch,tmp_path,5 if fault == 'remove_unmet' else 54)
    primary=h.x.c.refs[0];old=json.loads(h.kwargs['source_context_bytes']);new=deepcopy(h.after_context)
    if fault=='remove_unmet':new['preparation']['targets']=()
    elif fault=='retain_achieved':new['preparation']['targets']=((primary,6),)
    elif fault=='new_higher_target':new['preparation']['targets']=((primary,55),)
    elif fault=='source_target_erased':old['preparation']['targets']=[]
    elif fault=='archive_rewritten':new['field_carrier']['preparation_before']['targets']=[]
    h.kwargs['source_context_bytes']=json.dumps(old,sort_keys=True).encode()
    h.kwargs['expected_source_context_sha256']=sha256(h.kwargs['source_context_bytes']).hexdigest()
    h.kwargs['exported_context_bytes']=json.dumps(new,sort_keys=True).encode()
    h.result['context_sha256']=sha256(h.kwargs['exported_context_bytes']).hexdigest()
    h.row['evidence']['active_preparation_projection_sha256']=canonical_sha256(new['preparation'])
    assert driver._qualified_zero_input_carrier_abort_handoff(h.result,**h.kwargs)is None