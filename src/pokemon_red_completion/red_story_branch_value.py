"""Learned choice among competing story objectives, after the kind-level choice.

The immediate goal model (e.g. Main94) keeps every kind-level decision: story
versus evolution, capture, healing, resupply. Only when its own choice is a
story executor and two or more distinct story objectives are executable does
this child rank those story executors. Non-story choices and single-branch
menus pass through unchanged, so retained kind-level choices cannot change.

Features are identity-free branch facts: the executor's planned remaining route
to its own endpoint, whether it continues the previous story selection, the
observed effort already spent on that branch, and existing candidate scalars.
Targets use the story-branch task-or-horizon progress contract (sequence channels plus
objective-scoped progress). Fits accept TRAIN
rows only; unknown channels stay unknown and cannot carry utility.
"""

import math
import random
from dataclasses import asdict, dataclass, field, replace

import numpy as np

from .goal_manager import GoalKind
from .player_sequence_targets import SEQUENCE_TARGET_NAMES
from .provenance import canonical_sha256
from .recorded_branch_history import RecordedBranchHistory

STORY_BRANCH_FEATURE_CONTRACT = "red-story-branch-features-v2"
STORY_BRANCH_HEAD_SCHEMA = "pokemon.red.story-branch-head.v1"
STORY_BRANCH_DECISION_SCHEMA = "pokemon.red.story-branch-decision.v1"
ROUTE_COST_SCALE = 500.0
ROUTE_BOUNDARY_SCALE = 3.0
HISTORY_NAMES = (
    "history.attempts", "history.actions", "history.frames", "history.cash_debits",
    "history.cash_credits", "history.losses", "history.quest_gains", "history.unattributed",
)
STORY_BRANCH_FEATURE_NAMES = (
    "route.known", "route.remaining_cost", "route.remaining_boundaries",
    "continues_previous_story_choice",
    *HISTORY_NAMES,
    "candidate.execution_effort", "candidate.party_risk",
    "challenge.present", "challenge.combat_required", "challenge.opposition_known",
    "challenge.median_level_deficit", "challenge.maximum_level_deficit",
    "story_unit.movement", "story_unit.interaction", "story_unit.requires_further_selected_unit",
    *("readiness." + n for n in (
        "observed", "history_observed", "current.median_combat_level_gap", "current.lowest_combat_level_gap",
        "current.hp_fraction", "current.fainted_fraction", "current.status_fraction", "current.pp_known", "current.pp_fraction",
        "recent.won", "recent.lost", "recent.fainted_fraction", "combat_required_x_hp_fraction", "combat_required_x_fainted_fraction")),
)
FEATURE_WIDTH = len(STORY_BRANCH_FEATURE_NAMES)
# Same magnitudes as DEFAULT_LIVING_DEX_GOAL_UTILITY (completion 4, dependency 3,
# action 0.2, frame 0.1, resource 0.5, party 1.0); not tuned toward any order.
# Story-branch target contract: the task-or-horizon sequence channels, where
# native_progress counts story battles WON on the committed objective (native
# battle evidence), plus route_progress = net reduction of that objective's
# measured remaining distance by the window end (1.0 when it completes). The
# caller declares the distance metric (e.g. map hops on the static ROM map
# graph from the observed map); it must be the same metric at both ends.
STORY_BRANCH_TARGET_CONTRACT = "red-story-branch-task-or-horizon-progress-v1"
STORY_BRANCH_TARGET_NAMES = (*SEQUENCE_TARGET_NAMES, "route_progress")
STORY_BRANCH_TARGET_SCALES = (1, 1, 1000, 60000, 1000, 1000, 1, None)
DEFAULT_STORY_BRANCH_UTILITY = (3.0, 4.0, -0.2, -0.1, -0.5, 0.0, -1.0, 3.0)


