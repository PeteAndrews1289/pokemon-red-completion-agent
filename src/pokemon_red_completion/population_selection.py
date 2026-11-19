"""Small population fitness selection on matched TRAIN outcomes.

This is an optimizer-side comparison,never a player policy or admission API.
Callers independently authenticate native evidence before constructing trials.
Selecting parents is training,including when no gradient optimizer runs.
"""

import math
import random
import re
from dataclasses import dataclass, replace

from .provenance import canonical_sha256

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")


@dataclass(frozen=True)
class PopulationMember:
    member_id: str
    component: str
    model_sha256: str
    generation: int
    baseline: bool = False

    def __post_init__(self):
        if (
            not _NAME.fullmatch(self.member_id)
            or self.component not in {"goal", "venue"}
            or not _SHA.fullmatch(self.model_sha256)
            or type(self.generation) is not int
            or self.generation < 0
            or type(self.baseline) is not bool
        ):
            raise ValueError("invalid population member")


@dataclass(frozen=True)
class PopulationTrial:
    member_id: str
    case_id: str
    source_state_sha256: str
    seed: int
    objective_sha256: str
    protocol_sha256: str
    runtime_sha256: str
    native_audit_sha256: str
    partition: str
    completed: bool
    safe_terminal: bool
    native_verified: bool
    execution_error: bool
    frames: int
    inputs: int
    heals: int
    cash_debits: int
    target_xp: int | None = None
    other_party_xp: int | None = None

    def __post_init__(self):
        if self.partition != "train":
            raise ValueError("population parent selection is TRAIN;DEV/test cannot select parents")
        if not _NAME.fullmatch(self.member_id) or not _NAME.fullmatch(self.case_id):
            raise ValueError("invalid population trial identity")
        for value in (
            self.source_state_sha256,
            self.objective_sha256,
            self.protocol_sha256,
            self.runtime_sha256,
            self.native_audit_sha256,
        ):
            if not _SHA.fullmatch(value):
                raise ValueError("population trial needs exact provenance and audit hashes")
        for value in (self.seed, self.frames, self.inputs, self.heals, self.cash_debits):
            if type(value) is not int or value < 0:
                raise ValueError("population costs and seed must be observed nonnegative integers")
        for value in (self.target_xp, self.other_party_xp):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("unknown XP stays unknown;observed XP must be nonnegative")
        for value in (
            self.completed,
            self.safe_terminal,
            self.native_verified,
            self.execution_error,
        ):
            if type(value) is not bool:
                raise ValueError("population outcome facts must be explicit booleans")
        if self.completed and (self.execution_error or not self.safe_terminal):
            raise ValueError("unsafe or execution-error trial cannot claim task completion")

    @property
    def matched_case(self):
        return (
            self.case_id,
            self.source_state_sha256,
            self.seed,
            self.objective_sha256,
            self.protocol_sha256,
            self.runtime_sha256,
        )


