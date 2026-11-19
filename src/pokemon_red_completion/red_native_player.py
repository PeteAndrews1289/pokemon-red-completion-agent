"""Bounded native assembly of the existing continuous goal loop.

No ROM opening, reset, source selection, fit or model promotion. The caller
authenticates source/partition and supplies the existing runtime and observed
battle history. One guarded action port is shared across all goals and verifiers.
"""

import math
import json
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path

from .bootstrap import DEFAULT_NEW_GAME_TIMING
from .executor import (
    CountingExecutor,
    MonotonicWallTimeBudgetController,
    NativeLessonController,
    RestorationBudgetExhausted,
)
from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalVerification
from .goal_search_memory import GoalSearchMemory
from .post_battle_strategy import BattleAftermath
from .provenance import canonical_sha256
from .red_autonomous_player import AutonomousSnapshot, _record, _write, run_autonomous_options
from .red_integrated_play import settled_player_boundary
from .red_player_curriculum import NativePlayerCurriculum, PlayerCurriculumCompletion
from .red_player_lesson import capture_player_lesson_snapshot
from .red_player_lesson_runtime import (
    _RecordedActions,
    observe_native_player_options,
    player_diagnostic_state,
)
from .red_player_party_guard import RedPlayerPartyGuard
from .red_player_support import PlayerBudgetStop, RedPlayerSupport


@dataclass(frozen=True)
class NativeExecutionIdentity:
    """Path-free experiment identity; never part of a policy feature vector."""

    run_id: str
    arm_id: str
    model_sha256: str
    seed: int

    def __post_init__(self):
        for value in (self.run_id, self.arm_id):
            if (
                not isinstance(value, str)
                or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}", value) is None
            ):
                raise ValueError("native execution needs explicit path-free run and arm IDs")
        if (
            not isinstance(self.model_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.model_sha256) is None
        ):
            raise ValueError("native execution model digest differs")
        if type(self.seed) is not int or not 0 <= self.seed < 2**64:
            raise ValueError("native execution seed must be an unsigned 64-bit integer")

    @property
    def claim_id(self):
        return "rnp-execution-" + canonical_sha256(asdict(self))


