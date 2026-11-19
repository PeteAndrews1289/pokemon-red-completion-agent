"""Explicit TRAIN reuse of the current whole-player menu and existing K pools.

Source ancestry remains the caller's independently authenticated duty. This
composition grants no TRAIN row admission, model fitting or campaign authority.
It never restricts the menu to its battle contracts: an unsupported selected
contract fails before battle input instead of choosing a replacement goal.
"""

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

from .executor import ReadOnlyController
from .provenance import canonical_sha256
from .red_scoped_training_battlers import ScopedTrainingBattlers, scoped_train_root_lineage_id
from .red_story_battle import StoryTrainerContract


@dataclass(frozen=True)
class ScopedTrainComposition:
    source_state_sha256: str
    source_origin_sha256: str
    source_commit: str
    context_sha256: str
    work_order_sha256: str
    native_plan_path: Path
    contracts: tuple[StoryTrainerContract, ...]
    include_silph: bool = False

    def __post_init__(self):
        for value, width in (
            (self.source_state_sha256, 64),
            (self.source_origin_sha256, 64),
            (self.source_commit, 40),
            (self.context_sha256, 64),
            (self.work_order_sha256, 64),
        ):
            if (
                type(value) is not str
                or len(value) != width
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError("scoped TRAIN composition requires exact identities")
        if (
            not isinstance(self.native_plan_path, Path)
            or not self.native_plan_path.is_absolute()
            or type(self.contracts) is not tuple
            or not 1 <= len(self.contracts) <= 4096
            or any(type(c) is not StoryTrainerContract for c in self.contracts)
            or len(set(self.contracts)) != len(self.contracts)
        ):
            raise ValueError("scoped TRAIN composition requires finite unique contracts")
        if type(self.include_silph) is not bool:
            raise ValueError("scoped TRAIN Silph opt-in requires a boolean")
        if self.include_silph and not {c.objective_id for c in self.contracts} <= {
            "defeat_erika",
            "rescue_fuji",
            "reach_saffron",
            "liberate_silph",
        }:
            raise ValueError("extended TRAIN scope contains an undeclared objective")
        groups = {}
        for contract in self.contracts:
            groups.setdefault(
                (contract.objective_id, contract.battle_plan_id, contract.map_id), []
            ).append(contract)
        if len({c.objective_id for c in self.contracts}) > 3 + int(self.include_silph) or any(
            len(v) > 32 for v in groups.values()
        ):
            raise ValueError("scoped TRAIN composition exceeds existing finite pool scope")
        # A physical trainer may obstruct different model-selected goals. Keep
        # each existing exact-contract actor; aliases cannot change native reward.
        native = {}
        for contract in self.contracts:
            key = (contract.map_id, contract.trainer_identity, contract.defeated_event)
            reward = (contract.victory_money, contract.victory_items, contract.victory_badge_bits)
            if key in native and native[key] != reward:
                raise ValueError("scoped TRAIN aliases disagree on native reward")
            native[key] = reward

    @property
    def root_lineage_id(self):
        return scoped_train_root_lineage_id(self.source_origin_sha256)

    def require_source(self, payload, context_bytes, work_order_bytes, *, origin_sha, origin_id):
        if (
            sha256(payload).hexdigest() != self.source_state_sha256
            or sha256(context_bytes).hexdigest() != self.context_sha256
            or sha256(work_order_bytes).hexdigest() != self.work_order_sha256
            or origin_sha != self.source_origin_sha256
            or origin_id != self.root_lineage_id
        ):
            raise ValueError("scoped TRAIN source/context/work order differs")
        context = json.loads(context_bytes)
        if context.get("state_sha256") != self.source_state_sha256:
            raise ValueError("scoped TRAIN context names another state")

    def bind(self, prototype, *, source, output, initial):
        if (
            source.get("partition") != "train"
            or source.get("state_sha256") != self.source_state_sha256
            or source.get("origin_sha256") != self.source_origin_sha256
            or source.get("source_commit") != self.source_commit
            or source.get("experiment_sha256") != self.work_order_sha256
        ):
            raise ValueError("scoped TRAIN assembly source differs")
        native_sha = None
        output = Path(output)
        if isinstance(prototype.session, ReadOnlyController):
            # The production caller assembles read-only before binding its native
            # controller. Preserve both declarations without consuming execution.
            output = output.with_name(output.name + "-read-only")
        if not isinstance(prototype.session, ReadOnlyController):
            plan = json.loads(self.native_plan_path.read_bytes())
            if (
                not isinstance(plan.get("source"), dict)
                or any(plan["source"].get(k) != v for k, v in source.items())
                or prototype.session.frames_executed != 0
            ):
                raise ValueError("scoped TRAIN native plan must bind before input")
            native_sha = canonical_sha256(plan)
        groups = {}
        for contract in self.contracts:
            groups.setdefault(
                (contract.objective_id, contract.battle_plan_id, contract.map_id), []
            ).append(contract)
        Path(output).mkdir(parents=True, exist_ok=False)
        pools = {
            objective: ScopedTrainingBattlers.for_native_source(
                prototype,
                source=source,
                contracts=tuple(contracts),
                output=output
                / (
                    objective[0]
                    + "--"
                    + sha256(objective[1].encode()).hexdigest()[:12]
                    + "--map"
                    + str(objective[2])
                ),
                experiment_sha256=self.work_order_sha256,
                initial=initial,
                native_plan_sha256=native_sha,
                allow_train_pp_reentry=True,
            )
            for objective, contracts in sorted(groups.items())
        }
        return ScopedTrainBattlerGroup(pools, source=source, output=output, initial=initial)


def scoped_composition_history(pools, initial):
    """Join each existing pool's measured latest battle, never sum duplicate XP."""
    histories = [(pool.history(), pool) for pool in pools.values()]
    active = [(history, pool) for history, pool in histories if pool.receipts]
    if not active:
        return initial

    def terminal_frame(pair):
        # Existing invocation receipts, not guessed episode ordering.
        row = json.loads(sorted(pair[1].output.glob("battle-*-end.json"))[-1].read_bytes())
        return row["after_frame"]

    return max(active, key=terminal_frame)[0]


class ScopedTrainBattlerGroup(ScopedTrainingBattlers):
    """Delegate exact roles to unchanged finite pools; no choice or fallback.

    Different mechanical roles may quote the same trainer for a selected goal.
    Each child retains its original no-alias/call/input guards. Their disjoint
    real invocation intervals are merged only for measured history and losses.
    """

    def __init__(self, pools, *, source, output, initial):
        self.pools = MappingProxyType(dict(pools))
        self.output, self.initial, self.receipts = Path(output), initial, ()
        document = dict(
            schema="pokemon.red.scoped-train-battler-group.v2",
            source_commit=source["source_commit"],
            source=dict(source),
            children={
                key[0] + ":" + key[1] + ":map:" + str(key[2]): pool.declaration_sha256
                for key, pool in pools.items()
            },
            training_eligible=False,
        )
        self.declaration_sha256 = canonical_sha256(document)
        with (self.output / "declaration.json").open("x") as f:
            json.dump(document, f, sort_keys=True, indent=2)

    def _check_group(self):
        document = json.loads((self.output / "declaration.json").read_bytes())
        children = {
            key[0] + ":" + key[1] + ":map:" + str(key[2]): pool.declaration_sha256
            for key, pool in self.pools.items()
        }
        if (
            canonical_sha256(document) != self.declaration_sha256
            or document["children"] != children
        ):
            raise ValueError("scoped TRAIN group declaration changed")

    def story(self, contract):
        self._check_group()
        key = (contract.objective_id, contract.battle_plan_id, contract.map_id)
        if key not in self.pools:
            raise ValueError("selected TRAIN contract is outside prospective scope")
        return self.pools[key].story(contract)

    @property
    def wild(self):
        self._check_group()
        return next(iter(self.pools.values())).wild

    def history(self):
        self._check_group()
        result = scoped_composition_history(self.pools, self.initial)
        self.receipts = tuple(
            (str(key), receipt)
            for key, pool in sorted(self.pools.items())
            for receipt in pool.receipts
        )
        return result

    def verified_outcomes(
        self, *, expected_native_plan_sha256, expected_declaration_sha256, source_sha256
    ):
        self._check_group()
        if expected_declaration_sha256 != self.declaration_sha256:
            raise ValueError("scoped TRAIN group audit declaration differs")
        rows = []
        for pool in self.pools.values():
            rows.extend(
                pool.verified_outcomes(
                    expected_native_plan_sha256=expected_native_plan_sha256,
                    expected_declaration_sha256=pool.declaration_sha256,
                    source_sha256=source_sha256,
                )
            )
        ordered = sorted(rows, key=lambda row: (row.before_frame, row.after_frame))
        previous = -1
        for row in ordered:
            if row.before_frame < previous or row.after_frame <= row.before_frame:
                raise ValueError("scoped TRAIN group has overlapping native battles")
            previous = row.after_frame
        return tuple(replace(row, ordinal=i) for i, row in enumerate(ordered))


_SELECTOR_TOKEN = object()


def scoped_selector_declaration(model, head, *, objective_ref, challenge_ref, flags, sequence_horizon=None):
    """Describe the existing selector, never replace its choices or features."""
    from .living_dex_option_value import LivingDexOptionValueModel
    from .player_challenge_consequence import (
        ChallengeConsequenceHead,
        consequence_feature_versions_compatible,
    )
    from .red_consequence_choice import branch_recovery_identity, branch_recovery_scope_ref

    required = {
        "greedy_selection": True,
        "refine_preparation": True,
        "defer_unbound_preparation": False,
        "allow_singleton_parent_support": False,
        "associate_unique_combat": True,
        "explore_outside_scope": False,
        "explore_on_movement_recurrence": True,
    }
    if (
        type(model) is not LivingDexOptionValueModel
        or model.feature_version != 16
        or type(head) is not ChallengeConsequenceHead
        or head.provenance != "native_train"
        or head.feedback_version != 2
        or not consequence_feature_versions_compatible(head.feature_version, model.feature_version)
        or type(flags) is not dict
        or flags != required
        or any(type(v) is not bool for v in flags.values())
        or challenge_ref != branch_recovery_scope_ref(objective_ref)
    ):
        raise ValueError("scoped TRAIN selector requires the exact existing V16 recurrence recipe")
    if sequence_horizon is not None and (
        type(sequence_horizon) is not int or not 1 <= sequence_horizon <= 4
    ):
        raise ValueError("passive TRAIN recording requires a horizon in1..4")
    identity = branch_recovery_identity(
        model.model_sha256, head.model_sha256, objective_ref, **flags
    )
    return dict(
        schema=("pokemon.red.scoped-train-selector-inference.v1" if sequence_horizon is None
                else "pokemon.red.scoped-train-selector-inference.v2"),
        parent_model_sha256=model.model_sha256,
        consequence_head_sha256=head.model_sha256,
        selector_sha256=identity,
        objective_refs=list(objective_ref) if type(objective_ref) is tuple else [objective_ref],
        challenge_ref=challenge_ref,
        flags=dict(flags),
        movement_revisit_saturation=True,
        sequence_policy=False,
        sequence_collector=sequence_horizon is not None,
        **({"sequence_horizon": sequence_horizon} if sequence_horizon is not None else {}),
        automatic_fit=False,
        optimizer_admission=False,
    )


def _selector_input_declaration(*, composition, source, source_state, context_bytes, work_order_bytes, model, head, objective_ref, challenge_ref, flags):
    if type(composition) is not ScopedTrainComposition:
        raise ValueError("TRAIN selector construction needs typed composition")
    composition.require_source(
        source_state,
        context_bytes,
        work_order_bytes,
        origin_sha=source.get("origin_sha256"),
        origin_id=composition.root_lineage_id,
    )
    if any(
        source.get(k) != v
        for k, v in dict(
            partition="train",
            state_sha256=composition.source_state_sha256,
            origin_sha256=composition.source_origin_sha256,
            source_commit=composition.source_commit,
            experiment_sha256=composition.work_order_sha256,
        ).items()
    ):
        raise ValueError("scoped TRAIN selector source differs")
    context, work = map(json.loads, (context_bytes, work_order_bytes))
    declaration = scoped_selector_declaration(
        model, head, objective_ref=objective_ref, challenge_ref=challenge_ref, flags=flags,
        sequence_horizon=work.get("sequence_horizon"),
    )
    if (
        context.get("schema") != "pokemon.red.native-player-continuation.v1"
        or context.get("fit_allowed") is not False
        or context.get("grants_new_budget") is not False
        or work.get("partition") != "train"
        or work.get("fit_allowed") is not False
        or work.get("production_selector") != declaration
    ):
        raise ValueError("scoped TRAIN selector context/work order differs")
    qualification = work.get("source_qualification")
    if type(qualification) is not dict or set(qualification) != {"path", "sha256"}:
        raise ValueError("scoped TRAIN selector needs pinned original source qualification")
    qbytes = Path(qualification["path"]).read_bytes()
    q = json.loads(qbytes)
    if (
        sha256(qbytes).hexdigest() != qualification["sha256"]
        or work.get("pins", {}).get(qualification["path"]) != qualification["sha256"]
        or q.get("partition") != "train"
        or q.get("full_current_menu_constructed") is not True
        or q.get("original_state_unchanged") is not True
        or q.get("source", {}).get("sha256") != composition.source_state_sha256
        or q.get("native_boundary", {}).get("state_sha256") != composition.source_state_sha256
    ):
        raise ValueError("scoped TRAIN selector source qualification differs")
    return declaration, qualification


@dataclass(frozen=True, init=False)
class ScopedTrainSelectorInference:
    """Input-byte witness beside existing TRAIN pools; no fitting authority.

    The caller still authenticates original registry ancestry. This witness
    checks its pinned native source qualification and the existing sealed
    execution declaration, without inventing an admission or a new policy.
    """

    _bytes: bytes
    _source_bytes: bytes
    _composition: ScopedTrainComposition
    _native_sha256: str
    _token: object

    def __init__(self, document, *, source, composition, native_sha256, _token=None):
        if _token is not _SELECTOR_TOKEN:
            raise ValueError("scoped TRAIN selector needs authenticated native input bytes")

        def pack(value):
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

        object.__setattr__(self, "_bytes", pack(document))
        object.__setattr__(self, "_source_bytes", pack(source))
        object.__setattr__(self, "_composition", composition)
        object.__setattr__(self, "_native_sha256", native_sha256)
        object.__setattr__(self, "_token", _SELECTOR_TOKEN)

    @classmethod
    def authenticate(
        cls,
        *,
        composition,
        source,
        source_state,
        context_bytes,
        work_order_bytes,
        session,
        model,
        head,
        objective_ref,
        challenge_ref,
        flags,
    ):
        from .private_artifacts import PrivateArtifactRoot
        from .red_native_player import NativeExecutionIdentity, NativePlayerSession

        if type(session) is not NativePlayerSession:
            raise ValueError("scoped TRAIN selector requires an existing native session")
        store = session.store
        if (
            type(composition) is not ScopedTrainComposition
            or type(store) is not PrivateArtifactRoot
            or session.source != source
            or session.actions.actions_executed != 0
            or session.controller.frames_executed != 0
            or session.output / "native-plan.json" != composition.native_plan_path
        ):
            raise ValueError("scoped TRAIN selector requires typed composition and native store")
        declaration, qualification = _selector_input_declaration(
            composition=composition, source=source, source_state=source_state,
            context_bytes=context_bytes, work_order_bytes=work_order_bytes,
            model=model, head=head, objective_ref=objective_ref,
            challenge_ref=challenge_ref, flags=flags,
        )
        native = json.loads(composition.native_plan_path.read_bytes())
        execution = NativeExecutionIdentity(**native["execution"])
        sealed = store.find_sealed_record(
            execution.claim_id, expected_kind="red_native_player_execution"
        )
        if (
            native.get("schema") != "pokemon.red.native-continuous-player.v2"
            or native.get("source") != source
            or session.execution != execution
            or execution.model_sha256 != declaration["selector_sha256"]
            or native.get("automatic_fit") is not False
            or native.get("promotion") is not False
            or native.get("passive_sequence_horizon") != declaration.get("sequence_horizon")
            or sealed is None
            or canonical_sha256(sealed.read()) != canonical_sha256(native)
        ):
            raise ValueError("scoped TRAIN selector sealed execution differs")
        document = dict(
            declaration,
            source_identity_sha256=canonical_sha256(source),
            source_qualification_sha256=qualification["sha256"],
            work_order_sha256=composition.work_order_sha256,
            context_sha256=composition.context_sha256,
            native_plan_sha256=canonical_sha256(native),
            source_ancestry_and_fit_admission_not_conferred=True,
        )
        return cls(
            document,
            source=source,
            composition=composition,
            native_sha256=canonical_sha256(native),
            _token=_SELECTOR_TOKEN,
        )

    def document(self):
        return json.loads(self._bytes)

    @property
    def identity(self):
        return sha256(self._bytes).hexdigest()

    def require(self, *, source, model, head, objective_ref, challenge_ref, flags):
        declaration = scoped_selector_declaration(
            model, head, objective_ref=objective_ref, challenge_ref=challenge_ref, flags=flags,
            sequence_horizon=self.document().get("sequence_horizon"),
        )
        pack = json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
        document = self.document()
        if (
            getattr(self, "_token", None) is not _SELECTOR_TOKEN
            or pack != self._source_bytes
            or any(document.get(k) != v for k, v in declaration.items())
            or canonical_sha256(json.loads(self._composition.native_plan_path.read_bytes()))
            != self._native_sha256
        ):
            raise ValueError("scoped TRAIN selector witness differs")


def validate_train_selector_scope(scope, **kwargs):
    if type(scope) is not ScopedTrainSelectorInference:
        raise ValueError("scoped TRAIN selector requires its exact authenticated witness")
    scope.require(**kwargs)
    return True


_AUTHENTICATION_TOKEN = object()


@dataclass(frozen=True, init=False)
class ScopedTrainSelectorAuthentication:
    """Construction request; selection still needs a zero-input sealed witness."""

    _source_bytes: bytes
    _state: bytes
    _context: bytes
    _work: bytes
    _composition: object
    _document_bytes: bytes
    _token: object

    def __init__(self, *, source, source_state, context_bytes, work_order_bytes,
                 composition, document, _token=None):
        if _token is not _AUTHENTICATION_TOKEN:
            raise ValueError("TRAIN selector authentication requires input-byte checks")
        pack = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        for name, value in dict(_source_bytes=pack(source), _state=bytes(source_state),
                                _context=bytes(context_bytes), _work=bytes(work_order_bytes),
                                _composition=composition, _document_bytes=pack(document),
                                _token=_token).items():
            object.__setattr__(self, name, value)

    @classmethod
    def authenticate(cls, *, composition, source, source_state, context_bytes,
                     work_order_bytes, model, head, objective_ref, challenge_ref, flags):
        declaration, qualification = _selector_input_declaration(
            composition=composition, source=source, source_state=source_state,
            context_bytes=context_bytes, work_order_bytes=work_order_bytes,
            model=model, head=head, objective_ref=objective_ref,
            challenge_ref=challenge_ref, flags=flags,
        )
        work = json.loads(work_order_bytes)
        recipe = work.get("native_session_recipe")
        expected_recipe = dict(force_resource_safety=False, include_live_pp_readiness=True,
                               allow_collection_restoration=True, continue_safe_route_failures=False,
                               story_milestone_commitment=True, story_kind_commitment=True)
        if (recipe != expected_recipe or not isinstance(recipe, dict)
                or any(type(v) is not bool for v in recipe.values())
                or type(work.get("native_limits")) is not dict):
            raise ValueError("TRAIN selector needs exact production session recipe and limits")
        document = dict(declaration, construction_only=True,
                        source_identity_sha256=canonical_sha256(source),
                        source_qualification_sha256=qualification["sha256"],
                        context_sha256=composition.context_sha256,
                        work_order_sha256=composition.work_order_sha256,
                        native_session_recipe=recipe, native_limits=work["native_limits"])
        return cls(composition=composition, source=source, source_state=source_state,
                   context_bytes=context_bytes, work_order_bytes=work_order_bytes,
                   document=document, _token=_AUTHENTICATION_TOKEN)

    def document(self):
        return json.loads(self._document_bytes)

    @property
    def identity(self):
        return sha256(self._document_bytes).hexdigest()

    def require(self, *, source, model, head, objective_ref, challenge_ref, flags,
                native_recipe=None, limits=None):
        if (getattr(self, "_token", None) is not _AUTHENTICATION_TOKEN
                or canonical_sha256(source) != self.document()["source_identity_sha256"]):
            raise ValueError("TRAIN selector construction source differs")
        declaration, _ = _selector_input_declaration(
            composition=self._composition, source=source, source_state=self._state,
            context_bytes=self._context, work_order_bytes=self._work,
            model=model, head=head, objective_ref=objective_ref,
            challenge_ref=challenge_ref, flags=flags,
        )
        if any(self.document().get(k) != v for k,v in declaration.items()):
            raise ValueError("TRAIN selector construction recipe differs")
        if ((native_recipe is not None and native_recipe != self.document()["native_session_recipe"])
                or (limits is not None and limits != self.document()["native_limits"])):
            raise ValueError("TRAIN selector actual session recipe or limits differ")

    def bind(self, *, session, source, model, head, objective_ref, challenge_ref, flags):
        self.require(source=source, model=model, head=head, objective_ref=objective_ref,
                     challenge_ref=challenge_ref, flags=flags)
        plan = json.loads((session.output / "native-plan.json").read_bytes())
        policy = plan.get("consequence_policy", {})
        resource = plan.get("player_resource_configuration", {})
        recipe = dict(force_resource_safety=resource.get("force_resource_safety", True),
                      include_live_pp_readiness=resource.get("include_live_pp_readiness", False),
                      allow_collection_restoration=plan.get("allow_collection_restoration", False),
                      continue_safe_route_failures=plan.get("continue_safe_route_failures", False),
                      story_milestone_commitment=plan.get("story_milestone_commitment", False),
                      story_kind_commitment=plan.get("story_kind_commitment", False))
        if recipe != self.document()["native_session_recipe"] or plan["limits"] != self.document()["native_limits"]:
            raise ValueError("TRAIN selector sealed session recipe differs")
        if (plan.get("scoped_train_selector_authentication") != self.document()
                or policy.get("head_sha256") != head.model_sha256
                or policy.get("branch_model_sha256") != model.model_sha256
                or not plan.get("allow_greedy_branch_recovery")
                or plan.get("passive_sequence_horizon") != self.document().get("sequence_horizon")
                or any(plan.get(k, False) != v for k,v in flags.items())):
            raise ValueError("TRAIN selector sealed native configuration differs")
        return ScopedTrainSelectorInference.authenticate(
            composition=self._composition, source=source, source_state=self._state,
            context_bytes=self._context, work_order_bytes=self._work,
            session=session, model=model, head=head, objective_ref=objective_ref,
            challenge_ref=challenge_ref, flags=flags,
        )


def validate_selector_authentication(value, *, allow, train_inference_scope, **kwargs):
    if (type(value) is not ScopedTrainSelectorAuthentication or allow is not True
            or train_inference_scope is not None):
        raise ValueError("TRAIN selector requires its exact construction bundle")
    value.require(**kwargs)
    return True


def validate_passive_train_sequence(scope, horizon, *, sequence_policy=None, consequence_spec=None):
    """Recording only, beside the unchanged selector; no fit or policy authority."""
    if scope is None:
        return False
    if type(scope) not in (ScopedTrainSelectorAuthentication, ScopedTrainSelectorInference):
        raise ValueError("passive TRAIN sequence needs its typed selector witness")
    document = scope.document()
    declared = document.get("sequence_horizon")
    if declared is None:
        return False
    if (type(horizon) is not int or horizon != declared
            or document.get("sequence_collector") is not True
            or document.get("sequence_policy") is not False
            or document.get("optimizer_admission") is not False
            or sequence_policy is not None or consequence_spec is not None):
        raise ValueError("passive TRAIN sequence differs from declared recording scope")
    return True


_PRODUCTION_SEQUENCE_TOKEN = object()


def production_sequence_train_declaration(model, policy, limits, recipe):
    """Pin the normal selector; this grants neither fitting nor native labels."""
    from .living_dex_option_value import LivingDexOptionValueModel
    from .player_sequence_policy import SequencePolicy
    from .red_native_player import NativePlayerLimits
    required = {'force_resource_safety', 'include_live_pp_readiness',
                'allow_collection_restoration', 'story_kind_commitment',
                'respect_combat_preparation_choice', 'movement_revisit_saturation'}
    if (type(model) is not LivingDexOptionValueModel or model.feature_version != 16
            or type(policy) is not SequencePolicy or policy.baseline_sha256 != model.model_sha256
            or policy.head.feature_version != 16 or type(limits) is not NativePlayerLimits
            or type(recipe) is not dict or set(recipe) != required
            or any(type(v) is not bool for v in recipe.values())):
        raise ValueError('production TRAIN sequence requires the declared normal recipe')
    from dataclasses import asdict
    return dict(schema='pokemon.red.production-sequence-train.v1',
        goal_model_sha256=model.model_sha256, sequence_policy_sha256=policy.model_sha256,
        sequence_horizon=policy.head.horizon, target_contract=policy.head.target_contract,
        selection_history_contract=policy.head.history_contract, limits=asdict(limits),
        recipe=dict(recipe), full_normal_menu=True, teacher_selection=False,
        optimizer_admission=False, campaign=False)


@dataclass(frozen=True, init=False)
class ProductionSequenceTrainScope:
    """Use existing authenticated League TRAIN fixtures in the normal player.

    This is a construction witness. Native inputs, costs, outcomes and row
    admission remain separately checked. The original synthetic/correlated
    fixture ancestry and exact retained battle-component restrictions remain.
    """
    _bytes: bytes
    funding_admission: object

    def __init__(self, document, admission, *, _token=None):
        if _token is not _PRODUCTION_SEQUENCE_TOKEN:
            raise ValueError('production TRAIN scope requires actual authenticated bytes')
        object.__setattr__(self, '_bytes', json.dumps(document,sort_keys=True,separators=(',',':')).encode())
        object.__setattr__(self, 'funding_admission', admission)

    @classmethod
    def authenticate(cls, *, admission, source_state, context_bytes, work_order_bytes,
                     model, policy, limits, recipe):
        from .red_production_train_admission import LeagueFundingTrainAdmission
        if (type(admission) is not LeagueFundingTrainAdmission
                or any(type(p) is not bytes for p in (source_state,context_bytes,work_order_bytes))):
            raise ValueError('production TRAIN sequence requires an authenticated TRAIN source')
        admission.require_work_order(work_order_bytes)
        declaration=production_sequence_train_declaration(model,policy,limits,recipe)
        work=json.loads(work_order_bytes);context=json.loads(context_bytes)
        supplied=work.get('synthetic_context_prerequisites',[])
        allowed={'defeat_lorelei','defeat_bruno','defeat_agatha','defeat_lance',
                 'defeat_champion','enter_hall_of_fame'}
        if (type(supplied) is not list or any(type(x) is not str for x in supplied)
                or len(supplied)!=len(set(supplied)) or not set(supplied)<=allowed
                or not set(supplied)<=set(context.get('lesson',{}).get('completed_objectives',[]))):
            raise ValueError('TRAIN context prerequisites must be explicit supplied history')
        from .recorded_branch_history import STORY_HISTORY, validate_history_contract
        collection_history=work.get('sequence_collection_history_contract',policy.head.history_contract)
        validate_history_contract(collection_history)
        if (sha256(source_state).hexdigest()!=admission.source_state_sha256
                or context.get('state_sha256')!=admission.source_state_sha256
                or work.get('production_sequence')!=declaration
                or work.get('fit_allowed') is not False
                or work.get('campaign') is not False):
            raise ValueError('production TRAIN sequence source/context/recipe differs')
        doc=dict(declaration,source_state_sha256=admission.source_state_sha256,
            source_origin_sha256=admission.source_origin_sha256,source_commit=admission.source_commit,
            work_order_sha256=admission.work_order_sha256,work_canonical_sha256=canonical_sha256(work),
            context_sha256=sha256(context_bytes).hexdigest(),funding_admission_sha256=admission.identity,
            collection_history_contract=collection_history,
            synthetic_context_prerequisites=supplied,
            supplied_story_progress_is_earned=False,
            source_partition='train',fit_admission=False,new_independent_origin=False)
        return cls(doc,admission,_token=_PRODUCTION_SEQUENCE_TOKEN)

    def document(self):
        return json.loads(self._bytes)

    @property
    def identity(self):
        return canonical_sha256(self.document())

    def require_plan(self, plan):
        d=self.document()
        if (canonical_sha256(plan)!=d['work_canonical_sha256']
                or d['funding_admission_sha256']!=self.funding_admission.identity):
            raise ValueError('production TRAIN sequence work order changed')

    def require_source(self, source):
        d=self.document()
        expected=dict(partition='train',state_sha256=d['source_state_sha256'],
            origin_sha256=d['source_origin_sha256'],source_commit=d['source_commit'],
            experiment_sha256=d['work_order_sha256'])
        if any(source.get(k)!=v for k,v in expected.items()):
            raise ValueError('production TRAIN sequence native source differs')

    def require_assembly(self, *, payload, context_bytes, work_order_bytes, origin_sha, origin_id):
        self.funding_admission.require_work_order(work_order_bytes)
        self.require_plan(json.loads(work_order_bytes));d=self.document()
        if (sha256(payload).hexdigest()!=d['source_state_sha256']
                or sha256(context_bytes).hexdigest()!=d['context_sha256']
                or origin_sha!=d['source_origin_sha256']
                or origin_id!=self.funding_admission.root_lineage_id):
            raise ValueError('production TRAIN sequence assembly source differs')

    def require_session(self, *, source, execution, limits, recipe):
        from dataclasses import asdict
        self.require_source(source);d=self.document()
        expected_recipe={k:v for k,v in d['recipe'].items() if k!='movement_revisit_saturation'}
        if (execution.model_sha256!=d['sequence_policy_sha256']
                or asdict(limits)!=d['limits'] or recipe!=expected_recipe):
            raise ValueError('production TRAIN sequence session recipe differs')

    def require_policy(self, *, source, model, policy, limits, recipe):
        self.require_source(source);actual=production_sequence_train_declaration(model,policy,limits,recipe)
        d=self.document()
        if any(d.get(k)!=v for k,v in actual.items()):
            raise ValueError('production TRAIN sequence selector differs')

    def require_collection(self, *, history_contract, task_kind, task_sha256):
        from .constants import POKEMON_RED_US_REV_0
        from .player_sequence_targets import registration_task_catalog
        expected=registration_task_catalog(POKEMON_RED_US_REV_0.sha256)['task_sha256']
        if (history_contract!=self.document()['collection_history_contract']
                or task_kind!='next_registration' or task_sha256!=expected):
            raise ValueError('production TRAIN sequence collection/task contract differs')
