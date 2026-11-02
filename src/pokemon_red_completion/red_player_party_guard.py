"""Protect retained party individuals while permitting earned level evolution.

This opt-in DEVELOPMENT assembly guard replaces species-count reservations,
not registration history. It never edits the cartridge or refreshes its baseline.
"""

from collections import Counter
from dataclasses import asdict, dataclass, replace

from .collection import CollectionLocation
from .gen1_field_moves import GEN1_FIELD_MOVE_IDS
from .observation import PokemonRedStateReader
from .party import PartyObservation
from .provenance import canonical_sha256
from .red_goal_manager import PokemonRedGoalStateAdapter
from .red_party import PokemonRedPartyReader
from .red_trainer_evolution import level_evolution_edges


def _level_line_contains(source, target, edges):
    """Related box collisions remain ambiguous across the whole level lineage."""
    pending, visited = [source], {source}
    while pending:
        species = pending.pop()
        for old, new, _ in edges:
            if old != species or new in visited:
                continue
            if new == target:
                return True
            visited.add(new)
            pending.append(new)
    return False

BIRD_CAPTURE_LOAN_POLICY = {
    "schema": "pokemon.red.bird-capture-loan-policy.v1",
    "purpose": "bird_capture_only",
    "eligibility": "preserve_observed_field_moves",
    "selection": "first_eligible_original",
}

SNORLAX_CAPTURE_LOAN_POLICY = {
    "schema": "pokemon.red.snorlax-capture-loan-policy.v1",
    "purpose": "route16_snorlax_capture_only",
    "eligibility": "preserve_observed_field_moves",
    "selection": "first_eligible_original",
}


def validate_snorlax_capture_loan_declaration(declaration):
    """Separate the second Snorlax source's support from bird-only permission."""
    if declaration is not None and (
        type(declaration) is not dict or declaration != SNORLAX_CAPTURE_LOAN_POLICY
    ):
        raise ValueError("Snorlax loan requires its exact Route16-only transport-safe policy")


def validate_bird_capture_loan_declaration(declaration):
    """Freeze support eligibility, not a strategic goal or a guessed identity."""
    if declaration is None:
        return
    if type(declaration) is not dict:
        raise ValueError("bird loan requires a typed declaration")
    if declaration.get("schema") == BIRD_CAPTURE_LOAN_POLICY["schema"]:
        if declaration != BIRD_CAPTURE_LOAN_POLICY:
            raise ValueError("bird loan policy cannot weaken observed transport or exact return")
        return
    refs = declaration.get("original_refs")
    if (
        declaration.get("schema") != "pokemon.red.bird-capture-loan.v1"
        or declaration.get("purpose") != "bird_capture_only"
        or declaration.get("user_authorized") is not True
        or declaration.get("species_id") != 166
        or type(refs) is not list
        or len(refs) != 6
        or any(type(ref) is not str or not ref for ref in refs)
        or len(set(refs)) != 6
        or declaration.get("specimen_ref") not in refs
    ):
        raise ValueError("named bird loan requires its approved exact original individual")


def observed_transport_safe_bird_guard(runtime, declaration, *, helper_moves):
    """Bind one currently observed original; preserve all held field capabilities.

    This is temporary PC-slot mechanics after the model selects a bird goal.
    No species, old save fingerprint, battle role, training or destination is
    substituted. The caller retains this exact guard until the individual returns.
    """
    validate_bird_capture_loan_declaration(declaration)
    if declaration != BIRD_CAPTURE_LOAN_POLICY:
        raise ValueError("observed bird eligibility requires the frozen semantic policy")
    return _observed_transport_safe_capture_guard(runtime, helper_moves=helper_moves)


def observed_transport_safe_snorlax_guard(runtime, declaration, *, helper_moves):
    """Reuse exact custody/field-move mechanics under a distinct source scope."""
    validate_snorlax_capture_loan_declaration(declaration)
    if declaration != SNORLAX_CAPTURE_LOAN_POLICY:
        raise ValueError("observed Snorlax eligibility requires its explicit policy")
    return _observed_transport_safe_capture_guard(runtime, helper_moves=helper_moves)