@dataclass(frozen=True)
class NativePlayerLimits:
    """Declared finite episode bounds, not an artificial short-trial ceiling."""

    decisions: int = 6
    actions: int = 3000
    frames: int = 300000
    seconds: int = 300
    heals: int = 6
    # None explicitly opts into ordinary-game economy, retaining actual costs.
    cash_debits: int | None = 0

    def __post_init__(self):
        for name in ("decisions", "actions", "frames", "seconds"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError("native player requires positive integer limits")
        if self.cash_debits is not None and (
            type(self.cash_debits) is not int or self.cash_debits < 0
        ):
            raise ValueError("native player decision/cash limit differs")
        if type(self.heals) is not int or self.heals < 0:
            raise ValueError("native player healing limit must be nonnegative")


class NativePlayerActions(CountingExecutor):
    """One metered input port, including nested restoration prerequisites."""

    def __init__(
        self,
        delegate,
        restoration,
        training_healing=None,
        *,
        observe_cash=None,
        evolution_subgoal=None,
    ):
        if observe_cash is not None and not callable(observe_cash):
            raise TypeError("Native cash observation must be callable")
        super().__init__(delegate)
        self.execute_restoration = restoration
        self.execute_training_healing = training_healing
        if evolution_subgoal is not None and not callable(evolution_subgoal):
            raise TypeError("guarded evolution delegation must be callable")
        self.execute_evolution_subgoal = evolution_subgoal
        self.observe_cash = observe_cash
        self.observed_cash_debits = 0
        self.observed_cash_rewards = 0
        self.observed_cash_changes = 0

    def execute(self, action):
        before = None if self.observe_cash is None else self.observe_cash()
        try:
            return super().execute(action)
        finally:
            after = None if self.observe_cash is None else self.observe_cash()
            if (
                type(before) is int
                and type(after) is int
                and 0 <= before <= 999999
                and 0 <= after <= 999999
                and before != after
            ):
                self.observed_cash_debits += max(0, before - after)
                self.observed_cash_rewards += max(0, after - before)
                self.observed_cash_changes += 1


class NativePlayerSession:
    """Trusted adapter assembly; not a sandbox for arbitrary Python factories."""

    def __init__(
        self,
        *,
        store,
        emulator,
        runtime_factory,
        source,
        execution,
        output,
        limits,
        combat_specimen_refs,
        battle_observer,
        target_cash,
        enumerate_bindings=None,
        enumerate_supplements=None,
        observe_challenges=None,
        observe_preparations=None,
        observe_matchups=None,
        observe_preparation_party=None,
        model_feature_version=5,
        curriculum=None,
        capture_reserve=None,
        resource_setup_receipt=None,
        collection_teacher_setup_receipt=None,
        consequence_spec=None,
        consequence_head=None,
        consequence_challenge_ref=None,
        consequence_objective_ref=None,
        consequence_branch_model=None,
        greedy_selection=False,
        allow_greedy_branch_recovery=False,
        refine_preparation=False,
        defer_unbound_preparation=False,
        allow_singleton_parent_support=False,
        associate_unique_combat=False,
        explore_outside_scope: bool = False,
        explore_on_movement_recurrence: bool = False,
        story_milestone_commitment: bool = False,
        story_kind_commitment: bool = False,
        respect_combat_preparation_choice: bool = False,
        allow_collection_restoration=False,
        force_resource_safety=True,
        include_live_pp_readiness=False,
        continue_safe_route_failures=False,
        train_inference_scope=None,
        train_selector_authentication=None,
        passive_sequence_horizon=None,
        production_train_scope=None,
        record_milestone_splits: bool = False,
        collection_cost_frame_horizon=None,
    ):
        if collection_cost_frame_horizon is not None and (
            type(collection_cost_frame_horizon) is not int or collection_cost_frame_horizon < 1
            or source.get("partition") != "development"
        ):
            raise ValueError("collection cost measurement requires a positive development frame horizon")
        if type(record_milestone_splits) is not bool:
            raise TypeError("milestone recording permission must be boolean")
        if observe_preparation_party is not None and (
            not callable(observe_preparation_party) or model_feature_version not in (15, 16)
        ):
            raise ValueError("party-count observer requires V15 and a callable")
        if observe_matchups is not None and (
            not callable(observe_matchups) or model_feature_version not in (15, 16)
        ):
            raise ValueError("native matchup observer requires V15 and a callable")
        if not isinstance(limits, NativePlayerLimits):
            raise TypeError("native player requires typed limits")
        if type(force_resource_safety) is not bool or type(include_live_pp_readiness) is not bool:
            raise TypeError("native player resource/readiness permissions must be boolean")
        if production_train_scope is not None:
            from .red_scoped_train_composition import ProductionSequenceTrainScope
            if type(production_train_scope) is not ProductionSequenceTrainScope:
                raise TypeError("typed production TRAIN sequence scope required")
            production_train_scope.require_session(source=source,execution=execution,limits=limits,
                recipe=dict(force_resource_safety=force_resource_safety,
                    include_live_pp_readiness=include_live_pp_readiness,
                    allow_collection_restoration=allow_collection_restoration,
                    story_kind_commitment=story_kind_commitment,
                    respect_combat_preparation_choice=respect_combat_preparation_choice))
        if type(respect_combat_preparation_choice) is not bool or (
            respect_combat_preparation_choice and (not story_kind_commitment or
                (source.get("partition") != "development" and production_train_scope is None))
        ):
            raise ValueError("combat preparation choice requires declared DEVELOPMENT story commitment")
        construction_train_inference = False
        if train_selector_authentication is not None:
            from .red_scoped_train_composition import validate_selector_authentication
            construction_train_inference = validate_selector_authentication(
                train_selector_authentication, allow=allow_greedy_branch_recovery,
                train_inference_scope=train_inference_scope, source=source,
                model=consequence_branch_model, head=consequence_head,
                objective_ref=consequence_objective_ref, challenge_ref=consequence_challenge_ref,
                flags=dict(greedy_selection=greedy_selection, refine_preparation=refine_preparation,
                           defer_unbound_preparation=defer_unbound_preparation,
                           allow_singleton_parent_support=allow_singleton_parent_support,
                           associate_unique_combat=associate_unique_combat,
                           explore_outside_scope=explore_outside_scope,
                           explore_on_movement_recurrence=explore_on_movement_recurrence),
                native_recipe=dict(force_resource_safety=force_resource_safety,
                                   include_live_pp_readiness=include_live_pp_readiness,
                                   allow_collection_restoration=allow_collection_restoration,
                                   continue_safe_route_failures=continue_safe_route_failures,
                                   story_milestone_commitment=story_milestone_commitment,
                                   story_kind_commitment=story_kind_commitment),
                limits=asdict(limits),
            )
        if passive_sequence_horizon is not None:
            from .red_scoped_train_composition import validate_passive_train_sequence
            if not construction_train_inference or not validate_passive_train_sequence(
                train_selector_authentication, passive_sequence_horizon
            ):
                raise ValueError("passive sequence needs authenticated TRAIN construction")
        elif train_selector_authentication is not None and train_selector_authentication.document().get("sequence_horizon") is not None:
            raise ValueError("declared passive sequence was omitted from native construction")
        if not force_resource_safety and source.get("partition") != "development" and not construction_train_inference and production_train_scope is None:
            raise ValueError("model resource authority requires declared DEVELOPMENT scope")
        self.force_resource_safety = force_resource_safety
        self.include_live_pp_readiness = include_live_pp_readiness
        if type(continue_safe_route_failures) is not bool or (
            continue_safe_route_failures and source.get("partition") != "development"
        ):
            raise ValueError("native safe route continuation requires DEVELOPMENT")
        self.continue_safe_route_failures = continue_safe_route_failures
        if type(allow_collection_restoration) is not bool:
            raise TypeError("collection restoration permission must be boolean")
        teacher_receipt = collection_teacher_setup_receipt or resource_setup_receipt
        if collection_teacher_setup_receipt is not None and (
            source.get("partition") != "train"
            or not isinstance(collection_teacher_setup_receipt, str)
            or re.fullmatch(r"[0-9a-f]{64}", collection_teacher_setup_receipt) is None
        ):
            raise ValueError("collection teacher receipt requires declared TRAIN setup")
        train_collection_lesson = (
            source.get("partition") == "train"
            and isinstance(teacher_receipt, str)
            and re.fullmatch(r"[0-9a-f]{64}", teacher_receipt) is not None
        )
        if (
            allow_collection_restoration
            and source.get("partition") != "development"
            and not train_collection_lesson
            and not construction_train_inference
            and production_train_scope is None
        ):
            raise ValueError("collection nursing requires DEVELOPMENT or authenticated TRAIN setup")
        self.allow_collection_restoration = allow_collection_restoration
        state = emulator.save_state_bytes()
        if (
            source.get("partition") not in {"train", "development"}
            or source.get("state_sha256") != sha256(state).hexdigest()
        ):
            raise ValueError("native player requires the authenticated declared source")
        if not callable(battle_observer):
            raise TypeError("native player needs an observed battle-history provider")
        if not isinstance(execution, NativeExecutionIdentity):
            raise TypeError("native player requires a typed execution identity")
        if (consequence_head is None) != (consequence_challenge_ref is None):
            raise ValueError("native consequence head/context pair differs")
        if (consequence_objective_ref is None) != (consequence_branch_model is None):
            raise ValueError("native branch recovery model/objective pair differs")
        from .red_consequence_choice import validate_greedy_branch_recovery_scope

        if train_selector_authentication is not None:
            from .red_scoped_train_composition import validate_selector_authentication

            train_inference = validate_selector_authentication(
                train_selector_authentication, allow=allow_greedy_branch_recovery,
                train_inference_scope=train_inference_scope, source=source,
                model=consequence_branch_model, head=consequence_head,
                objective_ref=consequence_objective_ref, challenge_ref=consequence_challenge_ref,
                flags=dict(greedy_selection=greedy_selection, refine_preparation=refine_preparation,
                           defer_unbound_preparation=defer_unbound_preparation,
                           allow_singleton_parent_support=allow_singleton_parent_support,
                           associate_unique_combat=associate_unique_combat,
                           explore_outside_scope=explore_outside_scope,
                           explore_on_movement_recurrence=explore_on_movement_recurrence),
            )
        else:
            train_inference = validate_greedy_branch_recovery_scope(
                allow=allow_greedy_branch_recovery,
                greedy_selection=greedy_selection,
                refine_preparation=refine_preparation,
                defer_unbound_preparation=defer_unbound_preparation,
                allow_singleton_parent_support=allow_singleton_parent_support,
                associate_unique_combat=associate_unique_combat,
                explore_outside_scope=explore_outside_scope,
                explore_on_movement_recurrence=explore_on_movement_recurrence,
                source=source,
                model=consequence_branch_model,
                head=consequence_head,
                objective_ref=consequence_objective_ref,
                challenge_ref=consequence_challenge_ref,
                train_inference_scope=train_inference_scope,
            )

        if type(greedy_selection) is not bool or (
            greedy_selection
            and (
                (source["partition"] != "development" and not train_inference)
                or (consequence_head is not None and not allow_greedy_branch_recovery)
            )
        ):
            raise ValueError("native highest-score composition requires declared DEVELOPMENT scope")
        expected_policy = None
        if consequence_objective_ref is not None:
            from .living_dex_option_value import LivingDexOptionValueModel
            from .red_consequence_choice import branch_recovery_identity

            if (
                consequence_head is None
                or not isinstance(consequence_branch_model, LivingDexOptionValueModel)
                or consequence_branch_model.feature_version not in (7, 9, 10, 11, 15, 16)
                or consequence_branch_model.feature_version != model_feature_version
            ):
                raise ValueError("native branch recovery requires the exact declared branch model")
            expected_policy = branch_recovery_identity(
                consequence_branch_model.model_sha256,
                consequence_head.model_sha256,
                consequence_objective_ref,
                greedy_selection=greedy_selection,
                refine_preparation=refine_preparation,
                defer_unbound_preparation=defer_unbound_preparation,
                allow_singleton_parent_support=allow_singleton_parent_support,
                associate_unique_combat=associate_unique_combat,
                explore_outside_scope=explore_outside_scope,
                explore_on_movement_recurrence=explore_on_movement_recurrence,
            )
        if consequence_head is not None:
            from .player_challenge_consequence import (
                ChallengeConsequenceHead,
                consequence_feature_versions_compatible,
            )

            if (
                type(consequence_head) is not ChallengeConsequenceHead
                or consequence_head.provenance != "native_train"
                or consequence_head.feedback_version != 2
                or (source["partition"] != "development" and not train_inference)
                or model_feature_version not in (7, 9, 10, 11, 15, 16)
                or not consequence_feature_versions_compatible(
                    consequence_head.feature_version, model_feature_version
                )
                or consequence_spec is not None
                or execution.model_sha256
                != (consequence_head.model_sha256 if expected_policy is None else expected_policy)
                or type(consequence_challenge_ref) is not str
                or not consequence_challenge_ref.strip()
            ):
                raise ValueError(
                    "native consequence adoption requires provisional development scope"
                )
        if curriculum is not None and not isinstance(curriculum, NativePlayerCurriculum):
            raise TypeError("native player requires a typed curriculum")
        if resource_setup_receipt is not None and (
            source.get("partition") != "train"
            or not isinstance(resource_setup_receipt, str)
            or re.fullmatch(r"[0-9a-f]{64}", resource_setup_receipt) is None
        ):
            raise ValueError("resource lessons require a declared TRAIN setup receipt")
        self.store, self.source, self.execution = store, source, execution
        self.resource_setup_receipt = resource_setup_receipt
        if consequence_spec is not None:
            from .red_challenge_consequence import ChallengeConsequenceSpec

            if (
                type(consequence_spec) is not ChallengeConsequenceSpec
                or source["partition"] != "train"
                or model_feature_version not in (7, 9, 10, 15, 16)
            ):
                raise ValueError("consequence recording requires explicit TRAIN V7 or V9 scope")
        # Reopening a receipt is safe; re-executing its inputs under that identity
        # is not. All current callers are single-writer, including this claim.
        if store.find_sealed_record(execution.claim_id) is not None:
            raise ValueError("native execution identity already consumed")
        self.output = Path(output)
        self.output.mkdir(mode=0o700, parents=False, exist_ok=False)
        self.limits = limits
        self.milestone_splits = None
        if record_milestone_splits:
            from .red_milestone_splits import MilestoneSplits
            self.milestone_splits = MilestoneSplits(
                source_state_sha256=source["state_sha256"],
                required_species=getattr(curriculum, "required_species", ()),
                identity=dict(model_sha256=execution.model_sha256,
                    execution_claim_id=execution.claim_id, partition=source["partition"]))
        self.wall = MonotonicWallTimeBudgetController(emulator, maximum_wall_seconds=limits.seconds)
        self.controller = NativeLessonController(self.wall, maximum_frames=limits.frames)
        self.roles, self.battle_observer, self.target_cash = (
            combat_specimen_refs,
            battle_observer,
            target_cash,
        )
        self.enumerate_bindings = enumerate_bindings
        self.enumerate_supplements = enumerate_supplements
        self.observe_challenges = observe_challenges
        self.observe_preparations = observe_preparations
        self.observe_matchups = observe_matchups
        self.observe_preparation_party = observe_preparation_party
        self.model_feature_version = model_feature_version
        self.curriculum = curriculum
        if capture_reserve is not None:
            from .red_capture_readiness import CapturePreparationBudget

            if not isinstance(capture_reserve, CapturePreparationBudget):
                raise TypeError("native player capture reserve must be typed")
        self.capture_reserve = capture_reserve
        self.decisions = self.heals = self.support_restorations = self.training_healing_trips = 0
        self.training_restoration_overlaps = 0
        self._training_nurse_credit = None
        self.active_kind = None
        plan = dict(
            schema="pokemon.red.native-continuous-player.v2",
            source=source,
            execution=asdict(execution),
            curriculum=None if curriculum is None else asdict(curriculum),
            capture_reserve=None if capture_reserve is None else asdict(capture_reserve),
            resource_setup_receipt=resource_setup_receipt,
            limits=asdict(limits),
            combat_specimen_refs=list(combat_specimen_refs),
            target_cash=target_cash,
            automatic_fit=False,
            promotion=False,
            controller_timing=asdict(DEFAULT_NEW_GAME_TIMING.controller_timing()),
        )
        if record_milestone_splits:
            plan["record_milestone_splits"] = True
        if collection_cost_frame_horizon is not None:
            plan["collection_cost_frame_horizon"] = collection_cost_frame_horizon
        if production_train_scope is not None:
            plan["production_train_sequence_scope"] = production_train_scope.document()
            plan["production_train_sequence_scope_sha256"] = production_train_scope.identity
        if passive_sequence_horizon is not None:
            plan["passive_sequence_horizon"] = passive_sequence_horizon
        if allow_collection_restoration:
            plan["allow_collection_restoration"] = True
        if collection_teacher_setup_receipt is not None:
            plan["collection_teacher_setup_receipt"] = collection_teacher_setup_receipt
        if not force_resource_safety or include_live_pp_readiness:
            plan["player_resource_configuration"] = dict(
                force_resource_safety=force_resource_safety,
                include_live_pp_readiness=include_live_pp_readiness,
            )
        if train_selector_authentication is not None:
            plan["scoped_train_selector_authentication"] = train_selector_authentication.document()
            plan["scoped_train_selector_authentication_sha256"] = train_selector_authentication.identity
        elif train_inference:
            plan["production_train_consequence_inference"] = train_inference_scope.document()
            plan["production_train_consequence_inference_sha256"] = train_inference_scope.identity
        if greedy_selection:
            plan["greedy_selection"] = True
        if allow_greedy_branch_recovery:
            plan["allow_greedy_branch_recovery"] = True
        if refine_preparation:
            plan["refine_preparation"] = True
        if defer_unbound_preparation:
            plan["defer_unbound_preparation"] = True
        if allow_singleton_parent_support:
            plan["allow_singleton_parent_support"] = True
        if associate_unique_combat:
            plan["associate_unique_combat"] = True
        if explore_outside_scope:
            plan["explore_outside_scope"] = True
        if explore_on_movement_recurrence:
            plan["explore_on_movement_recurrence"] = True
        if story_milestone_commitment:
            plan["story_milestone_commitment"] = True
        if story_kind_commitment:
            plan["story_kind_commitment"] = True
        if respect_combat_preparation_choice:
            plan["respect_combat_preparation_choice"] = True
        if consequence_spec is not None:
            plan["consequence_spec"] = consequence_spec.document()
        if model_feature_version in (9, 10, 11, 15, 16) and (
            consequence_spec is not None or consequence_head is not None
        ):
            plan["consequence_feature_version"] = (
                consequence_head.feature_version
                if consequence_head is not None
                else model_feature_version
            )
            if (
                consequence_head is not None
                and model_feature_version == 16
                and consequence_head.feature_version == 15
            ):
                plan["consequence_input_projection"] = dict(
                    schema="pokemon.consequence.v16-to-v15-prefix.v1",
                    observed_feature_version=16,
                    child_feature_version=15,
                    observed_width=510,
                    child_raw_width=506,
                    child_model_sha256=consequence_head.model_sha256,
                    child_weights_and_provenance_unchanged=True,
                )
        if consequence_head is not None:
            plan["consequence_policy"] = dict(
                head=consequence_head.document(),
                head_sha256=consequence_head.model_sha256,
                challenge_ref=consequence_challenge_ref,
                provisional=True,
                **(
                    {}
                    if consequence_objective_ref is None
                    else dict(
                        objective_ref=consequence_objective_ref,
                        branch_model_sha256=consequence_branch_model.model_sha256,
                        branch_recovery=True,
                        score_blending=False,
                    )
                ),
            )
        if continue_safe_route_failures:
            plan["continue_safe_route_failures"] = True
        store.publish_sealed_record(
            execution.claim_id, kind="red_native_player_execution", record=plan
        )
        _record(self.output / "native-plan.json", plan)
        _write(self.output / "source.state", state)
        self.recorder = _RecordedActions(
            self.controller,
            store,
            canonical_sha256(plan),
            limits.actions,
            timing=DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        self.actions = NativePlayerActions(
            self.recorder,
            self.execute_restoration,
            self.execute_training_healing if allow_collection_restoration else None,
            evolution_subgoal=(
                self.execute_evolution_subgoal if allow_collection_restoration else None
            ),
        )
        self._evolution_subgoal_active = False
        self.runtime = runtime_factory(self.controller)
        if (
            self.runtime.emulator is not self.controller
            or self.runtime.registration_policy is None
            or self.controller.save_state_bytes() != state
        ):
            raise ValueError("native runtime changed source or bypassed the guarded port")
        # Original party/loan reservations remain permanent. This separate
        # observation baseline covers all individuals present for one goal,
        # including new catches, without reserving them from ordinary PC use.
        self._decision_party_guard = None
        self._decision_party_guard_pending = True
        from .red_goal_context import RedGoalContextRuntime

        if isinstance(self.runtime, RedGoalContextRuntime):
            self.actions.observe_cash = lambda: self.runtime.reader.read().player_money

        if allow_collection_restoration and isinstance(self.runtime, RedGoalContextRuntime):
            from .red_team_training import evolution_reserve_requested

            requested = self.runtime.evolution_stop_requested
            self.runtime = replace(
                self.runtime,
                evolution_stop_requested=lambda: (
                    self.evolution_reserve_reached() or evolution_reserve_requested(requested)
                ),
            )
        self.consequence = None
        if consequence_spec is not None:
            from .red_challenge_consequence import NativeConsequenceRecorder

            self.consequence = NativeConsequenceRecorder(self, consequence_spec)

    def evolution_reserve_reached(self):
        """Leave finite headroom for the already selected goal's safe PC return."""
        return (
            self.limits.actions - len(self.recorder.trace)
            <= min(3000, max(1, self.limits.actions // 4))
            or self.limits.frames - self.controller.frames_executed
            <= min(250000, max(1, self.limits.frames // 4))
            or self.limits.seconds - self.wall.elapsed_seconds
            <= min(60, max(1, self.limits.seconds // 4))
        )

    def decision_admission_reserve_reached(self):
        """Keep one work allowance above the existing settlement reserve.

        This uniform boundary margin is not an upper bound on arbitrary routes.
        In-flight goals retain their separate, smaller settlement threshold.
        """
        return (
            self.limits.actions - len(self.recorder.trace)
            <= 2 * min(3000, max(1, self.limits.actions // 4))
            or self.limits.frames - self.controller.frames_executed
            <= 2 * min(250000, max(1, self.limits.frames // 4))
            or self.limits.seconds - self.wall.elapsed_seconds
            <= 2 * min(60, max(1, self.limits.seconds // 4))
        )

    def execute_evolution_subgoal(self, binding):
        """Execute the acquisition's already bound evolution, not a new goal.

        The outer kind stays ACQUIRE and all controller/budget accounting stays
        shared. Only this typed child may temporarily own the inner nurse port.
        """
        if (
            not self.allow_collection_restoration
            or not self.recorder.enabled
            or self.active_kind is not GoalKind.ACQUIRE_SPECIES
            or not isinstance(binding, ExecutableGoalBinding)
            or binding.kind is not GoalKind.EVOLVE_SPECIES
            or getattr(self, "_evolution_subgoal_active", False)
        ):
            raise ValueError("evolution delegation requires selected acquisition and typed child")
        self._evolution_subgoal_active = True
        try:
            record = getattr(self.actions, "record_diagnostic_event", None)
            if callable(record):
                record(
                    "evolution_subgoal_delegation",
                    dict(
                        outer_kind=self.active_kind.value,
                        inner_kind=binding.kind.value,
                        binding_ref=binding.binding_ref,
                        model_queries=0,
                    ),
                )
            return binding.execute()
        finally:
            self._evolution_subgoal_active = False

    def execute_training_healing(self, healer, reader, emulator):
        """Count an inner evolution recovery attempt before its native inputs."""
        if (
            not self.allow_collection_restoration
            or not self.recorder.enabled
            or not (
                self.active_kind is GoalKind.EVOLVE_SPECIES
                or (
                    self.active_kind is GoalKind.ACQUIRE_SPECIES
                    and getattr(self, "_evolution_subgoal_active", False)
                )
            )
            or reader is not self.runtime.reader
            or emulator is not self.controller
            or not callable(healer)
        ):
            raise ValueError("inner nursing requires the selected guarded evolution port")
        if getattr(self, "_training_nurse_credit", None) is not None:
            raise ValueError("training recovery already owns its nursing scope")
        if self.heals >= self.limits.heals:
            raise RestorationBudgetExhausted(
                maximum_heals=self.limits.heals, restoration_attempts=self.heals
            )
        self.heals += 1
        self.training_healing_trips += 1
        prefix = self.output / f"training-healing-{self.training_healing_trips:03d}"
        prefix.mkdir()
        start_actions, start_frames = len(self.recorder.trace), self.controller.frames_executed
        _record(prefix / "started.json", dict(actions=start_actions, frames=start_frames))
        error = None
        # The whole trip already reserved one attempt. Its first independently
        # verified free Center call is the same recovery, not another charge.
        # Any second call still consumes the ordinary restoration budget.
        self._training_nurse_credit = 1
        started = time.monotonic()
        try:
            return healer(self.actions, reader, emulator)
        except BaseException as caught:
            error = type(caught).__name__
            raise
        finally:
            elapsed = time.monotonic() - started
            self._training_nurse_credit = None
            _record(
                prefix / "result.json",
                dict(
                    succeeded=error is None,
                    error_type=error,
                    model_queries=0,
                    actions=len(self.recorder.trace) - start_actions,
                    frames=self.controller.frames_executed - start_frames,
                    seconds=elapsed,
                    timing_scope="healer_callback_including_travel_and_nested_nursing",
                ),
            )

    def execute_restoration(self, binding):
        """Meter a disclosed selected-goal prerequisite, not another model choice."""
        income_nurse = (
            self.active_kind is GoalKind.RESUPPLY
            and binding.binding_ref
            in {
                "pokemon.red:recovery:pokemon-center",
                "pokemon.red:recovery:pokemon-center-pp",
            }
            and binding.maximum_cash_debit in (None, 0)
        )
        collection_nurse = (
            getattr(self, "allow_collection_restoration", False)
            and self.active_kind in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
            and binding.binding_ref
            in {
                "pokemon.red:recovery:pokemon-center",
                "pokemon.red:recovery:pokemon-center-pp",
            }
            and binding.maximum_cash_debit in (None, 0)
        )
        if (
            not self.recorder.enabled
            or not (self.active_kind is GoalKind.DEVELOP_TEAM or income_nurse or collection_nurse)
            or binding.kind is not GoalKind.RESTORE_TEAM
        ):
            raise ValueError(
                "nested restoration requires selected development or free income nursing"
            )
        overlaps_training = (
            collection_nurse
            and type(getattr(self, "_training_nurse_credit", None)) is int
            and self._training_nurse_credit == 1
        )
        if overlaps_training:
            self._training_nurse_credit = 0
            self.training_restoration_overlaps = (
                getattr(self, "training_restoration_overlaps", 0) + 1
            )
        else:
            if self.heals >= self.limits.heals:
                raise RestorationBudgetExhausted(
                    maximum_heals=self.limits.heals, restoration_attempts=self.heals
                )
            self.heals += 1
        ordinal = self.support_restorations
        self.support_restorations += 1
        before = self.snapshot()
        prefix = self.output / f"restoration-{ordinal:03d}"
        prefix.mkdir()
        _write(prefix / "before.state", before.state)
        _record(
            prefix / "intent.json",
            dict(
                before=dict(before.facts),
                support_role=(
                    "selected_income_restoration"
                    if income_nurse
                    else "selected_collection_restoration"
                    if collection_nurse
                    else "selected_development_restoration"
                ),
                model_queries=0,
                binding_ref=binding.binding_ref,
                remaining_heals=self.limits.heals - self.heals,
                charged_by_training_trip=overlaps_training,
            ),
        )
        error = None
        succeeded = False
        try:
            report = binding.execute()
            terminal = self.snapshot()
            self.recorder.enabled = False
            verification = binding.verify(report)
            if (
                self.snapshot() != terminal
                or verification.status is not GoalDecisionOutcome.SUCCEEDED
            ):
                raise ValueError("nested restoration failed independent verification")
            if (
                report.actions_executed
                != terminal.facts["completed_actions"] - before.facts["completed_actions"]
                or report.frames_executed != terminal.facts["frames"] - before.facts["frames"]
            ):
                raise ValueError("nested restoration costs differ from actual inputs")
            succeeded = True
            return report
        except BaseException as caught:
            error = type(caught).__name__
            raise
        finally:
            self.recorder.enabled = True
            terminal = self.snapshot()
            _write(prefix / "terminal.state", terminal.state)
            _record(
                prefix / "result.json",
                dict(
                    succeeded=succeeded,
                    error_type=error,
                    after=dict(terminal.facts),
                    terminal_sha256=terminal.sha256,
                    actions=terminal.facts["actions"] - before.facts["actions"],
                    frames=terminal.facts["frames"] - before.facts["frames"],
                    model_queries=0,
                ),
            )

    def finish_decision(self):
        """The existing loop calls this only after a certified safe outcome.

        Keep the roster baseline fixed through execution, nested restorations
        and verification. A completed outcome permits the next observed scope;
        an unclassified failure stops before reaching this callback.
        """
        if self.recorder.enabled or self.active_kind is not None:
            raise ValueError("party evidence scope cannot change during native execution")
        self._decision_party_guard_pending = True
        return self.consequence is not None and self.consequence.done

    def snapshot(self):
        state = self.controller.save_state_bytes()
        observation, lesson = capture_player_lesson_snapshot(self.runtime)
        raw = observation.raw
        counts = Counter(m.species_ref for m in observation.collection_observation.specimens)
        facts = dict(
            actions=len(self.recorder.trace),
            completed_actions=self.actions.actions_executed,
            frames=self.controller.frames_executed,
            cash=raw.player_money,
            owned_species=sorted(observation.collection_observation.owned_species),
            specimen_counts=dict(counts),
            combat_specimen_refs=list(self.roles),
            restoration_attempts=self.heals,
            nested_restoration_attempts=self.support_restorations,
            training_healing_attempts=self.training_healing_trips,
            **(
                {"training_restoration_overlaps": self.training_restoration_overlaps}
                if getattr(self, "training_restoration_overlaps", 0)
                else {}
            ),
            completed_objectives=lesson["completed_objectives"],
            battle_state=raw.battle_state,
            input_ready=(
                observation.input_ready
                and not self.runtime.reader.read_bottom_dialogue_box_visible()
            ),
            buttons_released=not self.controller.pressed_buttons,
            player_lesson=lesson,
            **({"movement_event_flags": raw.event_flags.hex(),
                "movement_coins": self.runtime.reader.read_game_corner_coins()}
               if getattr(self, "movement_revisit_saturation", False)
               and raw.event_flags is not None else {}),
            diagnostics=player_diagnostic_state(
                observation, registration_policy=self.runtime.registration_policy
            ),
            **({"costly_search_session": asdict(self.runtime.reader.read_safari_session_state())}
               if getattr(self, "costly_search_recurrence", False)
               and callable(getattr(self.runtime.reader, "read_safari_session_state", None)) else {}),
        )
        guard = getattr(getattr(self.runtime, "adapter", None), "party_guard", None)
        if isinstance(guard, RedPlayerPartyGuard):
            guard.verify()
            if getattr(self, "continue_safe_route_failures", False):
                from .gen1_route_runtime import Gen1TraversalObserver

                facts["party_guard_verified"] = True
                facts["bag_items"] = raw.bag_items
                facts["coins"] = self.runtime.reader.read_game_corner_coins()
                if raw.battle_state == 0 and facts["input_ready"]:
                    route = Gen1TraversalObserver(self.runtime.reader).observe()
                    facts["route_boundary"] = dict(
                        map_id=route.map_id,
                        at=list(route.at),
                        ready=route.ready,
                        interruption=route.interruption,
                        mode=route.mode,
                    )
            if getattr(self, "_decision_party_guard_pending", True):
                self._decision_party_guard = replace(
                    guard,
                    before=guard.reader.read(),
                    refs=guard.reader.preparation_specimen_refs(),
                    loanable_refs=frozenset(),
                    field_carrier=None,
                )
                self._decision_party_guard.verify()
                self._decision_party_guard_pending = False
            scoped = self._decision_party_guard
            # New catches are stock, not additional guarded/reserved individuals.
            # Keep the old baseline fixed; a failed partial capture must separately
            # authenticate its capture receipts before this census permits recovery.
            # Missing original active members/storage exchanges get no certificate.
            evidence = (
                scoped.continuation_evidence(
                    observation.collection_observation, include_unreserved_additions=True
                )
                if set(scoped.refs) <= set(scoped.reader.preparation_specimen_refs())
                else None
            )
            if evidence is not None:
                facts["retained_party_continuation"] = evidence
        compulsory = (
            getattr(self, "sequence_compulsory_control", False) is True
            and self.source.get("partition") == "development"
            and raw.battle_state in (1, 2)
        )
        if compulsory:
            facts["compulsory_battle_control"] = True
        safe = bool((raw.battle_state == 0 or compulsory) and not self.controller.pressed_buttons)
        if self.controller.save_state_bytes() != state:
            raise ValueError("native snapshot audit changed state")
        splits = getattr(self, "milestone_splits", None)
        if splits is not None and splits.observe(facts, frames=facts["frames"],
                actions=facts["actions"], wall_seconds=self.wall.elapsed_seconds,
                state_sha256=sha256(state).hexdigest()):
            splits.write(self.output / "milestone-splits.json")
        return AutonomousSnapshot(state, facts, safe)

    def observe(self, ordinal):
        self.wall.check_wall_time_budget()
        if (
            len(self.recorder.trace) >= self.limits.actions
            or self.controller.frames_executed >= self.limits.frames
        ):
            raise RuntimeError("native player cumulative input budget exhausted")
        battle = self.battle_observer()
        if battle is not None and not isinstance(battle, BattleAftermath):
            raise ValueError("native player battle history is unavailable")
        remaining = (
            (self.limits.decisions - ordinal) / self.limits.decisions,
            (self.limits.actions - len(self.recorder.trace)) / self.limits.actions,
            (self.limits.frames - self.controller.frames_executed) / self.limits.frames,
            max(0.0, 1 - self.wall.elapsed_seconds / self.limits.seconds),
            (self.limits.heals - self.heals) / max(1, self.limits.heals),
        )
        if self.capture_reserve is not None:
            from .red_capture_readiness import capture_reserve_purchase

            _, reserve_quote = capture_reserve_purchase(
                self.runtime.adapter.observe(),
                self.capture_reserve,
                self.runtime.provider_for(GoalKind.RESUPPLY, self.actions),
            )
            self.target_cash = reserve_quote["full_reserve_cost"]
        options = observe_native_player_options(
            self.runtime,
            self.actions,
            battle=battle,
            combat_specimen_refs=self.roles,
            remaining_budget=remaining,
            target_cash=self.target_cash,
            ordering_seed_sha256=canonical_sha256({"ordinal": ordinal}),
            allow_support=True,
            enumerate_bindings=self.enumerate_bindings,
            enumerate_supplements=self.enumerate_supplements,
            observe_challenges=self.observe_challenges,
            observe_preparations=self.observe_preparations,
            observe_matchups=self.observe_matchups,
            observe_preparation_party=self.observe_preparation_party,
            model_feature_version=self.model_feature_version,
            curriculum=self.curriculum,
            capture_reserve=self.capture_reserve,
            force_resource_safety=self.force_resource_safety,
            include_live_pp_readiness=self.include_live_pp_readiness,
        )
        if isinstance(options, (PlayerCurriculumCompletion, PlayerBudgetStop)):
            return options

        # A new goal needs work headroom above the in-flight return reserve.
        # Menu construction is charged before this uniform admission check.
        # Preserve first-decision diagnostics and their wall-only safeguard;
        # keep compulsory recovery available while control is still unsettled.
        if (
            self.source.get("partition") == "development"
            and self.allow_collection_restoration
            and (
                (self.decisions > 0 and self.decision_admission_reserve_reached())
                or (
                    self.limits.seconds - self.wall.elapsed_seconds
                    <= min(60, max(1, self.limits.seconds // 4))
                    and self.evolution_reserve_reached()
                )
            )
        ):
            from .red_integrated_play import settled_player_boundary

            boundary = self.snapshot()
            if settled_player_boundary(boundary):
                return PlayerBudgetStop(boundary.sha256, "settlement_budget")

        # Count support attempts before input, so a failed restore is not refunded.
        def wrap(binding):
            resource_record = None

            def execute():
                nonlocal resource_record
                if self.consequence is not None:
                    self.consequence.begin(options, binding)
                if self.resource_setup_receipt is not None and binding.kind in {
                    GoalKind.RESUPPLY,
                    GoalKind.ACQUIRE_SPECIES,
                }:
                    from .red_player_resource_recording import begin_resource_recording

                    resource_record = begin_resource_recording(self, options, binding, remaining)
                if binding.kind is GoalKind.RESTORE_TEAM:
                    if self.heals >= self.limits.heals:
                        raise RestorationBudgetExhausted(
                            maximum_heals=self.limits.heals, restoration_attempts=self.heals
                        )
                    self.heals += 1
                self.decisions += 1
                self.active_kind = binding.kind
                self.recorder.enabled = True
                try:
                    return binding.execute()
                except BaseException as error:
                    if self.consequence is not None:
                        self.recorder.enabled = False
                        self.consequence.end(None, None, error)
                    raise
                finally:
                    self.recorder.enabled = False
                    self.active_kind = None

            def verify(report):
                try:
                    verdict = binding.verify(report)
                    if not isinstance(verdict, GoalVerification):
                        raise ValueError("continuous resource verifier returned an invalid verdict")
                except BaseException as error:
                    if self.consequence is not None:
                        self.consequence.end(report, None, error)
                    raise
                if self.consequence is not None:
                    self.consequence.end(report, verdict)
                if resource_record is not None:
                    from .red_player_resource_recording import finish_resource_recording

                    # Admission is separate from gameplay verification. A failed
                    # importer cannot erase the terminal or turn a win into a loss.
                    try:
                        item = finish_resource_recording(self, resource_record, report, verdict)
                        admission = dict(admitted=True, item=item.public_dict())
                    except Exception as error:
                        admission = dict(admitted=False, error_type=type(error).__name__)
                    _record(
                        self.output / f"resource-lesson-{ordinal:03d}.json",
                        dict(
                            declaration_sha256=resource_record["declaration"],
                            **admission,
                            comparative_choice=False,
                            automatic_fit=False,
                        ),
                    )
                return verdict

            return replace(binding, execute=execute, verify=verify)

        if isinstance(options, RedPlayerSupport):
            bindings = replace(
                options.bindings,
                bindings=tuple(wrap(binding) for binding in options.bindings.bindings),
            )
        else:
            bindings = tuple(wrap(binding) for binding in options.bindings)
        return replace(options, bindings=bindings)


def validate_settlement_refinement_scope(
    *,
    allow,
    source,
    model,
    head,
    objective_ref,
    challenge_ref,
    settlement_requested,
    sequence_horizon,
    sequence_policy,
    consequence_spec,
):
    """Resume one declared trained child only beyond a verified compulsory preface."""
    if type(allow) is not bool:
        raise ValueError("settled branch refinement permission must be boolean")
    if not allow:
        return False
    from .living_dex_option_value import LivingDexOptionValueModel
    from .player_challenge_consequence import (
        ChallengeConsequenceHead,
        consequence_feature_versions_compatible,
    )
    from .red_consequence_choice import (
        branch_recovery_scope_ref,
        valid_branch_recovery_objectives,
    )

    if (
        source.get("partition") != "development"
        or not settlement_requested
        or not isinstance(model, LivingDexOptionValueModel)
        or model.feature_version not in (7, 9, 10, 11, 15, 16)
        or type(head) is not ChallengeConsequenceHead
        or not consequence_feature_versions_compatible(head.feature_version, model.feature_version)
        or head.provenance != "native_train"
        or head.feedback_version != 2
        or not valid_branch_recovery_objectives(objective_ref)
        or challenge_ref != branch_recovery_scope_ref(objective_ref)
        or sequence_horizon is not None
        or sequence_policy is not None
        or consequence_spec is not None
    ):
        raise ValueError(
            "settled branch refinement requires matching declared native-TRAIN V2 DEVELOPMENT"
        )
    return True


def _ordinary_retained_capture_loss(capture, before, after, report, verdict, before_raw, after_raw):
    """Recognize the verified consumed Route12 loss without granting a catch."""
    from .observation import EventFlag, ItemId, MapId
    from .red_player_wild_recovery import static_escape_expected_events
    from .red_static_capture import RedStaticCaptureTarget

    if (not capture or before_raw is None or after_raw is None
            or verdict.status is not GoalDecisionOutcome.FAILED
            or verdict.failure_reason is not GoalFailureReason.RESOURCE_LOST
            or report.evidence.get("captured") is not False):
        return False
    loss = report.evidence.get("lost_static_target")
    if not isinstance(loss, dict):
        return False
    try:
        target = RedStaticCaptureTarget(**loss)
        if (target.species_number != 143 or target.map_id != int(MapId.ROUTE_12)
                or target.event_flag != int(EventFlag.BEAT_ROUTE12_SNORLAX)
                or before_raw.map_id != target.map_id or before_raw.battle_state != 1):
            return False
        expected_events = static_escape_expected_events(before_raw, target)
    except (TypeError, ValueError):
        return False
    if after_raw.bag_items is None:
        return False
    stock = dict(after_raw.bag_items)
    return (
        after_raw.battle_state == 0
        and after_raw.event_flags == expected_events
        and all(getattr(before_raw, key) == getattr(after_raw, key)
                for key in ("map_id", "player_x", "player_y", "player_money", "badge_bits"))
        and not any(stock.get(int(ball), 0) for ball in (
            ItemId.POKE_BALL, ItemId.GREAT_BALL, ItemId.ULTRA_BALL, ItemId.MASTER_BALL))
        and all(before.facts.get(key) is not None
                and before.facts[key] == after.facts.get(key)
                for key in ("cash", "owned_species", "specimen_counts"))
    )


def run_native_continuous_player(
    *,
    store,
    emulator,
    runtime_factory,
    source,
    output,
    model,
    seed,
    run_id,
    arm_id,
    limits,
    combat_specimen_refs,
    battle_observer,
    target_cash,
    enumerate_bindings=None,
    enumerate_supplements=None,
    observe_challenges=None,
    observe_preparations=None,
    observe_matchups=None,
    observe_preparation_party=None,
    curriculum=None,
    capture_reserve=None,
    resource_setup_receipt=None,
    collection_teacher_setup_receipt=None,
    sequence_horizon=None,
    sequence_window_stride=None,
    sequence_target_contract=None,
    sequence_task_sha256=None,
    sequence_task_kind=None,
    sequence_history_contract=None,
    sequence_policy=None,
    consequence_spec=None,
    consequence_head=None,
    consequence_challenge_ref=None,
    consequence_objective_ref=None,
    greedy_selection=False,
    exploration_mix=0.25,
    allow_greedy_branch_recovery=False,
    refine_preparation=False,
    defer_unbound_preparation=False,
    allow_singleton_parent_support=False,
    associate_unique_combat=False,
    explore_outside_scope: bool = False,
    explore_on_movement_recurrence: bool = False,
    story_milestone_commitment: bool = False,
    story_kind_commitment: bool = False,
    respect_combat_preparation_choice: bool = False,
    story_kind_commitment_carrier=None,
    settle_existing_blackout=False,
    settle_existing_wild=False,
    settle_existing_capture=False,
    settle_existing_trainer=False,
    settle_existing_motion=False,
    resume_branch_refinement_after_settlement=False,
    allow_collection_restoration=False,
    force_resource_safety=True,
    include_live_pp_readiness=False,
    initial_search_memory=None,
    movement_revisit_saturation=False,
    collection_cost_frame_horizon=None,
    train_inference_scope=None,
    train_selector_authentication=None,
    production_train_scope=None,
    record_milestone_splits: bool = False,
):
    """Execute one isolated, already authorized native episode; never reset it."""
    if type(record_milestone_splits) is not bool:
        raise TypeError("milestone recording permission must be boolean")
    if (
        isinstance(exploration_mix, bool)
        or not isinstance(exploration_mix, (int, float))
        or not math.isfinite(exploration_mix)
        or not 0 <= exploration_mix <= 1
    ):
        raise ValueError("native exploration mix must be finite within zero and one")
    if exploration_mix != 0.25 and (
        source.get("partition") != "development"
        or greedy_selection
        or sequence_horizon is not None
        or sequence_policy is not None
        or consequence_spec is not None
        or consequence_head is not None
    ):
        raise ValueError("custom exploration requires separate native DEVELOPMENT scope")
    if production_train_scope is not None:
        from .red_scoped_train_composition import ProductionSequenceTrainScope
        if (type(production_train_scope) is not ProductionSequenceTrainScope
                or consequence_head is not None or consequence_spec is not None
                or train_selector_authentication is not None or train_inference_scope is not None
                or greedy_selection is not False or sequence_policy is None
                or sequence_horizon != sequence_policy.head.horizon):
            raise ValueError("production TRAIN sequence cannot mix selectors or change its horizon")
        production_train_scope.require_policy(source=source,model=model,policy=sequence_policy,limits=limits,
            recipe=dict(force_resource_safety=force_resource_safety,
                include_live_pp_readiness=include_live_pp_readiness,
                allow_collection_restoration=allow_collection_restoration,
                story_kind_commitment=story_kind_commitment,
                respect_combat_preparation_choice=respect_combat_preparation_choice,
                movement_revisit_saturation=movement_revisit_saturation))
        production_train_scope.require_collection(
            history_contract=sequence_history_contract or sequence_policy.head.history_contract,
            task_kind=sequence_task_kind,task_sha256=sequence_task_sha256)
    search_memory = (
        initial_search_memory if initial_search_memory is not None else GoalSearchMemory()
    )
    if not isinstance(search_memory, GoalSearchMemory):
        raise ValueError("native search memory requires measured typed history")
    resume_refinement = validate_settlement_refinement_scope(
        allow=resume_branch_refinement_after_settlement,
        source=source,
        model=model,
        head=consequence_head,
        objective_ref=consequence_objective_ref,
        challenge_ref=consequence_challenge_ref,
        settlement_requested=any(
            (
                settle_existing_blackout,
                settle_existing_wild,
                settle_existing_capture,
                settle_existing_trainer,
                settle_existing_motion,
            )
        ),
        sequence_horizon=sequence_horizon,
        sequence_policy=sequence_policy,
        consequence_spec=consequence_spec,
    )
    if (
        type(settle_existing_blackout) is not bool
        or type(settle_existing_wild) is not bool
        or type(settle_existing_capture) is not bool
        or type(settle_existing_trainer) is not bool
        or type(settle_existing_motion) is not bool
        or (settle_existing_capture and settle_existing_wild)
        or (
            (
                settle_existing_blackout
                or settle_existing_wild
                or settle_existing_capture
                or settle_existing_trainer
                or settle_existing_motion
            )
            and (
                source.get("partition") != "development"
                or limits.decisions < 2
                or sequence_policy is not None
                or sequence_horizon is not None
                or consequence_spec is not None
                or (consequence_head is not None and not resume_refinement)
            )
        )
    ):
        raise ValueError("existing blackout preface requires separate continuous DEVELOPMENT scope")
    from .red_consequence_choice import validate_greedy_branch_recovery_scope

    if train_selector_authentication is not None:
        from .red_scoped_train_composition import validate_selector_authentication

        train_inference = validate_selector_authentication(
            train_selector_authentication, allow=allow_greedy_branch_recovery,
            train_inference_scope=train_inference_scope, source=source,
            model=model, head=consequence_head,
            objective_ref=consequence_objective_ref, challenge_ref=consequence_challenge_ref,
            flags=dict(greedy_selection=greedy_selection, refine_preparation=refine_preparation,
                       defer_unbound_preparation=defer_unbound_preparation,
                       allow_singleton_parent_support=allow_singleton_parent_support,
                       associate_unique_combat=associate_unique_combat,
                       explore_outside_scope=explore_outside_scope,
                       explore_on_movement_recurrence=explore_on_movement_recurrence),
        )
    else:
        train_inference = validate_greedy_branch_recovery_scope(
            allow=allow_greedy_branch_recovery,
            greedy_selection=greedy_selection,
            refine_preparation=refine_preparation,
            defer_unbound_preparation=defer_unbound_preparation,
            allow_singleton_parent_support=allow_singleton_parent_support,
            associate_unique_combat=associate_unique_combat,
            explore_outside_scope=explore_outside_scope,
            explore_on_movement_recurrence=explore_on_movement_recurrence,
            source=source,
            model=model,
            head=consequence_head,
            objective_ref=consequence_objective_ref,
            challenge_ref=consequence_challenge_ref,
            train_inference_scope=train_inference_scope,
        )

    from .red_scoped_train_composition import validate_passive_train_sequence
    passive_collection = train_inference and validate_passive_train_sequence(
        train_selector_authentication, sequence_horizon,
        sequence_policy=sequence_policy, consequence_spec=consequence_spec,
    )
    if type(greedy_selection) is not bool or (
        greedy_selection
        and (
            (source.get("partition") != "development" and not train_inference)
            or sequence_policy is not None
            or (sequence_horizon is not None and not passive_collection)
            or consequence_spec is not None
            or (consequence_head is not None and not allow_greedy_branch_recovery)
        )
    ):
        raise ValueError("highest-score selection requires separate native DEVELOPMENT scope")
    if explore_on_movement_recurrence and movement_revisit_saturation is not True:
        raise ValueError("recurrence escape requires observed movement history")
    collector = None
    branch_policy_sha = None
    if consequence_objective_ref is not None:
        from .red_consequence_choice import branch_recovery_identity

        if consequence_head is None:
            raise ValueError("native branch recovery requires an explicit consequence head")
        branch_policy_sha = branch_recovery_identity(
            model.model_sha256,
            consequence_head.model_sha256,
            consequence_objective_ref,
            greedy_selection=greedy_selection,
            refine_preparation=refine_preparation,
            defer_unbound_preparation=defer_unbound_preparation,
            allow_singleton_parent_support=allow_singleton_parent_support,
            associate_unique_combat=associate_unique_combat,
            explore_outside_scope=explore_outside_scope,
            explore_on_movement_recurrence=explore_on_movement_recurrence,
        )
    if consequence_head is not None and (
        sequence_policy is not None or (sequence_horizon is not None and not passive_collection) or consequence_spec is not None
    ):
        raise ValueError("consequence adoption cannot combine with sequence/TRAIN recording")
    if consequence_spec is not None and (
        sequence_policy is not None or sequence_horizon is not None
    ):
        raise ValueError("challenge consequence and sequence experiments must remain separate")
    if sequence_policy is not None:
        from .player_sequence_policy import SequencePolicy

        if (
            type(sequence_policy) is not SequencePolicy
            or sequence_horizon is None
            or sequence_policy.head.horizon != sequence_horizon
            or sequence_policy.baseline_sha256 != model.model_sha256
            or model.feature_version != sequence_policy.head.feature_version
        ):
            raise ValueError("native sequence policy requires matching model and horizon")
    if sequence_policy is not None and sequence_policy.selection_mode in {"stable_recurrence", "stable_costly_recurrence"} and movement_revisit_saturation is not True:
        raise ValueError("stable sequence recurrence requires observed movement history")
    if sequence_task_kind is not None and (
        sequence_task_kind != "next_registration" or
        (source.get("partition") != "development" and production_train_scope is None)
        or sequence_policy is None or sequence_task_sha256 is None
    ):
        raise ValueError("registration task stop needs declared DEVELOPMENT sequence policy")
    if (sequence_target_contract is not None or sequence_task_sha256 is not None) and sequence_horizon is None:
        raise ValueError("sequence task contract requires a declared horizon")
    if sequence_policy is not None and sequence_target_contract is not None and (
        sequence_policy.head.target_contract != sequence_target_contract
    ):
        raise ValueError("native sequence target contract differs from the frozen policy")
    if sequence_window_stride is not None and sequence_horizon is None:
        raise ValueError("sequence window stride requires a declared horizon")
    if sequence_horizon is not None:
        from .player_sequence_collector import SequenceTraceCollector

        collector = SequenceTraceCollector(
            source_sha256=source["state_sha256"],
            partition=source["partition"],
            horizon=sequence_horizon,
            **({"target_contract": sequence_target_contract}
               if sequence_target_contract is not None else {}),
            **({"task_sha256": sequence_task_sha256}
               if sequence_task_sha256 is not None else {}),
            **({"window_stride": sequence_window_stride} if sequence_window_stride is not None else {}),
            feature_version=16 if model.feature_version == 16 else 6,
            **({"history_contract": sequence_history_contract,
                "selection_history_contract": sequence_policy.head.history_contract}
               if sequence_history_contract is not None and sequence_policy is not None else
               {"history_contract": sequence_history_contract} if sequence_history_contract is not None else
               {"history_contract": sequence_policy.head.history_contract} if sequence_policy is not None else {}),
            **({"declaration_store": store} if passive_collection else {}),
        )
    session = NativePlayerSession(
        store=store,
        emulator=emulator,
        runtime_factory=runtime_factory,
        source=source,
        execution=NativeExecutionIdentity(
            run_id,
            arm_id,
            (
                branch_policy_sha
                if branch_policy_sha is not None
                else consequence_head.model_sha256
                if consequence_head is not None
                else model.model_sha256
                if sequence_policy is None
                else sequence_policy.model_sha256
            ),
            seed,
        ),
        output=output,
        limits=limits,
        combat_specimen_refs=combat_specimen_refs,
        battle_observer=battle_observer,
        target_cash=target_cash,
        enumerate_bindings=enumerate_bindings,
        enumerate_supplements=enumerate_supplements,
        observe_challenges=observe_challenges,
        observe_preparations=observe_preparations,
        observe_matchups=observe_matchups,
        observe_preparation_party=observe_preparation_party,
        **({"collection_cost_frame_horizon": collection_cost_frame_horizon}
           if collection_cost_frame_horizon is not None else {}),
        **({"record_milestone_splits": True} if record_milestone_splits else {}),
        model_feature_version=model.feature_version,
        curriculum=curriculum,
        capture_reserve=capture_reserve,
        resource_setup_receipt=resource_setup_receipt,
        collection_teacher_setup_receipt=collection_teacher_setup_receipt,
        consequence_spec=consequence_spec,
        consequence_head=consequence_head,
        consequence_challenge_ref=consequence_challenge_ref,
        consequence_objective_ref=consequence_objective_ref,
        consequence_branch_model=(None if consequence_objective_ref is None else model),
        greedy_selection=greedy_selection,
        allow_greedy_branch_recovery=allow_greedy_branch_recovery,
        refine_preparation=refine_preparation,
        defer_unbound_preparation=defer_unbound_preparation,
        allow_singleton_parent_support=allow_singleton_parent_support,
        associate_unique_combat=associate_unique_combat,
        explore_outside_scope=explore_outside_scope,
        explore_on_movement_recurrence=explore_on_movement_recurrence,
        story_milestone_commitment=story_milestone_commitment,
        story_kind_commitment=story_kind_commitment,
        **({"respect_combat_preparation_choice": True} if respect_combat_preparation_choice else {}),
        allow_collection_restoration=allow_collection_restoration,
        force_resource_safety=force_resource_safety,
        include_live_pp_readiness=include_live_pp_readiness,
        continue_safe_route_failures=(
            source.get("partition") == "development"
            and collector is None
            and sequence_policy is None
            and consequence_head is None
        ),
        train_inference_scope=train_inference_scope,
        **({"production_train_scope": production_train_scope} if production_train_scope is not None else {}),
        **({"passive_sequence_horizon": sequence_horizon} if passive_collection else {}),
        **({"train_selector_authentication": train_selector_authentication}
           if train_selector_authentication is not None else {}),
    )
    session.sequence_compulsory_control = sequence_policy is not None and (source.get("partition") == "development" or production_train_scope is not None)
    registration_task_owned = (frozenset(session.runtime.reader.read_pokedex_state().owned_species)
                               if sequence_task_kind == "next_registration" else None)

    def finish_with_declared_task():
        if registration_task_owned is None:
            return session.finish_decision()
        return finish_native_registration_task(session, collector,
            initial_owned=registration_task_owned, task_sha256=sequence_task_sha256)

    try:
        blackout = None
        preface_cash_debits = 0
        preface_key = "supplied_blackout_preface"
        if collection_cost_frame_horizon is not None:
            native_plan_sha = canonical_sha256(json.loads((session.output / "native-plan.json").read_text()))
            document = dict(native_plan_sha256=native_plan_sha, source_sha256=source["state_sha256"],
                            frame_horizon=collection_cost_frame_horizon,
                            initial_costs=search_memory.private_dict().get("collection_training", {}))
            store.publish_sealed_record("rnp-colcost-" + native_plan_sha,
                                        kind="red_native_collection_cost_origin", record=document)
            _record(session.output / "collection-cost-origin.json", document)
        if sequence_policy is not None and sequence_policy.selection_mode in {"stable_recurrence", "stable_costly_recurrence"}:
            native_plan_sha = canonical_sha256(json.loads((session.output / "native-plan.json").read_text()))
            document = dict(schema="pokemon.red.sequence-recurrence-origin.v1",
                            native_plan_sha256=native_plan_sha, policy_sha256=sequence_policy.model_sha256,
                            initial_memory=search_memory.private_dict(), source_sha256=source["state_sha256"])
            store.publish_sealed_record("rnp-seqrec-" + native_plan_sha,
                                        kind="red_native_sequence_recurrence_origin", record=document)
            _record(session.output / "sequence-recurrence-origin.json", document)
        train_selector_scope = None
        if train_selector_authentication is not None:
            train_selector_scope = train_selector_authentication.bind(
                session=session, source=source, model=model, head=consequence_head,
                objective_ref=consequence_objective_ref, challenge_ref=consequence_challenge_ref,
                flags=dict(greedy_selection=greedy_selection, refine_preparation=refine_preparation,
                           defer_unbound_preparation=defer_unbound_preparation,
                           allow_singleton_parent_support=allow_singleton_parent_support,
                           associate_unique_combat=associate_unique_combat,
                           explore_outside_scope=explore_outside_scope,
                           explore_on_movement_recurrence=explore_on_movement_recurrence),
            )
            # Companion record avoids a hash cycle with the already sealed plan.
            document = train_selector_scope.document()
            store.publish_sealed_record("rnp-selector-" + train_selector_scope.identity,
                                        kind="red_native_train_selector", record=document)
            _record(session.output / "scoped-train-selector-witness.json",
                    dict(document=document, identity=train_selector_scope.identity))
        if (
            settle_existing_blackout
            or settle_existing_wild
            or settle_existing_capture
            or settle_existing_trainer
            or settle_existing_motion
        ):
            raw = session.runtime.reader.read()
            loss = (
                settle_existing_blackout
                and raw.party_hp
                and not any(raw.party_hp)
                and (
                    raw.battle_state in {1, 2}
                    or raw.battle_state == 0
                    and not session.runtime.reader.read_input_readiness().ready
                    and session.runtime.reader.read_bottom_dialogue_box_visible()
                )
            )
            escape = (
                settle_existing_wild
                and raw.battle_state == 1
                and raw.party_hp
                and any(raw.party_hp)
            )
            capture = (
                settle_existing_capture
                and raw.battle_state == 1
                and raw.party_hp
                and any(raw.party_hp)
            )
            trainer = (
                settle_existing_trainer
                and raw.battle_state == 2
                and raw.party_hp
                and any(raw.party_hp)
            )
            motion = (
                settle_existing_motion
                and raw.battle_state == 0
                and raw.party_hp
                and any(raw.party_hp)
                and not session.snapshot().facts["input_ready"]
            )
            if loss or escape or capture or trainer or motion:
                # An already-lost battle is not a policy decision boundary.
                # Settle only its explicit compulsory executor on the same
                # guarded port, then enter the ordinary unchanged goal loop.
                before = session.snapshot()
                options = session.observe(0)
                # A cartridge-qualified trainer introduction may precede
                # battle2 and its movement latch. Only the existing exact,
                # sole recovery binding can refine this motion preface.
                if (
                    motion
                    and settle_existing_trainer
                    and isinstance(options, RedPlayerSupport)
                    and options.binding.kind is GoalKind.RECOVER_CONTROL
                    and options.binding.binding_ref
                    == "pokemon.red:retained-engagement:" + before.sha256
                    and len(options.bindings.bindings) == 1
                ):
                    trainer, motion = True, False
                # The live inventory can authenticate a retained one-off
                # allocation at an otherwise ordinary wild control boundary.
                # Refine only its sole exact-state capture binding; never
                # authorize Run, another target or a replacement policy choice.
                if (
                    escape
                    and isinstance(options, RedPlayerSupport)
                    and options.binding.kind is GoalKind.RECOVER_CONTROL
                    and options.binding.binding_ref
                    == "pokemon.red:retained-capture:" + before.sha256
                    and len(options.bindings.bindings) == 1
                ):
                    capture, escape = True, False
                expected_ref = (
                    "pokemon.red:field-blackout:"
                    if loss
                    else "pokemon.red:retained-motion:"
                    if motion
                    else "pokemon.red:retained-engagement:"
                    if trainer
                    else "pokemon.red:retained-capture:"
                    if capture
                    else "pokemon.red:interrupted-wild:"
                ) + before.sha256
                if (
                    not isinstance(options, RedPlayerSupport)
                    or options.binding.kind is not GoalKind.RECOVER_CONTROL
                    or options.binding.binding_ref != expected_ref
                    or len(options.bindings.bindings) != 1
                ):
                    raise ValueError(
                        "native blackout/wild boundary needs its one mandatory executor"
                    )
                preface_key = (
                    "supplied_blackout_preface"
                    if loss
                    else "supplied_motion_preface"
                    if motion
                    else "supplied_trainer_preface"
                    if trainer
                    else "supplied_capture_preface"
                    if capture
                    else "supplied_wild_escape_preface"
                )
                prefix = session.output / (
                    "blackout-preface"
                    if loss
                    else "retained-motion-preface"
                    if motion
                    else "retained-trainer-preface"
                    if trainer
                    else "retained-capture-preface"
                    if capture
                    else "wild-escape-preface"
                )
                prefix.mkdir()
                _write(prefix / "before.state", before.state)
                _record(
                    prefix / "intent.json",
                    dict(
                        source_sha256=before.sha256,
                        binding_ref=options.binding.binding_ref,
                        comparative_choice=False,
                        model_queries=0,
                        supplied_control_recovery=True,
                    ),
                )
                capture_before = session.runtime.reader.read() if capture else None
                report = options.binding.execute()
                verdict = options.binding.verify(report)
                after = session.snapshot()
                ordinary_capture_loss = _ordinary_retained_capture_loss(
                    capture, before, after, report, verdict, capture_before,
                    session.runtime.reader.read() if capture else None,
                )
                preface_cash_debits = max(0, before.facts["cash"] - after.facts["cash"])
                chained = report.evidence.get("chained_trainer_recovery")
                ordinary_trainer_loss = (
                    (
                        trainer
                        or escape
                        and isinstance(chained, dict)
                        and chained.get("binding_ref")
                        == "pokemon.red:retained-engagement:" + str(chained.get("source_sha256"))
                        and chained.get("support") == "already_engaged_native_trainer"
                        and chained.get("battle") == report.evidence.get("battle")
                        and chained.get("terminal_sha256") == after.sha256
                    )
                    and verdict.status is GoalDecisionOutcome.FAILED
                    and verdict.failure_reason is GoalFailureReason.RESOURCE_LOST
                    and report.evidence.get("battle", {}).get("outcome") == "lost"
                    and report.evidence.get("battle", {}).get("field_ready") is True
                )
                if (
                    (
                        verdict.status is not GoalDecisionOutcome.SUCCEEDED
                        and not ordinary_trainer_loss
                        and not ordinary_capture_loss
                    )
                    or not settled_player_boundary(after)
                    or report.actions_executed
                    != (after.facts["completed_actions"] - before.facts["completed_actions"])
                    or report.frames_executed != after.facts["frames"] - before.facts["frames"]
                ):
                    raise ValueError(
                        "native blackout/wild escape preface did not independently settle"
                    )
                blackout = dict(
                    source_sha256=before.sha256,
                    terminal_sha256=after.sha256,
                    actions=report.actions_executed,
                    frames=report.frames_executed,
                    cash_spent=preface_cash_debits,
                    verification=verdict.status.value,
                    failure_reason=(
                        None if verdict.failure_reason is None else verdict.failure_reason.value
                    ),
                    ordinary_setback=ordinary_trainer_loss or ordinary_capture_loss,
                    evidence=dict(report.evidence),
                    learned=False,
                    operator_relaunch=False,
                )
                _write(prefix / "terminal.state", after.state)
                _record(prefix / "result.json", blackout)
        remaining_cash = (
            limits.cash_debits
            if blackout is None or limits.cash_debits is None
            else limits.cash_debits - blackout["cash_spent"]
        )
        if remaining_cash is not None and remaining_cash < 0:
            raise ValueError("native blackout exceeds retained cash-debit allowance")
        if resume_refinement:
            if blackout is None or not settled_player_boundary(session.snapshot()):
                raise ValueError("settled branch refinement has no verified compulsory boundary")
            _record(
                session.output / "settled-branch-refinement.json",
                dict(
                    schema="pokemon.red.settled-branch-refinement.v1",
                    head_sha256=consequence_head.model_sha256,
                    objective_ref=consequence_objective_ref,
                    settlement_terminal_sha256=blackout["terminal_sha256"],
                    goal_model_queries_before_settlement=0,
                    partition="development",
                    new_fit=False,
                ),
            )
        session.movement_revisit_saturation = movement_revisit_saturation
        session.costly_search_recurrence = (
            sequence_policy is not None and sequence_policy.selection_mode == "stable_costly_recurrence")
        result = run_autonomous_options(
            model=model,
            output=session.output / "episode",
            snapshot=session.snapshot,
            observe=session.observe,
            seed=seed,
            maximum_decisions=limits.decisions - session.decisions,
            maximum_seconds=limits.seconds,
            provenance=dict(
                source=source, **({} if blackout is None else dict(**{preface_key: blackout}))
            ),
            continuous_player=True,
            continue_safe_route_failures=session.continue_safe_route_failures,
            initial_search_memory=search_memory,
            movement_revisit_saturation=movement_revisit_saturation,
            **({"collection_cost_frame_horizon": collection_cost_frame_horizon}
               if collection_cost_frame_horizon is not None else {}),
            greedy_selection=greedy_selection,
            exploration_mix=float(exploration_mix),
            allow_greedy_branch_recovery=allow_greedy_branch_recovery,
            refine_preparation=refine_preparation,
            defer_unbound_preparation=defer_unbound_preparation,
            allow_singleton_parent_support=allow_singleton_parent_support,
            associate_unique_combat=associate_unique_combat,
            explore_outside_scope=explore_outside_scope,
            explore_on_movement_recurrence=explore_on_movement_recurrence,
            story_milestone_commitment=story_milestone_commitment,
            story_kind_commitment=story_kind_commitment,
            **({"respect_combat_preparation_choice": True} if respect_combat_preparation_choice else {}),
            story_kind_commitment_carrier=story_kind_commitment_carrier,
            maximum_cash_spent=remaining_cash,
            sequence_collector=collector,
            sequence_policy=sequence_policy,
            consequence_head=consequence_head,
            consequence_challenge_ref=consequence_challenge_ref,
            consequence_objective_ref=consequence_objective_ref,
            stop_after_outcome=finish_with_declared_task,
            train_inference_scope=train_inference_scope,
            **({"train_selector_scope": train_selector_scope}
               if train_selector_scope is not None else {}),
        )
        if blackout is not None:
            result = dict(
                result,
                **{preface_key: blackout},
                accounted_cash_spent=result["accounted_cash_spent"] + blackout["cash_spent"],
            )
            _record(session.output / "continuation-result.json", result)
        return result
    finally:
        finalize_native_player_session(session, search_memory, preface_cash_debits=preface_cash_debits)


def finalize_native_player_session(session, search_memory, *, preface_cash_debits=0):
    """Seal the existing meters and terminal for a caller-owned native session.

    Does not close or reload the emulator. Both the continuous runner and the
    bounded TRAIN sequence adapter use this same accounting/cleanup path.
    """
    session.controller.input_enabled = False
    session.recorder.enabled = False
    if getattr(session, "milestone_splits", None) is not None:
        session.milestone_splits.write(session.output / "milestone-splits.json")
    _write(session.output / "terminal.state", session.controller.save_state_bytes())
    _record(session.output / "search-memory.json", search_memory.private_dict())
    _record(
        session.output / "native-costs.json",
        dict(
            schema="pokemon.red.native-player-costs.v1",
            actions_attempted=len(session.recorder.trace),
            actions_completed=session.actions.actions_executed,
            frames=session.controller.frames_executed,
            seconds=session.wall.elapsed_seconds,
            goal_attempts=session.decisions,
            restore_attempts=session.heals,
            nested_restore_attempts=session.support_restorations,
            training_healing_attempts=session.training_healing_trips,
            **(
                {"training_restoration_overlaps": session.training_restoration_overlaps}
                if getattr(session, "training_restoration_overlaps", 0)
                else {}
            ),
            control_recovery_cash_debits=preface_cash_debits,
            **(
                dict(
                    observed_cash_debits=session.actions.observed_cash_debits,
                    observed_cash_rewards=session.actions.observed_cash_rewards,
                    observed_cash_changes=session.actions.observed_cash_changes,
                )
                if session.actions.observe_cash is not None
                else {}
            ),
            buttons_released=not session.controller.pressed_buttons,
            automatic_fit=False,
            promotions=0,
            diagnostic_events=len(session.recorder.diagnostic_events),
            diagnostic_journal_seconds=session.recorder.diagnostic_journal_seconds,
        ),
    )
    from .red_player_lesson_runtime import (
        JournalBackedDiagnosticEvents,
        summarize_player_diagnostic_events,
        write_streamed_player_diagnostic_journal,
    )

    if isinstance(session.recorder.diagnostic_events, JournalBackedDiagnosticEvents):
        # Same bytes as the ordinary writer, one event in memory at a time.
        write_streamed_player_diagnostic_journal(
            session.output / "diagnostic-events.json", session.recorder.diagnostic_events
        )
    else:
        _record(
            session.output / "diagnostic-events.json",
            dict(
                schema="pokemon.red.player-diagnostic-journal.v1",
                diagnostic_only=True,
                automatic_fit=False,
                events=session.recorder.diagnostic_events,
                coverage=summarize_player_diagnostic_events(session.recorder.diagnostic_events),
            ),
        )
    if session.consequence is not None:
        session.consequence.finish()


def finish_native_registration_task(session, collector, *, initial_owned, task_sha256):
    """Stop only after a real newly observed native registration at a safe boundary.

    This supplies no target, choice, executor, reward or fit label. The caller
    pins its task catalog; independent native verification remains required.
    """
    stop = session.finish_decision()
    owned = frozenset(session.runtime.reader.read_pokedex_state().owned_species)
    if owned - initial_owned:
        snapshot = session.snapshot()
        if not snapshot.safe:
            raise ValueError("registration task cannot mark an unsafe terminal")
        collector.mark_task_terminal(task_sha256=task_sha256, boundary_sha256=snapshot.sha256)
        return True
    return stop
