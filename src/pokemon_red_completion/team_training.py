"""Reusable equal-level and evolution-ready team development policies.

The project's qualified route trained one overleveled carry and let the rest of
the party idle.  That route is durable teacher evidence, but it teaches a habit
a transferable agent should not learn: it makes progress depend on a single
Pokémon surviving every remaining battle.

The module retains that strict equal-level rule set for experiments that need
it, and adds the completion-efficient contract used by the main teacher: fill
the declared final-form roster and train one designated workhorse to its target
without grinding every already-evolved specimen to the same level. Like
:mod:`pokemon_red_completion.training`, it decides *why* to fight, heal, switch,
or stop; game adapters remain responsible for navigation, menus, and battle
execution.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .party import (
    MAX_LEVEL,
    MIN_LEVEL,
    PARTY_SLOT_LIMIT,
    PartyMemberObservation,
    PartyObservation,
    PartyRole,
    StatusCondition,
)

LEAD_SLOT = 1


class TeamTrainingDirective(StrEnum):
    """One semantic action requested by the balanced-team policy."""

    RECRUIT_MEMBER = "recruit_member"
    EVOLVE_MEMBER = "evolve_member"
    RESTORE_TEAM = "restore_team"
    SWITCH_TRAINEE = "switch_trainee"
    TRAIN_MEMBER = "train_member"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class RosterSlot:
    """One planned party position, bound to a role and a concrete species.

    ``substitution_reason`` documents why this species replaced the roster's
    default choice.  A substitution without a recorded reason is rejected so a
    roster change can never enter the repository unexplained.
    """

    role: PartyRole
    species_id: int
    is_substitution: bool = False
    substitution_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, PartyRole):
            raise TypeError("role must be a PartyRole")
        if type(self.species_id) is not int or self.species_id <= 0:
            raise ValueError("species_id must be a positive integer")
        if self.is_substitution and not (self.substitution_reason or "").strip():
            raise ValueError("a roster substitution requires a recorded reason")
        if not self.is_substitution and self.substitution_reason is not None:
            raise ValueError("substitution_reason is only meaningful for a substitution")


@dataclass(frozen=True, slots=True)
class TeamRosterPlan:
    """The intended six-member roster expressed as roles plus species bindings."""

    slots: tuple[RosterSlot, ...]

    def __post_init__(self) -> None:
        if not self.slots:
            raise ValueError("a roster plan needs at least one slot")
        if len(self.slots) > PARTY_SLOT_LIMIT:
            raise ValueError(f"a roster plan cannot exceed {PARTY_SLOT_LIMIT} slots")
        if any(not isinstance(slot, RosterSlot) for slot in self.slots):
            raise TypeError("slots must contain RosterSlot entries")
        roles = [slot.role for slot in self.slots]
        if len(set(roles)) != len(roles):
            raise ValueError("a roster plan cannot repeat a role")
        species = [slot.species_id for slot in self.slots]
        if len(set(species)) != len(species):
            raise ValueError("a roster plan cannot repeat a species")

    @property
    def species_ids(self) -> tuple[int, ...]:
        """Every planned species, in roster order."""

        return tuple(slot.species_id for slot in self.slots)

    @property
    def substitutions(self) -> tuple[RosterSlot, ...]:
        """Every slot that deviates from the roster's default choice."""

        return tuple(slot for slot in self.slots if slot.is_substitution)

    def missing_from(self, party: PartyObservation) -> tuple[RosterSlot, ...]:
        """Roster slots whose species is not currently in the active party."""

        present = set(party.species_ids())
        return tuple(slot for slot in self.slots if slot.species_id not in present)

    def unplanned_in(self, party: PartyObservation) -> tuple[int, ...]:
        """Species present in the party that the roster plan does not name."""

        planned = set(self.species_ids)
        return tuple(species for species in party.species_ids() if species not in planned)


