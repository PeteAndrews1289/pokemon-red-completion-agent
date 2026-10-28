"""Explicit consequence-only observed party context; raw option inputs stay exact."""
from dataclasses import dataclass
from math import isfinite
from .party_preparation import PreparationMember, PreparationPlan, PreparationPurpose

PARTY_PROJECTION="prospective_preparation_party_context_v1"
PARTY_SCHEMA="pokemon.core.preparation-party-counts.v1"
TAIL_NAMES=("preparation_party.observed","preparation_party.total_fraction",
            "preparation_party.noncombat_fraction","preparation_party.undecided_fraction")

@dataclass(frozen=True,slots=True)
class PreparationPartyCounts:
    total: int
    noncombat: int
    undecided: int
    def __post_init__(self):
        if (any(type(x) is not int for x in (self.total,self.noncombat,self.undecided))
                or not 1<=self.total<=6 or not 0<=self.undecided<=self.noncombat<=self.total):
            raise ValueError("complete observed party counts required")
    def document(self):
        return dict(schema=PARTY_SCHEMA,total=self.total,noncombat=self.noncombat,undecided=self.undecided)
    @classmethod
    def from_document(cls,document):
        if type(document) is not dict or set(document)!={"schema","total","noncombat","undecided"} or document["schema"]!=PARTY_SCHEMA:
            raise ValueError("party-count context schema differs")
        return cls(document["total"],document["noncombat"],document["undecided"])
    @classmethod
    def from_members(cls,members):
        if (type(members) is not tuple or not members or len(members)>6
                or any(type(m) is not PreparationMember for m in members)
                or len({m.specimen_ref for m in members})!=len(members)
                or sorted(m.observation.slot for m in members)!=list(range(1,len(members)+1))):
            raise ValueError("complete typed observed member roster required")
        return cls(len(members),sum(m.purpose is not PreparationPurpose.COMBAT for m in members),
                   sum(m.purpose is PreparationPurpose.UNDECIDED for m in members))
    def vector(self):
        return (1.0,self.total/6,self.noncombat/6,self.undecided/6)


def from_authenticated_preinput(lesson,plan):
    """Same semantic reducer as runtime; authentication remains the caller's gate.

    The existing sealed lesson proves complete party membership; the same-state
    restored PreparationPlan proves roles. No post-outcome data are read here.
    """
    if (type(plan) is not PreparationPlan or type(lesson) is not dict
            or lesson.get("schema")!="pokemon.red.player-lesson-snapshot.v1"):
        raise ValueError("same-boundary typed role plan and lesson required")
    party=lesson.get("party")
    if (type(party) is not list or len(party)!=len(plan.roster)
            or any(type(m) is not dict or type(m.get("specimen_ref")) is not str for m in party)
            or len({m["specimen_ref"] for m in party})!=len(party)
            or {m["specimen_ref"] for m in party}!={m.specimen_ref for m in plan.roster}):
        raise ValueError("sealed input party does not match the complete role witness")
    return PreparationPartyCounts.from_members(plan.roster)



from .provenance import canonical_sha256
import re

@dataclass(frozen=True,slots=True)
class PreparationPartyWitness:
    source_state_sha256: str
    roles: tuple[tuple[str,str], ...]
    def __post_init__(self):
        if (type(self.source_state_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}",self.source_state_sha256) is None
                or type(self.roles) is not tuple or not 1<=len(self.roles)<=6
                or any(type(x) is not tuple or len(x)!=2 or type(x[0]) is not str or not x[0]
                       or type(x[1]) is not str or x[1] not in {v.value for v in PreparationPurpose} for x in self.roles)
                or len({r for r,_ in self.roles})!=len(self.roles)):
            raise ValueError("complete source-bound preparation roles required")
    @property
    def counts(self):
        return PreparationPartyCounts(len(self.roles),sum(p!="combat" for _,p in self.roles),sum(p=="undecided" for _,p in self.roles))
    def validate_lesson(self,lesson,source_state_sha256):
        if source_state_sha256!=self.source_state_sha256 or type(lesson) is not dict or lesson.get("schema")!="pokemon.red.player-lesson-snapshot.v1":
            raise ValueError("party witness source differs")
        party=lesson.get("party")
        if (type(party) not in (list,tuple) or len(party)!=len(self.roles)
                or any(not isinstance(m,dict) or type(m.get("specimen_ref")) is not str for m in party)
                or len({m["specimen_ref"] for m in party})!=len(party)
                or {m["specimen_ref"] for m in party}!={r for r,_ in self.roles}):
            raise ValueError("complete current party and role witness differ")
        return self
    @classmethod
    def from_members(cls,source_state_sha256,members):
        PreparationPartyCounts.from_members(members)
        return cls(source_state_sha256,tuple((m.specimen_ref,m.purpose.value) for m in members))
    def document(self):
        return dict(schema="pokemon.red.preparation-party-witness.v1",source_state_sha256=self.source_state_sha256,
                    roles=[list(r) for r in self.roles],counts=self.counts.document())
    @property
    def identity(self):return canonical_sha256(self.document())
    @classmethod
    def from_document(cls,document):
        if type(document) is not dict or set(document)!={"schema","source_state_sha256","roles","counts"} or document["schema"]!="pokemon.red.preparation-party-witness.v1":
            raise ValueError("party witness schema differs")
        result=cls(document["source_state_sha256"],tuple(tuple(r) for r in document["roles"]))
        if result.document()!=document:raise ValueError("party witness counts or roles differ")
        return result
