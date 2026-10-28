"""Read-only Red matchup projection from one boundary and an exact trainer quote.

The caller proves source bytes and final binding identity at the native boundary.
This module validates their witness and observed roster; it executes no controller,
heuristic member selection, model query, or hypothetical evolution/stat update.
"""
from dataclasses import dataclass, asdict
from math import fsum

from .battle_matchups import project_party_matchups
from .gen1_trainer_parties import TrainerPartyQuote, TrainerPartyMember
from .party import StatusCondition
from .party_preparation import PreparationMember, PreparationPurpose
from .player_option_matchup import MATCHUP_NAMES, OptionMatchup
from .provenance import canonical_sha256
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref, pokemon_red_species_ref
from .red_party import decode_status
from .red_party_pp import decode_red_party_pp
from .red_story_battle import StoryTrainerContract


def _digest(value):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('matchup requires an exact SHA256 source')


def _integer(value, low, high, subject):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('invalid matchup ' + subject)


@dataclass(frozen=True)
class ExactTrainerMatchupWitness:
    """Private current-binding proof; never serialized in policy measurements."""
    source_sha256: str
    binding_ref: str
    contract: StoryTrainerContract
    quote: TrainerPartyQuote

    def __post_init__(self):
        _digest(self.source_sha256)
        if type(self.binding_ref) is not str or not self.binding_ref:
            raise ValueError('matchup witness requires final binding')
        if not isinstance(self.contract, StoryTrainerContract) or not isinstance(self.quote, TrainerPartyQuote):
            raise TypeError('typed story contract and cartridge quote required')
        self.contract.__post_init__()
        q, c = self.quote, self.contract
        if (type(q.opponent_id) is not int or type(q.trainer_set) is not int
                or (q.opponent_id, q.opponent_id - 200, q.trainer_set) != c.trainer_identity
                or type(q.expected_victory_money) is not int or q.expected_victory_money != c.victory_money
                or type(q.party) is not tuple or not 1 <= len(q.party) <= 6):
            raise ValueError('matchup quote differs from current contract')
        _integer(q.base_money, 0, 999999, 'base money')
        for mon in q.party:
            if not isinstance(mon, TrainerPartyMember):
                raise TypeError('typed quoted opponent required')
            _integer(mon.internal_species, 1, 255, 'opponent species')
            _integer(mon.species, 1, 151, 'opponent dex')
            _integer(mon.level, 1, 100, 'opponent level')
            RED_BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(mon.internal_species))


def _pair(values):
    return (min(values), fsum(sorted(values)) / len(values)) if values else (0., 0.)