@dataclass(frozen=True, slots=True)
class LevelParityContract:
    """How far behind the local opposition a party member may fall.

    An absolute level floor is a Red-specific magic number: ``50`` means nothing
    in a game whose Elite Four sits at 70, and it over-trains in one whose gyms
    top out at 30.  Competent play is relative—stay near what you are actually
    facing—so this contract is expressed against the opposition's level and
    transfers to any mainline title unchanged.

    It also makes training self-pacing.  A party measured against the local
    difficulty curve trains continuously as that curve rises, instead of
    grinding to a fixed number in one late block.
    """

    max_levels_behind: int = 10

    def __post_init__(self) -> None:
        if type(self.max_levels_behind) is not int or self.max_levels_behind < 0:
            raise ValueError("max_levels_behind must be a non-negative integer")

    def required_level(self, opposition_level: int) -> int:
        """The lowest level a member may hold and still be considered ready."""

        if type(opposition_level) is not int or not MIN_LEVEL <= opposition_level <= MAX_LEVEL:
            raise ValueError(f"opposition_level must be between {MIN_LEVEL} and {MAX_LEVEL}")
        return max(MIN_LEVEL, opposition_level - self.max_levels_behind)

    def members_behind(
        self,
        party: PartyObservation,
        opposition_level: int,
    ) -> tuple[PartyMemberObservation, ...]:
        """Every member that trails the opposition by more than the tolerance."""

        floor = self.required_level(opposition_level)
        return tuple(member for member in party.members if member.level < floor)

    def is_met_by(self, party: PartyObservation, opposition_level: int) -> bool:
        """Whether a non-empty party is ready for this opposition."""

        return bool(party.members) and not self.members_behind(party, opposition_level)

    def deficit(self, party: PartyObservation, opposition_level: int) -> int | None:
        """How many levels the weakest member is short, or ``None`` if ready."""

        if not party.members:
            return None
        shortfall = self.required_level(opposition_level) - min(party.levels)
        return shortfall if shortfall > 0 else None


COMPLETION_LEVEL_PARITY = LevelParityContract()


@dataclass(frozen=True, slots=True)
class DevelopedTeamPolicy:
    """Completion-efficient roster policy with one deliberately trained workhorse.

    The roster species are the adapter-declared final available forms.  This
    makes evolution completion explicit without forcing every non-workhorse to
    copy the carry's level, and gives collection curricula the same semantic
    gate they need when evolving one living specimen at a time.
    """

    roster: TeamRosterPlan
    workhorse_species_id: int
    workhorse_target_level: int = 75
    level_parity: LevelParityContract | None = None
    parity_opposition_level: int | None = None

    def __post_init__(self) -> None:
        if self.workhorse_species_id not in self.roster.species_ids:
            raise ValueError("workhorse_species_id must belong to the final-form roster")
        if not MIN_LEVEL < self.workhorse_target_level <= MAX_LEVEL:
            raise ValueError(f"workhorse_target_level must be between 2 and {MAX_LEVEL}")
        if (self.level_parity is None) != (self.parity_opposition_level is None):
            raise ValueError("level_parity and parity_opposition_level must be provided together")
        if self.parity_opposition_level is not None and not (
            MIN_LEVEL <= self.parity_opposition_level <= MAX_LEVEL
        ):
            raise ValueError(f"parity_opposition_level must be between {MIN_LEVEL} and {MAX_LEVEL}")

    @property
    def trains_whole_party(self) -> bool:
        """Whether this policy trains every member or only the workhorse.

        Left ``False`` by default so the completion-efficient behaviour is
        unchanged until a caller opts in deliberately.
        """

        return self.level_parity is not None and self.parity_opposition_level is not None


@dataclass(frozen=True, slots=True)
class DevelopedTeamReport:
    """Portable receipt for final forms plus a trained completion workhorse."""

    required_species_ids: tuple[int, ...]
    observed_species_ids: tuple[int, ...]
    workhorse_species_id: int
    workhorse_target_level: int
    observed_workhorse_level: int | None
    fainted_count: int
    required_minimum_level: int | None = None
    observed_levels: tuple[int, ...] = ()

    @property
    def has_final_form_roster(self) -> bool:
        return len(self.observed_species_ids) == len(self.required_species_ids) and set(
            self.observed_species_ids
        ) == set(self.required_species_ids)

    @property
    def workhorse_ready(self) -> bool:
        return (
            self.observed_workhorse_level is not None
            and self.observed_workhorse_level >= self.workhorse_target_level
        )

    @property
    def minimum_level(self) -> int | None:
        """The weakest member's level, or ``None`` when no levels were observed."""

        return min(self.observed_levels) if self.observed_levels else None

    @property
    def maximum_level(self) -> int | None:
        """The strongest member's level."""

        return max(self.observed_levels) if self.observed_levels else None

    @property
    def level_spread(self) -> int | None:
        """The distance between the strongest and weakest member."""

        if not self.observed_levels:
            return None
        return max(self.observed_levels) - min(self.observed_levels)

    @property
    def passed(self) -> bool:
        """Whether the roster is complete, the workhorse is trained, and none fainted.

        If a level parity contract was requested, this also asserts that every party
        member has reached the required minimum level.
        """

        if not (self.has_final_form_roster and self.workhorse_ready and self.fainted_count == 0):
            return False
        return not (
            self.required_minimum_level is not None
            and (self.minimum_level is None or self.minimum_level < self.required_minimum_level)
        )


