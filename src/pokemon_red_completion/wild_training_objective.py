"""Private selected-goal facts for a wild battle; no learned action or model feature migration.

Stable specimen references bind current slots and declared purposes. They remain
private evidence and never become the existing battle heads' numerical features.
"""
from dataclasses import dataclass
from .party_preparation import PreparationMember
from .player_preparation_party_context import PreparationPartyWitness
from .provenance import canonical_sha256

WILD_TRAINING_OBJECTIVE_VERSION=1
WILD_TRAINING_OBJECTIVE_SCHEMA='pokemon.core.wild-training-objective.v1'

@dataclass(frozen=True,slots=True)
class WildTrainingObjective:
    party_witness: PreparationPartyWitness
    slot_refs: tuple[str,...]
    trainee_ref: str
    target_level: int
    current_level: int
    current_experience: int

    def __post_init__(self):
        if type(self.party_witness)is not PreparationPartyWitness:
            raise ValueError('typed wild training party witness required')
        roles=dict(self.party_witness.roles)
        if (type(self.slot_refs)is not tuple or len(self.slot_refs)!=len(roles)
                or any(type(r)is not str or not r for r in self.slot_refs)
                or len(set(self.slot_refs))!=len(self.slot_refs) or set(self.slot_refs)!=set(roles)):
            raise ValueError('complete current wild training slot binding required')
        if type(self.trainee_ref)is not str or roles.get(self.trainee_ref)!='combat':
            raise ValueError('selected wild trainee must match the declared combat roster')
        if (type(self.current_level)is not int or not 1<=self.current_level<100
                or type(self.target_level)is not int or not self.current_level<self.target_level<=100
                or type(self.current_experience)is not int or not 0<=self.current_experience<=0xffffff):
            raise ValueError('observed wild training level and XP facts required')

    @property
    def trainee_slot(self):return self.slot_refs.index(self.trainee_ref)+1

    @classmethod
    def from_members(cls,*,source_state_sha256,trainee_ref,target_level,members):
        if (type(members)is not tuple or any(type(m)is not PreparationMember for m in members)
                or tuple(m.observation.slot for m in members)!=tuple(range(1,len(members)+1))):
            raise ValueError('complete ordered semantic wild party observations required')
        witness=PreparationPartyWitness.from_members(source_state_sha256,members)
        selected=next((m for m in members if m.specimen_ref==trainee_ref),None)
        if selected is None:raise ValueError('selected wild trainee is absent')
        return cls(witness,tuple(m.specimen_ref for m in members),trainee_ref,target_level,
                   selected.observation.level,selected.observation.experience)

    def document(self):
        return dict(schema=WILD_TRAINING_OBJECTIVE_SCHEMA,party_witness=self.party_witness.document(),
                    slot_refs=list(self.slot_refs),trainee_ref=self.trainee_ref,target_level=self.target_level,
                    current_level=self.current_level,current_experience=self.current_experience)

    @classmethod
    def from_document(cls,d):
        keys={'schema','party_witness','slot_refs','trainee_ref','target_level','current_level','current_experience'}
        if type(d)is not dict or set(d)!=keys or d['schema']!=WILD_TRAINING_OBJECTIVE_SCHEMA or type(d['slot_refs'])is not list:
            raise ValueError('wild training objective schema differs')
        return cls(PreparationPartyWitness.from_document(d['party_witness']),tuple(d['slot_refs']),
                   d['trainee_ref'],d['target_level'],d['current_level'],d['current_experience'])

    @property
    def identity(self):return canonical_sha256(self.document())

    def diagnostics(self):
        # Current generic/proposed-control heads do not consume this context.
        # A future trained feature schema must make any consumption explicit.
        return dict(schema=WILD_TRAINING_OBJECTIVE_SCHEMA,objective_sha256=self.identity,
                    trainee_slot=self.trainee_slot,target_level=self.target_level,
                    current_level=self.current_level,current_experience=self.current_experience,
                    context_supplied=True,current_heads_consume_context=False)
