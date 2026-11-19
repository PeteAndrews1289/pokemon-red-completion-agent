"""Settle an ordinary survey encounter after the target and catcher have fainted."""
import json
from hashlib import sha256
from pathlib import Path

from .actions import MacroAction, MacroActionKind
from .goal_manager import GoalAvailability, GoalFailureReason, GoalKind, GoalOpportunity, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet, GoalExecutionReport, GoalVerification
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_evolution_helper_xp import ordinary_red_xp_upper_bound
from .red_player_field_goals import _field_ready
from .red_party import PokemonRedPartyReader
from .red_player_wild_recovery import retained_native_static_target



def _matching_survey_loss(parent, result, state_hash, raw):
    if not (result.get('paired_context_authenticated') and result.get('released')
            and result.get('state_sha256') == state_hash and result.get('field_ready') is False):
        return False
    context_bytes = (parent/'CONTEXT.json').read_bytes()
    context = json.loads(context_bytes)
    if (result.get('context_sha256') != sha256(context_bytes).hexdigest()
            or context.get('state_sha256') != state_hash or result.get('spent') != context.get('spent')):
        return False
    episode = result.get('episode', {})
    outcomes = episode.get('outcomes') or ()
    if not outcomes or episode.get('stop_reason') != 'execution_failed':
        return False
    outcome = outcomes[-1]
    chain = outcome.get('error_chain') or ()
    if raw.party_hp[raw.active_party_index] > 0 and chain and chain[0].get('error_type') == 'RouteExecutionError':
        return _growth_receipt(outcome, state_hash, raw) is not None
    if (len(chain) == 1 and chain[0].get('error_type') == 'RouteExecutionError'
            and chain[0].get('reason_code') == 'world_state_diverged'
            and chain[0].get('error') == 'indoor collection departure flee lost its protected encounter boundary.'):
        return _matching_indoor_flee(outcome, state_hash, raw)
    if outcome.get('selected_kind') == 'recover_control':
        return _retained_knockout_lesson(parent, outcome, state_hash, raw)
    if (len(chain) != 1 or chain[0].get('error_type') != 'RedCaptureStatusError'
            or chain[0].get('reason_code') != 'capture_status.target_hp'
            or outcome.get('selected_kind') != 'acquire_species' or outcome.get('failure_phase') != 'execution'
            or outcome.get('terminal_state_sha256') != state_hash):
        return False
    events = json.loads((parent/'native/diagnostic-events.json').read_bytes())['events']
    if len(events) < 2:
        return False
    decision, failure = events[-2:]
    a, z = decision['payload'], failure['payload']
    if (decision['kind'] != 'survey_decision' or failure['kind'] != 'survey_action_failed'
            or a.get('directive') != 'capture_encounter' or z.get('operation') != 'capture_encounter'
            or z.get('reason_code') != 'capture_status.target_hp'
            or a.get('source_id') != z.get('source_id') or not str(a.get('source_id')).startswith('wild:')):
        return False
    before, after = a['state'], z['state']
    index = raw.active_party_index
    changed = ('map_id','player_x','player_y','party_species_ids','party_levels','party_pp_current',
               'bag_items','owned_species','specimen_counts','player_money','enemy_level','enemy_species_id')
    return (
        all(key in before and before[key] == after.get(key) for key in changed)
        and before.get('battle_state') == after.get('battle_state') == raw.battle_state == 1
        and before.get('enemy_hp', 0) > 0 and after.get('enemy_hp') == raw.enemy_hp == 0
        and after.get('active_party_index') == index and before['party_hp'][index] > 0
        and tuple(after['party_hp']) == raw.party_hp
        and (raw.party_hp[index] == 0 or
             (0 < raw.party_hp[index] < before['party_hp'][index]
              and all(before['party_hp'][i] == hp for i,hp in enumerate(raw.party_hp) if i != index)))
        and raw.map_id == after['map_id'] and raw.enemy_species_id == after['enemy_species_id']
        and raw.player_money == after['player_money']
    )