def plan_team_development(
    party: PartyObservation,
    policy: DevelopedTeamPolicy,
) -> TeamTrainingDecision:
    """Choose recruitment, evolution, workhorse training, or a completed stop."""

    if not party.members:
        return TeamTrainingDecision(
            TeamTrainingDirective.RECRUIT_MEMBER,
            "party is empty",
            target_slot=LEAD_SLOT,
        )
    if party.fainted_count or party.is_wiped_out:
        return TeamTrainingDecision(
            TeamTrainingDirective.RESTORE_TEAM,
            f"{party.fainted_count} member(s) fainted",
        )
    missing = policy.roster.missing_from(party)
    unplanned = policy.roster.unplanned_in(party)
    if party.size < len(policy.roster.slots) and not unplanned:
        return TeamTrainingDecision(
            TeamTrainingDirective.RECRUIT_MEMBER,
            f"party holds {party.size} of {len(policy.roster.slots)} final-form members",
            target_slot=party.size + 1,
        )
    if missing or unplanned:
        target = next(
            (member.slot for member in party.members if member.species_id in set(unplanned)),
            None,
        )
        return TeamTrainingDecision(
            TeamTrainingDirective.EVOLVE_MEMBER,
            "party has not reached its declared final available forms",
            target_slot=target,
        )
    workhorse = next(
        (member for member in party.members if member.species_id == policy.workhorse_species_id),
        None,
    )
    if workhorse is None:
        return TeamTrainingDecision(
            TeamTrainingDirective.RECRUIT_MEMBER,
            "declared workhorse is absent",
        )
    if workhorse.level < policy.workhorse_target_level:
        directive = (
            TeamTrainingDirective.TRAIN_MEMBER
            if workhorse.slot == LEAD_SLOT
            else TeamTrainingDirective.SWITCH_TRAINEE
        )
        return TeamTrainingDecision(
            directive,
            f"workhorse is below level {policy.workhorse_target_level}",
            target_slot=workhorse.slot,
        )
    if policy.trains_whole_party:
        assert policy.level_parity is not None
        assert policy.parity_opposition_level is not None
        behind = policy.level_parity.members_behind(party, policy.parity_opposition_level)
        if behind:
            trainable = [member for member in behind if member.is_trainable]
            if not trainable:
                return TeamTrainingDecision(
                    TeamTrainingDirective.RESTORE_TEAM,
                    "no member trailing the opposition can currently gain experience",
                )
            weakest = min(trainable, key=lambda member: (member.level, member.slot))
            required = policy.level_parity.required_level(policy.parity_opposition_level)
            directive = (
                TeamTrainingDirective.TRAIN_MEMBER
                if weakest.slot == LEAD_SLOT
                else TeamTrainingDirective.SWITCH_TRAINEE
            )
            return TeamTrainingDecision(
                directive,
                f"slot {weakest.slot} is level {weakest.level}, below the level {required} "
                f"needed against opposition at {policy.parity_opposition_level}",
                target_slot=weakest.slot,
            )

    return TeamTrainingDecision(
        TeamTrainingDirective.STOP,
        "final-form roster and workhorse target are complete",
    )


def summarize_team_development(
    party: PartyObservation,
    policy: DevelopedTeamPolicy,
) -> DevelopedTeamReport:
    """Build the final-form and workhorse receipt used by game adapters."""

    workhorse = next(
        (member for member in party.members if member.species_id == policy.workhorse_species_id),
        None,
    )
    return DevelopedTeamReport(
        required_species_ids=policy.roster.species_ids,
        observed_species_ids=party.species_ids(),
        workhorse_species_id=policy.workhorse_species_id,
        workhorse_target_level=policy.workhorse_target_level,
        observed_workhorse_level=workhorse.level if workhorse else None,
        fainted_count=party.fainted_count,
        required_minimum_level=(
            policy.level_parity.required_level(policy.parity_opposition_level)
            if policy.trains_whole_party and policy.level_parity and policy.parity_opposition_level
            else None
        ),
        observed_levels=party.levels,
    )


