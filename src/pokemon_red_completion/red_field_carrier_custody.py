"""Private, explicit custody for one selected owned field-carrier exchange.

The original six-member identity baseline is immutable. A pending transaction
permits only its named displacement; committed custody keeps the carrier active
until a separately selected return. This is not a new combat/preparation role.
"""
from dataclasses import asdict, dataclass, replace

from .party import MoveObservation, PartyMemberObservation, PartyObservation, StatusCondition
from .provenance import canonical_sha256

SCHEMA = "pokemon.red.owned-field-carrier-custody.v1"


def _member(document):
    d = dict(document)
    d["status"] = StatusCondition(d["status"])
    d["moves"] = tuple(MoveObservation(**m) for m in d["moves"])
    return PartyMemberObservation(**d)


@dataclass(frozen=True)
class FieldCarrierCustody:
    phase: str
    move_id: int
    objective_ref: str
    displaced_ref: str
    carrier_ref: str
    carrier_species: int
    carrier_level: int
    carrier_experience: int
    original_before: PartyObservation
    original_refs: tuple[str, ...]
    original_loanable_refs: frozenset[str]
    selected_source_sha256: str
    preparation_before: object = None

    def __post_init__(self):
        from .party_preparation import PreparationPlan, PreparationPurpose
        if self.preparation_before is not None:
            plan = self.preparation_before
            if (not isinstance(plan, PreparationPlan) or {m.specimen_ref for m in plan.roster} != set(self.original_refs)
                    or next(m for m in plan.roster if m.specimen_ref == self.displaced_ref).purpose is PreparationPurpose.COMBAT):
                raise ValueError("field-carrier cannot displace an unrecorded or combat member")
        if (
            self.phase not in {"pending", "active"}
            or type(self.move_id) is not int or self.move_id not in {15, 19, 57, 70, 148}
            or type(self.objective_ref) is not str or not self.objective_ref
            or type(self.original_refs) is not tuple or len(self.original_refs) != 6
            or len(set(self.original_refs)) != 6
            or any(type(r) is not str or not r for r in self.original_refs)
            or self.displaced_ref not in self.original_refs
            or type(self.carrier_ref) is not str or not self.carrier_ref
            or self.carrier_ref in self.original_refs
            or not isinstance(self.original_before, PartyObservation)
            or self.original_before.size != 6
            or type(self.original_loanable_refs) is not frozenset
            or not self.original_loanable_refs <= set(self.original_refs)
            or type(self.carrier_species) is not int or not 1 <= self.carrier_species <= 255
            or type(self.carrier_level) is not int or not 1 <= self.carrier_level <= 100
            or type(self.carrier_experience) is not int or self.carrier_experience < 0
            or type(self.selected_source_sha256) is not str
            or len(self.selected_source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.selected_source_sha256)
        ):
            raise ValueError("field-carrier custody declaration differs")

    def private_dict(self):
        d = asdict(self)
        d["original_loanable_refs"] = sorted(self.original_loanable_refs)
        d["original_refs"] = list(self.original_refs)
        return dict(schema=SCHEMA, **d, original_guard_sha256=self.original_guard_sha256)

    @property
    def original_guard_sha256(self):
        return canonical_sha256(dict(before=asdict(self.original_before), refs=self.original_refs,
                                     loanable=sorted(self.original_loanable_refs)))

    @classmethod
    def from_private_dict(cls, document):
        from dataclasses import fields
        if (type(document) is not dict or document.get("schema") != SCHEMA
                or set(document) != {f.name for f in fields(cls)} | {"schema", "original_guard_sha256"}):
            raise ValueError("field-carrier custody schema differs")
        d = {k: v for k, v in document.items() if k not in {"schema", "original_guard_sha256"}}
        d["original_before"] = PartyObservation(tuple(_member(m) for m in d["original_before"]["members"]))
        d["original_refs"] = tuple(d["original_refs"])
        d["original_loanable_refs"] = frozenset(d["original_loanable_refs"])
        if d["preparation_before"] is not None:
            from .red_player_continuation import _plan
            d["preparation_before"] = _plan(d["preparation_before"])
        result = cls(**d)
        if result.original_guard_sha256 != document["original_guard_sha256"]:
            raise ValueError("field-carrier original baseline digest differs")
        return result

    def verify(self, guard):
        from .red_player_continuation import _earned_evolution
        if (guard.before != self.original_before or guard.refs != self.original_refs
                or guard.loanable_refs != self.original_loanable_refs or guard.storage_reader is None):
            raise ValueError("field-carrier changed its original identity guard")
        active_refs, party = guard.reader.preparation_specimen_refs(), guard.reader.read()
        boxes = guard.storage_reader.read_box_specimen_identities()
        candidates = [m for r, m in zip(active_refs, party.members, strict=True) if r == self.carrier_ref]
        candidates += [m for m in boxes if m.preparation_ref == self.carrier_ref]
        if len(candidates) != 1:
            raise ValueError("field-carrier is missing or ambiguous")
        member = candidates[0]
        from types import SimpleNamespace
        old = SimpleNamespace(species_id=self.carrier_species, level=self.carrier_level,
                              experience=self.carrier_experience)
        if (member.level < self.carrier_level or member.experience < self.carrier_experience
                or (member.species_id != self.carrier_species and not _earned_evolution(old, member, guard.edges))):
            raise ValueError("field-carrier identity or earned progress regressed")
        if self.phase == "active":
            expected = (set(self.original_refs) - {self.displaced_ref}) | {self.carrier_ref}
            if len(active_refs) != 6 or set(active_refs) != expected:
                raise ValueError("field-carrier active roster differs from selected exchange")
            carrier = party.members[active_refs.index(self.carrier_ref)]
            if self.move_id not in {m.move_id for m in carrier.moves}:
                raise ValueError("field-carrier lacks its committed field move")