def retained_survey_faint_inventory(runtime, actions, *, parent, rom, failed_result=None):
    reader = getattr(runtime, 'reader', None)
    if not callable(getattr(reader, 'read', None)):
        return None
    raw = reader.read()
    if (getattr(raw,'battle_state',None) != 1 or getattr(raw,'enemy_hp',None) != 0
            or not raw.party_hp or not any(raw.party_hp) or type(raw.active_party_index) is not int
            or not 0 <= raw.active_party_index < len(raw.party_hp)):
        return None
    parent = Path(parent)
    source = runtime.emulator.save_state_bytes()
    state_hash = sha256(source).hexdigest()
    if (not (parent/'terminal.state').is_file() or (parent/'terminal.state').read_bytes() != source
            or runtime.emulator.pressed_buttons):
        return None
    if failed_result is None and not (parent/'RESULT.json').is_file():
        return None
    result = failed_result if failed_result is not None else json.loads((parent/'RESULT.json').read_bytes())
    if not _matching_survey_loss(parent, result, state_hash, raw):
        return None
    held_recovery = result['episode']['outcomes'][-1].get('selected_kind') == 'recover_control'
    if held_recovery and reader.read_move_learning_prompt(raw) is None:
        return None
    cartridge_bytes = rom()
    identity = reader.read_retained_wild_identity()
    if (identity is None or identity.original_species_id != raw.enemy_species_id
            or retained_native_static_target(reader, cartridge_bytes) is not None):
        return None
    cartridge = RedPracticeCartridge(cartridge_bytes)
    party = PokemonRedPartyReader(runtime.emulator)
    initial = party.read().members
    specimen_refs = party.preparation_specimen_refs()
    dex = reader.read_pokedex_state().owned_species
    persistent = ('map_id','player_y','player_x','party_species_ids','party_count','party_moves','party_pp',
                  'party_status','bag_items','player_money','badge_bits','event_flags')
    upper = ordinary_red_xp_upper_bound(cartridge.species(raw.enemy_species_id).base_experience,raw.enemy_level)
    growth_gain = None
    if (raw.party_hp[raw.active_party_index] > 0 and
            result['episode']['outcomes'][-1].get('error_type') == 'RouteExecutionError'):
        growth_gain = _growth_receipt(result['episode']['outcomes'][-1], state_hash, raw)
        member = initial[raw.active_party_index]
        growth = cartridge.species(member.species_id)
        previous = result['episode']['outcomes'][-1]['after']['retained_party_continuation']['individuals']
        if (growth_gain is None or growth_gain > upper or not _level_stats_screen(reader, member)
                or member.experience != previous[specimen_refs[raw.active_party_index]]['experience']
                or not growth.experience_at_level(member.level) <= member.experience
                or member.level < 100 and member.experience >= growth.experience_at_level(member.level+1)):
            return None
    terminal = None
    consumed = False

    def execute():
        nonlocal consumed, terminal
        if consumed or runtime.emulator.save_state_bytes() != source:
            raise ValueError('survey knockout text belongs to a different state')
        consumed = True
        start_actions, start_frames = actions.actions_executed, runtime.emulator.frame_count
        for _ in range(48):
            current = reader.read()
            if (any(getattr(current,k) != getattr(raw,k) for k in persistent)
                    or reader.read_pokedex_state().owned_species != dex
                    or current.battle_state not in (0,1)
                    or current.battle_state == 1 and current.enemy_hp != 0):
                raise ValueError('survey knockout settlement changed protected state')
            if _field_ready(runtime):
                break
            # Dismiss battle-result text only; no attack, item or party choice is required.
            if growth_gain is not None:
                if actions.actions_executed == start_actions and _level_stats_screen(reader, initial[raw.active_party_index]):
                    actions.execute(MacroAction(MacroActionKind.CANCEL))
                elif reader.read_bottom_dialogue_box_visible():
                    rows = [row.strip() for row in reader.read_screen_text_rows()[12:] if row.strip()]
                    if rows and not _level_stats_screen(reader, initial[raw.active_party_index]):
                        raise ValueError('unexpected prompt after native wild level-up')
            elif (prompt := reader.read_move_learning_prompt(current)) is not None:
                from .battle_runtime import move_learning_preservation_action
                actions.execute(move_learning_preservation_action(prompt))
            elif reader.read_bottom_dialogue_box_visible():
                actions.execute(MacroAction(MacroActionKind.CANCEL))
            actions.execute(MacroAction(MacroActionKind.WAIT,repeat=60))
        else:
            raise ValueError('survey knockout did not return field control')
        final = party.read().members
        if party.preparation_specimen_refs() != specimen_refs:
            raise ValueError('survey knockout settlement changed individual party custody')
        gains = []
        for i,(old,new) in enumerate(zip(initial,final,strict=True)):
            gain = new.experience - old.experience
            growth = cartridge.species(new.species_id)
            if (old.species_id != new.species_id or not 0 <= gain <= upper
                    or not old.level <= new.level <= 100 or (raw.party_hp[i] == 0 and gain)
                    or gain == 0 and old.level != new.level
                    or gain > 0 and (new.experience < growth.experience_at_level(new.level)
                        or new.level < 100 and new.experience >= growth.experience_at_level(new.level+1))
                    or current.party_hp[i]-raw.party_hp[i] != current.party_max_hp[i]-raw.party_max_hp[i]
                    or new.level == old.level and current.party_max_hp[i] != raw.party_max_hp[i]):
                raise ValueError('survey knockout XP or HP disagrees with the native growth curve')
            gains.append(gain)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(actions.actions_executed-start_actions,runtime.emulator.frame_count-start_frames,
            dict(support='native_survey_knockout',captured=False,model_queries=0,party_xp_gains=gains,
                 previously_awarded_wild_growth=growth_gain, retained_move_learning_prompt=held_recovery,
                 surviving_catcher=raw.party_hp[raw.active_party_index] > 0,
                 source_sha256=state_hash,terminal_sha256=sha256(terminal).hexdigest()))

    def verify(report):
        if terminal is not None and runtime.emulator.save_state_bytes() == terminal and _field_ready(runtime):
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    b = ExecutableGoalBinding('pokemon.red:retained-survey-faint:'+state_hash,GoalKind.RECOVER_CONTROL,
                              0.04,0.02,execute,verify)
    closed=GoalOpportunity(b.binding_ref+':settlement-only',GoalKind.ADVANCE_STORY,GoalAvailability.UNAVAILABLE,
                           unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED)
    return GoalBindingSet((b.opportunity,closed),(b,))



