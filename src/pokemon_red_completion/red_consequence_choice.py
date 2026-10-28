"""Opt-in frozen consequence ranking over the existing native option bindings."""

from dataclasses import dataclass, replace
import json
from math import isfinite

from .goal_manager import GoalKind
from .goal_manager_runtime import GoalCashOutcome
from .goal_resource_quote import GoalResourceQuote
from .living_dex_goal_policy import living_dex_option_kind_for_goal
from .living_dex_option_value import (
    LivingDexOptionValueModel, LivingDexOptionAvailability, LivingDexOptionUnavailableReason,
)
from .player_challenge_consequence import (
    ChallengeConsequenceHead, supports_consequence_preparation,
)
from .provenance import canonical_sha256
from .red_live_option_menu import (
    RedLiveOptionChoice,
    RedLiveOptionSelectionMode,
    RedLiveOptionSet,
    select_red_live_option,
    select_red_live_safety_option,
)


def condition_consequence_candidate(candidate, parent):
    """Reuse only the exact observed combat parent's current challenge facts."""
    challenge = parent.challenge
    if (parent.features.kind is not living_dex_option_kind_for_goal(GoalKind.ADVANCE_STORY, feature_version=15)
            or challenge is None or not challenge.combat_required
            or not challenge.opposition_known):
        raise ValueError("consequence conditioning requires an observed combat parent")
    return replace(candidate, challenge=challenge)


def recovery_purchase_quote(quote):
    """An actual medicine purchase, not earning, balls, a sale or consumption."""
    return (
        type(quote) is GoalResourceQuote
        and quote.purchase_cost > 0
        and quote.funding_proceeds == 0
        and quote.expected_income == 0
        and quote.available_recovery_units is None
        and len(quote.reserves) == 1
        and quote.reserves[0].resource == "recovery"
    )


def branch_recovery_objectives(objective_ref):
    """Normalize private scope metadata without ordering goals or policy features."""
    if type(objective_ref) is str and objective_ref.strip():
        return (objective_ref,)
    if (
        type(objective_ref) is tuple
        and len(objective_ref) >= 2
        and all(type(ref) is str and ref.strip() for ref in objective_ref)
        and tuple(sorted(set(objective_ref))) == objective_ref
    ):
        return objective_ref
    raise ValueError("branch recovery requires one branch or a canonical declared branch set")


def valid_branch_recovery_objectives(objective_ref):
    try:
        branch_recovery_objectives(objective_ref)
    except ValueError:
        return False
    return True


def branch_recovery_scope_ref(objective_ref):
    scope = branch_recovery_objectives(objective_ref)
    return (objective_ref if type(objective_ref) is str else
            "pokemon.red:readiness-scope:" + canonical_sha256(list(scope)))


def branch_recovery_identity(
    branch_sha256, head_sha256, objective_ref, *, greedy_selection=False,
    refine_preparation=False, defer_unbound_preparation=False, allow_singleton_parent_support=False,
):
    """Private dispatch context binds authority,never enters model features."""
    if (
        any(
            type(s) is not str or len(s) != 64 or any(c not in "0123456789abcdef" for c in s)
            for s in (branch_sha256, head_sha256)
        )
        or not valid_branch_recovery_objectives(objective_ref)
    ):
        raise ValueError("branch/recovery authority requires exact component identities")
    if type(greedy_selection) is not bool:
        raise ValueError("branch recovery selection rule must be boolean")
    if type(refine_preparation) is not bool or refine_preparation and not greedy_selection:
        raise ValueError("preparation refinement requires declared highest-score selection")
    if type(defer_unbound_preparation) is not bool or defer_unbound_preparation and not greedy_selection:
        raise ValueError("parent-bound preparation requires declared highest-score selection")
    if type(allow_singleton_parent_support) is not bool or allow_singleton_parent_support and (
        not defer_unbound_preparation or not greedy_selection
    ):
        raise ValueError("singleton parent support requires explicit parent-bound preparation")
    plural = type(objective_ref) is tuple
    if plural and not greedy_selection:
        raise ValueError("plural branch recovery requires declared highest-score selection")
    return canonical_sha256(
        dict(
            schema=("pokemon.red.branch-recovery-policy.v6" if allow_singleton_parent_support
                    else "pokemon.red.branch-recovery-policy.v5" if defer_unbound_preparation
                    else "pokemon.red.branch-recovery-policy.v4" if refine_preparation
                    else "pokemon.red.branch-recovery-policy.v3" if plural
                    else "pokemon.red.branch-recovery-policy.v2" if greedy_selection
                    else "pokemon.red.branch-recovery-policy.v1"),
            branch_sha256=branch_sha256,
            head_sha256=head_sha256,
            **({"objective_refs": list(objective_ref)} if plural
               else {"objective_ref": objective_ref}),
            **({"parent_selection_rule": "maximum_score_with_seeded_ties"}
               if greedy_selection else {}),
            **({"refine_preparation": True} if refine_preparation else {}),
            **({"defer_unbound_preparation": True} if defer_unbound_preparation else {}),
            **({"allow_singleton_parent_support": True} if allow_singleton_parent_support else {}),
        )
    )


