"""Private pre-input selector inputs; no controller or executable callback codec.

Replay authenticates recorded safety selection and binding identity. It does not
prove native observation truth or that an arbitrary Python executor was honest.
"""

from dataclasses import asdict, replace

from .goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from .goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet
from .goal_resource_quote import GoalResourceQuote
from .goal_search_memory import GoalSearchHistory
from .living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY, living_dex_option_kind_for_goal
from .living_dex_policy_codec import restore_living_dex_policy_menu
from .player_readiness import PlayerReadiness
from .player_sequence_policy import SequenceChoiceContext, SequencePolicy
from .provenance import canonical_sha256
from .red_live_option_menu import RedLiveOptionChoice, RedLiveOptionSet, select_red_live_option
from .red_player_support import RedPlayerSupport, RedPlayerSupportChoice


def _opportunity_document(opportunity):
    return dict(binding_ref=opportunity.binding_ref, policy=opportunity.policy_dict())


def record_selection_authority(options, *, allow_earning_exploration: bool,
                               greedy_selection: bool = False):
    if type(greedy_selection) is not bool:
        raise TypeError("highest-score authority opt-in must be boolean")
    support = isinstance(options, RedPlayerSupport)
    original = options.bindings if support else options.original_bindings
    bindings = original.bindings if support else options.bindings
    return dict(
        schema="pokemon.red.recorded-selection-authority.v1",
        allow_earning_exploration=allow_earning_exploration,
        **({"greedy_selection": True} if greedy_selection else {}),
        situation=None if support else asdict(options.situation),
        opportunities=[_opportunity_document(o) for o in original.opportunities],
        original_binding_refs=[b.binding_ref for b in original.bindings],
        allow_resource_variants=original.allow_resource_variants,
        live_bindings=[_opportunity_document(b.opportunity) for b in bindings],
        ordinary_binding_refs=[] if support else sorted(options.ordinary_binding_refs),
        ordering_seed_sha256=None if support else options.ordering_seed_sha256,
    )


def _restore_opportunity(document):
    p = document["policy"]
    o = GoalOpportunity(
        binding_ref=document["binding_ref"], kind=GoalKind(p["kind"]),
        availability=GoalAvailability(p["availability"]),
        estimated_effort=p["estimated_effort"], estimated_risk=p["estimated_risk"],
        unavailable_reason=None if p["unavailable_reason"] is None
        else GoalUnavailableReason(p["unavailable_reason"]),
        resource_quote=None if "resource_quote" not in p
        else GoalResourceQuote.from_public_dict(p["resource_quote"]),
        search_history=None if "search_history" not in p
        else GoalSearchHistory.from_public_dict(p["search_history"]),
    )
    if canonical_sha256(_opportunity_document(o)) != canonical_sha256(document):
        raise ValueError("recorded opportunity differs")
    return o


def _inert(*args, **kwargs):
    raise RuntimeError("recorded selector replay cannot execute or verify a goal")


def _binding(o):
    return ExecutableGoalBinding(
        o.binding_ref, o.kind, o.estimated_effort, o.estimated_risk,
        _inert, _inert, resource_quote=o.resource_quote, search_history=o.search_history,
    )


def _restore_recorded_options(intent):
    """Reconstruct an inert menu;never reconstruct a controller or verifier."""
    document = intent["private_selection_authority"]
    opportunities = tuple(_restore_opportunity(o) for o in document["opportunities"])
    refs = document["original_binding_refs"]
    by_ref = {o.binding_ref: o for o in opportunities}
    original = GoalBindingSet(
        opportunities, tuple(_binding(by_ref[r]) for r in refs),
        document["allow_resource_variants"],
    )
    bindings = tuple(_binding(_restore_opportunity(o)) for o in document["live_bindings"])
    menu = intent["menu"]
    options: RedPlayerSupport | RedLiveOptionSet
    if menu["schema"] == "pokemon.red.player-support.v1":
        if intent.get("sequence_context") is not None:
            raise ValueError("forced support cannot have a sequence query context")
        options = RedPlayerSupport(original, PlayerReadiness.from_public(menu["readiness"]))
    else:
        restored = restore_living_dex_policy_menu(
            menu["menu"], binding_refs=tuple(b.binding_ref for b in bindings),
        )
        if any(living_dex_option_kind_for_goal(b.kind, feature_version=restored.feature_version)
               is not c.features.kind for b, c in zip(bindings, restored.candidates, strict=True)):
            raise ValueError("recorded executor kind differs from selected menu")
        options = RedLiveOptionSet(
            GoalSituation(**document["situation"]), original, restored, bindings,
            frozenset(document["ordinary_binding_refs"]), document["ordering_seed_sha256"],
            force_resource_safety=menu.get("resource_authority") != "model",
        )
    return options


