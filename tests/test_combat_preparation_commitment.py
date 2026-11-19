"""A combat-boundary opt-in preserves the real model preparation choice."""
from dataclasses import replace
from types import SimpleNamespace as N
import importlib.util,sys
import pytest
from test_story_branch_value import _options,_story,_parent,_index
from test_red_live_option_menu import _binding
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion import red_story_kind_commitment as kc

def choice(combat=True,kind=GoalKind.DEVELOP_TEAM):
 options=_options([_story("boss","objective"),_binding(kind,binding_ref="prep",calls=[])])
 at=_index(options,"boss");rows=list(options.menu.candidates)
 rows[at]=replace(rows[at],challenge=None if combat is None else OptionChallenge(combat,False,0,0,0))
 options=replace(options,menu=replace(options.menu,candidates=tuple(rows)))
 return _parent(options,"prep")

def test_combat_optin_keeps_exact_model_choice_and_does_not_claim_support(monkeypatch):
 monkeypatch.setattr(kc,"party_fit",lambda _:True);parent=choice();commit=kc.StoryKindCommitment("objective")
 result,receipt=kc.commit_story_kind(parent,commit,respect_combat_preparation_choice=True)
 assert result is parent and result.public_dict()==parent.public_dict()
 assert receipt["combat_preparation_choice_preserved"]and not receipt["overridden"]
 assert kc.commitment_after_choice(commit,receipt)==commit
 baseline,old=kc.commit_story_kind(parent,commit)
 assert old["overridden"]and baseline.selected_binding.kind is GoalKind.ADVANCE_STORY
 assert "respect_combat_preparation_choice"not in old

@pytest.mark.parametrize("combat",[False,None])
def test_noncombat_or_unknown_still_continues_story(monkeypatch,combat):
 monkeypatch.setattr(kc,"party_fit",lambda _:True)
 result,receipt=kc.commit_story_kind(choice(combat),kc.StoryKindCommitment("objective"),respect_combat_preparation_choice=True)
 assert result.selected_binding.kind is GoalKind.ADVANCE_STORY and receipt["overridden"]
 assert not receipt["combat_preparation_choice_preserved"]

def test_other_goal_kind_is_not_given_a_new_priority(monkeypatch):
 monkeypatch.setattr(kc,"party_fit",lambda _:True)
 result,receipt=kc.commit_story_kind(choice(True,GoalKind.EVOLVE_SPECIES),kc.StoryKindCommitment("objective"),respect_combat_preparation_choice=True)
 assert receipt["overridden"]and result.selected_binding.kind is GoalKind.ADVANCE_STORY

@pytest.mark.parametrize("bad",[1,None,"yes"])
def test_helper_rejects_implicit_declaration(bad):
 with pytest.raises(TypeError,match="must be boolean"):kc.commit_story_kind(None,None,respect_combat_preparation_choice=bad)

@pytest.mark.parametrize("combat",[True,False,None])
def test_default_receipts_and_choice_bytes_equal_frozen_f67(monkeypatch,combat):
 from pathlib import Path
 import os
 configured=os.environ.get("POKEMON_FROZEN_PARITY_PACKAGE")
 if configured is None:pytest.skip("optional local frozen parity fixture")
 package=Path(configured)
 name="pokemon_red_completion._f67_commitment_baseline";spec=importlib.util.spec_from_file_location(name,package/"checkout/src/pokemon_red_completion/red_story_kind_commitment.py");old=importlib.util.module_from_spec(spec);sys.modules[name]=old;spec.loader.exec_module(old)
 monkeypatch.setattr(kc,"party_fit",lambda _:True);monkeypatch.setattr(old,"party_fit",lambda _:True)
 parent=choice(combat);a,ar=old.commit_story_kind(parent,old.StoryKindCommitment("objective"));b,br=kc.commit_story_kind(parent,kc.StoryKindCommitment("objective"))
 assert a.public_dict()==b.public_dict()and ar==br

@pytest.mark.parametrize("bad",[1,None,"yes"])
def test_runner_declaration_rejects_bad_flag(bad):
 import run_configured_red_player as s
 p=dict(partition="development",goal_selection=dict(mode="greedy",reason="test",story_milestone_commitment=True,story_kind_commitment=True,respect_combat_preparation_choice=bad))
 with pytest.raises(ValueError,match="combat preparation choice"):s.declared_greedy_selection(p)

def test_runner_requires_commitment_and_forwards_only_explicit_optin(monkeypatch):
 import run_configured_red_player as s
 p=dict(partition="development",goal_selection=dict(mode="greedy",reason="test",respect_combat_preparation_choice=True))
 with pytest.raises(ValueError,match="combat preparation choice"):s.declared_greedy_selection(p)
 p["goal_selection"].update(story_milestone_commitment=True,story_kind_commitment=True)
 monkeypatch.setattr(s,"requires_compulsory_settlement",lambda _:False);monkeypatch.setattr(s,"declared_player_curriculum",lambda *_:None)
 args=(p,object(),[object()],N(native_callbacks=lambda:{}))
 assert s.native_player_options(*args,refinement={})["respect_combat_preparation_choice"]is True
 p["goal_selection"].pop("respect_combat_preparation_choice")
 assert "respect_combat_preparation_choice"not in s.native_player_options(*args,refinement={})

@pytest.mark.parametrize("partition,commitment,flag",[("train",True,True),("development",False,True),("development",True,1)])
def test_autonomous_scope_rejects_before_allocating(tmp_path,partition,commitment,flag):
 from pokemon_red_completion.red_autonomous_player import run_autonomous_options
 with pytest.raises(ValueError,match="combat preparation choice"):
  run_autonomous_options(model=N(feature_version=16),output=tmp_path/"unused",snapshot=None,observe=None,seed=1,provenance=dict(source=dict(partition=partition)),continuous_player=True,story_milestone_commitment=True,story_kind_commitment=commitment,respect_combat_preparation_choice=flag)
 assert not(tmp_path/"unused").exists()
