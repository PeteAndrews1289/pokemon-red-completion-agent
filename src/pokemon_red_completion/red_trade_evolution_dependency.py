"""Physical intermediate demand for a missing native NPC trade registration.

Registration credit is never removed to make a precursor look missing. This
scoped execution policy permits one authenticated level edge solely to supply
an absent, unprotected trade ingredient. It does not change the ordinary policy
or claim that an intermediate transformation completed the acquisition goal.
"""

from collections import Counter
from dataclasses import dataclass, fields
from hashlib import sha256

from .gen1_cartridge import EvolutionMethod, evolution_graph
from .red_collection import red_species_ref
from .red_npc_trade import stationary_npc_trades
from .red_registration_policy import RedRegistrationPolicy


@dataclass(frozen=True, slots=True, kw_only=True)
class TradeEvolutionRegistrationPolicy(RedRegistrationPolicy):
    source_species: int
    intermediate_species: int
    final_species: int
    evolution_level: int
    trade_index: int
    cartridge_sha256: str

    def __post_init__(self):
        RedRegistrationPolicy.__post_init__(self)
        if (
            any(
                type(n) is not int or not 1 <= n <= 151
                for n in (self.source_species, self.intermediate_species, self.final_species)
            )
            or len({self.source_species, self.intermediate_species, self.final_species}) != 3
            or type(self.evolution_level) is not int
            or not 2 <= self.evolution_level <= 100
            or type(self.trade_index) is not int
            or not 0 <= self.trade_index <= 9
            or len(self.cartridge_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.cartridge_sha256)
        ):
            raise ValueError("trade evolution dependency identity differs")

    def document(self):
        return {
            "schema": "pokemon.red.trade-evolution-execution-binding.v1",
            "base": RedRegistrationPolicy.document(self),
            "source_species": self.source_species,
            "intermediate_species": self.intermediate_species,
            "final_species": self.final_species,
            "evolution_level": self.evolution_level,
            "trade_index": self.trade_index,
            "cartridge_sha256": self.cartridge_sha256,
            "intermediate_is_acquisition_success": False,
        }

    def evolution_allowed(self, current, source, target):
        registered = self.goal_registered(current)
        counts = Counter(s.species_ref for s in current.specimens)
        final = red_species_ref(self.final_species)
        return (
            source == red_species_ref(self.source_species)
            and target == red_species_ref(self.intermediate_species)
            and final in self.targets
            and final not in registered
            and counts[target] == 0
            and self.protected_counts.get(target, 0) == 0
            and counts[source] > self.protected_counts.get(source, 0)
        )


def bind_trade_evolution_dependency(
    policy, current, rom, *, trade_index, source_species, completed_trades
):
    """Authenticate a single native level-edge → exchange, without game input.

    This factory, not raw construction from actor data, is the admission path.
    Completed trades and actual intermediate stock invalidate the dependency.
    """
    if type(policy) is not RedRegistrationPolicy:
        raise ValueError("dependency requires an ordinary unmodified registration policy")
    trades = tuple(t for t in stationary_npc_trades(rom) if t.index == trade_index)
    if len(trades) != 1 or trade_index in completed_trades:
        raise ValueError("dependency has no unused supported native exchange")
    trade = trades[0]
    edges = tuple(
        e
        for e in evolution_graph(rom).get(source_species, ())
        if e.method is EvolutionMethod.LEVEL and e.to_species == trade.give
    )
    if len(edges) != 1:
        raise ValueError("dependency has no unique cartridge level edge")
    scoped = TradeEvolutionRegistrationPolicy(
        **{f.name: getattr(policy, f.name) for f in fields(RedRegistrationPolicy)},
        source_species=source_species,
        intermediate_species=trade.give,
        final_species=trade.receive,
        evolution_level=edges[0].requirement,
        trade_index=trade.index,
        cartridge_sha256=sha256(rom).hexdigest(),
    )
    if not scoped.evolution_allowed(
        current, red_species_ref(source_species), red_species_ref(trade.give)
    ):
        raise ValueError("dependency has no eligible physical demand")
    return scoped
