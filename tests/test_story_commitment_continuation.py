"""ROM-free cross-chunk commitment lifecycle and authenticated continuation."""
import json
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
import run_configured_red_player as driver
from test_red_native_player_continuation import fixture
from test_red_player_configuration import config
from test_story_kind_commitment import menu, outcome, _index, _parent

from pokemon_red_completion import red_player_continuation as continuation
from pokemon_red_completion import red_story_kind_commitment as kc
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_configuration import assemble_configured_player
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory


@pytest.mark.parametrize("fault", ["schema", "extra", "missing", "empty", "bool", "exhausted", "negative", "not_dict"])
def test_commitment_document_rejects_invalid_scope_and_counters(fault):
    doc = kc.StoryKindCommitment("rescue_fuji", 1, 7).document()
    if fault == "schema": doc["schema"] = "other"
    if fault == "extra": doc["force"] = True
    if fault == "missing": del doc["overrides"]
    if fault == "empty": doc["objective_ref"] = ""
    if fault == "bool": doc["consecutive_failures"] = True
    if fault == "exhausted": doc["consecutive_failures"] = 2
    if fault == "negative": doc["overrides"] = -1
    if fault == "not_dict": doc = []
    with pytest.raises(ValueError): kc.StoryKindCommitment.from_document(doc)


def assemble(parent, output):
    inventory = NativeStoryBranchInventory(lambda *_: GoalBindingSet((), ()), lambda *_: ())
    backend = N(assembly=lambda *a, **k: (b"terminal", None, inventory, {}, {"partition": "development"}))
    return assemble_configured_player(backend, config(), parent, output, plan_path=output / "PLAN.json")[3]


def test_chunk_export_rebuild_keeps_real_lifecycle_and_independent_carrier(tmp_path, monkeypatch):
    runtime, plan, battle, original, *_ = fixture(monkeypatch)
    options = menu()
    fuji = options.binding(_index(options, "s-fuji"))
    carrier = kc.StoryKindCommitmentCarrier()
    carrier.current = kc.commitment_after_outcome(None, fuji, outcome())
    carrier.current = kc.commitment_after_choice(carrier.current, {"overridden": True})
    carrier.current = kc.commitment_after_outcome(carrier.current, fuji, outcome(ok=False))
    doc = continuation.capture_player_continuation(runtime, preparation=plan, battle=battle,
        spent=original["spent"], story_kind_commitment_carrier=carrier)
    (tmp_path / "CONTEXT.json").write_text(json.dumps(doc))
    restored = continuation.restore_player_continuation(runtime, json.loads(json.dumps(doc)),
        expected_sha256=canonical_sha256(doc))
    assert restored.story_kind_commitment == carrier.current
    first, second = assemble(tmp_path, tmp_path), assemble(tmp_path, tmp_path)
    resumed = driver._story_kind_commitment_carrier(first)
    assert resumed is not carrier and resumed.current == carrier.current
    assert driver._story_kind_commitment_carrier(second) is not resumed
    assert resumed.current.consecutive_failures == 1 and resumed.current.overrides == 1
    monkeypatch.setattr(kc, "party_fit", lambda _: True)
    choice, receipt = kc.commit_story_kind(_parent(options, "private:restore"), resumed.current)
    assert receipt["overridden"] and choice.selected_binding.story_objective_ref == "rescue_fuji"
    # The failure before renewal is retained; another failure releases it.
    resumed.current = kc.commitment_after_outcome(resumed.current, fuji, outcome(ok=False))
    assert resumed.current is None
    assert carrier.current is not None
    empty = continuation.capture_player_continuation(runtime, preparation=plan, battle=battle,
        spent=original["spent"], story_kind_commitment_carrier=resumed)
    (tmp_path / "CONTEXT.json").write_text(json.dumps(empty))
    assert "story_kind_commitment" not in empty
    assert canonical_sha256(empty) == canonical_sha256(original)
    assert driver._story_kind_commitment_carrier(assemble(tmp_path,tmp_path)).current is None
    assert runtime.emulator.save_state_bytes() == b"terminal"


@pytest.mark.parametrize("release", ["completed", "revisit", "movement_return", "unfit"])
def test_rehydrated_commitment_preserves_release_and_party_safety(release, monkeypatch):
    state = kc.StoryKindCommitment("rescue_fuji", 1, 7)
    carrier = kc.StoryKindCommitmentCarrier.from_document(json.loads(json.dumps(state.document())))
    options = menu(); fuji = options.binding(_index(options,"s-fuji"))
    if release == "completed":
        assert kc.commitment_after_outcome(carrier.current,fuji,outcome(completed=["rescue_fuji"])) is None
        assert kc.StoryKindCommitmentCarrier.from_document(state.document(),completed_objectives=["rescue_fuji"]).current is None
    elif release == "revisit":
        assert kc.commitment_after_choice(carrier.current,{"committed_movement_revisit":True}) is None
    elif release == "movement_return":
        assert kc.commitment_after_movement_return(carrier.current,object()) is None
    else:
        monkeypatch.setattr(kc,"party_fit",lambda _:False)
        parent=_parent(options,"private:restore")
        selected,receipt=kc.commit_story_kind(parent,carrier.current)
        assert selected is parent and not receipt["overridden"]


