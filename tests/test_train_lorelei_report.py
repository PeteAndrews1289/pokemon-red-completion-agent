"""Synthetic boundary fixtures; no ROM, emulator, learned fit or native evidence."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from test_red_train_lorelei import controller
from test_red_trainer_story import fixture as story_fixture
from test_red_post_battle_strategy import episode as episode_document, project
from test_challenge_consequence import documents
from test_progress_consequence import progressive
from pokemon_red_completion import red_player_league_options as options
from pokemon_red_completion.red_trainer_practice_episode import RedTrainerPracticeEpisode
from pokemon_red_completion.red_trainer_battle_lifecycle import TrainerBattleCompletion
from pokemon_red_completion.red_lorelei_story import LoreleiStoryBattleStopped
from pokemon_red_completion.objective_skills import ObjectiveSkillExecution
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.red_challenge_consequence import NativeConsequenceRecorder, project_consequence


def typed_episode(won):
    ep=episode_document()
    if won:
        row=ep['decisions'][0]
        row['state_after']['party_hp']=[100]
        row.update(referee_opponent_roster_hp_before=[100,150],
                   referee_opponent_roster_hp_after=[0,0],opponent_faints=2)
    return RedTrainerPracticeEpisode('synthetic','a'*64,'synthetic',tuple(ep['decisions']),
        won,0 if won else 2,'battle_won' if won else 'party_defeated',opening_idle_frames=4)


def execute_binding(tmp_path, monkeypatch, won, fault=None):
    skill,reader,inputs,observe,_=story_fixture.__wrapped__(monkeypatch)
    ctl=controller(tmp_path,monkeypatch);rt=skill.runtime
    rt.league_story_battle_controller=ctl
    rt.emulator.save_state_bytes=lambda:repr(reader.raw).encode()
    monkeypatch.setattr(options,'_field_ready',lambda r:True)
    monkeypatch.setattr(options,'trainer_party_quote',lambda *a:skill._quote(244,1))
    ep=typed_episode(won)
    after=project(ep.public_dict())
    if fault=='history':after=project(typed_episode(not won).public_dict())
    history_calls=[]
    def history():history_calls.append(1);return after
    if fault=='missing_history':history=None
    initial=reader.raw
    flags=bytearray(initial.event_flags)
    if won:flags[284]|=2
    terminal=replace(initial,event_flags=bytes(flags),battle_state=0,
                     player_money=initial.player_money+5400 if won else initial.player_money//2)
    completion=TrainerBattleCompletion('won' if won else 'lost',True,False,(),
        terminal.player_money-initial.player_money,terminal,ep)
    if fault=='stale':ctl.last_completion=completion
    def execute(self):
        self.actions.execute(MacroAction(MacroActionKind.WAIT,repeat=1))
        ctl.battler.calls+=2 if fault=='extra_battle' else 1
        reader.raw=terminal
        ctl.last_completion=completion
        if fault=='missing':ctl.last_completion=None
        elif fault=='unsettled':ctl.last_completion=replace(completion,field_ready=False)
        elif fault=='terminal':ctl.last_completion=replace(completion,final_state=initial)
        elif fault=='wrong_outcome':ctl.last_completion=replace(completion,outcome='unresolved')
        if not won:raise LoreleiStoryBattleStopped('retained loss')
        return ObjectiveSkillExecution(1,24,{'synthetic_skill_boundary':True})
    monkeypatch.setattr(options.RedCartridgeLoreleiSkill,'execute',execute)
    result=options.league_story_option(rt,skill.actions,
        route=NS(route_world=skill.world,rom=skill.world.rom),combat_levels=(63,55),
        rematch=False,history=history)
    assert result is not None
    binding=result[0];report=binding.execute();verdict=binding.verify(report)
    assert len(history_calls)==1
    return report,verdict,ep


@pytest.mark.parametrize('won',[False,True])
def test_real_binding_report_survives_recorder_and_projection(tmp_path,monkeypatch,won):
    report,verdict,ep=execute_binding(tmp_path,monkeypatch,won)
    assert report.evidence['battle']['episode']==ep.public_dict()
    # Reuse the actual recorder/projector with a prepared synthetic predecessor.
    plan,phases,_=documents(tmp_path/'projection',monkeypatch)
    progressive(plan,phases)
    before=phases[0]['after'];after=deepcopy(before)
    after.update(actions=before['actions']+report.actions_executed,
        completed_actions=before['completed_actions']+report.actions_executed,
        frames=before['frames']+report.frames_executed,
        cash=before['cash']+5400 if won else before['cash']//2,state_sha256='c'*64)
    after['endpoint']['events']=[won]
    output=tmp_path/'recorder';output.mkdir()
    recorder=object.__new__(NativeConsequenceRecorder)
    recorder.session=NS(output=output,recorder=NS(trace=[{'succeeded':True}]*after['actions']))
    recorder.spec_document=plan['spec']
    recorder.phases=phases[:1]
    recorder.active=dict(ordinal=1,kind='advance_story',binding_ref='challenge',before=before)
    recorder.capture=lambda:after
    recorder.end(report,verdict)
    phase=recorder.phases[-1]
    assert phase['cost_verified'] and phase['battle']==('won' if won else 'lost')
    assert phase['challenge_episode']==ep.public_dict()
    assert ep.final_battle_state==(0 if won else 2)
    row=project_consequence(plan,recorder.phases)
    assert row.censor_reason is None and row.outcome.attempted
    assert row.outcome.completed is won
    assert row.outcome.challenge_progress==pytest.approx(1 if won else .495)
    assert row.outcome.actions==100+report.actions_executed
    assert row.outcome.frames==6000+report.frames_executed
    assert row.outcome.cash_credits==(5400 if won else 0)
    assert row.outcome.cash_debits==(0 if won else 750)


@pytest.mark.parametrize('fault',['stale','missing','unsettled','terminal',
                                 'wrong_outcome','extra_battle','history','missing_history'])
def test_unauthenticated_train_completion_never_becomes_feedback(tmp_path,monkeypatch,fault):
    with pytest.raises(ValueError):execute_binding(tmp_path,monkeypatch,True,fault)