def restore_custody_guard(runtime, custody, *, rom):
    """Restore the recorded baseline; never adopt the substituted active party."""
    from .red_party import PokemonRedPartyReader
    from .red_player_party_guard import RedPlayerPartyGuard
    from .red_trainer_evolution import level_evolution_edges
    guard = RedPlayerPartyGuard(PokemonRedPartyReader(runtime.emulator), custody.original_before,
                                custody.original_refs, level_evolution_edges(rom), runtime.reader,
                                custody.original_loanable_refs, custody)
    guard.verify()
    return guard


def settle_pending_field_carrier(runtime, actions, world):
    """Repay only a pending exchange; committed field custody is not a debt."""
    from .red_player_party_loan import restore_guarded_party_loan
    guard = runtime.adapter.party_guard
    custody = guard.field_carrier
    if custody is None or custody.phase != "pending":
        raise ValueError("only a pending field-carrier exchange may settle here")
    guard.verify()
    from .red_pc_storage import close_generic_pc_session
    close_generic_pc_session(actions, runtime.reader)
    scoped = replace(guard, field_carrier=None, loanable_refs=frozenset({custody.displaced_ref}))
    runtime.adapter.party_guard = scoped
    try:
        changed = restore_guarded_party_loan(runtime, actions, world, allow_cut_return=(custody.move_id == 15))
        scoped.verify_active_roster_restored()
        runtime.adapter.party_guard = replace(guard, field_carrier=None)
        runtime.adapter.party_guard.verify_active_roster_restored()
        return changed
    except BaseException:
        runtime.adapter.party_guard = guard
        raise


def active_carrier_preparation(plan, runtime, custody):
    """An explicit roster view; archived original roles/targets remain in custody."""
    from .party_preparation import PreparationMember, PreparationPurpose
    if plan is None:
        return None
    prior = {m.specimen_ref: m for m in plan.roster}
    if set(prior) != set(custody.original_refs):
        raise ValueError("field-carrier original preparation roster differs")
    reader = runtime.adapter.party_guard.reader
    refs, members = reader.preparation_specimen_refs(), reader.read().members
    roster = tuple(replace(prior[r], observation=replace(prior[r].observation, slot=i))
                   if r in prior else PreparationMember(r, m, PreparationPurpose.FIELD_UTILITY, "selected owned field carrier")
                   for i, (r,m) in enumerate(zip(refs, members, strict=True),1))
    return replace(plan, roster=roster, targets=tuple((r,t) for r,t in plan.targets if r in refs))


def restored_carrier_preparation(custody, runtime, *, rom):
    from .red_player_continuation import refresh_preparation_roster
    return (None if custody.preparation_before is None else
            refresh_preparation_roster(runtime.emulator, custody.preparation_before, evolution_rom=rom))


def aborted_active_carrier_preparation(custody, runtime):
    """Fresh active observations with immutable original purposes kept in custody."""
    state = runtime.emulator.save_state_bytes()
    guard = runtime.adapter.party_guard
    if custody.phase != "active" or guard.field_carrier != custody:
        raise ValueError("aborted return requires verified active custody")
    guard.verify_authorized_active_roster()
    view = active_carrier_preparation(custody.preparation_before, runtime, custody)
    if view is None:
        raise ValueError("aborted return requires the retained original purpose map")
    reader = guard.reader
    refs, party = reader.preparation_specimen_refs(), reader.read()
    observed = dict(zip(refs, party.members, strict=True))
    if set(observed) != {m.specimen_ref for m in view.roster}:
        raise ValueError("aborted return active purpose/physical roster differs")
    # Achieved original targets stay archived verbatim in preparation_before.
    # A current-observation view keeps only the same targets still unmet; never
    # manufacture a higher level or label the metadata change a game success.
    targets = tuple((ref, level) for ref, level in view.targets
                    if observed[ref].level < level)
    result = replace(view, roster=tuple(
        replace(member, observation=observed[member.specimen_ref]) for member in view.roster
    ), targets=targets)
    if runtime.emulator.save_state_bytes() != state:
        raise ValueError("aborted return preparation projection changed native state")
    return result