def _matching_indoor_flee(outcome, state_hash, raw):
    if (outcome.get('terminal_state_sha256') != state_hash or outcome.get('failure_phase') != 'execution'
            or outcome.get('selected_kind') not in ('resupply','acquire_species')):
        return False
    before, after = outcome['before'], outcome['after']
    a, z = before['diagnostics'], after['diagnostics']
    keys = ('map_id','party_species_ids','party_levels','party_status','party_moves','party_max_hp',
            'party_pp_current','bag_items','badge_bits','owned_species','specimen_counts','box_counts','player_money')
    return (before.get('movement_event_flags') is not None
            and before['movement_event_flags'] == after.get('movement_event_flags')
            and all(k in a and a[k] == z.get(k) for k in keys)
            and a['battle_state'] == 0 and z['battle_state'] == raw.battle_state == 1
            and z['enemy_hp'] == raw.enemy_hp == 0 and z['enemy_species_id'] == raw.enemy_species_id
            and z['active_party_index'] == raw.active_party_index == 0
            and a['party_hp'][0] > 0 and z['party_hp'][0] == 0 and tuple(z['party_hp']) == raw.party_hp
            and a['party_hp'][1:] == z['party_hp'][1:] and any(z['party_hp'][1:])
            and (z['map_id'],z['player_y'],z['player_x']) == (raw.map_id,raw.player_y,raw.player_x)
            and z['player_money'] == raw.player_money)



def _level_stats_screen(reader, member):
    rows = [line.strip() for line in reader.read_screen_text_rows()]
    return (reader.read_bottom_dialogue_box_visible()
            and [value for value in rows if value in ('ATTACK','DEFENSE','SPEED','SPECIAL')]
                == ['ATTACK','DEFENSE','SPEED','SPECIAL']
            and rows[14].endswith(' grew') and rows[16] == f'to level {member.level}')