def validate_greedy_branch_recovery_scope(
    *, allow, greedy_selection, source, model, head, objective_ref, challenge_ref,
    refine_preparation=False, defer_unbound_preparation=False, allow_singleton_parent_support=False,
    train_inference_scope=None,
):
    """Default-off composition admission, not a new choice policy or feature."""
    if type(allow) is not bool:
        raise ValueError("greedy branch recovery permission must be boolean")
    if type(refine_preparation) is not bool or refine_preparation and (
        not allow or greedy_selection is not True
    ):
        raise ValueError("preparation refinement requires explicit greedy branch recovery scope")
    if type(defer_unbound_preparation) is not bool or defer_unbound_preparation and (
        not allow or greedy_selection is not True
    ):
        raise ValueError("parent-bound preparation requires explicit greedy branch recovery scope")
    if type(allow_singleton_parent_support) is not bool or allow_singleton_parent_support and (
        not allow or not defer_unbound_preparation or greedy_selection is not True
    ):
        raise ValueError("singleton parent support requires explicit DEVELOPMENT composition scope")
    train_inference = False
    if train_inference_scope is not None:
        from .red_production_train_inference import validate_train_consequence_inference
        train_inference = validate_train_consequence_inference(train_inference_scope,
            source=source, model=model, head=head, objective_ref=objective_ref, challenge_ref=challenge_ref)
        if not allow or greedy_selection is not True:
            raise ValueError("typed TRAIN inference requires explicit existing greedy branch recovery")
    if not allow:
        return
    if (
        greedy_selection is not True
        or (source.get("partition") != "development" and not train_inference)
        or not isinstance(model, LivingDexOptionValueModel)
        or model.feature_version not in (7, 9, 10, 11, 15)
        or type(head) is not ChallengeConsequenceHead
        or head.feature_version != model.feature_version
        or head.feedback_version != 2
        or head.provenance != "native_train"
        or not valid_branch_recovery_objectives(objective_ref)
        or type(challenge_ref) is not str or not challenge_ref.strip()
        or (type(objective_ref) is tuple
            and challenge_ref != branch_recovery_scope_ref(objective_ref))
        or any(
            type(source.get(key)) is not str
            or len(source[key]) != 64
            or any(c not in "0123456789abcdef" for c in source[key])
            for key in ("state_sha256", "experiment_sha256")
        )
    ):
        raise ValueError("greedy branch recovery requires exact declared DEVELOPMENT scope")
    branch_recovery_identity(model.model_sha256, head.model_sha256, objective_ref,
                             greedy_selection=True, refine_preparation=refine_preparation,
                             defer_unbound_preparation=defer_unbound_preparation,
            allow_singleton_parent_support=allow_singleton_parent_support)
    return True if train_inference else None


def _refinement_branch(parent, scope, *, refine_preparation, defer_unbound_preparation=False, allow_singleton_parent_support=False):
    """Bind an existing combat question without guessing a preparation target."""
    options = parent.options
    selected = parent.selected_binding
    candidate = options.menu.candidates[parent.selected_candidate_index]
    challenge = candidate.challenge
    if challenge is None or not challenge.combat_required or not challenge.opposition_known:
        return None
    if selected.kind is GoalKind.ADVANCE_STORY:
        return selected if selected.story_objective_ref in scope else None
    if not (
        refine_preparation
        and selected.kind is GoalKind.DEVELOP_TEAM
        and supports_consequence_preparation(candidate, options.menu.feature_version)
    ):
        return None
    matches = tuple(
        options.binding(i)
        for i in options.menu.available_indices
        if options.binding(i).kind is GoalKind.ADVANCE_STORY
        and options.menu.candidates[i].challenge == challenge
    )
    return (matches[0] if len(matches) == 1
            and matches[0].story_objective_ref in scope else None)