def _observed_transport_safe_capture_guard(runtime, *, helper_moves):
    """Mechanical eligibility only; callers separately authenticate the target."""
    guard = runtime.adapter.party_guard
    if not isinstance(guard, RedPlayerPartyGuard):
        raise ValueError("bird eligibility needs the retained individual guard")
    guard.verify_active_roster_restored()
    refs = guard.reader.preparation_specimen_refs()
    moves = runtime.reader.read().party_moves
    if (
        not 2 <= len(refs) <= 6
        or set(refs) != set(guard.refs)
        or moves is None
        or len(moves) != len(refs)
        or any(len(row) != 4 for row in moves)
        or len(helper_moves) != 4
        or any(
            type(move) is not int or not 0 <= move <= 165
            for row in (*moves, helper_moves)
            for move in row
        )
    ):
        raise ValueError("bird eligibility requires the exact active roster and observed moves")
    required = GEN1_FIELD_MOVE_IDS & {move for row in moves for move in row}
    for index, ref in enumerate(refs):
        remaining = {move for i, row in enumerate(moves) if i != index for move in row}
        if required <= remaining | set(helper_moves):
            scoped = replace(guard, loanable_refs=frozenset({ref}))
            scoped.verify_active_roster_restored()
            return scoped
    return None


@dataclass(frozen=True)
class RedPlayerPartyGuard:
    reader: PokemonRedPartyReader
    before: PartyObservation
    refs: tuple[str, ...]
    edges: frozenset[tuple[int, int, int]]
    storage_reader: PokemonRedStateReader | None = None
    loanable_refs: frozenset[str] = frozenset()

    @classmethod
    def from_rom(cls, rom, emulator, *, loanable_refs=frozenset(), storage_reader=None):
        reader = PokemonRedPartyReader(emulator)
        guard = cls(
            reader,
            reader.read(),
            reader.preparation_specimen_refs(),
            level_evolution_edges(rom),
            storage_reader,
            loanable_refs,
        )
        guard.verify()
        return guard

    def verify(self):
        # A retained player segment can span several earned evolutions. Reuse
        # its existing continuation matcher without changing the strictly
        # one-stage per-battle guard or refreshing this original observation.
        from .red_player_continuation import _earned_evolution

        party, refs = self.reader.read(), self.reader.preparation_specimen_refs()
        if (
            len(set(self.refs)) != len(self.refs)
            or len(self.refs) != self.before.size
            or len(set(refs)) != len(refs)
            or len(refs) != party.size
            or not isinstance(self.loanable_refs, frozenset)
            or not self.loanable_refs <= set(self.refs)
            or (self.loanable_refs and self.storage_reader is None)
            or not (set(self.refs) - self.loanable_refs) <= set(refs)
        ):
            raise ValueError("retained party lost or duplicated an individual")
        current = dict(zip(refs, party.members, strict=True))
        original = dict(zip(self.refs, self.before.members, strict=True))
        if self.storage_reader is not None:
            for member in self.storage_reader.read_box_specimen_identities():
                ref = member.preparation_ref
                if ref in self.refs:
                    old = original[ref]
                    # Red's OT/DV fingerprint is not globally unique. A newly
                    # caught, unrelated species cannot be this retained member.
                    # Same-species/evolution-line collisions remain ambiguous
                    # and fail closed below; progress is checked afterward.
                    if member.species_id != old.species_id and not _level_line_contains(
                        old.species_id, member.species_id, self.edges
                    ):
                        continue
                    if ref in current:
                        raise ValueError("retained party lost or duplicated an individual")
                    current[ref] = member
        if not set(self.refs) <= current.keys():
            raise ValueError("retained party lost or duplicated an individual")
        for ref, old in zip(self.refs, self.before.members, strict=True):
            new = current[ref]
            if (
                old.experience is None
                or new.experience is None
                or new.experience < old.experience
                or new.level < old.level
                or (
                    new.species_id != old.species_id
                    and not _earned_evolution(old, new, self.edges)
                )
            ):
                raise ValueError("retained individual identity or earned progress differs")

    def verify_active_roster_restored(self):
        """Temporary loans must be repaid before a continuation is exported."""
        self.verify()
        if not set(self.refs) <= set(self.reader.preparation_specimen_refs()):
            raise ValueError("retained active party has not been restored")

    def continuation_evidence(self, collection, *, include_unreserved_additions=False):
        """Read-only census proof for earned evolution at a continuation boundary.

        Only the original guarded individuals receive identity coverage. An
        explicit scoped observation may also count new, unreserved party members
        among the other stock. The referee must separately reconcile those
        additions against verified capture receipts. No new loan/reservation or
        instruction to heal/train is granted.
        """
        self.verify()
        if type(include_unreserved_additions) is not bool:
            raise ValueError("unreserved census additions require an explicit boolean")
        refs = self.reader.preparation_specimen_refs()
        if not set(self.refs) <= set(refs) or (
            not include_unreserved_additions and set(refs) != set(self.refs)
        ):
            return None
        party = self.reader.read()
        semantic = {
            m.slot_index: m for m in collection.specimens if m.location is CollectionLocation.PARTY
        }
        if set(semantic) != set(range(party.size)):
            raise ValueError("retained party semantic census differs")
        return dict(
            schema="pokemon.red.retained-party-continuation.v1",
            guard_sha256=canonical_sha256(
                dict(refs=self.refs, before=asdict(self.before), edges=sorted(self.edges))
            ),
            native_identity_verified=True,
            individuals={
                ref: dict(
                    species_ref=semantic[i].species_ref,
                    level=member.level,
                    experience=member.experience,
                )
                for i, (ref, member) in enumerate(zip(refs, party.members, strict=True))
                if ref in self.refs
            },
            other_specimen_counts=dict(
                Counter(
                    m.species_ref
                    for m in collection.specimens
                    if m.location is not CollectionLocation.PARTY
                    or refs[m.slot_index] not in self.refs
                )
            ),
        )


