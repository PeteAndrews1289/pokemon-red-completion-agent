"""What a *campaign* can obtain, as opposed to what one save can.

:class:`~pokemon_red_completion.pokedex.PokedexTarget` answers "what can one
cartridge register", and its exclusion reasons say so explicitly: they are the
reasons a species cannot be registered *by single-cartridge play*. That is the
right question for one run and the wrong one for a living Pokédex, which spans
several.

Carrying single-cartridge exclusions into a multi-run plan understates what is
reachable. Measured against Red: four species — Alakazam, Machamp, Golem and
Gengar — are marked ``REQUIRES_TRADE`` and therefore counted as unobtainable,
when every one of them is obtained by trading its precursor to a second live
save, letting it evolve on arrival, and trading it back. The obstacle was never
the species; it was that nothing could say "a partner save exists".

So a campaign is modelled as concurrent *vessels*. A vessel is one save that can
hold specimens and act as a trade partner. Two facts follow, and both are
conditional rather than assumed:

* a trade-gated species is reachable only when the plan runs at least two
  vessels **and** some vessel can obtain its precursor;
* a version-exclusive species is reachable only when some vessel runs a title
  that offers it.

Nothing here knows about Red. A vessel carries a title reference and a target,
and both come from an adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.pokedex import ExclusionReason, PokedexTarget


class CampaignPlanError(ValueError):
    """Raised when a campaign plan cannot describe a reachable collection."""


@dataclass(frozen=True, slots=True)
class Vessel:
    """One concurrent save, able to hold specimens and to trade.

    "Concurrent" is the load-bearing word. Three sequential runs on one
    cartridge are not three vessels: the second overwrites the first, and
    nothing from the first survives to be traded. A vessel is a save that
    exists *at the same time* as the others.
    """

    vessel_id: str
    title_ref: str
    target: PokedexTarget

    def __post_init__(self) -> None:
        for name in ("vessel_id", "title_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise CampaignPlanError(f"{name} must be a non-empty label")
        if not isinstance(self.target, PokedexTarget):
            raise TypeError("target must be a PokedexTarget")


@dataclass(frozen=True, slots=True)
class CampaignReach:
    """What a plan can register, and what it still cannot."""

    obtainable: frozenset[int]
    unreachable: Mapping[int, ExclusionReason]
    lifted_by_trade: frozenset[int] = field(default_factory=frozenset)
    lifted_by_version: frozenset[int] = field(default_factory=frozenset)

    @property
    def total_obtainable(self) -> int:
        return len(self.obtainable)

    def public_dict(self) -> dict[str, object]:
        return {
            "obtainable": sorted(self.obtainable),
            "total_obtainable": self.total_obtainable,
            "lifted_by_trade": sorted(self.lifted_by_trade),
            "lifted_by_version": sorted(self.lifted_by_version),
            "unreachable": {
                str(species): reason.value for species, reason in sorted(self.unreachable.items())
            },
        }


@dataclass(frozen=True, slots=True)
class CampaignPlan:
    """Several vessels run together as one collection."""

    vessels: tuple[Vessel, ...]

    def __post_init__(self) -> None:
        if not self.vessels:
            raise CampaignPlanError("a campaign needs at least one vessel")
        identifiers = [vessel.vessel_id for vessel in self.vessels]
        if len(set(identifiers)) != len(identifiers):
            raise CampaignPlanError("vessel identifiers must be distinct")

    @property
    def has_trade_partner(self) -> bool:
        """Whether any vessel has somewhere to trade to.

        One vessel cannot trade with itself, so a single-vessel campaign lifts
        nothing — which is exactly the single-cartridge case the underlying
        target already describes.
        """

        return len(self.vessels) >= 2

    @property
    def titles(self) -> frozenset[str]:
        return frozenset(vessel.title_ref for vessel in self.vessels)

    def union_obtainable(self) -> frozenset[int]:
        """Everything some vessel can obtain on its own."""

        reached: frozenset[int] = frozenset()
        for vessel in self.vessels:
            reached |= vessel.target.obtainable
        return reached


def campaign_reach(
    plan: CampaignPlan,
    *,
    trade_evolutions: Mapping[int, int] = {},
) -> CampaignReach:
    """What the whole plan can register.

    ``trade_evolutions`` maps an evolved species to the precursor that must be
    traded for it. A species is lifted only when the plan has a trade partner
    *and* some vessel can obtain that precursor — because trading requires
    something to send, and a plan that cannot produce the precursor cannot
    produce the evolution either.

    Version exclusivity is lifted by a vessel that simply offers the species;
    that needs no trade partner to *obtain*, only to consolidate, which is a
    separate question answered by :func:`consolidation_required`.
    """

    if not isinstance(plan, CampaignPlan):
        raise TypeError("plan must be a CampaignPlan")

    union = plan.union_obtainable()

    # Anything no vessel can obtain keeps the reason recorded against it, so
    # the result can be audited rather than merely counted.
    still_excluded: dict[int, ExclusionReason] = {}
    # A species one vessel is excluded from but another can obtain was lifted
    # by running a second title or a second set of choices. Computed against
    # every vessel's exclusions, not against what survives them -- an earlier
    # version looked for lifted species inside the still-excluded set, which
    # by construction can never contain them, so it always reported none.
    lifted: set[int] = set()
    for vessel in plan.vessels:
        for species, reason in vessel.target.exclusions.items():
            if species in union:
                lifted.add(species)
            else:
                still_excluded.setdefault(species, reason)
    lifted_by_version = frozenset(lifted)

    lifted_by_trade: set[int] = set()
    if plan.has_trade_partner:
        for species, precursor in trade_evolutions.items():
            if species not in still_excluded:
                continue
            if still_excluded[species] is not ExclusionReason.REQUIRES_TRADE:
                continue
            if precursor in union:
                lifted_by_trade.add(species)

    for species in lifted_by_trade:
        still_excluded.pop(species, None)

    return CampaignReach(
        obtainable=union | frozenset(lifted_by_trade),
        unreachable=dict(sorted(still_excluded.items())),
        lifted_by_trade=frozenset(lifted_by_trade),
        lifted_by_version=lifted_by_version,
        )


def consolidation_required(plan: CampaignPlan, reach: CampaignReach) -> frozenset[int]:
    """Species that must be moved to make the collection live in one place.

    A living Pokédex is one collection, not several. Anything a vessel other
    than the first can obtain has to be traded home.

    A lone vessel therefore returns nothing, and it does so by arithmetic
    rather than by a guard: with no partner it lifts nothing, so its reach is
    exactly its own target and the difference is empty. An explicit
    ``has_trade_partner`` check was tried here and removed — no input could
    distinguish it, so the test that claimed to cover it was passing for the
    wrong reason, which is the defect this repository keeps finding in itself.
    """

    home = plan.vessels[0]
    return frozenset(
        species for species in reach.obtainable if species not in home.target.obtainable
    )
