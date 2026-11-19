"""Opt-in kind-level story commitment (session 32): keep advancing a story objective that is under way.

Milestone commitment only ranks story executors against each other; the goal model still picks the goal
kind. Fresh runs therefore abandoned an unfinished story stretch (a multi-floor dungeon such as Pokemon
Tower) for a catch/heal/evolve detour that left the area, then repeated the whole stretch, many times.

With this commitment, once a story step for objective X has succeeded without completing X, a later model
choice of another goal kind is replaced by X's story executor while the party is fit (enough HP, nobody
fainted, PP not exhausted), until X completes, a verified native story battle is lost, or X's other story steps fail twice in a row. Unfit parties keep the
model's choice (heal, train). Deterministic, recorded per step, no fitting; the goal model is unchanged.

The commitment never forces travel in a circle: a story leg whose endpoint was already reached with nothing
changed since is not forced over the model's choice, and the commitment is released when such a leg is the
only one on offer or when an executed leg is recorded as an unchanged return.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .goal_manager import GoalKind
from .provenance import canonical_sha256

STORY_KIND_COMMITMENT_SCHEMA = "pokemon.red.story-kind-commitment.v1"
MAXIMUM_CONSECUTIVE_FAILURES = 2
MINIMUM_HP_FRACTION = 0.5
MINIMUM_PP_FRACTION = 0.25


@dataclass(frozen=True)
class StoryKindCommitment:
    objective_ref: str
    consecutive_failures: int = 0
    overrides: int = 0

    def __post_init__(self):
        if (
            type(self.objective_ref) is not str
            or not self.objective_ref
            or type(self.consecutive_failures) is not int
            or not 0 <= self.consecutive_failures < MAXIMUM_CONSECUTIVE_FAILURES
            or type(self.overrides) is not int
            or self.overrides < 0
        ):
            raise ValueError("story kind commitment differs")

    def document(self):
        return dict(
            schema=STORY_KIND_COMMITMENT_SCHEMA,
            objective_ref=self.objective_ref,
            consecutive_failures=self.consecutive_failures,
            overrides=self.overrides,
        )


    @classmethod
    def from_document(cls, document):
        if (
            type(document) is not dict
            or set(document) != {"schema", "objective_ref", "consecutive_failures", "overrides"}
            or document["schema"] != STORY_KIND_COMMITMENT_SCHEMA
        ):
            raise ValueError("story kind commitment document differs")
        return cls(document["objective_ref"], document["consecutive_failures"], document["overrides"])


class StoryKindCommitmentCarrier:
    """Carries the commitment across native chunks of one run (each chunk is a separate goal loop)."""

    __slots__ = ("current",)

    def __init__(self):
        self.current = None

    def document(self):
        return None if self.current is None else self.current.document()

    @classmethod
    def from_document(cls, document, *, completed_objectives=()):
        carrier = cls()
        if document is not None:
            current = StoryKindCommitment.from_document(document)
            if current.objective_ref not in completed_objectives:
                carrier.current = current
        return carrier



def party_fit(readiness) -> bool:
    """True only for a typed readiness showing enough HP, no fainted member and PP not exhausted."""
    from .player_readiness import READINESS_NAMES, PlayerReadiness

    if type(readiness) is not PlayerReadiness:
        return False
    values = dict(zip(READINESS_NAMES[1:], readiness.values, strict=True))
    if values["current.hp_fraction"] < MINIMUM_HP_FRACTION or values["current.fainted_fraction"] > 0.0:
        return False
    if values["current.pp_known"] > 0.0 and values["current.pp_fraction"] < MINIMUM_PP_FRACTION:
        return False
    return True


def _committed_indices(options, objective_ref):
    return tuple(
        i
        for i in options.menu.available_indices
        if options.binding(i).kind is GoalKind.ADVANCE_STORY
        and options.binding(i).story_objective_ref == objective_ref
    )


def commit_story_kind(choice, commitment, *, respect_combat_preparation_choice=False):
    """Return ``(choice, receipt)``.

    ``receipt`` is None when the commitment does not apply. When it applies but the party is unfit, the
    model's choice is kept and the receipt says so. Otherwise the returned choice selects the committed
    objective's story executor (lowest such index) with all probability on it.
    """
    from .red_live_option_menu import RedLiveOptionChoice, RedLiveOptionSelectionMode

    if type(respect_combat_preparation_choice) is not bool:
        raise TypeError("combat preparation choice declaration must be boolean")
    if commitment is None or not isinstance(choice, RedLiveOptionChoice):
        return choice, None
    if type(commitment) is not StoryKindCommitment:
        raise TypeError("typed story kind commitment required")
    if (
        choice.mode not in {RedLiveOptionSelectionMode.MODEL_GREEDY, RedLiveOptionSelectionMode.MODEL_EXPLORATION}
        or choice.consequence_receipt_json is not None
        or choice.sequence_policy is not None
        or (
            choice.branch_recovery is not None
            and (choice.branch_recovery.child is not None or choice.branch_recovery.unique_combat_witness is not None)
        )
        or choice.selected_binding.kind is GoalKind.ADVANCE_STORY
    ):
        return choice, None
    options = choice.options
    indices = _committed_indices(options, commitment.objective_ref)
    if not indices:
        return choice, None
    # A story leg whose endpoint was already reached with nothing changed since
    # is travel in a circle. Never force that leg over the model's own choice.
    fresh = tuple(i for i in indices if options.menu.candidates[i].movement_revisit is not True)
    revisit_only = not fresh
    index = min(indices) if revisit_only else min(fresh)
    fit = party_fit(options.menu.candidates[index].readiness)
    challenge = options.menu.candidates[index].challenge
    preserve_preparation = (
        respect_combat_preparation_choice
        and choice.selected_binding.kind is GoalKind.DEVELOP_TEAM
        and challenge is not None and challenge.combat_required
    )
    overridden = fit and not revisit_only and not preserve_preparation
    receipt = dict(
        schema=STORY_KIND_COMMITMENT_SCHEMA,
        commitment=commitment.document(),
        parent_selected_candidate_index=choice.selected_candidate_index,
        parent_selected_kind=choice.selected_binding.kind.value,
        parent_mode=choice.mode.value,
        parent_model_sha256=choice.model_sha256,
        committed_candidate_index=index,
        party_fit=fit,
        committed_movement_revisit=revisit_only,
        overridden=overridden,
        selected_candidate_index=index if overridden else choice.selected_candidate_index,
        automatic_fit=False,
        goal_model_unchanged=True,
        **({"respect_combat_preparation_choice": True,
            "combat_preparation_choice_preserved": preserve_preparation}
           if respect_combat_preparation_choice else {}),
    )
    if not overridden:
        return choice, receipt
    count = len(options.menu.candidates)
    overridden = RedLiveOptionChoice(
        options,
        index,
        RedLiveOptionSelectionMode.MODEL_EXPLORATION,
        tuple(None for _ in range(count)),
        tuple(float(i == index) for i in range(count)),
        choice.seed,
        canonical_sha256(receipt),
    )
    return overridden, receipt


def commitment_after_choice(commitment, receipt):
    """Count an applied override; release a commitment whose only leg is a revisit."""
    if commitment is None or receipt is None:
        return commitment
    if receipt.get("committed_movement_revisit"):
        return None
    if not receipt.get("overridden"):
        return commitment
    return replace(commitment, overrides=commitment.overrides + 1)


def commitment_after_movement_return(commitment, recurrence):
    """Release the commitment once an executed leg returned to an unchanged, already-seen endpoint."""
    if commitment is not None and type(commitment) is not StoryKindCommitment:
        raise TypeError("typed story kind commitment required")
    return commitment if recurrence is None else None


def commitment_after_outcome(commitment, selected_binding, outcome):
    """Start, keep, reset or release the commitment from one recorded outcome."""
    if commitment is not None and type(commitment) is not StoryKindCommitment:
        raise TypeError("typed story kind commitment required")
    after = set(((outcome.get("after") or {}).get("completed_objectives")) or ())
    if commitment is not None and commitment.objective_ref in after:
        commitment = None
    objective = getattr(selected_binding, "story_objective_ref", None)
    if selected_binding.kind is not GoalKind.ADVANCE_STORY or objective is None:
        return commitment
    if objective in after:
        return None if commitment is None or commitment.objective_ref == objective else commitment
    # A blackout returns a healed party. Fitness alone would then force another
    # attempt, and successful return travel would reset the failure counter.
    # Release support after the verified loss so the unchanged model reconsiders.
    battle = (outcome.get("evidence") or {}).get("battle") or {}
    native_loss = (
        outcome.get("verification") == "failed"
        and outcome.get("error_type") is None
        and outcome.get("ordinary_setback") is True
        and outcome.get("failure_reason") == "resource_lost"
        and isinstance(battle, dict)
        and (battle.get("episode") or {}).get("battle_won") is False
    )
    if native_loss and commitment is not None and commitment.objective_ref == objective:
        return None
    succeeded = outcome.get("verification") == "succeeded" and outcome.get("error_type") is None
    if commitment is None or commitment.objective_ref != objective:
        return StoryKindCommitment(objective) if succeeded else commitment
    if succeeded:
        return replace(commitment, consecutive_failures=0)
    failures = commitment.consecutive_failures + 1
    return None if failures >= MAXIMUM_CONSECUTIVE_FAILURES else replace(commitment, consecutive_failures=failures)
