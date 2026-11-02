"""Numeric branch experience from a checked prefix, not another memory store.

This diagnostic is not wired into model V6 or TRAIN admission. Branch references
are private joins to pre-input declarations, never features. No lookup of future
opponents or a recommended next objective exists. A live collector will need an
incremental authenticated prefix reader before using this projection online.
"""

from dataclasses import dataclass

from .goal_search_memory import GoalSearchHistory
from .red_sequence_receipts import RecordedSequenceProjection


@dataclass(frozen=True)
class RecordedBranchHistory:
    attempts: int
    actions: int
    frames: int
    observed_cash_debits: int
    observed_cash_credits: int
    reported_losses: int
    observed_quest_gains: int
    unattributed_prior_story_choices: int

    def vector(self) -> tuple[float, ...]:
        """Bounded observed counts, not success probabilities or future estimates."""
        return tuple(value / (value + scale) for value, scale in zip(
            (self.attempts, self.actions, self.frames, self.observed_cash_debits,
             self.observed_cash_credits, self.reported_losses, self.observed_quest_gains,
             self.unattributed_prior_story_choices),
            (1, 1000, 60000, 1000, 1000, 1, 1, 1), strict=True,
        ))


def recorded_branch_history(
    episode: RecordedSequenceProjection, *, objective_ref: str, boundary_sha256: str,
    expected_source_sha256: str, expected_plan_sha256: str,
) -> RecordedBranchHistory:
    """Only choices strictly before the supplied boundary can contribute.

    The source AND behavior-plan identity are required: paired evaluation arms
    may start from identical state bytes but must not borrow one another's past.
    These are consistency checks, not a replacement for native/source admission.
    Zero observations mean unknown history before tracking, not a never-tried quest.
    """
    if (
        not isinstance(episode, RecordedSequenceProjection)
        or episode.source_sha256 != expected_source_sha256
        or episode.plan_sha256 != expected_plan_sha256
        or type(objective_ref) is not str or not objective_ref
        or not len(episode.choices) == len(episode.story_contexts) == len(episode.selected_kinds)
    ):
        raise ValueError("branch history source/plan/context differs")
    boundaries = [s.before_sha256 for s in episode.choices]
    if episode.choices:
        boundaries.append(episode.choices[-1].after_sha256)
    if boundaries.count(boundary_sha256) != 1:
        raise ValueError("branch history boundary absent or ambiguous")
    stop = boundaries.index(boundary_sha256)
    attempts = actions = frames = debits = credits = losses = gains = unknown = 0
    prior_quests = set(episode.initial_quests)
    for step, context, kind in zip(
        episode.choices[:stop], episode.story_contexts[:stop], episode.selected_kinds[:stop],
        strict=True,
    ):
        new_quests = set(step.quests) - prior_quests
        prior_quests.update(step.quests)
        if kind == "advance_story" and context is None:
            unknown += 1
        if context != objective_ref:
            continue
        attempts += 1
        actions += step.actions
        frames += step.frames
        debits += step.cash_debits
        credits += step.cash_credits
        losses += step.blackouts
        gains += len(new_quests)
    # Reuse existing strict effort-counter validation without calling story
    # failures "exhausted searches" or changing the acquisition memory schema.
    GoalSearchHistory(attempts=attempts, actions=actions, frames=frames)
    return RecordedBranchHistory(attempts, actions, frames, debits, credits, losses, gains, unknown)
