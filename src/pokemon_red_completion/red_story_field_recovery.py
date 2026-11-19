"""Return a verified native field faint to the model without choosing its recovery."""
from hashlib import sha256

from .goal_manager_runtime import GoalExecutionReport
from .red_routed_recovery import (
    SETTLED_ROUTE_FIELD_RECOVERY_SCHEMA, SettledNativeFieldRecovery,
    settled_route_field_recovery_evidence,
)


class NativeFieldFaintStop:
    """Keep the existing route handler; stop only after its strict faint certificate."""

    def __init__(self, inner, actions, reader, emulator):
        self.inner, self.actions, self.reader, self.emulator = inner, actions, reader, emulator

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def handle(self, interruption):
        state = self.emulator.save_state_bytes()
        a, f = self.actions.actions_executed, self.emulator.frame_count
        cash = self.reader.read().player_money
        receipt = self.inner.handle(interruption)
        if receipt.details.get("native_field_faint") is not True:
            return receipt
        after = self.reader.read()
        terminal = self.emulator.save_state_bytes()
        evidence = dict(
            schema=SETTLED_ROUTE_FIELD_RECOVERY_SCHEMA, verified=True,
            support="native_field_poison_faint", learned_recovery=False, model_queries=0,
            protected_resources_verified=True,
            source_sha256=sha256(state).hexdigest(), terminal_sha256=sha256(terminal).hexdigest(),
            cash_before=cash, cash_after=after.player_money,
            actions=self.actions.actions_executed-a, frames=self.emulator.frame_count-f,
            party_hp=list(after.party_hp or ()),
            new_fainted_slots=receipt.details.get("new_fainted_slots"),
        )
        if receipt.details.get("verified") is not True or not settled_route_field_recovery_evidence(evidence):
            raise RuntimeError("native field faint lacks its verified metered certificate")
        raise SettledNativeFieldRecovery(GoalExecutionReport(evidence["actions"], evidence["frames"], evidence))


def certify_story_field_recovery(recovery, before, after, source, terminal, objective):
    """Keep a failed travel receipt only with unchanged custody and protected resources."""
    cert = dict(recovery.report.evidence)
    if (
        type(recovery) is not SettledNativeFieldRecovery
        or not settled_route_field_recovery_evidence(cert)
        or cert["terminal_sha256"] != sha256(terminal).hexdigest()
        or after.party_hp != tuple(cert["party_hp"])
        or any(getattr(before, k) != getattr(after, k) for k in (
            "player_money", "bag_items", "badge_bits", "event_flags", "party_count",
            "party_species_ids", "party_levels", "party_max_hp", "party_stats", "party_pp", "party_moves",
        ))
    ):
        raise RuntimeError("native story field faint changed protected resources")
    return dict(
        schema="pokemon.red.story-field-recovery.v1", objective=objective,
        objective_completed=False, support="native_story_field_faint", automatic_objectives=[],
        purchases=0, trainer_battles=0,
        source_sha256=sha256(source).hexdigest(), terminal_sha256=sha256(terminal).hexdigest(),
        native_story_field_recovery=cert,
    )
