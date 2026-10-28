"""Source-bound conditional opening control, without play or learner integration."""
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import re
from types import SimpleNamespace

from .battle_semantics import BattleFeatureProjector
from .provenance import canonical_sha256
from .red_battle_catalog import RED_BATTLE_CATALOG
from .red_battle_scenario import red_battle_move_unsupported_reason
from .red_trajectory import _battle_resources
from .red_trainer_opening_preview import OpeningPreviewUnavailable, _fresh_trainer_view, _hash, _integer
from .red_trainer_practice_features import MOVE_SCHEMA_ID, project_trainer_switch_features
from .red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from .red_trainer_proposed_control import PROPOSED_CONTROL_SCHEMA, PROPOSED_CONTROL_NAMES, proposed_control
from .red_status_battle_features import project_for_head

ORDINARY_FRESH_POLICY_CONFIGURATION = {
    'switch_guard_revision':'attack-obligation-v2',
    'allow_immune_switch_recovery':False, 'mechanics_aware_choices':False,
    'pp_depleted_switch_screen':False, 'diagnostic_stay_when_productive':False,
    'diagnostic_status_release':False, 'diagnostic_prompt_stay':False,
    'screen_capped_status_moves':False, 'allow_model_struggle':False,
    'allow_status_moves':False, 'allow_stranded_accuracy_move':True,
    'episode_forced_struggle':True,
}
_ORDINARY_POLICY_SHA256 = canonical_sha256(ORDINARY_FRESH_POLICY_CONFIGURATION)

@dataclass(frozen=True, slots=True)
class TrainerOpeningControl:
    source_sha256: str
    model_sha256: str
    policy_sha256: str
    input_sha256: str
    opponent_quote_sha256: str
    feature_names: tuple[str, ...]
    candidate_vectors: tuple[tuple[float, ...], ...]
    probabilities: tuple[float, float]
    move_slots: tuple[int, ...]
    supported_mask: tuple[bool, ...]
    switch_slots: tuple[int, ...]
    proposed_move_slot: int
    proposed_switch_slot: int | None
    selected_control: str
    forced_attack: bool
    assumptions: tuple[str, ...]
    preparation: dict | None = None

    def public_dict(self):
        return dict(schema='pokemon.red.conditional-opening-control.v1', **asdict(self))


def _control_view(before, *, opponent_base_stats, machine_lesson, stats_peer,
        trainer_quote=None, expected_trainer_quote_sha256=None, preparation_configuration=None, **opening):
    if type(opponent_base_stats) is not dict or set(opponent_base_stats)!={'hp','attack','defense','speed','special'}:
        raise OpeningPreviewUnavailable('quoted public opponent HP and four stat bases required')
    hp_base=_integer(opponent_base_stats['hp'],1,255,'opponent HP base')
    view=_fresh_trainer_view(before, opponent_base_stats={k:v for k,v in opponent_base_stats.items() if k!='hp'},
        machine_lesson=machine_lesson, stats_peer=stats_peer, **opening)
    economy=before.get('economy')
    if stats_peer is not None:
        if (type(stats_peer) is not dict or stats_peer.get('state_sha256')!=before.get('state_sha256')
                or stats_peer.get('lesson',{}).get('party')!=before.get('lesson',{}).get('party')
                or stats_peer.get('lesson',{}).get('in_battle') is not False
                or any(type(stats_peer.get(k)) is not int or stats_peer[k]!=0 for k in ('actions','frames'))):
            raise OpeningPreviewUnavailable('control peer does not match exact pre-input source and party')
        for key in ('cash','economy'):
            if key in before and key in stats_peer and before[key]!=stats_peer[key]:
                raise OpeningPreviewUnavailable('control peer resource facts differ')
        if economy is None:economy=stats_peer.get('economy')
    if type(economy) is not dict or economy.get('schema')!='pokemon.core.resource-economy-snapshot.v1':
        raise OpeningPreviewUnavailable('observed pre-input economy required')
    cash=_integer(economy.get('cash'),0,999999,'cash')
    if type(before.get('cash')) is not int or before['cash']!=cash:
        raise OpeningPreviewUnavailable('cash snapshots differ')
    inventory=economy.get('inventory')
    if not isinstance(inventory,list):raise OpeningPreviewUnavailable('observed bag inventory required')
    items={}
    for pair in inventory:
        if not isinstance(pair,(list,tuple)) or len(pair)!=2 or type(pair[0]) is not str or re.fullmatch(r'red-item-[0-9]{3}',pair[0]) is None:
            raise OpeningPreviewUnavailable('observed item identity invalid')
        item=_integer(int(pair[0][-3:]),1,255,'item')
        count=_integer(pair[1],1,99,'item quantity')
        if item in items:raise OpeningPreviewUnavailable('duplicate bag item')
        items[item]=count
    # The shared builder authenticates the peer source/party before this join.
    boundary=before.get('machine_boundary')
    if boundary is None:boundary=stats_peer.get('machine_boundary') if isinstance(stats_peer,dict) else None
    badges=_integer(boundary.get('badges') if isinstance(boundary,dict) else None,0,255,'badge bits')
    view['features']['resources']=_battle_resources(SimpleNamespace(bag_items=tuple(items.items()),player_money=cash))
    view['features']['progress']={'badge_count':badges.bit_count()}
    view['features']['battle'].update(opponent_using_trapping_move=False)
    view['features']['battle']['opponent_public_base_stats']['hp']=hp_base
    if trainer_quote is not None:
        view = _compose_trainer_preparation(view, before=before, quote=trainer_quote,
            expected_quote_sha256=expected_trainer_quote_sha256,
            configuration=preparation_configuration)
    elif expected_trainer_quote_sha256 is not None or preparation_configuration is not None:
        raise OpeningPreviewUnavailable('preparation requires its authenticated complete trainer quote')
    return view