def _growth_receipt(outcome, state_hash, raw):
    chain = outcome.get('error_chain') or ()
    if (len(chain) != 2 or chain[0].get('reason_code') != 'world_state_diverged'
            or chain[0].get('error_type') != 'RouteExecutionError'
            or chain[0].get('error') != 'guarded resource-goal transport: escape party resources changed'
            or chain[1].get('error_type') != 'ValueError' or chain[1].get('error') != 'escape party resources changed'
            or outcome.get('terminal_state_sha256') != state_hash or outcome.get('failure_phase') != 'execution'
            or outcome.get('selected_kind') != 'acquire_species'):
        return None
    before, after = outcome['before'], outcome['after']
    a, z = before['diagnostics'], after['diagnostics']
    keys = ('party_species_ids','party_status','party_moves','party_pp_encoded','bag_items','badge_bits',
            'owned_species','specimen_counts','box_counts','player_money')
    i = raw.active_party_index
    if (not all(k in a and a[k] == z.get(k) for k in keys)
            or not before.get('movement_event_flags') or before['movement_event_flags'] != after.get('movement_event_flags')
            or a['battle_state'] != 0 or z['battle_state'] != raw.battle_state or raw.battle_state != 1
            or z['enemy_hp'] != raw.enemy_hp or raw.enemy_hp != 0 or z['enemy_species_id'] != raw.enemy_species_id
            or (z['map_id'],z['player_y'],z['player_x']) != (raw.map_id,raw.player_y,raw.player_x)
            or z['active_party_index'] != i or tuple(z['party_hp']) != raw.party_hp or raw.party_hp[i] <= 0
            or a['party_levels'][i]+1 != z['party_levels'][i]
            or any(a[k][j] != z[k][j] for k in ('party_levels','party_max_hp','party_hp','party_stats')
                   for j in range(len(raw.party_hp)) if j != i)):
        return None
    old, new = (state['retained_party_continuation'] for state in (before,after))
    if not (old['native_identity_verified'] and new['native_identity_verified']):
        return None
    old, new = old['individuals'], new['individuals']
    if old.keys() != new.keys():
        return None
    changed = [k for k in old if old[k] != new[k]]
    if len(changed) == 1:
        src, dst = old[changed[0]], new[changed[0]]
        if (dst['species_ref'] == src['species_ref'] and dst['level'] == z['party_levels'][i]
                and src['level'] == a['party_levels'][i] and dst['experience'] > src['experience']):
            return dst['experience'] - src['experience']
    return None


def _retained_knockout_lesson(parent, outcome, state_hash, raw):
    """Authenticate both the interrupted settlement and its original capture failure."""
    from types import SimpleNamespace
    chain = outcome.get('error_chain') or ()
    if (len(chain)!=1 or chain[0].get('error_type')!='ValueError'
            or chain[0].get('error')!='survey knockout did not return field control'
            or outcome.get('terminal_state_sha256')!=state_hash or outcome.get('failure_phase')!='execution'):
        return False
    plan=json.loads((parent/'PLAN.json').read_bytes())
    prior=Path(plan['actual_parent']).resolve()
    if (parent.parent.resolve()!=prior.parent or not parent.name.startswith('segment-')
            or prior.name != f"segment-{int(parent.name[8:])-1:03d}"):
        return False
    src=outcome['before_state_sha256']
    if (src!=plan['source_sha256'] or sha256((prior/'terminal.state').read_bytes()).hexdigest()!=src
            or sha256((prior/'CONTEXT.json').read_bytes()).hexdigest()!=plan['context_sha256']):
        return False
    before,after=outcome['before']['diagnostics'],outcome['after']['diagnostics']
    keys=('map_id','player_x','player_y','enemy_species_id','enemy_level','enemy_hp','battle_state',
          'active_party_index','party_moves','party_status','party_pp_encoded','bag_items','player_money',
          'badge_bits','owned_species','box_counts','specimen_counts','party_species_ids')
    if not all(k in before and before[k]==after.get(k) for k in keys):
        return False
    if (tuple(after['party_hp'])!=raw.party_hp or after['active_party_index']!=raw.active_party_index
            or after['map_id']!=raw.map_id or after['enemy_species_id']!=raw.enemy_species_id):
        return False
    earlier=json.loads((prior/'RESULT.json').read_bytes())
    if earlier['episode']['outcomes'][-1].get('selected_kind')!='acquire_species':
        return False
    snapshot=SimpleNamespace(**before)
    snapshot.party_hp=tuple(before['party_hp'])
    return _matching_survey_loss(prior,earlier,src,snapshot)