@dataclass(frozen=True)
class BranchRecoveryDecision:
    """Two existing decisions,with no score blending or fixed branch order."""

    parent: RedLiveOptionChoice
    child: RedLiveOptionChoice | None
    head_sha256: str
    objective_ref: str | tuple[str, ...]
    greedy_selection: bool = False
    refine_preparation: bool = False
    defer_unbound_preparation: bool = False
    allow_singleton_parent_support: bool = False

    @property
    def identity(self):
        return branch_recovery_identity(
            self.parent.model_sha256, self.head_sha256, self.objective_ref,
            greedy_selection=self.greedy_selection,
            refine_preparation=self.refine_preparation,
            defer_unbound_preparation=self.defer_unbound_preparation,
            allow_singleton_parent_support=self.allow_singleton_parent_support,
        )

    def validate(self, choice):
        if (
            type(self.greedy_selection) is not bool
            or type(self.refine_preparation) is not bool
            or type(self.defer_unbound_preparation) is not bool
            or type(self.allow_singleton_parent_support) is not bool
            or type(self.parent) is not RedLiveOptionChoice
            or self.parent.branch_recovery is not None
            or self.parent.sequence_policy is not None
            or self.parent.seed != choice.seed
            or self.parent.consequence_head_sha256 is not None
            or (self.parent.options is not choice.options and (
                not self.defer_unbound_preparation
                or self.parent.options != _preparation_parent_options(choice.options)))
            or choice.model_sha256 != self.identity
            or choice.sequence_policy is not None
            or choice.consequence_head_sha256 is not None
            or (self.greedy_selection and self.parent.mode
                is RedLiveOptionSelectionMode.MODEL_EXPLORATION)
            or (not self.greedy_selection and self.parent.mode
                is RedLiveOptionSelectionMode.MODEL_GREEDY)
        ):
            raise ValueError("branch recovery parent authority differs")
        selected = self.parent.selected_binding
        forced_parent = self.parent.mode is RedLiveOptionSelectionMode.FORCED_SINGLETON_SUPPORT
        if forced_parent and (
            not self.allow_singleton_parent_support or not self.defer_unbound_preparation
            or self.child is None
            or self.parent.options is not choice.options
            or self.parent.selected_candidate_index != _sole_observed_combat_parent(
                choice.options, branch_recovery_objectives(self.objective_ref))
        ):
            raise ValueError("forced singleton parent differs from exact observed combat binding")
        if self.child is None:
            if (
                choice.selected_binding is not selected
                or choice.mode is not (
                    RedLiveOptionSelectionMode.MODEL_EXPLORATION
                    if self.defer_unbound_preparation
                    and _branch_scope_available(choice.options, branch_recovery_objectives(self.objective_ref))
                    and self.parent.mode is RedLiveOptionSelectionMode.MODEL_GREEDY
                    else self.parent.mode)
                or choice.scores != self.parent.scores
                or choice.probabilities != self.parent.probabilities
            ):
                raise ValueError("branch recovery changed an unrefined branch")
            return
        branch = _refinement_branch(
            self.parent, branch_recovery_objectives(self.objective_ref),
            refine_preparation=self.refine_preparation,
            defer_unbound_preparation=self.defer_unbound_preparation,
            allow_singleton_parent_support=self.allow_singleton_parent_support,
        )
        if (
            type(self.child) is not RedLiveOptionChoice
            or self.child.branch_recovery is not None
            or self.child.consequence_head_sha256 != self.head_sha256
            or branch is None
            or choice.selected_binding is not self.child.selected_binding
            or self.child.selected_binding not in choice.options.bindings
        ):
            raise ValueError("branch recovery child crosses its selected objective")
        parent_challenge = self.parent.options.menu.candidates[
            self.parent.selected_candidate_index
        ].challenge
        if (
            parent_challenge is None
            or not parent_challenge.combat_required
            or not parent_challenge.opposition_known
            or any(c.challenge != parent_challenge for c in self.child.options.menu.candidates)
            or not any(b is branch for b in self.child.options.bindings)
            or any(
                b.kind is GoalKind.ADVANCE_STORY and b is not branch
                for b in self.child.options.bindings
            )
        ):
            raise ValueError("branch recovery has incomparable challenge contexts")
        original = {
            b.binding_ref: (b, c)
            for b, c in zip(choice.options.bindings, choice.options.menu.candidates, strict=True)
        }
        if (
            self.child.options.original_bindings is not choice.options.original_bindings
            or self.child.options.force_resource_safety != choice.options.force_resource_safety
            or self.child.options.situation != choice.options.situation
            or self.child.options.menu.context != choice.options.menu.context
            or self.parent.mode is not (
                RedLiveOptionSelectionMode.FORCED_SINGLETON_SUPPORT if forced_parent
                else RedLiveOptionSelectionMode.MODEL_GREEDY if self.greedy_selection
                else RedLiveOptionSelectionMode.MODEL_EXPLORATION
            )
            or choice.mode is not RedLiveOptionSelectionMode.MODEL_EXPLORATION
            or self.child.seed != choice.seed
        ):
            raise ValueError("branch recovery changed the observed decision boundary")
        for binding, candidate in zip(
            self.child.options.bindings, self.child.options.menu.candidates, strict=True
        ):
            if (
                binding.binding_ref not in original
                or original[binding.binding_ref][0] is not binding
                or candidate
                != replace(original[binding.binding_ref][1], challenge=parent_challenge)
            ):
                raise ValueError("branch recovery invented a binding or semantic candidate")
        mapped = {
            b.binding_ref: s
            for b, s in zip(self.child.options.bindings, self.child.scores, strict=True)
        }
        if choice.scores != tuple(
            mapped.get(b.binding_ref) for b in choice.options.bindings
        ) or choice.probabilities != tuple(
            float(b is self.child.selected_binding) for b in choice.options.bindings
        ):
            raise ValueError("branch recovery scores or action distribution differ")

    def document(self):
        return dict(
            branch=self.parent.public_dict(),
            **({"parent_menu": self.parent.options.public_dict()} if self.defer_unbound_preparation else {}),
            recovery=None if self.child is None else self.child.public_dict(),
            recovery_menu=None if self.child is None else self.child.options.public_dict(),
            head_sha256=self.head_sha256,
            score_blending=False,
            provisional=True,
            model_queries=int(self.parent.mode in {
                RedLiveOptionSelectionMode.MODEL_EXPLORATION,
                RedLiveOptionSelectionMode.MODEL_GREEDY,
            })
            + int(self.child is not None),
            **({"declared_branch_count": len(self.objective_ref)}
               if type(self.objective_ref) is tuple else {}),
            **({"parent_selection_rule": (
                    "forced_singleton_support"
                    if self.parent.mode is RedLiveOptionSelectionMode.FORCED_SINGLETON_SUPPORT
                    else "maximum_score_with_seeded_ties")}
               if self.greedy_selection else {}),
            **({"parent_authority": (
                    "forced_singleton_support"
                    if self.parent.mode is RedLiveOptionSelectionMode.FORCED_SINGLETON_SUPPORT
                    else self.parent.mode.value),
                "parent_model_queries": int(self.parent.mode in {
                    RedLiveOptionSelectionMode.MODEL_EXPLORATION,
                    RedLiveOptionSelectionMode.MODEL_GREEDY}),
                "child_model_queries": int(self.child is not None),
                "allow_singleton_parent_support": True}
               if self.allow_singleton_parent_support else {}),
            **({"refine_preparation": True} if self.refine_preparation else {}),
            **({"defer_unbound_preparation": True} if self.defer_unbound_preparation else {}),
        )