def replay_selection_authority(model, intent, decision, *, allow_earning_exploration: bool,
                               sequence_policy: SequencePolicy | None = None,
                               train_form_balanced_exploration: bool = False,
                               exploration_mix: float = .25):
    """Return the exact selected private ref, without reconstructing callbacks.

    Defaults replay the historical sampler. A TRAIN-only form-balanced run must
    pass its declared plan values; they are re-derived, never trusted from
    the decision, so a mismatched sampler fails the byte-identical replay.
    """
    if type(train_form_balanced_exploration) is not bool or (
        (train_form_balanced_exploration or exploration_mix != .25) and sequence_policy is not None
    ):
        raise ValueError("recorded form-balanced sampler scope differs")
    document = intent["private_selection_authority"]
    greedy_selection = document.get("greedy_selection", False)
    if type(greedy_selection) is not bool or (greedy_selection and sequence_policy is not None):
        raise ValueError("recorded highest-score authority differs")
    context_document = intent.get("sequence_context")
    if (sequence_policy is None) != (context_document is None):
        raise ValueError("recorded sequence selection requires its frozen policy and context")
    context = None
    if sequence_policy is not None:
        if intent.get("model_sha256") != sequence_policy.model_sha256:
            raise ValueError("recorded sequence policy identity differs")
        context = SequenceChoiceContext.from_document(context_document)
    if (type(allow_earning_exploration) is not bool
        or document.get("allow_earning_exploration") is not allow_earning_exploration):
        raise ValueError("recorded earning authority differs")
    options = _restore_recorded_options(intent)
    menu = intent["menu"]
    if isinstance(options, RedPlayerSupport):
        choice = RedPlayerSupportChoice(options)
    else:
        choice = select_red_live_option(
            model, options, seed=intent["selection_seed"],
            allow_earning_exploration=allow_earning_exploration,
            greedy_selection=greedy_selection,
            sequence_policy=sequence_policy, sequence_context=context,
            utility=(DEFAULT_LIVING_DEX_GOAL_UTILITY if sequence_policy is None
                     else sequence_policy.immediate_utility),
            exploration_mix=(float(exploration_mix) if sequence_policy is None
                             else sequence_policy.exploration_mix),
            **({"form_balanced_exploration": True} if train_form_balanced_exploration else {}),
        )
    if (canonical_sha256(record_selection_authority(
            options, allow_earning_exploration=allow_earning_exploration,
            greedy_selection=greedy_selection))
        != canonical_sha256(document)
        or canonical_sha256(options.public_dict()) != canonical_sha256(menu)
        or canonical_sha256(choice.public_dict()) != canonical_sha256(decision)):
        raise ValueError("recorded safety/selection authority does not replay")
    return choice.selected_binding.binding_ref


def replay_unmodified_branch_recovery(model, head, intent, decision, *, objective_ref, flags):
    """Audit the existing parent when no declared combat scope is available.

    This grants neither source/native truth nor training admission. A refined
    child needs its own typed association proof and is deliberately rejected.
    """
    from .red_consequence_choice import (
        branch_recovery_identity, branch_recovery_objectives,
        select_branch_recovery_live_option,
    )
    identity = branch_recovery_identity(model.model_sha256, head.model_sha256,
                                        objective_ref, **flags)
    if intent.get("model_sha256") != identity or decision.get("model_sha256") != identity:
        raise ValueError("recorded branch selector identity differs")
    options = _restore_recorded_options(intent)
    if type(options) is not RedLiveOptionSet:
        raise ValueError("recorded branch parent needs a mixed model menu")
    contexts = intent["private_story_contexts"]
    if (type(contexts) is not list or len(contexts) != len(options.bindings)
            or any(set(row) != {"binding_ref", "objective_ref"}
                   or row["binding_ref"] != binding.binding_ref
                   or (row["objective_ref"] is not None and type(row["objective_ref"]) is not str)
                   for row, binding in zip(contexts, options.bindings, strict=True))):
        raise ValueError("recorded private story contexts differ")
    bindings = tuple(replace(binding, story_objective_ref=row["objective_ref"],
                             story_unit=candidate.story_unit,
                             story_approach_only=(candidate.story_unit is not None
                                 and candidate.story_unit.requires_further_selected_unit))
                     for binding, row, candidate in zip(
                         options.bindings, contexts, options.menu.candidates, strict=True))
    options = replace(options, bindings=bindings)
    scope = branch_recovery_objectives(objective_ref)
    if any(options.binding(i).kind is GoalKind.ADVANCE_STORY
           and options.binding(i).story_objective_ref in scope for i in options.menu.available_indices):
        raise ValueError("in-scope combat refinement needs its separate association audit")
    document = intent["private_selection_authority"]
    if (document.get("greedy_selection") is not flags["greedy_selection"]
            or canonical_sha256(record_selection_authority(
                options, allow_earning_exploration=True,
                greedy_selection=flags["greedy_selection"])) != canonical_sha256(document)
            or canonical_sha256(options.public_dict()) != canonical_sha256(intent["menu"])):
        raise ValueError("recorded branch menu authority differs")
    expected_recurrence = dict(declared_greedy_selection=flags["greedy_selection"],
                               explore_on_movement_recurrence=flags["explore_on_movement_recurrence"],
                               trigger_rule="greedy-selected-observed-unchanged-endpoint-v1")
    if intent.get("private_recurrence_sampling_policy") != expected_recurrence:
        raise ValueError("recorded recurrence recipe differs")
    choice = select_branch_recovery_live_option(
        model, options, head, objective_ref=objective_ref, seed=intent["selection_seed"],
        source_state_sha256=intent["state_sha256"], **flags)
    if canonical_sha256(choice.public_dict()) != canonical_sha256(decision):
        raise ValueError("recorded branch choice does not replay")
    return choice.selected_binding.binding_ref
