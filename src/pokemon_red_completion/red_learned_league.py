"""Explicit zero-item K qualification adapter; not default League promotion."""

from __future__ import annotations

from dataclasses import dataclass, field

from .observation import MapId
from .red_league_field_recovery import LeagueFieldRecovery
from .red_learned_trainer import FROZEN_K_SHA256, K_QUALIFICATION_SHA256, FrozenTrainerBattler


@dataclass
class FrozenLeagueController:
    battler: FrozenTrainerBattler
    recovery_contract: str = "strict-no-faint-v1"
    allow_immune_switch_recovery: bool = False
    field_recovery: LeagueFieldRecovery | None = None
    maximum_switches: int = field(default=80, init=False)
    heals_claimed: int = field(default=0, init=False)
    moves_selected: int = field(default=0, init=False)
    switches: list[object] = field(default_factory=list, init=False)

    def require_identity(self):
        if self.field_recovery is not None and (
            not isinstance(self.field_recovery, LeagueFieldRecovery)
            or self.recovery_contract != "league-profit-recovery-v1"
        ):
            raise ValueError("field recovery requires explicit recoverable-faints contract")
        if type(self.allow_immune_switch_recovery) is not bool or (
            self.allow_immune_switch_recovery
            and self.recovery_contract != "league-profit-recovery-v1"
        ):
            raise ValueError("immune recovery requires an explicit recoverable-faints contract")
        if self.recovery_contract not in {"strict-no-faint-v1", "league-profit-recovery-v1"}:
            raise ValueError("unknown League recovery contract")
        if (
            self.battler.model_sha256 != FROZEN_K_SHA256
            or self.battler.qualification_sha256 != K_QUALIFICATION_SHA256
        ):
            raise ValueError("League qualification requires exact receipt-bound K")

    def require_party_hp(self, raw):
        """Recoverable faints are permitted only under the explicit new contract."""
        hp = raw.party_hp
        if (
            type(raw.party_count) is not int
            or not 1 <= raw.party_count <= 6
            or hp is None
            or len(hp) != raw.party_count
            or any(type(value) is not int or value < 0 for value in hp)
            or not any(value > 0 for value in hp)
            or (self.recovery_contract == "strict-no-faint-v1" and any(value == 0 for value in hp))
        ):
            raise ValueError("League party HP invalid or outside recovery contract")

    def run(
        self,
        reader,
        executor,
        move_slot_policy,
        *,
        expected_map,
        intent,
        timing,
        label,
        consume_battle_start_schedule,
        move_decision_guard,
        battle_exit_guard=None,
    ):
        self.require_identity()
        allowed = {
            "defeat_lorelei": MapId.LORELEIS_ROOM,
            "defeat_bruno": MapId.BRUNOS_ROOM,
            "defeat_agatha": MapId.AGATHAS_ROOM,
            "defeat_lance": MapId.LANCES_ROOM,
            "defeat_champion": MapId.CHAMPIONS_ROOM,
        }
        if (
            consume_battle_start_schedule
            or intent.battle_plan_id not in {"cartridge-trainer-story", "cartridge-final-story"}
            or allowed.get(intent.objective_id) != expected_map
        ):
            raise ValueError("League actor received an undeclared battle boundary")
        # The supplied teacher policy is never invoked, including on failure.
        self.moves_selected = 0
        self.switches.clear()
        episode = self.battler._play(
            reader,
            executor,
            expected_map=int(expected_map),
            timing=timing,
            label=label,
            decision_guard=move_decision_guard,
            resume=False,
            require_win=True,
            authority="frozen-k-league-development",
            allow_immune_switch_recovery=self.allow_immune_switch_recovery,
        )
        # Detailed attack/switch counts remain in the authenticated episode log.
        self.moves_selected += sum(d.get("kind") == "attack" for d in episode.decisions)
        self.switches.extend(
            d
            for d in episode.decisions
            if d.get("kind") in {"voluntary_switch", "forced_switch", "switch_prompt"}
        )
        raw = reader.read()
        if battle_exit_guard is not None:
            battle_exit_guard(raw)
        return raw


def learned_league_controller(runtime):
    controller = getattr(runtime, "league_battle_controller", None)
    if controller is not None:
        if not isinstance(controller, FrozenLeagueController):
            raise ValueError("League actor must be the explicit frozen K adapter")
        controller.require_identity()
    return controller