def _branch_scope_available(options, scope):
    """Apply branch-specific preparation rules only where that branch is offered.

    A present but malformed in-scope challenge remains subject to the existing
    strict checks. Absence/completion of the declared branch is not such an error.
    """
    return any(options.binding(i).kind is GoalKind.ADVANCE_STORY
               and options.binding(i).story_objective_ref in scope
               for i in options.menu.available_indices)


def select_branch_recovery_live_option(
    model, options, head, *, objective_ref, seed, greedy_selection=False,
    refine_preparation=False, defer_unbound_preparation=False, allow_singleton_parent_support=False,
):
    """Let the parent choose first; refine its selected declared combat branch.

    Healing/development previews in the child refer to the selected future
    challenge. They are not substituted for the parent's immediate-action inputs.
    Other story branches never enter the homogeneous recovery comparison, even
    when the explicit authority scope includes more than one combat branch.
    """
    if (type(head) is not ChallengeConsequenceHead or head.feedback_version != 2
            or not isinstance(model, LivingDexOptionValueModel)
            or model.feature_version not in (7, 9, 10, 11, 15)
            or head.feature_version != model.feature_version):
        raise ValueError("branch recovery requires the prospective V2head")
    identity = branch_recovery_identity(model.model_sha256, head.model_sha256, objective_ref,
                                        greedy_selection=greedy_selection,
                                        refine_preparation=refine_preparation,
                             defer_unbound_preparation=defer_unbound_preparation,
            allow_singleton_parent_support=allow_singleton_parent_support)
    scope = branch_recovery_objectives(objective_ref)
    scope_available = _branch_scope_available(options, scope)
    defer_for_scope = defer_unbound_preparation and scope_available
    parent = _select_preparation_parent(model, options, seed=seed,
        greedy_selection=greedy_selection, defer_unbound_preparation=defer_for_scope,
        allow_singleton_parent_support=allow_singleton_parent_support and scope_available,
        scope=scope)
    selected = parent.selected_binding
    challenge = parent.options.menu.candidates[parent.selected_candidate_index].challenge
    branch = _refinement_branch(parent, scope, refine_preparation=refine_preparation,
                             defer_unbound_preparation=defer_unbound_preparation,
            allow_singleton_parent_support=allow_singleton_parent_support)
    child = None
    if (
        parent.mode in {
            RedLiveOptionSelectionMode.MODEL_EXPLORATION,
            RedLiveOptionSelectionMode.MODEL_GREEDY,
            RedLiveOptionSelectionMode.FORCED_SINGLETON_SUPPORT,
        }
        and branch is not None
        and challenge is not None
        and challenge.combat_required
        and challenge.opposition_known
    ):
        indices = tuple(
            i
            for i in options.menu.available_indices
            if options.binding(i) is branch
            or options.binding(i).kind is GoalKind.RESTORE_TEAM
            or (
                options.binding(i).kind is GoalKind.DEVELOP_TEAM
                and supports_consequence_preparation(options.menu.candidates[i], head.feature_version)
            )
            or (
                head.include_recovery_purchases
                and options.binding(i).kind is GoalKind.RESUPPLY
                and recovery_purchase_quote(options.binding(i).resource_quote)
            )
        )
        # V10 represents owned move lessons directly. Older heads retain their
        # level-dose scope; never supply a fictitious preparation descriptor.
        # With no preparation/restoration alternative,the parent already owns
        # the genuine branch choice. Do not invent an option or demand a second
        # query to repeat that choice. The single-head comparison stays strict.
        if len(indices) > 1:
            candidates = tuple(
                condition_consequence_candidate(options.menu.candidates[i],
                    next(options.menu.candidates[j] for j, b in enumerate(options.bindings)
                         if b is branch)) for i in indices
            )
            bindings = tuple(options.binding(i) for i in indices)
            submenu = replace(
                options,
                menu=replace(options.menu, candidates=candidates),
                bindings=bindings,
                ordinary_binding_refs=options.ordinary_binding_refs
                & {b.binding_ref for b in bindings},
            )
            child = select_consequence_live_option(
                submenu, head, challenge_ref=branch.story_objective_ref, seed=seed
            )
    receipt = BranchRecoveryDecision(parent, child, head.model_sha256, objective_ref,
                                     greedy_selection=greedy_selection,
                                     refine_preparation=refine_preparation,
                             defer_unbound_preparation=defer_unbound_preparation,
            allow_singleton_parent_support=allow_singleton_parent_support)
    if child is None:
        return replace(parent, options=options,
            mode=(RedLiveOptionSelectionMode.MODEL_EXPLORATION
                  if defer_for_scope and parent.mode is RedLiveOptionSelectionMode.MODEL_GREEDY
                  else parent.mode),
            model_sha256=identity, branch_recovery=receipt)
    child_by_ref = {b.binding_ref: i for i, b in enumerate(child.options.bindings)}
    at = next(i for i, b in enumerate(options.bindings) if b is child.selected_binding)
    return RedLiveOptionChoice(
        options,
        at,
        RedLiveOptionSelectionMode.MODEL_EXPLORATION,
        tuple(
            child.scores[child_by_ref[b.binding_ref]] if b.binding_ref in child_by_ref else None
            for b in options.bindings
        ),
        tuple(float(i == at) for i in range(len(options.bindings))),
        seed,
        identity,
        branch_recovery=receipt,
    )


