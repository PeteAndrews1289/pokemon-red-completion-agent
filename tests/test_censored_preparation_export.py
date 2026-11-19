from dataclasses import asdict
from hashlib import sha256
import json
import pytest
from test_retained_story_preparation import story
from pokemon_red_completion.battle_scenario_capture import build_battle_scenario_capture_payload
from pokemon_red_completion.battle_runtime import BattleRuntimeError
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog
from pokemon_red_completion.red_player_preparation_history import StoryPreparationHistory

def failed_tail(b,h):
 b.calls+=1;d=b.output/f'battle-{b.calls:04d}';d.mkdir();payload=b'failed-terminal';(d/'initial.state').write_bytes(b'initial')
 (d/'initial.state.json').write_bytes(build_battle_scenario_capture_payload(capture_id=f'player-trainer-{b.calls:04d}',root_lineage_id=b.root_lineage_id,partition=b.source_partition,state_bytes=b'initial',initial_observation_sha256='c'*64,source_commit=b.source_commit,expected_map=b.train_story_contract.map_id,expected_battle_state=2,source_state_sha256=b.source_state_sha256))
 (d/'final.state').write_bytes(payload);endpoint=dict(final_state_sha256=sha256(payload).hexdigest(),outcome_sha256=None,model_sha256=b.model_sha256,qualification_sha256=b.qualification_sha256,actor_returned_win=False,outer_goal_verification_required=True);(d/'endpoint.json').write_text(json.dumps(endpoint))
 log=TrainerPracticeEventLog(d/'events',run_identity=dict(model_sha256=b.model_sha256,qualification_sha256=b.qualification_sha256,source_commit=b.source_commit,root_lineage_id=b.root_lineage_id,parent_state_sha256=b.source_state_sha256,train_story_contract=asdict(b.train_story_contract)));log.fail(BattleRuntimeError('closed technical failure'))
 _,censor=h.checkpoint_after_execution_failure(terminal_state_sha256=endpoint['final_state_sha256'],error_type='BattleRuntimeError');return censor,d

def test_export_retains_complete_real_loss_prefix_without_labeling_failed_tail(tmp_path):
 b,h=story(tmp_path);censor,d=failed_tail(b,h);m=StoryPreparationHistory();m.refresh(dict(scoped_actors={'s':(b,h)},censored_battle_checkpoint=censor))
 assert m.retained.directory.name=='battle-0001' and len(h.outcomes)==len(h.receipts)==1 and not (d/'outcome.json').exists()
 with pytest.raises(FileNotFoundError):h()

@pytest.mark.parametrize('fault',['missing','terminal','ordinal','outcome','inference','identity','log'])
def test_export_refuses_missing_foreign_or_tampered_censor(tmp_path,fault):
 b,h=story(tmp_path);censor,d=failed_tail(b,h)
 if fault=='missing':censor=None
 elif fault=='terminal':censor['terminal_state_sha256']='0'*64
 elif fault=='ordinal':censor['ordinal']+=1
 elif fault=='outcome':censor['outcome']={}
 elif fault=='inference':censor['fresh_inference']=True
 elif fault=='identity':b.model_sha256='f'*64
 else:(d/'events/event-00002.json').write_text('{}')
 with pytest.raises((FileNotFoundError,ValueError,KeyError)):
  StoryPreparationHistory().refresh(dict(scoped_actors={'s':(b,h)},censored_battle_checkpoint=censor))