@dataclass(slots=True)
class RetainedPartyGoalStateAdapter(PokemonRedGoalStateAdapter):
    party_guard: RedPlayerPartyGuard | None = None

    def observe(self):
        if not isinstance(self.party_guard, RedPlayerPartyGuard):
            raise ValueError("retained-party observation requires an identity guard")
        self.party_guard.verify()
        return PokemonRedGoalStateAdapter.observe(self)


def retained_party_slot_is_depositable(adapter, party_slot):
    """Respect an existing retained-individual contract before offering storage.

    Ordinary collection adapters have no such reservation. An opted-in guard
    may still admit a newly acquired, unreserved individual, but its original
    individuals cannot be loaned to a box by an incompatible executor. An
    explicit storage-census contract admits only its named temporary loans.
    """
    if type(party_slot) is not int or not 1 <= party_slot <= 6:
        raise ValueError("storage needs a valid one-based party slot")
    guard = getattr(adapter, "party_guard", None)
    if guard is None:
        return True
    if not isinstance(guard, RedPlayerPartyGuard):
        raise ValueError("retained storage reservation requires an identity guard")
    guard.verify()
    refs = guard.reader.preparation_specimen_refs()
    if party_slot > len(refs):
        raise ValueError("storage slot is not observed in the retained party")
    return refs[party_slot - 1] not in guard.refs or refs[party_slot - 1] in guard.loanable_refs


def retained_party_slot_is_declared_loan(adapter, party_slot):
    """Recognize only a named, authenticated loan; never expand its permission."""
    if not retained_party_slot_is_depositable(adapter, party_slot):
        return False
    guard = getattr(adapter, "party_guard", None)
    if guard is None:
        return False
    refs = guard.reader.preparation_specimen_refs()
    return refs[party_slot - 1] in guard.loanable_refs