def consequence_cash_exposures(options, *, challenge_refs):
    """Compose only explicit state-bound single-battle/preserving certificates.

    The direct executable anchors the future challenge. A machine's zero debit
    applies only to teaching; its preserving certificate can inherit that exact
    future exposure. Other preparation and unknown approaches stay unbounded.
    Private identities authenticate this composition and never enter features.
    """
    if len(challenge_refs) != len(options.bindings):
        raise ValueError("cash composition requires aligned challenge references")
    available = options.menu.available_indices
    direct = [i for i in available if options.binding(i).kind is GoalKind.ADVANCE_STORY]
    values = [None] * len(options.bindings)
    if len(direct) != 1:
        return tuple(values)
    index = direct[0]
    binding = options.binding(index)
    proof = binding.cash_outcome
    if (type(proof) is not GoalCashOutcome or proof.kind != "single_trainer"
            or binding.story_approach_only
            or binding.story_objective_ref != challenge_refs[index]):
        return tuple(values)
    values[index] = proof.loss_debit
    challenge = options.menu.candidates[index].challenge
    for i in available:
        other = options.binding(i)
        candidate = options.menu.candidates[i]
        keep = other.cash_outcome
        if (other.kind is GoalKind.DEVELOP_TEAM
                and candidate.move_change is not None
                and candidate.preparation is None and candidate.level_workload is None
                and type(keep) is GoalCashOutcome
                and keep.kind == "preserves_cash_approach"
                and keep.source_sha256 == proof.source_sha256
                and challenge_refs[i] == challenge_refs[index]
                and candidate.challenge == challenge):
            values[i] = proof.loss_debit
    return tuple(values)