@dataclass(frozen=True, slots=True)
class TrainingException:
    """A recorded, temporary allowance to proceed while a rule is unmet.

    Progression sometimes has to come before balance—for example when a badge
    is required to reach the only safe training area.  Each allowance carries a
    reason so the deviation appears in evidence instead of silently weakening
    the policy.
    """

    reason: str
    allows_incomplete_party: bool = False
    allows_level_shortfall: bool = False
    allows_level_spread: bool = False

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("a training exception requires a non-empty reason")
        if not any(
            (
                self.allows_incomplete_party,
                self.allows_level_shortfall,
                self.allows_level_spread,
            )
        ):
            raise ValueError("a training exception must allow at least one deviation")


@dataclass(frozen=True, slots=True)
class BalancedTeamPolicy:
    """Stop, safety, balance, and opponent-selection rules for a whole team."""

    minimum_level: int = 50
    maximum_level_spread: int = 5
    required_size: int = PARTY_SLOT_LIMIT
    retreat_hp_ratio: float = 0.45
    reserve_total_pp: int = 2
    safe_lead_level: int | None = None
    max_enemy_level_delta: int = 4
    minimum_direct_level_advantage: int = 0
    max_battles: int = 400
    max_steps: int = 40_000
    max_healing_trips: int = 40
    max_faints: int = 3

    def __post_init__(self) -> None:
        if not MIN_LEVEL < self.minimum_level <= MAX_LEVEL:
            raise ValueError(f"minimum_level must be between 2 and {MAX_LEVEL}")
        if type(self.maximum_level_spread) is not int or self.maximum_level_spread < 0:
            raise ValueError("maximum_level_spread must be a non-negative integer")
        if not 1 <= self.required_size <= PARTY_SLOT_LIMIT:
            raise ValueError(f"required_size must be between 1 and {PARTY_SLOT_LIMIT}")
        if not 0 < self.retreat_hp_ratio < 1:
            raise ValueError("retreat_hp_ratio must be between zero and one")
        for name in (
            "reserve_total_pp",
            "max_enemy_level_delta",
            "minimum_direct_level_advantage",
            "max_battles",
            "max_steps",
            "max_healing_trips",
            "max_faints",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class TeamTrainingProgress:
    """Bounded effort already spent inside one training block."""

    battles_completed: int = 0
    steps_taken: int = 0
    healing_trips: int = 0
    faints: int = 0

    def __post_init__(self) -> None:
        for name in ("battles_completed", "steps_taken", "healing_trips", "faints"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class TeamTrainingDecision:
    """One directive plus the reasoning that produced it."""

    directive: TeamTrainingDirective
    reason: str
    target_slot: int | None = None
    exception_reason: str | None = None

    @property
    def used_exception(self) -> bool:
        """Whether a recorded allowance influenced this decision."""

        return self.exception_reason is not None


@dataclass(frozen=True, slots=True)
class GrindingArea:
    """A candidate training area described by its encounter level band.

    ``maximum_encounter_level`` is what nearly every encounter stays under, not
    the highest level the area can produce.  Those differ, and treating them as
    one rules out good venues: Diglett's Cave was measured at fifteen to
    twenty-one across twenty-nine encounters, with a rare Dugtrio at thirty-one.
    Summarised as "fifteen to thirty-one" it is unusable for the level-twenty
    trainee it in fact suits almost perfectly.  The rare ceiling is recorded
    separately so a caller can see what it is accepting; handling it is the
    escape path's job, which is the job the escape path exists for.
    """

    area_id: str
    minimum_encounter_level: int
    maximum_encounter_level: int
    has_nearby_healer: bool = True
    rare_maximum_encounter_level: int | None = None
    measured_samples: int | None = None

    def __post_init__(self) -> None:
        if not self.area_id.strip():
            raise ValueError("area_id must be a non-empty semantic label")
        for name in ("minimum_encounter_level", "maximum_encounter_level"):
            value = getattr(self, name)
            if type(value) is not int or not MIN_LEVEL <= value <= MAX_LEVEL:
                raise ValueError(f"{name} must be a valid level")
        if self.maximum_encounter_level < self.minimum_encounter_level:
            raise ValueError("maximum_encounter_level cannot be below the minimum")
        rare = self.rare_maximum_encounter_level
        if rare is not None:
            if type(rare) is not int or not MIN_LEVEL <= rare <= MAX_LEVEL:
                raise ValueError("rare_maximum_encounter_level must be a valid level")
            if rare < self.maximum_encounter_level:
                raise ValueError("rare_maximum_encounter_level cannot be below the typical maximum")
        samples = self.measured_samples
        if samples is not None and (type(samples) is not int or samples <= 0):
            raise ValueError("measured_samples must be a positive count when given")

    @property
    def is_measured(self) -> bool:
        """Whether this band came from counted encounters rather than memory."""

        return self.measured_samples is not None

    @property
    def worst_case_encounter_level(self) -> int:
        """The highest level this area is known to be able to field."""

        return self.rare_maximum_encounter_level or self.maximum_encounter_level


@dataclass(frozen=True, slots=True)
class BalancedTeamReport:
    """Portable receipt describing whether a team met the balance contract."""

    required_size: int
    minimum_level: int
    maximum_level_spread: int
    observed_size: int
    observed_minimum_level: int | None
    observed_level_spread: int | None
    fainted_count: int
    exception_reasons: tuple[str, ...] = ()

    @property
    def has_full_party(self) -> bool:
        """Whether every required party position is filled."""

        return self.observed_size >= self.required_size

    @property
    def meets_level_floor(self) -> bool:
        """Whether the weakest member reached the required level."""

        return (
            self.observed_minimum_level is not None
            and self.observed_minimum_level >= self.minimum_level
        )

    @property
    def is_balanced(self) -> bool:
        """Whether the level spread sits inside the allowed maximum."""

        return (
            self.observed_level_spread is not None
            and self.observed_level_spread <= self.maximum_level_spread
        )

    @property
    def passed(self) -> bool:
        """Whether the team satisfies every balance rule with nobody fainted."""

        return (
            self.has_full_party
            and self.meets_level_floor
            and self.is_balanced
            and self.fainted_count == 0
        )


def _member_is_unsafe(
    member: PartyMemberObservation,
    policy: BalancedTeamPolicy,
) -> bool:
    return (
        member.is_fainted
        or member.hp_ratio <= policy.retreat_hp_ratio
        or member.status is not StatusCondition.HEALTHY
        or member.total_pp <= policy.reserve_total_pp
    )


def _exhausted_bound(
    progress: TeamTrainingProgress,
    policy: BalancedTeamPolicy,
) -> str | None:
    if progress.battles_completed >= policy.max_battles:
        return "battle budget exhausted"
    if progress.steps_taken >= policy.max_steps:
        return "step budget exhausted"
    if progress.healing_trips >= policy.max_healing_trips:
        return "healing budget exhausted"
    if progress.faints > policy.max_faints:
        return "faint budget exhausted"
    return None


def plan_team_training(
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    progress: TeamTrainingProgress | None = None,
    exception: TrainingException | None = None,
) -> TeamTrainingDecision:
    """Choose the next semantic action for a balanced-team training block.

    The order of reasoning is deliberate: bounded effort stops the block first,
    an unusable team is restored before anything else, a short roster is filled
    before levels are chased, and a team that already satisfies the contract
    stops instead of grinding for no reason.
    """

    progress = progress or TeamTrainingProgress()
    exhausted = _exhausted_bound(progress, policy)
    if exhausted is not None:
        return TeamTrainingDecision(TeamTrainingDirective.STOP, exhausted)

    if not party.members:
        return TeamTrainingDecision(
            TeamTrainingDirective.RECRUIT_MEMBER,
            "party is empty",
            target_slot=LEAD_SLOT,
        )

    if party.fainted_count or party.is_wiped_out:
        return TeamTrainingDecision(
            TeamTrainingDirective.RESTORE_TEAM,
            f"{party.fainted_count} member(s) fainted"
            if party.fainted_count
            else "no member can currently act",
        )

    if party.size < policy.required_size:
        if exception is None or not exception.allows_incomplete_party:
            return TeamTrainingDecision(
                TeamTrainingDirective.RECRUIT_MEMBER,
                f"party holds {party.size} of {policy.required_size} members",
                target_slot=party.size + 1,
            )
        allowed_incomplete: str | None = exception.reason
    else:
        allowed_incomplete = None

    below_floor = party.members_below_level(policy.minimum_level)
    if below_floor and exception is not None and exception.allows_level_shortfall:
        below_floor = ()
        allowed_shortfall: str | None = exception.reason
    else:
        allowed_shortfall = None

    spread = party.level_spread
    over_spread = spread is not None and spread > policy.maximum_level_spread
    if over_spread and exception is not None and exception.allows_level_spread:
        over_spread = False
        allowed_spread: str | None = exception.reason
    else:
        allowed_spread = None

    granted = next(
        (
            reason
            for reason in (allowed_incomplete, allowed_shortfall, allowed_spread)
            if reason is not None
        ),
        None,
    )

    if not below_floor and not over_spread:
        return TeamTrainingDecision(
            TeamTrainingDirective.STOP,
            "party meets the level floor and spread contract",
            exception_reason=granted,
        )

    trainee = party.weakest_trainable_member
    if trainee is None:
        return TeamTrainingDecision(
            TeamTrainingDirective.RESTORE_TEAM,
            "no member can currently gain experience",
            exception_reason=granted,
        )

    if _member_is_unsafe(trainee, policy):
        return TeamTrainingDecision(
            TeamTrainingDirective.RESTORE_TEAM,
            f"slot {trainee.slot} is not safe to train",
            target_slot=trainee.slot,
            exception_reason=granted,
        )

    if trainee.slot != LEAD_SLOT:
        return TeamTrainingDecision(
            TeamTrainingDirective.SWITCH_TRAINEE,
            f"slot {trainee.slot} is the weakest trainable member",
            target_slot=trainee.slot,
            exception_reason=granted,
        )

    reason = (
        f"slot {trainee.slot} is below the level floor"
        if below_floor
        else f"slot {trainee.slot} trails the party by more than {policy.maximum_level_spread}"
    )
    return TeamTrainingDecision(
        TeamTrainingDirective.TRAIN_MEMBER,
        reason,
        target_slot=trainee.slot,
        exception_reason=granted,
    )


def is_matchup_acceptable(
    trainee: PartyMemberObservation,
    enemy_level: int | None,
    policy: BalancedTeamPolicy,
) -> bool:
    """Whether a trainee should engage an opponent rather than disengage.

    An unknown opponent level is treated as unacceptable so the policy fails
    toward safety instead of gambling on an unobserved encounter.
    """

    if enemy_level is None:
        return False
    if _member_is_unsafe(trainee, policy):
        return False
    if policy.safe_lead_level is not None and trainee.level >= policy.safe_lead_level:
        return True
    safety_ceiling = (
        trainee.level - policy.minimum_direct_level_advantage
        if policy.minimum_direct_level_advantage
        else trainee.level + policy.max_enemy_level_delta
    )
    return enemy_level <= safety_ceiling


def choose_grinding_area(
    areas: Iterable[GrindingArea],
    trainee: PartyMemberObservation,
    policy: BalancedTeamPolicy,
    require_healer: bool = True,
) -> GrindingArea | None:
    """Pick the fastest training area whose encounters stay inside the safety band.

    Areas whose strongest encounter could exceed the trainee's tolerance are
    rejected outright.  Among the safe remainder the highest minimum encounter
    level wins, because it yields the most experience per battle; ties resolve
    on the area label so the choice is reproducible.
    """

    ceiling = trainee.level + policy.max_enemy_level_delta
    safe = [
        area
        for area in areas
        if area.maximum_encounter_level <= ceiling
        and (area.has_nearby_healer or not require_healer)
    ]
    if not safe:
        return None
    return max(safe, key=lambda area: (area.minimum_encounter_level, area.area_id))


def summarize_team_readiness(
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    exception_reasons: Sequence[str] = (),
) -> BalancedTeamReport:
    """Build a portable receipt describing the team against the balance contract."""

    return BalancedTeamReport(
        required_size=policy.required_size,
        minimum_level=policy.minimum_level,
        maximum_level_spread=policy.maximum_level_spread,
        observed_size=party.size,
        observed_minimum_level=party.minimum_level,
        observed_level_spread=party.level_spread,
        fainted_count=party.fainted_count,
        exception_reasons=tuple(exception_reasons),
    )