def _sha(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("story branch identity differs")


@dataclass(frozen=True)
class StoryBranchTracker:
    """Observed per-objective effort and the previous selected story objective.

    Objective refs are private joins, never features. Zero counts mean no
    observation since tracking began, not a never-attempted objective.
    """

    histories: tuple[tuple[str, RecordedBranchHistory], ...] = ()
    previous_objective_ref: str | None = None
    unattributed_story_choices: int = 0

    def __post_init__(self):
        refs = [ref for ref, _ in self.histories]
        if (
            type(self.histories) is not tuple
            or len(set(refs)) != len(refs)
            or any(type(r) is not str or not r for r in refs)
            or any(type(h) is not RecordedBranchHistory for _, h in self.histories)
            or any(type(n) is not int or n < 0 for _, h in self.histories for n in asdict(h).values())
            or (self.previous_objective_ref is not None
                and (type(self.previous_objective_ref) is not str or not self.previous_objective_ref))
            or type(self.unattributed_story_choices) is not int or self.unattributed_story_choices < 0
        ):
            raise ValueError("story branch tracker differs")

    def history(self, objective_ref):
        found = dict(self.histories).get(objective_ref)
        return found if found is not None else RecordedBranchHistory(0, 0, 0, 0, 0, 0, 0, self.unattributed_story_choices)

    def after(self, *, kind, objective_ref, actions, frames, cash_debits=0, cash_credits=0,
              losses=0, quest_gains=0):
        """Return the tracker after one closed outcome; non-story outcomes keep the branch."""
        if any(type(v) is not int or v < 0 for v in (actions, frames, cash_debits, cash_credits, losses, quest_gains)):
            raise ValueError("story branch outcome counters must be non-negative integers")
        if kind is not GoalKind.ADVANCE_STORY:
            return self
        if objective_ref is None:
            return replace(self, unattributed_story_choices=self.unattributed_story_choices + 1)
        old = self.history(objective_ref)
        new = RecordedBranchHistory(old.attempts + 1, old.actions + actions, old.frames + frames,
                                    old.observed_cash_debits + cash_debits, old.observed_cash_credits + cash_credits,
                                    old.reported_losses + losses, old.observed_quest_gains + quest_gains,
                                    self.unattributed_story_choices)
        rows = tuple(sorted({**dict(self.histories), objective_ref: new}.items()))
        return replace(self, histories=rows, previous_objective_ref=objective_ref)

    def document(self):
        return dict(schema="pokemon.red.story-branch-tracker.v1",
                    histories=[[ref, asdict(h)] for ref, h in self.histories],
                    previous_objective_ref=self.previous_objective_ref,
                    unattributed_story_choices=self.unattributed_story_choices)

    @property
    def sha256(self):
        return canonical_sha256(self.document())


@dataclass(frozen=True)
class StoryBranchSegment:
    """TRAIN-only commitment: one sampled story objective kept for a sampled number of units.

    start_probability is the exact behaviour probability of choosing this objective at
    the branch point that opened the segment; continuation inside a segment is
    deterministic given the segment. Objective refs stay private joins.
    """

    objective_ref: str
    length: int
    remaining: int
    start_probability: float
    explored: bool
    start_seed: int

    def __post_init__(self):
        if (type(self.objective_ref) is not str or not self.objective_ref
                or type(self.length) is not int or self.length < 1
                or type(self.remaining) is not int or not 0 < self.remaining <= self.length
                or type(self.start_probability) is not float or not 0 < self.start_probability <= 1
                or type(self.explored) is not bool or type(self.start_seed) is not int or self.start_seed < 0):
            raise ValueError("story branch segment differs")

    def document(self):
        return dict(schema="pokemon.red.story-branch-segment.v1", **asdict(self))


def segment_after_outcome(segment, selected_binding, outcome):
    """Close the segment when its objective completes or its units are spent."""
    if segment is None:
        return None
    after = set((outcome.get("after") or {}).get("completed_objectives") or ())
    if segment.objective_ref in after:
        return None
    if selected_binding.kind is GoalKind.ADVANCE_STORY and selected_binding.story_objective_ref == segment.objective_ref:
        return None if segment.remaining <= 1 else replace(segment, remaining=segment.remaining - 1)
    return segment


def tracker_after_outcome(tracker, selected_binding, outcome):
    """Fold one recorded native outcome into the tracker; unknown costs count as zero effort only for history."""
    counters = outcome.get("observed_cost") or {}
    before = set((outcome.get("before") or {}).get("completed_objectives") or ())
    after = set((outcome.get("after") or {}).get("completed_objectives") or ())
    spent = counters.get("cash_spent")
    spent = spent if type(spent) is int else 0
    return tracker.after(
        kind=selected_binding.kind, objective_ref=selected_binding.story_objective_ref,
        actions=max(0, int(counters.get("actions") or 0)), frames=max(0, int(counters.get("frames") or 0)),
        cash_debits=max(0, spent), cash_credits=max(0, -spent), quest_gains=len(after - before))


READINESS_BRANCH_WIDTH = 14
# Milestone commitment (M0): keep a selected story objective until it completes or is no
# longer offered; the cap only bounds a segment record, it is not a strategy parameter.
STORY_MILESTONE_UNITS = 200


def readiness_branch_vector(readiness, *, combat_required):
    """Identity-free party readiness from the candidate's existing PlayerReadiness.

    Missing readiness is (0, ...) with observed=0, never a claimed healthy party.
    """
    if readiness is None:
        return (0.0,) * READINESS_BRANCH_WIDTH
    from .player_readiness import READINESS_NAMES, PlayerReadiness
    if type(readiness) is not PlayerReadiness:
        raise TypeError("typed player readiness required")
    v = dict(zip(READINESS_NAMES[1:], readiness.values, strict=True))
    c = float(combat_required)
    return (1.0, float(readiness.history_observed), float(v["current.median_combat_level_gap"]), float(v["current.lowest_combat_level_gap"]),
            float(v["current.hp_fraction"]), float(v["current.fainted_fraction"]), float(v["current.status_fraction"]),
            float(v["current.pp_known"]), float(v["current.pp_fraction"]), float(v["recent.won"]), float(v["recent.lost"]),
            float(v["recent.fainted_fraction"]), c * float(v["current.hp_fraction"]), c * float(v["current.fainted_fraction"]))


def story_branch_features(candidate, binding, tracker):
    """Identity-free bounded features for one executable story branch."""
    if binding.kind is not GoalKind.ADVANCE_STORY or binding.story_objective_ref is None:
        raise ValueError("story branch features require a bound story executor")
    if candidate.binding_ref != binding.binding_ref:
        raise ValueError("story branch candidate and binding differ")
    quote = binding.story_route_quote
    route = (0.0, 0.0, 0.0) if quote is None else (
        1.0,
        quote.remaining_cost / (quote.remaining_cost + ROUTE_COST_SCALE),
        quote.remaining_boundaries / (quote.remaining_boundaries + ROUTE_BOUNDARY_SCALE),
    )
    continues = float(tracker.previous_objective_ref == binding.story_objective_ref)
    history = tracker.history(binding.story_objective_ref).vector()
    f = candidate.features
    ch = candidate.challenge
    challenge = (0.0, 0.0, 0.0, 0.0, 0.0) if ch is None else (
        1.0, float(ch.combat_required), float(ch.opposition_known),
        max(-1.0, min(1.0, float(ch.median_level_deficit))), max(-1.0, min(1.0, float(ch.maximum_level_deficit))),
    )
    unit = candidate.story_unit
    story = (0.0, 0.0, 0.0) if unit is None else (
        float(unit.mode == "movement"), float(unit.mode == "interaction"), float(unit.requires_further_selected_unit))
    values = (*route, continues, *history, float(f.execution_effort), float(f.party_risk), *challenge, *story,
              *readiness_branch_vector(candidate.readiness, combat_required=challenge[1]))
    if len(values) != FEATURE_WIDTH or any(not math.isfinite(v) or not -1.0 <= v <= 1.0 for v in values):
        raise ValueError("story branch feature vector differs")
    return values


@dataclass(frozen=True)
class StoryBranchRow:
    """One TRAIN window: features at the branch choice, masked task-or-horizon targets."""

    window_sha256: str
    features: tuple[float, ...]
    targets: tuple[float | None, ...]
    partition: str

    def __post_init__(self):
        _sha(self.window_sha256)
        if (
            self.partition not in {"train", "development"}
            or type(self.features) is not tuple or len(self.features) != FEATURE_WIDTH
            or any(type(v) not in (int, float) or not math.isfinite(v) or not -1 <= v <= 1 for v in self.features)
            or type(self.targets) is not tuple or len(self.targets) != len(STORY_BRANCH_TARGET_NAMES)
            or any(v is not None and (type(v) not in (int, float) or not 0 <= v <= 1) for v in self.targets)
        ):
            raise ValueError("story branch row differs")


@dataclass(frozen=True)
class StoryBranchHead:
    """Per-channel ridge over the compact story-branch contract; unknown channels stay None."""

    parameters: tuple[tuple[float, ...] | None, ...]
    sample_counts: tuple[int, ...]
    dataset_sha256: str
    ridge: float
    utility: tuple[float, ...] = DEFAULT_STORY_BRANCH_UTILITY
    target_contract: str = STORY_BRANCH_TARGET_CONTRACT

    def __post_init__(self):
        _sha(self.dataset_sha256)
        n = len(STORY_BRANCH_TARGET_NAMES)
        if (
            type(self.parameters) is not tuple or len(self.parameters) != n
            or type(self.sample_counts) is not tuple or len(self.sample_counts) != n
            or type(self.ridge) not in (int, float) or not math.isfinite(self.ridge) or self.ridge <= 0
            or type(self.utility) is not tuple or len(self.utility) != n
            or any(type(w) not in (int, float) or not math.isfinite(w) for w in self.utility)
            or not any(self.utility[i] and self.parameters[i] is not None for i in range(n))
            or self.target_contract != STORY_BRANCH_TARGET_CONTRACT
        ):
            raise ValueError("story branch head contract differs")
        for row, count, weight in zip(self.parameters, self.sample_counts, self.utility, strict=True):
            if type(count) is not int or count < 0 or (row is None) != (count == 0) or count == 1:
                raise ValueError("story branch channel needs zero or at least two rows")
            if row is not None and (len(row) != FEATURE_WIDTH + 1 or any(not math.isfinite(v) for v in row)):
                raise ValueError("story branch channel parameters differ")
            if row is None and weight != 0:
                raise ValueError("story branch utility uses an unlearned channel")

    def document(self):
        return dict(schema=STORY_BRANCH_HEAD_SCHEMA, feature_contract=STORY_BRANCH_FEATURE_CONTRACT,
                    feature_names=list(STORY_BRANCH_FEATURE_NAMES), target_contract=self.target_contract,
                    target_names=list(STORY_BRANCH_TARGET_NAMES), parameters=[None if p is None else list(p) for p in self.parameters],
                    sample_counts=list(self.sample_counts), dataset_sha256=self.dataset_sha256, ridge=self.ridge,
                    utility=list(self.utility), live_policy_adopted=False)

    @property
    def model_sha256(self):
        return canonical_sha256(self.document())

    @classmethod
    def from_document(cls, document, *, expected_sha256):
        if canonical_sha256(document) != expected_sha256 or document.get("schema") != STORY_BRANCH_HEAD_SCHEMA:
            raise ValueError("story branch head identity differs")
        if document["feature_names"] != list(STORY_BRANCH_FEATURE_NAMES):
            raise ValueError("story branch head feature contract differs")
        head = cls(tuple(None if p is None else tuple(p) for p in document["parameters"]),
                   tuple(document["sample_counts"]), document["dataset_sha256"], document["ridge"],
                   tuple(document["utility"]), document["target_contract"])
        if head.model_sha256 != expected_sha256:
            raise ValueError("story branch head contract differs")
        return head

    def predict(self, features):
        if type(features) is not tuple or len(features) != FEATURE_WIDTH:
            raise ValueError("story branch features differ")
        return tuple(None if p is None else max(0.0, min(1.0, p[0] + math.fsum(w * x for w, x in zip(p[1:], features, strict=True))))
                     for p in self.parameters)

    def score(self, features):
        return math.fsum(w * v for w, v in zip(self.utility, self.predict(features), strict=True) if v is not None)


def fit_story_branch_head(rows, *, ridge, utility=DEFAULT_STORY_BRANCH_UTILITY):
    """TRAIN-only masked ridge; native admission must already have produced the rows."""
    if (
        type(rows) is not tuple or not rows
        or any(type(r) is not StoryBranchRow or r.partition != "train" for r in rows)
        or len({r.window_sha256 for r in rows}) != len(rows)
        or type(ridge) not in (int, float) or not math.isfinite(ridge) or ridge <= 0
    ):
        raise ValueError("story branch fit requires distinct TRAIN rows and positive ridge")
    parameters, counts = [], []
    for channel in range(len(STORY_BRANCH_TARGET_NAMES)):
        observed = tuple(r for r in rows if r.targets[channel] is not None)
        counts.append(len(observed))
        if len(observed) < 2:
            if observed:
                raise ValueError("story branch channel has fewer than two measured rows")
            parameters.append(None)
            continue
        x = np.asarray([r.features for r in observed], dtype=np.float64)
        y = np.asarray([r.targets[channel] for r in observed], dtype=np.float64)
        mean, scale = x.mean(axis=0), x.std(axis=0)
        scale = np.where(scale < 1e-12, 1.0, scale)
        z = (x - mean) / scale
        weights = np.linalg.solve(z.T @ z + ridge * np.eye(FEATURE_WIDTH), z.T @ (y - y.mean())) / scale
        parameters.append((float(y.mean() - mean @ weights), *(float(w) for w in weights)))
    utility = tuple(0.0 if p is None else float(w) for w, p in zip(utility, parameters, strict=True))
    dataset = canonical_sha256([dict(window=r.window_sha256, features=r.features, targets=r.targets, partition=r.partition) for r in rows])
    return StoryBranchHead(tuple(parameters), tuple(counts), dataset, float(ridge), utility)


@dataclass(frozen=True)
class StoryBranchDecision:
    """Receipt of the story-only child step; the parent choice is retained verbatim."""

    parent: object
    story_indices: tuple[int, ...]
    selected_candidate_index: int
    scores: tuple[float | None, ...]
    probabilities: tuple[float, ...]
    head_sha256: str | None
    tracker_sha256: str
    exploration_probability: float
    explored: bool
    seed: int
    features: tuple[tuple[float, ...], ...] = field(default=())
    segment: StoryBranchSegment | None = None
    segment_started: bool = False

    def document(self):
        return dict(schema=STORY_BRANCH_DECISION_SCHEMA, parent_selected_candidate_index=self.parent.selected_candidate_index,
                    parent_model_sha256=self.parent.model_sha256, story_indices=list(self.story_indices),
                    selected_candidate_index=self.selected_candidate_index, scores=list(self.scores),
                    probabilities=list(self.probabilities), head_sha256=self.head_sha256, tracker_sha256=self.tracker_sha256,
                    exploration_probability=self.exploration_probability, explored=self.explored, seed=self.seed,
                    feature_contract=STORY_BRANCH_FEATURE_CONTRACT, features=[list(f) for f in self.features],
                    kind_level_choice_unchanged=True,
                    **({} if self.segment is None else dict(segment=self.segment.document(), segment_started=self.segment_started)))

    @property
    def sha256(self):
        return canonical_sha256(self.document())

    @property
    def deterministic_continuation(self):
        """An existing unlearned segment overrides the fresh parent choice."""
        return (
            self.head_sha256 is None and self.exploration_probability == 0.0
            and not self.explored and self.segment is not None
            and not self.segment_started
            and self.selected_candidate_index != self.parent.selected_candidate_index
        )

    def choice(self):
        """A mixed-menu choice selecting the child's story executor (kind unchanged)."""
        from .red_live_option_menu import RedLiveOptionChoice, RedLiveOptionSelectionMode
        if self.selected_candidate_index == self.parent.selected_candidate_index and not self.explored and self.head_sha256 is None:
            return self.parent
        return RedLiveOptionChoice(self.parent.options, self.selected_candidate_index,
                                   RedLiveOptionSelectionMode.MODEL_EXPLORATION, self.scores, self.probabilities,
                                   self.seed, self.sha256)


def story_branch_indices(choice):
    """Available executable story branches with distinct objectives; () when not a branch point."""
    options = choice.options
    if choice.selected_binding.kind is not GoalKind.ADVANCE_STORY:
        return ()
    indices = tuple(i for i in options.menu.available_indices
                    if options.binding(i).kind is GoalKind.ADVANCE_STORY and options.binding(i).story_objective_ref is not None)
    if len({options.binding(i).story_objective_ref for i in indices}) < 2:
        return ()
    return indices


def refine_story_branch(choice, *, head, tracker, exploration_probability=0.0, seed, segment=None, segment_lengths=None):
    """Rank only the competing story executors; return None when not applicable.

    With a head, the best branch score wins; ties keep the parent's selection if
    it is among the maxima, else the lowest index. Without a head (pre-fit TRAIN
    collection), the parent's selection is the base policy. exploration_probability
    > 0 mixes a uniform branch choice and is intended for TRAIN collection only;
    the recorded probabilities are exact behaviour probabilities.
    """
    if type(tracker) is not StoryBranchTracker or (head is not None and type(head) is not StoryBranchHead):
        raise TypeError("story branch refinement requires a typed tracker and head")
    if type(exploration_probability) not in (int, float) or not 0 <= exploration_probability <= 1:
        raise ValueError("story branch exploration probability differs")
    if type(seed) is not int or seed < 0:
        raise ValueError("story branch seed differs")
    if segment_lengths is not None and (
        type(segment_lengths) is not tuple or len(segment_lengths) != 2
        or any(type(v) is not int for v in segment_lengths) or not 1 <= segment_lengths[0] <= segment_lengths[1] <= 200
    ):
        raise ValueError("story branch segment lengths differ")
    if segment is not None and (segment_lengths is None or type(segment) is not StoryBranchSegment):
        raise ValueError("story branch segment requires declared segment lengths")
    indices = story_branch_indices(choice)
    if not indices:
        return None
    options = choice.options
    feats = tuple(story_branch_features(options.menu.candidates[i], options.binding(i), tracker) for i in indices)
    objective_of = {i: options.binding(i).story_objective_ref for i in indices}
    branch_scores = (None,) * len(indices) if head is None else tuple(head.score(f) for f in feats)
    sel = story_branch_selection(indices=indices, objective_of=objective_of, parent_index=choice.selected_candidate_index,
                                 branch_scores=branch_scores, candidate_count=len(options.menu.candidates),
                                 exploration_probability=exploration_probability, seed=seed,
                                 segment=segment, segment_lengths=segment_lengths)
    scores = [None] * len(options.menu.candidates)
    for i, s in zip(indices, branch_scores, strict=True):
        scores[i] = s
    return StoryBranchDecision(choice, indices, sel["selected"], tuple(scores), sel["probabilities"],
                               None if head is None else head.model_sha256, tracker.sha256,
                               float(exploration_probability), sel["explored"], seed, feats,
                               sel["segment"], sel["segment_started"])


def story_branch_selection(*, indices, objective_of, parent_index, branch_scores, candidate_count,
                           exploration_probability, seed, segment=None, segment_lengths=None):
    """Pure selection core shared by the live child and the admission replay.

    Inputs are exactly what a story-branch receipt records; the same inputs always
    return the same selection, probabilities, exploration flag and segment.
    """
    if segment is not None and segment.objective_ref in objective_of.values():
        # Inside a committed segment: deterministic continuation of its objective.
        same = [i for i in indices if objective_of[i] == segment.objective_ref]
        selected = parent_index if parent_index in same else min(same)
        return dict(selected=selected, probabilities=tuple(float(i == selected) for i in range(candidate_count)),
                    explored=False, segment=segment, segment_started=False)
    if all(s is None for s in branch_scores):
        base = parent_index
    else:
        peak = max(branch_scores)
        best = [i for i, s in zip(indices, branch_scores, strict=True) if s == peak]
        base = parent_index if parent_index in best else min(best)
    p = float(exploration_probability)
    probabilities = [0.0] * candidate_count
    for i in indices:
        probabilities[i] = (1.0 - p) * float(i == base) + p / len(indices)
    rng = random.Random(seed)
    explored = p > 0 and rng.random() < p
    selected = indices[rng.randrange(len(indices))] if explored else base
    new_segment = None
    if segment_lengths is not None:
        objective = objective_of[selected]
        start_probability = math.fsum(probabilities[i] for i in indices if objective_of[i] == objective)
        length = rng.randint(*segment_lengths)
        new_segment = StoryBranchSegment(objective, length, length, float(min(1.0, start_probability)), explored, seed)
    return dict(selected=selected, probabilities=tuple(probabilities), explored=explored,
                segment=new_segment, segment_started=new_segment is not None)


@dataclass(frozen=True)
class StoryBranchStep:
    """One recorded closed outcome, reduced to what the progress contract may read.

    objective_quote is the committed objective's remaining distance measured at
    THIS step's decision, in the caller's declared metric (None when unknown).
    """

    kind: GoalKind
    story_objective_ref: str | None
    clean: bool
    battle_won: bool
    newly_completed: frozenset[str]
    actions: int
    frames: int
    cash_spent: int
    objective_quote: float | None = None


def story_branch_window_targets(steps, *, objective_ref, start_quote, horizon=4):
    """Task-or-horizon progress labels for the window that starts at steps[0].

    The window ends when the committed objective completes (task terminal) or after
    `horizon` story units. A window cut by an unclean outcome or the run end is
    censored: every target is None (never zero-filled). battle_losses stays unknown.
    route_progress uses the committed objective's distance at the first decision
    after the window (full progress when it completed); unknown distances leave it None.
    Returns (raw, targets, complete, task_terminal).
    """
    if type(objective_ref) is not str or not objective_ref or type(horizon) is not int or horizon < 1:
        raise ValueError("story branch window declaration differs")
    if start_quote is not None and (type(start_quote) not in (int, float) or not math.isfinite(start_quote) or start_quote < 0):
        raise ValueError("story branch start quote differs")
    story = done = won = actions = frames = debits = credits = 0
    terminal = complete = False
    end = len(steps)
    for i, s in enumerate(steps):
        if type(s) is not StoryBranchStep:
            raise TypeError("typed story branch steps required")
        if not s.clean:
            end = i
            break
        actions += s.actions; frames += s.frames
        debits += max(0, s.cash_spent); credits += max(0, -s.cash_spent)
        done += len(s.newly_completed)
        if s.kind is GoalKind.ADVANCE_STORY:
            story += 1
            if s.story_objective_ref == objective_ref and s.battle_won:
                won += 1
        if objective_ref in s.newly_completed:
            terminal = complete = True; end = i + 1
            break
        if story >= horizon:
            complete = True; end = i + 1
            break
    route = None
    if complete and start_quote is not None and start_quote > 0:
        if terminal:
            route = 1.0
        elif end < len(steps) and steps[end].objective_quote is not None:
            route = max(0.0, min(1.0, (start_quote - steps[end].objective_quote) / start_quote))
    raw = (won, done, actions, frames, debits, credits, None, route)
    targets = tuple(
        None if (not complete or value is None) else (value if scale is None else value / (value + scale))
        for value, scale in zip(raw, STORY_BRANCH_TARGET_SCALES, strict=True)
    )
    return raw, targets, complete, terminal