def validate_consequence_cash_receipt(choice):
    """Keep exact source certificates private and bind them to the selected menu."""
    value = choice.consequence_receipt_json
    if type(value) is not str:
        raise ValueError("consequence cash receipt must be immutable JSON")
    receipt = json.loads(value)
    if type(receipt) is not dict or type(receipt.get("challenge_refs")) is not list:
        raise ValueError("consequence cash receipt document differs")
    body = {k: v for k, v in receipt.items() if k != "choice_sha256"}
    if (receipt.get("choice_sha256") != canonical_sha256(body)
            or receipt.get("model_sha256") != choice.consequence_head_sha256
            or receipt.get("menu_sha256") != choice.options.menu.policy_sha256
            or receipt.get("menu") != choice.options.menu.policy_dict()
            or receipt.get("binding_ref") != choice.selected_binding.binding_ref
            or receipt.get("kind") != choice.selected_binding.kind.value
            or receipt.get("executed") is not False or receipt.get("teacher_selected") is not False
            or receipt.get("selection_rule") != "maximum_score_then_lowest_menu_index"
            or receipt.get("selected_index") != choice.selected_candidate_index
            or receipt.get("scores") != list(choice.scores)
            or receipt.get("binding_refs") != [b.binding_ref for b in choice.options.bindings]):
        raise ValueError("consequence cash receipt differs from exact live choice")
    from .player_preparation_party_context import PARTY_PROJECTION, PreparationPartyWitness
    if (choice.consequence_context_projection==PARTY_PROJECTION
            and receipt.get("cash_prediction")!=choice.consequence_cash_prediction):
        raise ValueError("party receipt cash mode differs from the selected frozen head")
    if receipt.get("cash_prediction")=="certified_single_trainer_v1":
        expected=consequence_cash_exposures(choice.options,challenge_refs=receipt["challenge_refs"])
        certificates=[None if b.cash_outcome is None else dict(source_sha256=b.cash_outcome.source_sha256,
            kind=b.cash_outcome.kind,loss_debit=b.cash_outcome.loss_debit) for b in choice.options.bindings]
        if receipt.get("single_battle_loss_debits")!=list(expected) or receipt.get("cash_certificates")!=certificates:
            raise ValueError("consequence cash certificates differ from exact live choice")
    elif (receipt.get("cash_prediction")!="independent"
            or choice.consequence_context_projection!=PARTY_PROJECTION
            or "single_battle_loss_debits" in receipt or "cash_certificates" in receipt):
        raise ValueError("consequence receipt cash mode differs")
    if choice.consequence_context_projection==PARTY_PROJECTION:
        witness=choice.options.preparation_party_witness
        if (type(witness) is not PreparationPartyWitness
                or receipt.get("schema")!="pokemon.red.consequence-choice.v2"
                or receipt.get("context_projection")!=PARTY_PROJECTION
                or receipt.get("preparation_party_witness")!=witness.document()):
            raise ValueError("consequence party context differs from mandatory exact live witness")
    elif ("preparation_party_witness" in receipt or "context_projection" in receipt
            or receipt.get("schema")!="pokemon.red.consequence-choice.v1"):
        raise ValueError("party projection receipt lacks its declared head context")
    return receipt