def select_population_parents(members, trials, *, parent_count=2, minimum_cases=2):
    """Retain multiple reliable completers,then rank full native frame cost.

    Every member must face the same complete cohort. Incomplete/failed costs
    remain in the report but cannot win by quitting early. Distinct native
    source states are required;changing seed labels on one snapshot does not
    establish repeated cartridge evidence. Related states are not independent
    origins. Selection never adopts a runtime model or changes the baseline.
    """
    members, trials = tuple(members), tuple(trials)
    if not 2 <= len(members) <= 8 or any(type(x) is not PopulationMember for x in members):
        raise ValueError("small population needs2to8typed members")
    if (
        len({m.member_id for m in members}) != len(members)
        or len({m.model_sha256 for m in members}) != len(members)
        or len({m.component for m in members}) != 1
        or len({m.generation for m in members}) != 1
        or sum(m.baseline for m in members) != 1
        or type(parent_count) is not int
        or not 1 <= parent_count <= len(members)
        or type(minimum_cases) is not int
        or minimum_cases < 2
    ):
        raise ValueError("population identities,baseline or cohort policy differ")
    grouped = {m.member_id: {} for m in members}
    for trial in trials:
        if type(trial) is not PopulationTrial or trial.member_id not in grouped:
            raise ValueError("population trial lacks a declared member")
        if trial.matched_case in grouped[trial.member_id]:
            raise ValueError("duplicate population trial is not another fitness observation")
        grouped[trial.member_id][trial.matched_case] = trial
    reference = set(next(iter(grouped.values())))
    if (
        len(reference) < minimum_cases
        or len({key[1] for key in reference}) < minimum_cases
        or any(set(rows) != reference for rows in grouped.values())
    ):
        raise ValueError("fitness needs matched cohorts with distinct native sources")
    ranking = []
    for member in members:
        rows = tuple(grouped[member.member_id].values())

        def known_sum(name, observations=rows):
            if all(getattr(row, name) is not None for row in observations):
                return sum(getattr(row, name) for row in observations)
            return None

        ranking.append(
            dict(
                member_id=member.member_id,
                model_sha256=member.model_sha256,
                cases=len(rows),
                completed_cases=sum(row.completed for row in rows),
                execution_errors=sum(row.execution_error for row in rows),
                eligible_parent=all(
                    row.completed
                    and row.safe_terminal
                    and row.native_verified
                    and not row.execution_error
                    for row in rows
                ),
                total_frames=sum(row.frames for row in rows),
                total_inputs=sum(row.inputs for row in rows),
                total_heals=sum(row.heals for row in rows),
                total_cash_debits=sum(row.cash_debits for row in rows),
                target_xp=known_sum("target_xp"),
                other_party_xp=known_sum("other_party_xp"),
                native_audits=sorted(row.native_audit_sha256 for row in rows),
            )
        )
    ranking.sort(
        key=lambda row: (
            not row["eligible_parent"],
            -row["completed_cases"],
            row["execution_errors"],
            row["total_frames"] if row["eligible_parent"] else 0,
            row["total_inputs"] if row["eligible_parent"] else 0,
            row["member_id"],
        )
    )
    parents = [row["member_id"] for row in ranking if row["eligible_parent"]][:parent_count]
    report = dict(
        schema="pokemon.small-population-selection.v1",
        component=members[0].component,
        generation=members[0].generation,
        ranking=ranking,
        parents=parents,
        baseline_retained=next(m.member_id for m in members if m.baseline),
        selection_is_training=True,
        automatic_runtime_adoption=False,
        no_qualified_parents=not parents,
        minimum_cases=minimum_cases,
        matched_cases=len(reference),
        distinct_source_states=len({key[1] for key in reference}),
        independent_origins_not_inferred=True,
    )
    report["selection_sha256"] = canonical_sha256(report)
    return report


def propose_sequence_offspring(parent, *, seed, relative_scale=0.02):
    """Propose symmetric parameter noise;this is not a fitted or adopted head.

    The external proposal receipt must accompany the ordinary head format.
    Ancestor sample counts describe only its original fit. Unknown channels,
    normalization,features,horizon,utility and sampler are never invented here.
    New native TRAIN fitness is required before selecting this proposal.
    """
    from .player_sequence_value import SequenceValueHead

    if (
        type(parent) is not SequenceValueHead
        or type(seed) is not int
        or not 0 <= seed < 2**64
        or type(relative_scale) not in (int, float)
        or not math.isfinite(relative_scale)
        or not 0 < relative_scale <= 0.1
    ):
        raise ValueError("invalid bounded sequence mutation proposal")
    rng = random.Random(seed)
    parameters = []
    for row in parent.parameters:
        if row is None:
            parameters.append(None)
            continue
        scale = relative_scale * max(math.sqrt(sum(v * v for v in row) / len(row)), 1e-6)
        parameters.append(tuple(v + rng.gauss(0, scale) for v in row))
    child = replace(parent, parameters=tuple(parameters))
    if child.model_sha256 == parent.model_sha256:
        raise ValueError("mutation proposal did not change parameters")
    proposal = dict(
        schema="pokemon.sequence-population-parameter-proposal.v1",
        parent_sha256=parent.model_sha256,
        head_sha256=child.model_sha256,
        seed=seed,
        relative_scale=relative_scale,
        mutation="independent-symmetric-Gaussian-per-known-channel-RMS-v1",
        unfitted_search_proposal=True,
        new_TRAIN_rows=0,
        optimizer_fit_calls=0,
        ancestor_dataset_sha256=parent.dataset_sha256,
        ancestor_sample_counts=list(parent.sample_counts),
        sample_counts_are_ancestral_not_new_evidence=True,
        unsupported_channels_unchanged=True,
        fitness_selection_pending=True,
        runtime_adopted=False,
    )
    return child, proposal