def test_optional_context_is_hash_bound_and_legacy_default_unchanged(monkeypatch):
    runtime, plan, battle, original, *_ = fixture(monkeypatch)
    assert "story_kind_commitment" not in original
    assert continuation.restore_player_continuation(runtime,original,expected_sha256=canonical_sha256(original)).story_kind_commitment is None
    changed=dict(original,story_kind_commitment=kc.StoryKindCommitment("rescue_fuji").document())
    with pytest.raises(ValueError,match="identity or scope"):
        continuation.restore_player_continuation(runtime,changed,expected_sha256=canonical_sha256(original))
    with pytest.raises(TypeError,match="typed story"):
        continuation.capture_player_continuation(runtime,preparation=plan,battle=battle,spent=original["spent"],story_kind_commitment_carrier=object())


@pytest.mark.parametrize("enabled",[False,True])
def test_shared_chunk_exports_the_exact_carrier_only_when_opted_in(tmp_path,monkeypatch,enabled):
    runtime,preparation,battle,original,*_=fixture(monkeypatch)
    raw=N(player_money=1600,map_id=1,player_y=2,player_x=3,party_levels=(7,))
    runtime.reader=N(read=lambda:raw)
    runtime.emulator.frame_count=0;runtime.emulator.pressed_buttons=()
    holder=dict(runtime=runtime,plan=preparation,prior_spent=original["spent"],observe_history=lambda **_:battle)
    if not enabled:
        holder["story_kind_commitment_carrier"] = kc.StoryKindCommitmentCarrier.from_document(kc.StoryKindCommitment("rescue_fuji").document())
    cap=driver.NativePlayerLimits()
    monkeypatch.setattr(driver,"native_player_options",lambda *a:dict(greedy_selection=True,resume_branch_refinement_after_settlement=False,**({"story_kind_commitment":True} if enabled else {})))
    monkeypatch.setattr(driver,"player_wiring_declaration",lambda *a:{})
    monkeypatch.setattr(driver,"_field_ready",lambda *a:True)
    monkeypatch.setattr(driver,"native_checkpoint_facts",lambda *a:{})
    def native(**kw):
        if enabled: kw["story_kind_commitment_carrier"].current=kc.StoryKindCommitment("rescue_fuji",1,3)
        else: assert "story_kind_commitment_carrier" not in kw
        return dict(outcomes=[],executed_decisions=0,stop_reason="decision_budget")
    monkeypatch.setattr(driver,"run_native_continuous_player",native)
    result,exported=driver.execute_player_chunk(plan={"seed":1},configuration=N(sha256="c"*64),c=N(digest=lambda p:sha256(p.read_bytes()).hexdigest()),emulator=runtime.emulator,factory=None,menu=None,holder=holder,source=None,output=tmp_path,model=N(model_sha256="d"*64),limits=cap,memory=None,store=None,ordinal=1)
    assert result["paired_context_authenticated"]
    if enabled: assert exported["story_kind_commitment"]==kc.StoryKindCommitment("rescue_fuji",1,3).document()
    else:
        assert "story_kind_commitment" not in exported
        receipt=json.loads((tmp_path/"story-kind-commitment-continuation.json").read_text())
        assert receipt["reason"]=="story_kind_commitment_not_declared" and not receipt["applied"]


def test_unknown_objective_fails_before_actions_and_completed_commitment_cannot_revive(monkeypatch):
    runtime,plan,battle,original,*_=fixture(monkeypatch)
    def objective(name):
        if name != "story": raise ValueError("unknown story objective")
        return N(completion_facts={"verified"})
    runtime.adapter.graph.objective=objective
    invalid=dict(original,story_kind_commitment=kc.StoryKindCommitment("unknown").document())
    with pytest.raises(ValueError,match="unknown story objective"):
        continuation.restore_player_continuation(runtime,invalid,expected_sha256=canonical_sha256(invalid))
    completed=dict(original,story_kind_commitment=kc.StoryKindCommitment("story").document())
    restored=continuation.restore_player_continuation(runtime,completed,expected_sha256=canonical_sha256(completed))
    assert restored.story_kind_commitment is None
    assert runtime.emulator.save_state_bytes()==b"terminal"


def test_assembly_factory_refuses_unknown_objective_before_other_runtime_wiring(tmp_path):
    doc={"lesson":{"completed_objectives":[]},"story_kind_commitment":kc.StoryKindCommitment("unknown").document()}
    (tmp_path/"CONTEXT.json").write_text(json.dumps(doc))
    calls=[]
    def graph_objective(name):
        calls.append(name)
        raise ValueError("unknown objective at configured factory")
    inventory=NativeStoryBranchInventory(lambda *_:GoalBindingSet((),()),lambda *_:())
    backend=N(assembly=lambda *a,**k:(b"terminal",lambda _:N(adapter=N(graph=N(objective=graph_objective))),inventory,{}, {"partition":"development"}))
    _,factory,_,_,_=assemble_configured_player(backend,config(),tmp_path,tmp_path,plan_path=tmp_path/"PLAN.json")
    with pytest.raises(ValueError,match="unknown objective at configured factory"):factory(object())
    assert calls==["unknown"]
    doc["story_kind_commitment"]["overrides"]=-1
    (tmp_path/"CONTEXT.json").write_text(json.dumps(doc))
    with pytest.raises(ValueError,match="story kind commitment"):
        assemble_configured_player(backend,config(),tmp_path,tmp_path,plan_path=tmp_path/"PLAN.json")
