"""Bind routed Pokémon Center recovery with escort preparation.

Profile may declare FIELD_RESTORE rather than Center restore; this explicit
gameplay mechanic adapter constructs the actual Center provider from runtime
without mutating profile parameters.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from hashlib import sha256
from typing import TYPE_CHECKING

from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
    Gen1WildFleeHandler,
    strongest_usable_move_slot,
)
from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalRecoveryRequired,
    GoalVerification,
)
from pokemon_red_completion.observation import PokemonRedStateReader, RawGameState
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    dependency_specimen_ledger,
)
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_goal_skills import (
    _POKEMON_CENTER_MAPS,
    RedCenterRestoreGoalProvider,
    _raw_party_restored,
    prepare_center_departure,
)
from pokemon_red_completion.red_pc_storage import face_pc_boundary
from pokemon_red_completion.route_1_wild import WildFleeStatusChange
from pokemon_red_completion.route_executor import (
    InterruptionReceipt,
    RouteActionPort,
    RouteExecutionError,
    RouteExecutionFailureReason,
    TraversalSnapshot,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError

if TYPE_CHECKING:
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter


class RedRoutedRecoveryError(RuntimeError):
    """Routed Pokémon Center recovery cannot preserve the party and collection."""


SETTLED_ROUTE_FIELD_RECOVERY_SCHEMA = "pokemon.red.settled-route-field-recovery.v1"


class SettledNativeFieldRecovery(RouteExecutionError, GoalRecoveryRequired):
    """A proved native poison faint settles text but fails the selected route."""

    failure_reason = GoalFailureReason.RECOVERY_REQUIRED

    def __init__(self, report):
        super().__init__("verified field exit needs native faint recovery",
                         reason=RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED)
        self.report = report
        self.evidence = dict(report.evidence)


SETTLED_ROUTE_WILD_RECOVERY_SCHEMA = "pokemon.red.settled-route-wild-recovery.v1"


class SettledNativeWildRecovery(SettledNativeFieldRecovery):
    """A verified wild exit stops the selected route for ordinary recovery."""

    def __init__(self, report):
        RouteExecutionError.__init__(self,
            "verified wild exit needs native party recovery",
            reason=RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED)
        self.report = report
        self.evidence = dict(report.evidence)


def settled_route_wild_recovery_evidence(evidence):
    """Require native whole-party escape, exact damage/status and metered custody."""
    from collections.abc import Mapping
    import re

    if not isinstance(evidence, Mapping):
        return False
    before, hp = evidence.get("party_hp_before"), evidence.get("party_hp")
    slots, wild = evidence.get("new_fainted_slots"), evidence.get("wild_escape")
    if (evidence.get("schema") != SETTLED_ROUTE_WILD_RECOVERY_SCHEMA
        or evidence.get("support") != "native_whole_party_wild_escape"
        or evidence.get("verified") is not True
        or evidence.get("learned_recovery") is not False
        or evidence.get("protected_resources_verified") is not True
        or type(evidence.get("model_queries")) is not int or evidence["model_queries"] != 0
        or not all(isinstance(evidence.get(k), str) and re.fullmatch(r"[0-9a-f]{64}", evidence[k])
                   for k in ("source_sha256", "terminal_sha256"))
        or not all(type(evidence.get(k)) is int and 0 <= evidence[k] <= 999999
                   for k in ("cash_before", "cash_after"))
        or evidence["cash_before"] != evidence["cash_after"]
        or not all(type(evidence.get(k)) is int and evidence[k] > 0 for k in ("actions", "frames"))
        or not isinstance(before, (tuple, list)) or not isinstance(hp, (tuple, list))
        or not 1 <= len(hp) == len(before) <= 6
        or not all(type(v) is int and v >= 0 for v in (*before, *hp))
        or not any(hp) or any(new > old for old, new in zip(before, hp))
        or not isinstance(slots, (tuple, list))
        or not all(type(v) is int for v in slots)
        or list(slots) != [i for i, (old, new) in enumerate(zip(before, hp), 1) if old > 0 and new == 0]
        or not isinstance(wild, Mapping)):
        return False
    changes = wild.get("native_status_changes", ())
    valid_changes = (
        isinstance(changes, (tuple, list))
        and all(isinstance(row, (tuple, list)) and len(row) == 3
                and all(type(v) is int for v in row)
                and 1 <= row[0] <= len(hp) and 0 <= row[1] <= 255
                and 0 <= row[2] <= 255 and row[1] != row[2] for row in changes)
        and len({row[0] for row in changes}) == len(changes)
    )
    attempts = wild.get("run_attempts")
    return (
        (bool(slots) or bool(changes)) and valid_changes
        and all(wild.get(k) is True for k in (
            "verified", "control_ready", "party_preserved", "level_preserved",
            "maximum_hp_preserved", "pp_preserved", "party_faints_allowed"))
        and wild.get("hp_scope") == "whole_party"
        and type(wild.get("initial_battle_state")) is int and wild["initial_battle_state"] == 1
        and type(wild.get("final_battle_state")) is int and wild["final_battle_state"] == 0
        and type(wild.get("initial_hp")) is int and wild["initial_hp"] == sum(before)
        and type(wild.get("final_hp")) is int and wild["final_hp"] == sum(hp)
        and wild.get("new_fainted_slots") == list(slots)
        and (wild.get("status_preserved") is True
             or bool(changes) and wild.get("status_changes_allowed") is True)
        and type(wild.get("map")) is int and wild["map"] == wild.get("expected_map")
        and isinstance(wild.get("position"), (tuple, list)) and len(wild["position"]) == 2
        and all(type(v) is int and v >= 0 for v in wild["position"])
        and type(wild.get("enemy_species_id")) is int and wild["enemy_species_id"] > 0
        and type(wild.get("enemy_level")) is int and wild["enemy_level"] > 0
        and type(wild.get("stabilization_frames")) is int and wild["stabilization_frames"] > 0
        and type(wild.get("battle_result")) is int
        and (wild["battle_result"] == 2 or wild["battle_result"] == 0
             and wild.get("ordinary_opponent_ko_exit") is True)
        and type(attempts) is int and (1 <= attempts <= 16 or attempts == 0
             and (wild.get("faint_prompt_exit") is True
                  or wild["battle_result"] == 0 and wild.get("ordinary_opponent_ko_exit") is True))
        and wild.get("native_purified_healing") is None
    )


def settled_route_field_recovery_evidence(evidence):
    from collections.abc import Mapping
    import re

    if not isinstance(evidence, Mapping):
        return False
    if evidence.get("schema") == SETTLED_ROUTE_WILD_RECOVERY_SCHEMA:
        return settled_route_wild_recovery_evidence(evidence)
    hp, slots = evidence.get("party_hp"), evidence.get("new_fainted_slots")
    return (
        evidence.get("schema") == SETTLED_ROUTE_FIELD_RECOVERY_SCHEMA
        and evidence.get("verified") is True
        and evidence.get("support") == "native_field_poison_faint"
        and evidence.get("learned_recovery") is False
        and evidence.get("protected_resources_verified") is True
        and type(evidence.get("model_queries")) is int and evidence["model_queries"] == 0
        and all(isinstance(evidence.get(key), str)
                and re.fullmatch(r"[0-9a-f]{64}", evidence[key])
                for key in ("source_sha256", "terminal_sha256"))
        and all(type(evidence.get(key)) is int and 0 <= evidence[key] <= 999999
                for key in ("cash_before", "cash_after"))
        and evidence["cash_before"] == evidence["cash_after"]
        and all(type(evidence.get(key)) is int and evidence[key] > 0
                for key in ("actions", "frames"))
        and isinstance(hp, (tuple, list)) and 1 <= len(hp) <= 6
        and all(type(value) is int and value >= 0 for value in hp)
        and any(value > 0 for value in hp)
        and isinstance(slots, (tuple, list)) and 1 <= len(slots) <= len(hp)
        and all(type(slot) is int and 1 <= slot <= len(hp) and hp[slot - 1] == 0
                for slot in slots)
        and len(set(slots)) == len(slots)
    )


def guarded_collection_route_handler(
    actions: RouteActionPort,
    reader: PokemonRedStateReader,
    *,
    route_name: str,
    maximum_flees: int = 16,
    maximum_scripted_dialogues: int = 0,
    allow_wild_faints: bool = False,
    allow_field_faints: bool = False,
    emulator: object | None = None,
) -> RecoveryRouteInterruptionHandler:
    """Bind protected living slots from the actual prepared party, not old indices."""
    raw = reader.read()
    return RecoveryRouteInterruptionHandler(
        actions, reader,
        post_prep_species=tuple(raw.party_species_ids or ()),
        post_prep_living_slots=tuple(i for i, hp in enumerate(raw.party_hp or ()) if hp > 0),
        maximum_flees=maximum_flees,
        maximum_scripted_dialogues=maximum_scripted_dialogues,
        route_name=route_name,
        allow_wild_faints=allow_wild_faints,
        allow_field_faints=allow_field_faints,
        emulator=emulator,
    )


@dataclass(slots=True)
class RecoveryRouteInterruptionHandler:
    """Resolve interruptions and halt if a new faint occurs or field is unsettled."""

    executor: RouteActionPort
    reader: PokemonRedStateReader
    post_prep_species: tuple[int, ...]
    post_prep_living_slots: tuple[int, ...]
    maximum_flees: int = 16
    maximum_trainer_battles: int = 8
    maximum_scripted_dialogues: int = 0
    stabilization_frames: int = 180
    route_name: str = "bounded routed recovery transport"
    inner: Gen1RouteInterruptionHandler | None = None
    verified_trainer_income: int = 0
    allow_wild_faints: bool = False
    emulator: object | None = None
    allow_field_faints: bool = False
    _field_faint: Gen1WildFleeHandler | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.allow_wild_faints) is not bool:
            raise TypeError("wild faint recovery opt-in must be boolean")
        if self.allow_wild_faints and self.emulator is None:
            raise ValueError("wild faint recovery requires its native emulator")
        if type(self.allow_field_faints) is not bool:
            raise TypeError("field faint recovery opt-in must be boolean")
        if self.allow_field_faints:
            if self.emulator is None:
                raise ValueError("field faint recovery requires its native emulator")
            self._field_faint = Gen1WildFleeHandler(
                self.executor, self.reader, maximum_flees=0,
                stabilization_frames=self.stabilization_frames,
                route_name=self.route_name, allow_party_faints=True,
                allow_field_faint_dialogue=True, emulator=self.emulator,
            )
        if self.inner is None:
            self.inner = Gen1RouteInterruptionHandler(
                self.executor,
                self.reader,
                maximum_flees=self.maximum_flees,
                maximum_trainer_battles=self.maximum_trainer_battles,
                maximum_scripted_dialogues=self.maximum_scripted_dialogues,
                stabilization_frames=self.stabilization_frames,
                route_name=self.route_name,
                move_slot_policy=self._safe_trainer_move,
                allow_wild_faints=self.allow_wild_faints,
                emulator=self.emulator if self.allow_wild_faints else None,
            )

    @property
    def handled_hazard_kinds(self) -> frozenset[str]:
        assert self.inner is not None
        return self.inner.handled_hazard_kinds

    @property
    def handled_interruption_kinds(self) -> frozenset[str]:
        assert self.inner is not None
        kinds = self.inner.handled_interruption_kinds
        return kinds | frozenset({"scripted_dialogue"}) if self.allow_field_faints else kinds

    def observe_native_field_boundary(self) -> None:
        from .route_executor import observe_native_field_boundary

        assert self.inner is not None
        observe_native_field_boundary(self.inner)
        if self._field_faint is not None:
            self._field_faint.observe_native_field_boundary()

    def handle(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        assert self.inner is not None
        current = self.reader.read()
        before_money = current.player_money
        new_field_faint = (
            interruption.interruption == "scripted_dialogue"
            and self._field_faint is not None
            and self._field_faint.has_new_field_faint(current)
        )
        wild_source = None
        if (self.allow_wild_faints and interruption.interruption == "wild_battle"
            and callable(getattr(self.emulator, "save_state_bytes", None))):
            wild_source = (sha256(self.emulator.save_state_bytes()).hexdigest(),
                           self.executor.actions_executed, self.emulator.frame_count)
        field_source = None
        if new_field_faint:
            field_source = (sha256(self.emulator.save_state_bytes()).hexdigest(),
                            self.executor.actions_executed, self.emulator.frame_count)
        try:
            # Reuse the strict poison-faint/custody check before text dismissal.
            # Generic dialogue is not evidence that a faint was legitimate.
            receipt = (self._field_faint.handle(interruption) if new_field_faint
                       else self.inner.handle(interruption))
        except RouteExecutionError as error:
            cause = error.__cause__
            if not isinstance(cause, WildFleeStatusChange):
                raise
            raw = self.reader.read()
            if raw != cause.after or not self.reader.read_input_readiness().ready:
                raise RedRoutedRecoveryError(
                    "status recovery terminal changed before handoff"
                ) from error
            self._require_preserved_living_slots(raw)
            raise GoalRecoveryRequired("verified wild exit needs party status recovery") from error
        raw = self.reader.read()
        if raw.player_money != before_money:
            if (
                type(before_money) is not int or type(raw.player_money) is not int
                or raw.player_money < before_money
                or receipt.kind != "trainer_engagement"
                or receipt.details.get("verified") is not True
                or receipt.details.get("battle_started") is not True
            ):
                raise RedRoutedRecoveryError("route interruption changed unverified money")
            self.verified_trainer_income += raw.player_money - before_money
        readiness = self.reader.read_input_readiness()
        if raw.battle_state != 0 or not readiness.ready:
            from .route_executor import _pending_verified_interruption

            observed = Gen1TraversalObserver(self.reader).observe()
            if not (
                _pending_verified_interruption(receipt, observed)
                and observed.interruption in self.handled_interruption_kinds
                and (observed.map_id, observed.at)
                == (receipt.resumed_map, receipt.resumed_at)
                == (interruption.map_id, interruption.at)
            ):
                raise RedRoutedRecoveryError("field not settled after route interruption")
        verified_field_faint = (
            new_field_faint and receipt.kind == "scripted_dialogue"
            and receipt.details.get("verified") is True
            and receipt.details.get("native_field_faint") is True
        )
        if verified_field_faint:
            record = getattr(self.executor, "record_diagnostic_event", None)
            if callable(record):
                record("collection_native_field_faint", dict(
                    actor="rule_based_support",
                    resumed_map=receipt.resumed_map, resumed_at=receipt.resumed_at,
                    **receipt.details,
                ))
        try:
            self._require_preserved_living_slots(
                raw, allow_faint_recovery=(verified_field_faint or
                    self.allow_wild_faints and receipt.kind == "wild_battle")
            )
        except GoalRecoveryRequired:
            if not verified_field_faint:
                report = self._wild_recovery_report(current, raw, receipt, wild_source)
                if report is not None:
                    raise SettledNativeWildRecovery(report) from None
                raise
            source_sha, start_actions, start_frames = field_source
            actions = self.executor.actions_executed - start_actions
            frames = self.emulator.frame_count - start_frames
            evidence = dict(
                schema=SETTLED_ROUTE_FIELD_RECOVERY_SCHEMA, verified=True,
                support="native_field_poison_faint", learned_recovery=False,
                model_queries=0, protected_resources_verified=True,
                source_sha256=source_sha,
                terminal_sha256=sha256(self.emulator.save_state_bytes()).hexdigest(),
                cash_before=before_money, cash_after=raw.player_money,
                actions=actions, frames=frames, party_hp=list(raw.party_hp),
                new_fainted_slots=list(receipt.details["new_fainted_slots"]),
            )
            if not settled_route_field_recovery_evidence(evidence):
                raise RedRoutedRecoveryError("field faint lacks metered native recovery proof")
            raise SettledNativeFieldRecovery(GoalExecutionReport(actions, frames, evidence)) from None
        if (self._field_faint is not None and raw.battle_state == 0 and readiness.ready
                and not self.reader.read_bottom_dialogue_box_visible()
                and not self.reader.trainer_engagement_active()):
            self.observe_native_field_boundary()
        if self.allow_wild_faints and receipt.kind == "wild_battle" and (
            receipt.details.get("native_status_changes")
        ):
            report = self._wild_recovery_report(current, raw, receipt, wild_source)
            if report is not None:
                raise SettledNativeWildRecovery(report) from None
            raise GoalRecoveryRequired("verified wild exit needs party status recovery")
        return receipt

    def _wild_recovery_report(self, before, after, receipt, source):
        if (source is None or not self.allow_wild_faints or receipt.kind != "wild_battle"
            or after.battle_state != 0 or not self.reader.read_input_readiness().ready
            or self.emulator.pressed_buttons
            or (after.map_id, (after.player_y, after.player_x))
               != (receipt.resumed_map, receipt.resumed_at)
            or any(getattr(before, key) != getattr(after, key) for key in (
                "player_money", "bag_items", "badge_bits", "event_flags", "party_count",
                "party_species_ids", "party_levels", "party_max_hp", "party_stats", "party_moves", "party_pp"))):
            return None
        source_sha, start_actions, start_frames = source
        actions = self.executor.actions_executed - start_actions
        frames = self.emulator.frame_count - start_frames
        evidence = dict(schema=SETTLED_ROUTE_WILD_RECOVERY_SCHEMA, verified=True,
            support="native_whole_party_wild_escape", learned_recovery=False,
            model_queries=0, protected_resources_verified=True,
            source_sha256=source_sha,
            terminal_sha256=sha256(self.emulator.save_state_bytes()).hexdigest(),
            cash_before=before.player_money, cash_after=after.player_money,
            actions=actions, frames=frames, party_hp_before=list(before.party_hp or ()),
            party_hp=list(after.party_hp or ()),
            new_fainted_slots=[i for i, (old, hp) in enumerate(
                zip(before.party_hp or (), after.party_hp or ()), 1) if old > 0 and hp == 0],
            wild_escape=dict(receipt.details))
        if not settled_route_wild_recovery_evidence(evidence):
            return None
        return GoalExecutionReport(actions, frames, evidence)


    def _require_preserved_living_slots(
        self, raw: RawGameState, *, allow_faint_recovery: bool = False
    ) -> None:
        current_species = tuple(raw.party_species_ids or ())
        current_hp = tuple(raw.party_hp or ())
        if (
            raw.party_count != len(self.post_prep_species)
            or len(current_species) != len(self.post_prep_species)
            or len(current_hp) != len(self.post_prep_species)
        ):
            raise RedRoutedRecoveryError(
                "party roster truncated or changed during route interruption"
            )
        if current_species != self.post_prep_species:
            raise RedRoutedRecoveryError(
                "party species changed during route interruption"
            )
        for slot in self.post_prep_living_slots:
            if current_hp[slot] <= 0:
                if allow_faint_recovery and any(hp > 0 for hp in current_hp):
                    raise GoalRecoveryRequired("verified route exit needs native faint recovery")
                raise RedRoutedRecoveryError(
                    f"party slot {slot} fainted during route interruption"
                )

    def _safe_trainer_move(self, raw: RawGameState) -> int:
        """Use the existing battle ranker without permitting sacrificial moves."""
        self._require_preserved_living_slots(raw)
        if raw.battler_moves is None or raw.battler_pp is None:
            raise RedRoutedRecoveryError("route battle lacks observed move/PP state")
        safe_pp = []
        for move_id, pp in zip(raw.battler_moves, raw.battler_pp, strict=True):
            allowed = False
            if move_id and pp & 0x3F:
                move = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move_id))
                allowed = (
                    move.category != "status" and move.power > 0
                    and "self_destruct" not in move.effect_flags
                )
            safe_pp.append(pp if allowed else 0)
        if not any(pp & 0x3F for pp in safe_pp):
            raise RedRoutedRecoveryError("route battle has no sustainable offensive move")
        return strongest_usable_move_slot(replace(raw, active_party_pp=tuple(safe_pp)))


def _is_at_nurse_boundary(raw: RawGameState) -> bool:
    return (
        raw.map_id in _POKEMON_CENTER_MAPS
        and raw.player_x == 3
        and raw.player_y is not None
        and 3 <= raw.player_y <= 7
    )


def _party_needs_recovery(observation: RedGoalObservation) -> bool:
    return (
        bool(observation.party.members)
        and observation.evidence.safety < 1.0
        and not _raw_party_restored(observation.raw)
    )


def _member_facts(
    raw: RawGameState,
) -> tuple[tuple[object, ...], ...]:
    species = raw.party_species_ids or ()
    hps = raw.party_hp or ()
    max_hps = raw.party_max_hp or ()
    statuses = raw.party_status or ()
    try:
        facts = tuple(zip(
            species, hps, max_hps, statuses, raw.party_levels or (),
            raw.party_moves or (), raw.party_pp or (), strict=True,
        ))
    except ValueError as error:
        raise RedRoutedRecoveryError("incomplete party state") from error
    if len(facts) != raw.party_count:
        raise RedRoutedRecoveryError("party count disagrees with member records")
    return facts


def _make_center_provider(
    router: RedResourceGoalRouter,
) -> RedCenterRestoreGoalProvider:
    runtime = router.runtime
    return RedCenterRestoreGoalProvider(
        actions=router.actions,
        reader=runtime.reader,
        emulator=runtime.emulator,
        adapter=runtime.adapter,
    )


def bind_routed_center_recovery(
    router: RedResourceGoalRouter,
    bindings: GoalBindingSet,
    observation: RedGoalObservation,
    *,
    prepare_escort: Callable[[], None],
    require_pp_restore: bool = False,
) -> GoalBindingSet:
    """Action-free route offer to a Pokémon Center nurse boundary.

    Creates or replaces an unavailable RESTORE_TEAM goal only. Never overwrites
    an existing available restore skill and leaves other goals unchanged.
    """
    if type(require_pp_restore) is not bool:
        raise ValueError("explicit PP recovery mode must be boolean")
    if not require_pp_restore and any(b.kind is GoalKind.RESTORE_TEAM for b in bindings.bindings):
        return bindings

    if not observation.input_ready or bool(observation.raw.battle_state):
        return bindings
    if not _party_needs_recovery(observation) and not (
        require_pp_restore and not _raw_party_restored(observation.raw)
    ):
        return bindings

    from pokemon_red_completion.red_resource_goal_router import (
        _ROUTE_LIMITS,
        _walking_plan,
    )

    traversal = Gen1TraversalObserver(router.runtime.reader)
    start = traversal.observe()
    at_boundary = _is_at_nurse_boundary(observation.raw)

    route: RoutePlan | None = None
    if at_boundary:
        route = None
    else:
        routes: list[RoutePlan] = []
        centers = ((observation.raw.map_id,) if observation.raw.map_id in _POKEMON_CENTER_MAPS
                   else sorted(_POKEMON_CENTER_MAPS))
        for center in centers:
            try:
                plan = router.world.plan_feasible_to_map(
                    start, int(center), goal_at=(7, 3)
                )
            except RoutePlanningError:
                continue
            if plan is not None and _walking_plan(plan):
                routes.append(plan)
        if not routes:
            from pokemon_red_completion.red_dig_recovery import bind_dig_recovery

            return bind_dig_recovery(
                router, bindings, observation, start, prepare_escort=prepare_escort,
                require_pp_restore=require_pp_restore,
            )
        route = min(routes, key=lambda r: (len(r.steps), r.terminal_map))
        if len(route.steps) == 0 and not at_boundary:
            return bindings

    claimed = False
    executed: list[tuple[ExecutableGoalBinding, GoalExecutionReport]] = []

    start_traversal = start
    start_bag = observation.raw.bag_items
    start_money = observation.raw.player_money
    start_ledger = dependency_specimen_ledger(observation.collection_observation)
    start_party_hp = tuple(observation.raw.party_hp or ())
    start_party_status = tuple(observation.raw.party_status or ())
    start_party_species = tuple(observation.raw.party_species_ids or ())
    start_party_moves = tuple(observation.raw.party_moves or ())
    start_party_pp = tuple(observation.raw.party_pp or ())

    post_prep_hp: tuple[int, ...] = start_party_hp
    post_prep_status: tuple[int, ...] = start_party_status
    post_prep_pp: tuple[tuple[int, ...], ...] = start_party_pp
    route_income = 0

    def execute() -> GoalExecutionReport:
        nonlocal claimed, post_prep_hp, post_prep_status, post_prep_pp, route_income
        if claimed:
            raise RedRoutedRecoveryError(
                "routed center recovery binding was already consumed"
            )
        claimed = True

        current = router.runtime.adapter.observe()
        current_traversal = traversal.observe()

        if current_traversal != start_traversal:
            raise RedRoutedRecoveryError(
                "starting traversal changed before execution"
            )
        if current.raw.battle_state != 0 or not current.input_ready:
            raise RedRoutedRecoveryError("starting state not ready for input")
        if current.raw.bag_items != start_bag:
            raise RedRoutedRecoveryError("bag items changed before execution")
        if current.raw.player_money != start_money:
            raise RedRoutedRecoveryError(
                "player money changed before execution"
            )
        if dependency_specimen_ledger(current.collection_observation) != start_ledger:
            raise RedRoutedRecoveryError(
                "living collection ledger changed before execution"
            )
        if (
            current.party != observation.party
            or _member_facts(current.raw) != _member_facts(observation.raw)
            or tuple(current.raw.party_hp or ()) != start_party_hp
            or tuple(current.raw.party_status or ()) != start_party_status
            or tuple(current.raw.party_species_ids or ()) != start_party_species
            or tuple(current.raw.party_moves or ()) != start_party_moves
            or tuple(current.raw.party_pp or ()) != start_party_pp
        ):
            raise RedRoutedRecoveryError("party state changed before execution")

        action_start = router.actions.actions_executed
        frame_start = router.runtime.emulator.frame_count

        prepare_escort()

        after_prep = router.runtime.adapter.observe()
        after_prep_traversal = traversal.observe()

        if after_prep.raw.battle_state != 0 or not after_prep.input_ready:
            raise RedRoutedRecoveryError(
                "field not settled after escort preparation"
            )
        if (
            after_prep_traversal.map_id, after_prep_traversal.at, after_prep_traversal.mode
        ) != (start.map_id, start.at, start.mode):
            raise RedRoutedRecoveryError("escort preparation moved the player")
        if (
            dependency_specimen_ledger(after_prep.collection_observation)
            != start_ledger
        ):
            raise RedRoutedRecoveryError(
                "escort preparation changed living collection ledger"
            )
        if after_prep.raw.bag_items != start_bag:
            raise RedRoutedRecoveryError("escort preparation changed bag items")
        if after_prep.raw.player_money != start_money:
            raise RedRoutedRecoveryError(
                "escort preparation changed player money"
            )

        if Counter(_member_facts(current.raw)) != Counter(
            _member_facts(after_prep.raw)
        ):
            raise RedRoutedRecoveryError(
                "escort preparation altered member health or identity"
            )

        post_prep_species = tuple(after_prep.raw.party_species_ids or ())
        post_prep_hp = tuple(after_prep.raw.party_hp or ())
        post_prep_status = tuple(after_prep.raw.party_status or ())
        post_prep_pp = tuple(tuple(p) for p in (after_prep.raw.party_pp or ()))
        post_prep_living_slots = tuple(
            i for i, hp in enumerate(post_prep_hp) if hp > 0
        )

        if not _is_at_nurse_boundary(after_prep.raw):
            active_route = route
            if (
                active_route is None
                or active_route.macro_path.maps[0] != after_prep_traversal.map_id
                or active_route.start_at != after_prep_traversal.at
            ):
                fresh_routes: list[RoutePlan] = []
                for center in sorted(_POKEMON_CENTER_MAPS):
                    try:
                        fresh_plan = router.world.plan_feasible_to_map(
                            after_prep_traversal, int(center), goal_at=(7, 3)
                        )
                    except RoutePlanningError:
                        continue
                    if fresh_plan is not None and _walking_plan(fresh_plan):
                        fresh_routes.append(fresh_plan)
                if not fresh_routes:
                    raise RedRoutedRecoveryError(
                        "no walking route to Center after escort preparation"
                    )
                active_route = min(
                    fresh_routes, key=lambda r: (len(r.steps), r.terminal_map)
                )

            if active_route is not None and len(active_route.steps) > 0:
                prepare_center_departure(router.actions, router.runtime.reader)
                interruption_handler = RecoveryRouteInterruptionHandler(
                    router.actions,
                    router.runtime.reader,
                    post_prep_species=post_prep_species,
                    post_prep_living_slots=post_prep_living_slots,
                    route_name="bounded routed recovery transport",
                )
                try:
                    transport = execute_route(
                        active_route,
                        router.actions,
                        traversal,
                        interruption_handler=interruption_handler,
                        replanner=router._replan,
                        limits=_ROUTE_LIMITS,
                    )
                except RouteExecutionError as error:
                    raise RedRoutedRecoveryError(
                        f"transport failed: {error}"
                    ) from error
                if not transport.passed:
                    raise RedRoutedRecoveryError("Center transport route failed")
                route_income = interruption_handler.verified_trainer_income

        at_nurse_obs = router.runtime.adapter.observe()
        raw_nurse = at_nurse_obs.raw
        if (
            not _is_at_nurse_boundary(raw_nurse)
            or raw_nurse.battle_state != 0
            or not at_nurse_obs.input_ready
        ):
            raise RedRoutedRecoveryError("not at verified Center nurse boundary")

        if (raw_nurse.player_x, raw_nurse.player_y) == (3, 3):
            face_pc_boundary(router.actions, router.runtime.reader, "up")

        center_provider = _make_center_provider(router)
        if require_pp_restore:
            center_provider = replace(center_provider, require_pp_restore=True)
        center_offer = center_provider.offer(at_nurse_obs)
        if center_offer.binding is None:
            raise RedRoutedRecoveryError(
                "Center restore offer unavailable at nurse boundary"
            )

        heal_report = center_offer.binding.execute()
        executed.append((center_offer.binding, heal_report))

        actions_executed = router.actions.actions_executed - action_start
        frames_executed = router.runtime.emulator.frame_count - frame_start
        return GoalExecutionReport(
            actions_executed=actions_executed,
            frames_executed=frames_executed,
            evidence={
                **heal_report.evidence,
                "routed_recovery": {
                    "escort_prepared": True,
                    "center_map_id": raw_nurse.map_id,
                    "actions_executed": actions_executed,
                    "frames_executed": frames_executed,
                    "verified_trainer_income": route_income,
                },
            },
        )

    def verify(report: GoalExecutionReport) -> GoalVerification:
        if len(executed) != 1:
            raise RedRoutedRecoveryError(
                "recovery has no completed underlying execution"
            )
        underlying_binding, underlying_report = executed[0]

        underlying_verif = underlying_binding.verify(underlying_report)
        if underlying_verif.status is not GoalDecisionOutcome.SUCCEEDED:
            return GoalVerification.failed(
                underlying_verif.failure_reason
                or GoalFailureReason.OUTCOME_NOT_VERIFIED
            )

        final_obs = router.runtime.adapter.observe()
        final_raw = final_obs.raw

        if (
            final_raw.map_id not in _POKEMON_CENTER_MAPS
            or final_raw.player_x != 3
            or final_raw.player_y is None
            or not (3 <= final_raw.player_y <= 7)
            or final_raw.battle_state != 0
            or not final_obs.input_ready
        ):
            return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)

        if dependency_specimen_ledger(final_obs.collection_observation) != start_ledger:
            return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)

        if final_raw.bag_items != start_bag:
            return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
        if route_income and type(start_money) is not int:
            return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
        expected_money = start_money + route_income if route_income else start_money
        if final_raw.player_money != expected_money:
            return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)

        if not _raw_party_restored(final_raw):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

        final_hp = tuple(final_raw.party_hp or ())
        final_status = tuple(final_raw.party_status or ())
        final_pp = tuple(tuple(p) for p in (final_raw.party_pp or ()))

        hp_needed = post_prep_hp != tuple(final_raw.party_max_hp or ())
        status_needed = any(s != 0 for s in post_prep_status)

        if hp_needed and final_hp == post_prep_hp:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if status_needed and final_status == post_prep_status:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if (final_hp, final_status, final_pp) == (
            post_prep_hp,
            post_prep_status,
            post_prep_pp,
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

        if report.actions_executed <= 0:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

        return GoalVerification.succeeded()

    if route is None or len(route.steps) == 0:
        target_map = observation.raw.map_id
        steps_count = 0
        effort = 0.04
        risk = 0.01
    else:
        target_map = route.terminal_map
        steps_count = len(route.steps)
        effort = min(1.0, 0.04 + 0.10 + steps_count / 1_000)
        risk = 0.05

    binding_ref = (
        f"pokemon.red:recovery:routed-center:"
        f"{canonical_sha256({'target_map': target_map, 'steps': steps_count})}"
    )

    supported = ExecutableGoalBinding(
        binding_ref=binding_ref,
        kind=GoalKind.RESTORE_TEAM,
        estimated_effort=effort,
        estimated_risk=risk,
        execute=execute,
        verify=verify,
    )

    has_restore_opp = any(
        opp.kind is GoalKind.RESTORE_TEAM for opp in bindings.opportunities
    )
    if has_restore_opp:
        new_opportunities = tuple(
            supported.opportunity if opp.kind is GoalKind.RESTORE_TEAM else opp
            for opp in bindings.opportunities
        )
    else:
        new_opportunities = (*bindings.opportunities, supported.opportunity)

    new_bindings = tuple(
        b for b in bindings.bindings if b.kind is not GoalKind.RESTORE_TEAM
    ) + (supported,)
    return GoalBindingSet(new_opportunities, new_bindings)