def _compose_trainer_preparation(view, *, before, quote, expected_quote_sha256, configuration):
    """Derive lesson-then-lead mechanics without rewriting an observed snapshot.

    The caller authenticates the complete cartridge quote. Only the declared
    ordinary preparation contract is supported; arbitrary permutations are absent.
    This is input-only conditional evidence, never an observed party or victory.
    """
    from .gen1_trainer_parties import TrainerPartyQuote
    from .party import MoveObservation, PartyMemberObservation, PartyObservation
    from .red_trainer_party import plan_trainer_party, RedTrainerPartyError

    _hash(expected_quote_sha256, 'complete trainer quote')
    ordinary = dict(minimum_hp_ratio=0., allow_fainted_reserves=True,
        maximum_level_deficit=5, allow_status=False)
    if (type(configuration) is not dict or canonical_sha256(configuration) != canonical_sha256(ordinary)
            or not isinstance(quote, TrainerPartyQuote) or not quote.party
            or canonical_sha256(asdict(quote)) != expected_quote_sha256):
        raise OpeningPreviewUnavailable('complete quote or ordinary preparation configuration differs')
    battle = view['features']['battle']
    first = quote.party[0]
    if (int(battle['opponent_species_ref'].rsplit(':', 1)[1]) != first.internal_species
            or battle['opponent_level'] != first.level):
        raise OpeningPreviewUnavailable('opening opponent differs from complete trainer quote')
    result = deepcopy(view)
    members = result['features']['party']['members']
    observed = []
    for i, member in enumerate(members):
        slots = {move['slot_index']: move for move in member['moves']}
        moves = tuple(MoveObservation(
            int(slots[j]['move_ref'].rsplit(':', 1)[1]) if j in slots else 0,
            slots[j]['pp'] if j in slots else 0) for j in range(4))
        observed.append(PartyMemberObservation(slot=i+1,
            species_id=int(member['species_ref'].rsplit(':', 1)[1]),
            level=member['level'],hp=member['hp'],max_hp=member['max_hp'],moves=moves))
    party = PartyObservation(tuple(observed))
    try:
        plan = plan_trainer_party(party, quote, **ordinary)
        plan.require_current(party, quote)
    except (RedTrainerPartyError, ValueError, TypeError) as error:
        raise OpeningPreviewUnavailable('postlesson party does not qualify for ordinary preparation') from error
    target = plan.lead.target_index
    permutation = list(range(len(members)))
    permutation[0], permutation[target] = permutation[target], permutation[0]
    derived = PartyObservation(tuple(replace(party.members[j], slot=i+1)
        for i,j in enumerate(permutation)))
    plan.lead.require_result(derived)
    members = [dict(members[j],party_index=i) for i,j in enumerate(permutation)]
    result['features']['party'].update(members=members,lead=members[0],active_index=0)
    specimens = [m['specimen_ref'] for m in before['lesson']['party']]
    result['conditional_preparation'] = dict(
        schema='pokemon.red.conditional-opening-preparation.v1',
        source_sha256=before['state_sha256'],observed_snapshot_sha256=canonical_sha256(before),
        complete_quote_sha256=expected_quote_sha256,configuration=ordinary,
        plan=plan.public_dict(),postlesson_party_sha256=canonical_sha256(asdict(party)),
        permutation=[j+1 for j in permutation],
        derived_specimen_order=[specimens[j] for j in permutation],
        observed_after=False,inputs=0)
    return result


