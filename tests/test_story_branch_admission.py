"""Story-branch admission audit: exact replay admits, any tampering rejects."""

import copy

from pokemon_red_completion.red_story_branch_admission import audit_story_branch_case
from pokemon_red_completion.red_story_branch_value import StoryBranchTracker, story_branch_selection

H = "a" * 64


def _candidate(eff=0.01, risk=0.15):
    return dict(features=dict(feature_names=["execution_effort", "party_risk"], values=[eff, risk]),
                challenge=None, story_unit=dict(mode="movement", requires_further_selected_unit=True))


def _case(segment_lengths=None):
    tracker = StoryBranchTracker()
    indices, refs = (1, 2), ("obj-a", "obj-b")
    sel = story_branch_selection(indices=indices, objective_of=dict(zip(indices, refs)), parent_index=1,
                                 branch_scores=(None, None), candidate_count=3, exploration_probability=0.5, seed=7,
                                 segment_lengths=segment_lengths)
    hist = tuple(tracker.history(r).vector() for r in refs)
    features = [[0.0, 0.0, 0.0, 0.0, *hist[k], 0.01, 0.15, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0] for k in range(2)]
    private = dict(story_indices=list(indices), objective_refs=list(refs), parent_selected_candidate_index=1,
                   selected_candidate_index=sel["selected"], probabilities=list(sel["probabilities"]), explored=sel["explored"],
                   exploration_probability=0.5, seed=7, head_sha256=None, tracker=tracker.document(), tracker_sha256=tracker.sha256,
                   features=features, **({"segment": sel["segment"].document()} if sel["segment"] else {}))
    contexts = [dict(objective_ref=None), dict(objective_ref="obj-a"), dict(objective_ref="obj-b")]
    intent = dict(menu=dict(menu=dict(candidates=[_candidate(), _candidate(), _candidate()])), private_story_contexts=contexts)
    outs = [dict(ordinal=0, selected_kind="advance_story", error_type=None, verification="succeeded", before_state_sha256="b" * 64,
                 terminal_state_sha256=H, observed_cost=dict(actions=10, frames=600, cash_spent=0),
                 before=dict(completed_objectives=[]), after=dict(completed_objectives=[])),
            dict(ordinal=1, selected_kind="restore_team", error_type=None, verification="succeeded", before_state_sha256=H,
                 terminal_state_sha256="c" * 64, observed_cost=dict(actions=5, frames=60, cash_spent=0),
                 before=dict(completed_objectives=[]), after=dict(completed_objectives=[]))]
    steps = {0: dict(intent=intent, decision=dict(selected_candidate_index=sel["selected"]), private=private, terminal_sha256=H),
             1: dict(intent=dict(private_story_contexts=[]), decision=dict(selected_candidate_index=0), private=None, terminal_sha256="c" * 64)}
    return outs, steps


def test_exact_replay_is_admitted_with_and_without_segments():
    for lengths in (None, (3, 9)):
        outs, steps = _case(lengths)
        a = audit_story_branch_case(outs, steps, segment_lengths=lengths)
        assert a["case_chain_ok"] and a["decisions"][0]["ok"], a


def test_tampered_receipts_and_chains_are_rejected():
    outs, steps = _case()
    s = copy.deepcopy(steps); s[0]["private"]["probabilities"][1] += 0.01
    assert not audit_story_branch_case(outs, s)["decisions"][0]["ok"]
    s = copy.deepcopy(steps); s[0]["private"]["features"][0][4] = 0.5
    assert not audit_story_branch_case(outs, s)["decisions"][0]["ok"]
    s = copy.deepcopy(steps); s[0]["private"]["features"][1][12] = 0.9
    assert not audit_story_branch_case(outs, s)["decisions"][0]["ok"]
    s = copy.deepcopy(steps); s[0]["private"]["tracker"]["unattributed_story_choices"] = 1
    assert not audit_story_branch_case(outs, s)["decisions"][0]["ok"]
    s = copy.deepcopy(steps); s[0]["private"]["head_sha256"] = "d" * 64
    assert not audit_story_branch_case(outs, s)["decisions"][0]["ok"]
    o = copy.deepcopy(outs); o[1]["before_state_sha256"] = "e" * 64
    a = audit_story_branch_case(o, steps)
    assert not a["case_chain_ok"] and not a["decisions"][0]["ok"]
    s = copy.deepcopy(steps); s[0]["terminal_sha256"] = "f" * 64
    assert not audit_story_branch_case(outs, s)["case_chain_ok"]


def test_undeclared_segment_lengths_do_not_replay_a_segmented_receipt():
    outs, steps = _case((3, 9))
    assert audit_story_branch_case(outs, steps, segment_lengths=(3, 9))["decisions"][0]["ok"]
    assert audit_story_branch_case(outs, steps, segment_lengths=(4, 9))["decisions"][0]["ok"] is False
