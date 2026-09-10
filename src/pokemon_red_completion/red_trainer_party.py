"""Party-dependent preparation, not a trainer victory prediction.

The roster comes from the cartridge; health and moves come from the current
party. Shared semantic matchup features choose an opening lead without an
opponent-name, species, or party-slot recipe. This is deterministic support,
not a learned switch policy or permission to enter a battle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .battle_matchups import PartyMatchupProfile, project_party_matchups
from .gen1_trainer_parties import TrainerPartyQuote
from .party import PartyObservation, StatusCondition
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref, pokemon_red_species_ref
from .red_capture_lead import RedCaptureLeadPlan

if TYPE_CHECKING:
    from .executor import CountingExecutor
    from .red_goal_context import RedGoalContextRuntime


class RedTrainerPartyError(ValueError):
    """The current party cannot support the declared preparation contract."""


def trainer_entry_candidates(
    party: PartyObservation, candidates: tuple[PartyMatchupProfile, ...],
    *, incoming_moves: tuple[int, ...], enemy_level: int | None = None,
    entry_speeds: tuple[int, tuple[int, ...]] | None = None,
    mirror_move_reset_qualified: bool = False,
) -> tuple[PartyMatchupProfile, ...]:
    """Screen ordinary coverage and qualified fixed incoming HP loss.

    Preparation scores only approximate incoming pressure using opponent types.
    Entry screening must also consider coverage moves. Preserve the caller's
    ranking and existing health/PP/level requirements; never call this a survival
    bound. Fixed damage must leave positive HP; ordinary neutral damage,
    criticals, multi-hit and status remain unresolved.
    Unsupported effects reject the screen, rather than becoming zero damage.
    """
    if (not isinstance(incoming_moves, tuple) or len(incoming_moves) != 4
            or any(type(move) is not int or not 0 <= move <= 165 for move in incoming_moves)
            or not any(incoming_moves)):
        raise RedTrainerPartyError("incoming move inventory is unavailable")
    attacking_types = []
    fixed_bound = 0
    if 119 in incoming_moves and mirror_move_reset_qualified is not True:
        raise RedTrainerPartyError("Mirror Move entry requires no committed copied move")
    has_ohko = any(move in (12, 32, 90) for move in incoming_moves)
    if has_ohko and (
        not isinstance(entry_speeds, tuple) or len(entry_speeds) != 2
        or type(entry_speeds[0]) is not int or not 1 <= entry_speeds[0] <= 1023
        or not isinstance(entry_speeds[1], tuple) or len(entry_speeds[1]) != party.size
        or any(type(speed) is not int or not 1 <= speed <= 999 for speed in entry_speeds[1])
    ):
        raise RedTrainerPartyError("OHKO entry requires observed current enemy and party speeds")
    for move in incoming_moves:
        if not move:
            continue
        if move == 119:
            # Switch-entry ONLY: SendOutMon clears both used-move bytes before
            # the reply, so MirrorMoveCopyMove fails. Never a general bound.
            continue
        if move in (12, 32, 90):
            continue  # Per-candidate strict speed predicate below, not zero damage.
        ref = pokemon_red_move_ref(move)
        fixed = RED_BATTLE_CATALOG.incoming_fixed_damage_bound(ref, enemy_level=enemy_level)
        if fixed is not None:
            fixed_bound = max(fixed_bound, fixed)
        else:
            attacking_types.append(RED_BATTLE_CATALOG.switch_entry_attack_type(ref))
    return tuple(candidate for candidate in candidates
                 if (not has_ohko or (entry_speeds is not None
                     and party.members[candidate.party_slot - 1].status is StatusCondition.HEALTHY
                     and entry_speeds[1][candidate.party_slot - 1] > entry_speeds[0]))
                 and party.members[candidate.party_slot - 1].hp > fixed_bound and all(
        attack_type is None or RED_BATTLE_CATALOG.type_effectiveness(
            attack_type, RED_BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(
                party.members[candidate.party_slot - 1].species_id,
            )).types,
        ) <= 1.0 for attack_type in attacking_types
    ))


def trainer_matchup_candidates(
    party: PartyObservation, *, opponent_species: int, opponent_level: int,
    minimum_hp_ratio: float = 0.5,
) -> tuple[PartyMatchupProfile, ...]:
    """Healthy, usable, non-immune matchups within five levels of an opponent.

    The five-level tolerance and shared half-HP floor are disclosed preparation
    heuristics, not calibrated survival bounds. Opponent moves, stats, critical
    hits and switch damage are not predicted here. A later executor must still
    observe every turn. Empty, fixed-damage, status-only and sacrificial moves
    cannot qualify a candidate through this ordinary offensive interface.
    """
    if not isinstance(party, PartyObservation) or not party.members:
        raise RedTrainerPartyError("trainer preparation requires an observed party")
    if minimum_hp_ratio not in (0.0, 0.5):
        raise RedTrainerPartyError("unsupported trainer HP screening mode")
    members: list[dict[str, object]] = []
    for member in party.members:
        moves: list[dict[str, object]] = []
        for move in member.moves:
            if not move.is_known:
                if move.current_pp:
                    raise RedTrainerPartyError("empty move has nonzero PP")
                continue
            ref = pokemon_red_move_ref(move.move_id)
            mechanics = RED_BATTLE_CATALOG.resolve_move(ref)
            if move.current_pp > 63:
                raise RedTrainerPartyError("ordinary move PP exceeds its observed range")
            if mechanics.effect_flags & {"self_destruct", "fixed_damage", "ohko"}:
                continue
            moves.append({"move_ref": ref, "pp": move.current_pp})
        members.append({
            "species_ref": pokemon_red_species_ref(member.species_id),
            "level": member.level, "hp": member.hp, "max_hp": member.max_hp,
            "status": None if member.status is StatusCondition.HEALTHY else member.status.value,
            "moves": moves,
        })
    profiles = project_party_matchups({"features": {
        "party": {"members": members},
        "battle": {"opponent_species_ref": pokemon_red_species_ref(opponent_species),
                   "opponent_level": opponent_level},
    }}, RED_BATTLE_CATALOG)
    return tuple(sorted(
        (profile for profile in profiles if profile.hp_ratio >= minimum_hp_ratio
         and not profile.has_status
         and profile.level_margin >= -0.05 and profile.offensive_power > 0),
        key=PartyMatchupProfile.switch_rank, reverse=True,
    ))


@dataclass(frozen=True, slots=True)
class RedTrainerPartyPlan:
    party: PartyObservation
    quote: TrainerPartyQuote
    matchups: tuple[tuple[PartyMatchupProfile, ...], ...]

    @property
    def lead(self) -> RedCaptureLeadPlan:
        return RedCaptureLeadPlan(self.matchups[0][0].party_slot - 1, self.party)

    def require_current(self, party: PartyObservation, quote: TrainerPartyQuote) -> None:
        """Recompute, so neither a stale roster nor a forged plan may swap."""
        if self != plan_trainer_party(party, quote):
            raise RedTrainerPartyError("trainer party, roster or preparation plan changed")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.trainer-party-preparation.v1",
            "authority": "deterministic-matchup-preparation",
            "opponent_count": len(self.matchups),
            "candidate_counts": [len(candidates) for candidates in self.matchups],
            "opening_party_slot": self.lead.target_index + 1,
            "preferred_party_slots": [candidates[0].party_slot for candidates in self.matchups],
            "requires_lead_swap": self.lead.requires_swap,
            "victory_predicted": False,
            "battle_execution_qualified": False,
            "training_examples": 0,
        }


def plan_trainer_party(party: PartyObservation, quote: TrainerPartyQuote) -> RedTrainerPartyPlan:
    """Require at least one observed matchup per quoted opponent, then plan the lead.

    Multiple opponents can share a candidate. This is *coverage*, not cumulative
    HP/PP sufficiency or a promise that switching during the battle is supported.
    """
    if not isinstance(quote, TrainerPartyQuote) or not 1 <= len(quote.party) <= 6:
        raise RedTrainerPartyError("trainer preparation requires a nonempty bounded roster")
    if not isinstance(party, PartyObservation) or not party.members or party.fainted_count:
        raise RedTrainerPartyError("trainer preparation requires a fully living party")
    matchups = tuple(
        trainer_matchup_candidates(
            party, opponent_species=member.internal_species, opponent_level=member.level,
        ) for member in quote.party
    )
    uncovered = tuple(index + 1 for index, candidates in enumerate(matchups) if not candidates)
    if uncovered:
        raise RedTrainerPartyError(
            f"no qualified offensive matchup for roster positions {uncovered}"
        )
    return RedTrainerPartyPlan(party, quote, matchups)


def prepare_trainer_lead(
    runtime: RedGoalContextRuntime, actions: CountingExecutor, plan: RedTrainerPartyPlan,
    *, current_quote: TrainerPartyQuote,
) -> bool:
    """Execute only the opening field swap; no battle, healing or route input."""
    from .red_capture_preparation import prepare_observed_lead

    if not isinstance(plan, RedTrainerPartyPlan):
        raise TypeError("plan must be a RedTrainerPartyPlan")
    plan.require_current(runtime.adapter.observe().party, current_quote)
    return prepare_observed_lead(
        runtime, actions, plan.lead, label="cartridge-roster matchup lead",
    )