def project_red_player_matchup(*, raw, members, source_sha256, binding_ref, witness=None):
    """Return (public descriptor, private receipt), with no inferred opposition.

    Missing all-party actual stats or moves/PP mask only those groups. A partial
    array or mismatch to the typed same-boundary roster is an error, not unknown.
    """
    _digest(source_sha256)
    if type(binding_ref) is not str or not binding_ref:
        raise ValueError('matchup requires final binding identity')
    if type(members) is not tuple or not 1 <= len(members) <= 6 or any(not isinstance(m, PreparationMember) for m in members):
        raise ValueError('matchup requires complete immutable role roster')
    count = getattr(raw, 'party_count', None)
    if type(count) is not int or count != len(members):
        raise ValueError('matchup role census differs from current party')
    if len({m.specimen_ref for m in members}) != count or {m.observation.slot for m in members} != set(range(1,count+1)):
        raise ValueError('matchup roles or slots repeat')
    members = tuple(sorted(members, key=lambda m: m.observation.slot))
    if type(getattr(raw, 'battle_state', None)) is not int or raw.battle_state != 0:
        raise ValueError('matchup requires a current field boundary')
    _integer(getattr(raw, 'map_id', None), 0, 255, 'current map')
    fields = ('party_species_ids','party_levels','party_hp','party_max_hp','party_status')
    for name in fields:
        values = getattr(raw, name, None)
        if type(values) is not tuple or len(values) != count:
            raise ValueError('matchup raw roster alignment differs')
    for i,m in enumerate(members):
        _integer(raw.party_status[i], 0, 255, 'party status')
        o=m.observation
        expected=(o.species_id,o.level,o.hp,o.max_hp,o.status)
        observed=(raw.party_species_ids[i],raw.party_levels[i],raw.party_hp[i],raw.party_max_hp[i],decode_status(raw.party_status[i]))
        if observed != expected:
            raise ValueError('matchup role roster does not match exact raw party')
        for n,value in enumerate(observed[:4]):
            _integer(value, 0 if n==2 else 1, (255,100,999,999)[n], 'party measurement')
        RED_BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(o.species_id))
    stats = getattr(raw,'party_stats',None)
    if stats is not None:
        if type(stats) is not tuple or len(stats) != count:
            raise ValueError('partial actual stats are not unknown stats')
        for row in stats:
            if type(row) is not tuple or len(row) != 4:
                raise ValueError('four actual party stats required')
            for v in row:_integer(v,1,999,'actual stat')
    move_rows, pp_rows = getattr(raw,'party_moves',None),getattr(raw,'party_pp',None)
    if (move_rows is None) != (pp_rows is None):
        raise ValueError('partial moves/PP are not unknown moves/PP')
    decoded = None
    if move_rows is not None:
        if type(move_rows) is not tuple or type(pp_rows) is not tuple or len(move_rows)!=count or len(pp_rows)!=count:
            raise ValueError('move/PP role alignment differs')
        decoded=tuple(decode_red_party_pp(m,p).moves for m,p in zip(move_rows,pp_rows,strict=True))
        for m,charges in zip(members,decoded,strict=True):
            old=m.observation.moves
            if len(old)!=4 or any((o.move_id,o.current_pp)!=(p.move_id,p.current_pp) or o.max_pp is not None and o.max_pp!=p.maximum_pp for o,p in zip(old,charges,strict=True)):
                raise ValueError('typed member moves do not match observed PP')
    if witness is not None:
        if not isinstance(witness,ExactTrainerMatchupWitness):raise TypeError('typed exact trainer witness required')
        witness.__post_init__()
        if witness.source_sha256!=source_sha256 or witness.binding_ref!=binding_ref or witness.contract.map_id!=getattr(raw,'map_id',None):
            raise ValueError('matchup witness belongs to another boundary/binding')
    combat=[i for i,m in enumerate(members) if m.purpose is PreparationPurpose.COMBAT]
    living=[i for i in combat if members[i].observation.hp>0]
    values={name:0. for name in MATCHUP_NAMES[1:]}
    values.update(own_members_known=1.,own_stats_known=float(stats is not None),opposition_roster_known=float(witness is not None),moves_and_pp_known=float(decoded is not None),declared_combat_fraction=len(combat)/6,living_combat_fraction=len(living)/6,opponent_fraction=len(witness.quote.party)/6 if witness else 0.)
    if stats is not None:
        for at,name in enumerate(('attack','defense','speed','special','max_hp')):
            measurements=[(stats[i][at] if at<4 else members[i].observation.max_hp)/999 for i in living]
            values['own.'+name+'.minimum'],values['own.'+name+'.mean']=_pair(measurements)
    semantic=[]; own_pp=[]
    for i in living:
        mon=members[i].observation; moves=[]; usable=[]
        for p in (() if decoded is None else decoded[i]):
            if not p.move_id:continue
            ref=pokemon_red_move_ref(p.move_id); move=RED_BATTLE_CATALOG.resolve_move(ref)
            moves.append(dict(move_ref=ref,pp=p.current_pp))
            if p.current_pp>0 and move.category!='status' and move.power>0:
                usable.append(p.current_pp / p.maximum_pp)
        own_pp.append((len(usable)/4,fsum(sorted(usable))/len(usable) if usable else 0.))
        semantic.append(dict(species_ref=pokemon_red_species_ref(mon.species_id),level=mon.level,hp=mon.hp,max_hp=mon.max_hp,status=None if mon.status is StatusCondition.HEALTHY else mon.status.value,moves=moves))
    if decoded is not None:
        for at,name in enumerate(('usable_move_fraction','usable_damaging_move_pp_fraction')):
            values['own.'+name+'.minimum'],values['own.'+name+'.mean']=_pair([row[at] for row in own_pp])
    all_profiles=[]
    if witness is not None and living:
        for opponent in witness.quote.party:
            profiles=project_party_matchups({'features':{'party':{'members':semantic},'battle':{'opponent_species_ref':pokemon_red_species_ref(opponent.internal_species),'opponent_level':opponent.level}}},RED_BATTLE_CATALOG)
            all_profiles.append(profiles)
        for field,name in (('offensive_power','available_offensive_power'),('offensive_type_margin','available_type_margin'),('defensive_resistance','available_defensive_resistance')):
            if decoded is None and field!='defensive_resistance':continue
            metrics=[max(getattr(p,field) for p in profiles) for profiles in all_profiles]
            values['opposition.'+name+'.minimum'],values['opposition.'+name+'.mean']=_pair(metrics)
    descriptor=OptionMatchup(tuple(values[n] for n in MATCHUP_NAMES[1:]))
    receipt=dict(schema='pokemon.red.private-option-matchup.v1',source_sha256=source_sha256,binding_ref=binding_ref,roles=[dict(specimen_ref=m.specimen_ref,slot=m.observation.slot,purpose=m.purpose.value) for m in members],contract=None if witness is None else asdict(witness.contract),quote=None if witness is None else asdict(witness.quote),quote_sha256=None if witness is None else canonical_sha256(asdict(witness.quote)),actual_party_stats=stats,observed_party=[asdict(m.observation) for m in members],raw_party_moves=move_rows,packed_party_pp=pp_rows,combat_slots=[i+1 for i in combat],living_combat_slots=[i+1 for i in living],per_opponent_profiles=[[asdict(p) for p in ps] for ps in all_profiles],policy=descriptor.public_dict(),assumptions=['existing type-based defensive resistance, not incoming move forecast','no victory, survival, cumulative HP/PP sufficiency or selected action claim'])
    return descriptor,receipt




def project_current_trainer_matchups(*, boundary, bindings, supplements, members, witnesses):
    """Join only exact witnesses emitted for this final current offered menu."""
    state_sha = __import__('hashlib').sha256(boundary.state).hexdigest()
    refs = {b.binding_ref for b in (*bindings.bindings, *(s.binding for s in supplements))}
    descriptors, receipts = {}, {}
    for witness in witnesses:
        if not isinstance(witness, ExactTrainerMatchupWitness):
            raise TypeError('typed current trainer witness required')
        if witness.source_sha256 != state_sha or witness.binding_ref not in refs:
            raise ValueError('stale source or unmatched current trainer witness')
        if witness.binding_ref in descriptors:
            raise ValueError('duplicate current trainer witness')
        descriptor, proof = project_red_player_matchup(raw=boundary.observation.raw,
            members=members, source_sha256=state_sha, binding_ref=witness.binding_ref,
            witness=witness)
        descriptors[witness.binding_ref] = descriptor
        receipts[witness.binding_ref] = proof
    return descriptors, receipts