def choose_consequence_binding(options, head, *, challenge_refs):
    """Return the exact executable and private receipt, without inputs or fitting.

    Highest score wins; exact ties use the existing menu's lowest available index.
    The caller must durably retain the receipt before invoking the returned native
    binding. This is explicit single-challenge authority, not global adoption.
    The ordinary player can opt in through select_consequence_live_option.
    """
    if type(options) is not RedLiveOptionSet or type(head) is not ChallengeConsequenceHead:
        raise TypeError("consequence choice requires a typed live menu and frozen head")
    menu = options.menu
    available = menu.available_indices
    if len(available) < 2:
        raise ValueError("consequence model choice requires real alternatives")
    for index in available:
        binding = options.binding(index)
        if menu.candidates[index].features.kind is not living_dex_option_kind_for_goal(
            binding.kind, feature_version=head.feature_version
        ):
            raise ValueError("consequence candidate and executable kind differ")
        if binding.kind is GoalKind.RESUPPLY and (
            not head.include_recovery_purchases
            or not recovery_purchase_quote(binding.resource_quote)
        ):
            raise ValueError("consequence purchase requires an actual recovery quote")
    exposures = (consequence_cash_exposures(options, challenge_refs=challenge_refs)
                 if head.cash_prediction == "certified_single_trainer_v1" else None)
    from .player_preparation_party_context import PARTY_PROJECTION, PreparationPartyWitness
    party_kwargs={}
    if head.context_projection==PARTY_PROJECTION:
        witness=options.preparation_party_witness
        if type(witness) is not PreparationPartyWitness:
            raise ValueError("party-context head requires an authenticated current runtime witness")
        # Cash-preserving preparation and current single-trainer quotes carry
        # exact boundary identities; fail closed if one has become stale.
        if any(b.cash_outcome is not None and b.cash_outcome.source_sha256!=witness.source_state_sha256
               for b in options.bindings):
            raise ValueError("party witness and current native execution source differ")
        party_kwargs["party_context"]=witness.counts
    scores = head.scores(menu, challenge_refs=challenge_refs,
                         single_battle_loss_debits=exposures,**party_kwargs)
    if any(scores[i] is None or not isfinite(scores[i]) for i in available):
        raise ValueError("consequence choice requires finite available scores")
    selected = max(available, key=lambda i: (scores[i], -i))
    binding = options.binding(selected)
    receipt = dict(
        schema="pokemon.red.consequence-choice.v1",
        model_sha256=head.model_sha256,
        menu=menu.policy_dict(),
        menu_sha256=menu.policy_sha256,
        challenge_refs=list(challenge_refs),
        binding_refs=[b.binding_ref for b in options.bindings],
        selected_index=selected,
        binding_ref=binding.binding_ref,
        kind=binding.kind.value,
        scores=list(scores),
        selection_rule="maximum_score_then_lowest_menu_index",
        executed=False,
        teacher_selected=False,
        **({"cash_prediction": head.cash_prediction,
            "single_battle_loss_debits": list(exposures),
            "cash_certificates": [None if b.cash_outcome is None else dict(
                source_sha256=b.cash_outcome.source_sha256, kind=b.cash_outcome.kind,
                loss_debit=b.cash_outcome.loss_debit) for b in options.bindings]}
           if exposures is not None else {}),
    )
    if party_kwargs:
        receipt["schema"]="pokemon.red.consequence-choice.v2"
        receipt["cash_prediction"]=head.cash_prediction
        receipt["preparation_party_witness"]=witness.document()
        receipt["context_projection"]=PARTY_PROJECTION
    receipt["choice_sha256"] = canonical_sha256(receipt)
    return binding, receipt


def select_consequence_live_option(options, head, *, challenge_ref, seed):
    """Scoped provisional ranking on the ordinary runner's exact choice port.

    No substitution, fitting or global adoption. Unexpressible alternatives and
    nonmatching challenge menus refuse before input rather than use a fallback.
    Existing compulsory support remains owned by the outer safety adapter.
    """
    if type(challenge_ref) is not str or not challenge_ref.strip():
        raise ValueError("consequence selection requires an explicit private challenge")
    if type(head) is not ChallengeConsequenceHead:
        raise TypeError("consequence selection requires a typed frozen head")
    if (
        len(
            {
                options.menu.candidate_vector(i, feature_version=head.feature_version)
                for i in options.menu.available_indices
            }
        )
        < 2
    ):
        raise ValueError("consequence alternatives lack distinct semantic inputs")
    _, receipt = choose_consequence_binding(
        options, head, challenge_refs=(challenge_ref,) * len(options.bindings)
    )
    selected = receipt["selected_index"]
    return RedLiveOptionChoice(
        options,
        selected,
        RedLiveOptionSelectionMode.MODEL_EXPLORATION,
        tuple(receipt["scores"]),
        tuple(float(i == selected) for i in range(len(options.bindings))),
        seed,
        head.model_sha256,
        consequence_head_sha256=head.model_sha256,
        consequence_context_projection=(head.context_projection if head.context_projection=="prospective_preparation_party_context_v1" else None),
        consequence_cash_prediction=(head.cash_prediction if head.context_projection=="prospective_preparation_party_context_v1" else None),
        consequence_receipt_json=(json.dumps(receipt, sort_keys=True, separators=(",", ":"))
                                  if head.cash_prediction != "independent" or head.context_projection=="prospective_preparation_party_context_v1" else None),
    )


