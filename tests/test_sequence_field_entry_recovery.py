"""Configured sequence entry preserves compulsory field support in its chain."""
from types import SimpleNamespace as N
import pytest
import run_configured_red_player as configured

@pytest.mark.parametrize("battle,sequence,expected", [(0,True,False),(0,False,True),(2,True,False),(2,False,True)])
def test_sequence_field_and_battle_control_use_the_existing_recorded_support_loop(monkeypatch,battle,sequence,expected):
    monkeypatch.setattr(configured,"requires_compulsory_settlement",lambda _:True)
    plan=dict(partition="development",objectives=["defeat_brock"],seed=31,
        goal_selection=dict(mode="exploration",reason="Retain the declared model."))
    if sequence: plan["sequence_policy"]={"declared_elsewhere":True}
    options=configured.native_player_options(plan,N(reader=N(read=lambda:N(battle_state=battle))),
        ("original",),N(native_callbacks=lambda:{}),refinement={})
    for kind in ("trainer","wild","blackout","motion"):
        assert options[f"settle_existing_{kind}"] is expected
    assert options["greedy_selection"] is False

def test_genuine_native_sequence_entry_retains_support_and_replays(monkeypatch,tmp_path):
    import test_red_native_sequence_policy as fixture
    from pokemon_red_completion.red_sequence_native_audit import audit_native_sequence_trace
    original=fixture.run_native_continuous_player
    monkeypatch.setattr(configured,"requires_compulsory_settlement",lambda _:True)
    def assembled(**args):
        plan=dict(partition="development",objectives=["defeat_brock"],seed=31,
            goal_selection=dict(mode="exploration",reason="Keep local policy."),
            sequence_policy={"declared_elsewhere":True})
        options=configured.native_player_options(plan,N(reader=N(read=lambda:N(battle_state=0))),
            args["combat_specimen_refs"],N(native_callbacks=lambda:{}),refinement={})
        args["source"]={**args["source"],"partition":"development"}
        # Reuse fake-cartridge readiness; forward the changed entry flags.
        flags={k:v for k,v in options.items() if k.startswith("settle_existing_")}
        return original(**{**args,**flags})
    monkeypatch.setattr(fixture,"run_native_continuous_player",assembled)
    args,result,executed,audit_args=fixture.run(tmp_path,monkeypatch,support="control")
    assert executed and result["model_decisions"]==0
    episode=args["output"]/"episode"
    before=fixture.read(episode/"step-000/before.json")
    outcome=fixture.read(episode/"step-000/outcome.json")
    assert before["state_sha256"]==args["source"]["state_sha256"]
    assert outcome["support_role"]=="deterministic_control_recovery"
    assert outcome["before_state_sha256"]==before["state_sha256"]
    audit=audit_native_sequence_trace(args["output"],**audit_args)
    assert audit.support_requiring_authority_audit==len(executed)