def preview_fresh_trainer_control(before, *, model, expected_model_sha256,
        policy_configuration, expected_policy_sha256, opponent_quote_sha256,
        fresh_trainer, approach_preserves_party, approach_preserves_resources,
        machine_lesson=None, stats_peer=None, **opening):
    """Preview the ordinary fresh K control branch, not future turns or victory."""
    if fresh_trainer is not True or approach_preserves_party is not True or approach_preserves_resources is not True:
        raise OpeningPreviewUnavailable('fresh trainer and unchanged approach facts required')
    _hash(expected_model_sha256,'three-head model');_hash(expected_policy_sha256,'policy');_hash(opponent_quote_sha256,'opponent quote')
    if (not isinstance(model,TrainerPracticeThreeHeadModel) or model.move.schema_id!=MOVE_SCHEMA_ID
            or model.control.schema_id!=PROPOSED_CONTROL_SCHEMA or model.damage_reference is not None
            or canonical_sha256(model.to_dict())!=expected_model_sha256):
        raise OpeningPreviewUnavailable('frozen ordinary three-head identity differs')
    if (type(policy_configuration) is not dict or canonical_sha256(policy_configuration)!=expected_policy_sha256
            or canonical_sha256(policy_configuration)!=_ORDINARY_POLICY_SHA256):
        raise OpeningPreviewUnavailable('ordinary opening policy configuration differs')
    view=_control_view(deepcopy(before),machine_lesson=deepcopy(machine_lesson),stats_peer=deepcopy(stats_peer),**opening)
    base=BattleFeatureProjector(RED_BATTLE_CATALOG,mask_counter_without_prior_damage=True).project(view)
    moves={m['slot_index']:m for m in view['features']['party']['lead']['moves']}
    mask=tuple(bool(legal and red_battle_move_unsupported_reason(int(moves[slot]['move_ref'].rsplit(':',1)[1]),moves[slot]['pp'],catalog=RED_BATTLE_CATALOG) is None)
        for slot,legal in zip(base.slot_indices,base.legal_mask,strict=True))
    base=replace(base,legal_mask=mask)
    move_slots=tuple(slot+1 for slot,legal in zip(base.slot_indices,mask,strict=True) if legal)
    if not move_slots:raise OpeningPreviewUnavailable('no ordinary supported attack; no fallback preview')
    members=view['features']['party']['members']
    switch_slots=project_trainer_switch_features(view,RED_BATTLE_CATALOG).candidate_slots if len(members)>1 else ()
    if switch_slots:
        proposal=proposed_control(view,catalog=RED_BATTLE_CATALOG,move_head=model.move,switch_head=model.switch,
            move_batch=base,move_slots=move_slots,switch_slots=switch_slots)
        vectors=proposal.candidate_vectors;probabilities=tuple(float(v) for v in model.control.probabilities(vectors))
        move_slot=proposal.move_slot;switch_slot=proposal.switch_slot
        selected=('attack','switch')[model.control.predict_index(vectors)]
    else:
        rich=project_for_head(view,base,model.move)
        candidates=tuple(rich.candidate_vectors[rich.candidate_slots.index(s)] for s in move_slots)
        move_slot=move_slots[model.move.predict_index(candidates)];switch_slot=None
        vectors=();probabilities=(1.,0.);selected='attack'
    return TrainerOpeningControl(before['state_sha256'],expected_model_sha256,expected_policy_sha256,
        canonical_sha256(view),opponent_quote_sha256,PROPOSED_CONTROL_NAMES,vectors,probabilities,
        move_slots,mask,switch_slots,move_slot,switch_slot,selected,not bool(switch_slots),
        ('fresh full-HP opponent, neutral stages, no disable or trapping',
         'healthy observed party and resources preserved during approach',
         'fresh policy history with no pending switch obligation',
         'ordinary supported attacks; fallback and mechanics interventions excluded',
         'conditional opening control only; not subsequent turns, damage or victory'),
        view.get('conditional_preparation'))


@dataclass(frozen=True, slots=True)
class TrainerMachineControlPreview:
    before: TrainerOpeningControl
    after: TrainerOpeningControl
    snapshot_sha256: str
    stats_peer_sha256: str | None
    lesson_sha256: str | None

    def public_dict(self):
        return dict(schema='pokemon.red.conditional-machine-control.v1',before=self.before.public_dict(),
            after=self.after.public_dict(),snapshot_sha256=self.snapshot_sha256,
            stats_peer_sha256=self.stats_peer_sha256,lesson_sha256=self.lesson_sha256)


def preview_machine_control(before, *, machine_lesson=None, stats_peer=None, **opening):
    """Construct both sides internally from the same authenticated pre-input facts."""
    snapshot=deepcopy(before);peer=deepcopy(stats_peer);lesson=deepcopy(machine_lesson)
    baseline=preview_fresh_trainer_control(snapshot,stats_peer=peer,**opening)
    proposed=baseline if lesson is None else preview_fresh_trainer_control(snapshot,stats_peer=peer,machine_lesson=lesson,**opening)
    return TrainerMachineControlPreview(baseline,proposed,canonical_sha256(snapshot),
        canonical_sha256(peer) if (snapshot.get('machine_boundary') is None or snapshot.get('economy') is None) and peer is not None else None,
        canonical_sha256(lesson) if lesson is not None else None)