def selected_preparation_parent(choice):
    """Return the exact combat binding and retain its separate parent authority.

    Private execution witness only. Missing parent intent never becomes an
    association by challenge similarity or menu order. Explicit singleton support
    is identified separately in the branch receipt and consumes no parent query.
    """
    if type(choice) is not RedLiveOptionChoice or choice.branch_recovery is None:
        return None
    receipt = choice.branch_recovery
    receipt.validate(choice)
    if (receipt.child is None or choice.selected_binding.kind is not GoalKind.DEVELOP_TEAM
            or receipt.parent.selected_binding.kind is not GoalKind.ADVANCE_STORY):
        return None
    parent = receipt.parent.selected_binding
    branch = _refinement_branch(receipt.parent, branch_recovery_objectives(receipt.objective_ref),
                                refine_preparation=receipt.refine_preparation)
    if branch is not parent:
        raise ValueError("preparation lacks its exact selected combat parent")
    return parent



def _preparation_parent_options(options):
    """A recorded temporary mask, not an inferred challenge association."""
    deferred = tuple(i for i, (b, c) in enumerate(zip(options.bindings, options.menu.candidates, strict=True))
        if b.kind is GoalKind.DEVELOP_TEAM and c.preparation is not None
        and c.move_change is None and c.challenge is None
        and i in options.menu.available_indices)
    if len(set(options.menu.available_indices) - set(deferred)) < 2:
        raise ValueError("parent-bound preparation requires two actual parent alternatives")
    candidates = tuple(replace(c, availability=LivingDexOptionAvailability.UNAVAILABLE,
            unavailable_reason=LivingDexOptionUnavailableReason.TEMPORARILY_BLOCKED)
        if i in deferred else c for i, c in enumerate(options.menu.candidates))
    return replace(options, menu=replace(options.menu, candidates=candidates))


def _sole_observed_combat_parent(options, scope):
    """Support only a sole actual observed branch, never a guessed dose target."""
    remaining = tuple(i for i in options.menu.available_indices
        if not _unbound_level_dose(options, i))
    if len(remaining) != 1:
        raise ValueError("singleton parent support requires exactly one actual parent")
    index = remaining[0]
    binding, candidate = options.binding(index), options.menu.candidates[index]
    if (binding.kind is not GoalKind.ADVANCE_STORY
        or binding.story_objective_ref not in scope
        or candidate.challenge is None
        or not candidate.challenge.combat_required
        or not candidate.challenge.opposition_known
        or not any(_unbound_level_dose(options, i) for i in options.menu.available_indices)):
        raise ValueError("singleton parent support requires exact observed combat and bounded doses")
    return index


def _unbound_level_dose(options, index):
    binding, candidate = options.bindings[index], options.menu.candidates[index]
    return (binding.kind is GoalKind.DEVELOP_TEAM and candidate.preparation is not None
            and candidate.move_change is None and candidate.challenge is None)


def _select_preparation_parent(model, options, *, seed, greedy_selection,
                               defer_unbound_preparation, allow_singleton_parent_support,
                               scope):
    """Explicit model parent or disclosed zero-query singleton support."""
    if not defer_unbound_preparation:
        return select_red_live_option(model, options, seed=seed, allow_earning_exploration=True,
            greedy_selection=greedy_selection, kind_balanced_exploration=False)
    safety = select_red_live_safety_option(model, options, seed=seed, allow_earning_exploration=True)
    if safety is not None:
        return safety
    remaining = tuple(i for i in options.menu.available_indices
                      if not _unbound_level_dose(options, i))
    if len(remaining) < 2 and allow_singleton_parent_support:
        index = _sole_observed_combat_parent(options, scope)
        return RedLiveOptionChoice(options, index,
            RedLiveOptionSelectionMode.FORCED_SINGLETON_SUPPORT,
            (None,) * len(options.bindings),
            tuple(float(i == index) for i in range(len(options.bindings))),
            seed, model.model_sha256)
    parent_options = _preparation_parent_options(options)
    parent = select_red_live_option(model, parent_options, seed=seed, allow_earning_exploration=True,
        greedy_selection=greedy_selection, kind_balanced_exploration=False)
    if parent.mode is RedLiveOptionSelectionMode.EQUIVALENT_EXPLORATION:
        raise ValueError("parent-bound preparation requires distinct model inputs")
    return parent
