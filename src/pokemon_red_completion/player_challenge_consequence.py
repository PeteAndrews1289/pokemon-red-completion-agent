"""One dose then one challenge: a separate target, never atomic goal success.

No temporal-difference targets, counterfactual labels, emulator or automatic fit.
Native admission belongs to the prospective continuous recorder. Synthetic rows
can exercise the numerical seam but cannot acquire native provenance here.
"""

from dataclasses import asdict, dataclass
from math import isfinite
from typing import cast
import time

import numpy as np

from .living_dex_option_value import (
    LivingDexOptionKind,
    _validate_numeric_matrix,
    _validate_numeric_vector,
    option_feature_names,
    project_move_context_features,
)
from .player_consequence_projection import (
    SHARED_CONTEXT, consequence_feature_names, project_consequence_features,
    consequence_normalization_scale, context_projection_metadata,
)
from .provenance import canonical_sha256
from .player_option_level_workload import OptionLevelWorkload

CONSEQUENCE_SCHEMA = "pokemon.player.challenge-consequence.v1"
TARGET_NAMES = (
    "attempted",
    "completed",
    "actions",
    "frames",
    "cash_debits",
    "cash_credits",
    "restorations",
)
# Frozen before collection. No positive reward for merely reaching battle or earning XP.
TARGET_SCALES = (1.0, 1.0, 6000.0, 600000.0, 1500.0, 1500.0, 4.0)
UTILITY = (0.0, 1.0, -0.1, -0.1, -0.25, 0.0, -0.05)
PROGRESS_CONSEQUENCE_SCHEMA = "pokemon.player.challenge-consequence.v2"
WORKLOAD_CONSEQUENCE_SCHEMA = "pokemon.player.challenge-consequence.v3"
MOVE_CHANGE_CONSEQUENCE_SCHEMA = "pokemon.player.challenge-consequence.v4"
MATCHUP_CONSEQUENCE_SCHEMA = "pokemon.player.challenge-consequence.v5"
PROGRESS_TARGET_NAMES = (*TARGET_NAMES, "initial_goal_failed", "challenge_progress")
PROGRESS_TARGET_SCALES = (*TARGET_SCALES, 1.0, 1.0)
# Prospective development feedback, not a rewrite of the frozen v1 experiment.
# Completing a dose alone earns no reward. Unknown battle progress is not invented.
PROGRESS_UTILITY = (*UTILITY, -0.5, 0.25)


def consequence_contract(version):
    if type(version) is not int or version not in (1, 2):
        raise ValueError("unsupported consequence feedback version")
    return (
        (CONSEQUENCE_SCHEMA, TARGET_NAMES, TARGET_SCALES, UTILITY)
        if version == 1
        else (PROGRESS_CONSEQUENCE_SCHEMA, PROGRESS_TARGET_NAMES,
              PROGRESS_TARGET_SCALES, PROGRESS_UTILITY)
    )


def require_digest(value):
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("consequence requires a SHA256 identity")


def _require_feature_version(version):
    if type(version) is not int or version not in (7, 9, 10, 11, 15):
        raise ValueError("consequence requires declared V7, V9, V10, V11 or V15 features")
    return len(option_feature_names(version))


def supports_consequence_preparation(candidate, feature_version):
    """Recognize represented preparation; never invent a level dose for a lesson."""
    return candidate.preparation is not None or (
        feature_version >= 10 and candidate.move_change is not None
    )


def require_preparation_workload(candidate, feature_version):
    """Keep a V9 dose's quoted workload bound to its observed preparation facts."""
    if feature_version >= 10 and candidate.move_change is not None:
        if candidate.preparation is not None or candidate.level_workload is not None:
            raise ValueError("machine preparation cannot borrow a level workload")
        return
    if feature_version in (9, 10, 11, 15) and candidate.features.kind is LivingDexOptionKind.DEVELOP:
        facts = candidate.preparation
        if facts is None or candidate.level_workload != OptionLevelWorkload(
            facts.current_level, facts.target_level, facts.remaining_xp
        ):
            raise ValueError("consequence workload differs from observed preparation")


@dataclass(frozen=True)
class ChallengeConsequence:
    attempted: bool
    completed: bool
    actions: int
    frames: int
    cash_debits: int
    cash_credits: int
    restorations: int
    feedback_version: int = 1
    initial_goal_failed: bool | None = None
    challenge_progress: float | None = None

    def __post_init__(self):
        if (
            type(self.attempted) is not bool
            or type(self.completed) is not bool
            or self.completed
            and not self.attempted
        ):
            raise ValueError("challenge completion requires an actual attempt")
        if any(type(getattr(self, k)) is not int or getattr(self, k) < 0 for k in TARGET_NAMES[2:]):
            raise ValueError("consequence costs must be observed nonnegative integers")
        consequence_contract(self.feedback_version)
        if self.feedback_version == 1:
            if self.initial_goal_failed is not None or self.challenge_progress is not None:
                raise ValueError("legacy consequence cannot borrow new feedback")
        elif (
            type(self.initial_goal_failed) is not bool
            or self.challenge_progress is None
            or type(self.challenge_progress) not in (int, float)
            or not isfinite(self.challenge_progress)
            or not 0 <= self.challenge_progress <= 1
            or self.completed and self.challenge_progress != 1
            or not self.attempted and self.challenge_progress != 0
            or self.initial_goal_failed and self.attempted
        ):
            raise ValueError("progress consequence lacks verified first-phase/battle feedback")

    def document(self):
        names = consequence_contract(self.feedback_version)[1]
        return {name: getattr(self, name) for name in names}

    def vector(self):
        names, scales = consequence_contract(self.feedback_version)[1:3]
        return tuple(
            float(getattr(self, k)) / scale for k, scale in zip(names, scales, strict=True)
        )


@dataclass(frozen=True)
class ConsequenceExample:
    declaration_sha256: str
    source_origin_sha256: str
    features: tuple[float, ...]
    outcome: ChallengeConsequence | None
    censor_reason: str | None
    provenance: str = "synthetic"
    feedback_version: int = 1
    feature_version: int = 7

    def __post_init__(self):
        require_digest(self.declaration_sha256)
        require_digest(self.source_origin_sha256)
        consequence_contract(self.feedback_version)
        width = _require_feature_version(self.feature_version)
        if self.feature_version == 11:
            raise ValueError("V11 consequence fitting projects original V10 rows; raw V11 rows are unsupported")
        if (
            type(self.features) is not tuple
            or len(self.features) != width
            or any(type(v) not in (int, float) or not isfinite(v) for v in self.features)
            or self.provenance not in {"synthetic", "native_train"}
            or (self.outcome is None) != (self.censor_reason is not None)
            or self.outcome is not None
            and type(self.outcome) is not ChallengeConsequence
            or self.outcome is not None and self.outcome.feedback_version != self.feedback_version
        ):
            raise ValueError("consequence example contract differs")

    def document(self):
        values = asdict(self)
        values.pop("feedback_version")
        values.pop("feature_version")
        values["outcome"] = None if self.outcome is None else self.outcome.document()
        if self.feature_version in (9, 10, 15):
            return dict(schema=(MATCHUP_CONSEQUENCE_SCHEMA if self.feature_version == 15 else
                                MOVE_CHANGE_CONSEQUENCE_SCHEMA if self.feature_version == 10
                                else WORKLOAD_CONSEQUENCE_SCHEMA), **values,
                        feature_version=self.feature_version, feedback_version=self.feedback_version)
        return dict(schema=consequence_contract(self.feedback_version)[0], **values)

    @classmethod
    def from_document(cls, document):
        workload = document.get("schema") in {WORKLOAD_CONSEQUENCE_SCHEMA, MOVE_CHANGE_CONSEQUENCE_SCHEMA, MATCHUP_CONSEQUENCE_SCHEMA}
        version = (document.get("feedback_version") if workload else
                   2 if document.get("schema") == PROGRESS_CONSEQUENCE_SCHEMA else 1)
        row = cls(
            document["declaration_sha256"],
            document["source_origin_sha256"],
            tuple(document["features"]),
            None if document["outcome"] is None else ChallengeConsequence(
                **document["outcome"], feedback_version=version),
            document["censor_reason"],
            document["provenance"],
            version,
            document.get("feature_version") if workload else 7,
        )
        if canonical_sha256(row.document()) != canonical_sha256(document):
            raise ValueError("consequence example document differs")
        return row


from .player_preparation_party_context import PARTY_PROJECTION, PreparationPartyCounts, PreparationPartyWitness

@dataclass(frozen=True)
class ConsequencePartyView:
    row: ConsequenceExample
    party_witness: PreparationPartyWitness
    source_context_sha256: str
    source_work_order_sha256: str
    role_evidence: str
    def __post_init__(self):
        if type(self.row) is not ConsequenceExample or self.row.feature_version!=15 or type(self.party_witness) is not PreparationPartyWitness:
            raise ValueError("party context requires an original raw V15 consequence row")
        require_digest(self.source_context_sha256)
        require_digest(self.source_work_order_sha256)
        if self.role_evidence not in {"work_order_context_pin","work_order_complete_four_combat_roster"}:
            raise ValueError("party view role evidence contract differs")
    def document(self):
        return dict(schema="pokemon.player.challenge-consequence-party-view.v1",row=self.row.document(),
            party_witness=self.party_witness.document(),source_context_sha256=self.source_context_sha256,source_work_order_sha256=self.source_work_order_sha256,role_evidence=self.role_evidence)
    @classmethod
    def from_document(cls,document):
        if type(document) is not dict or set(document)!={"schema","row","party_witness","source_context_sha256","source_work_order_sha256","role_evidence"} or document["schema"]!="pokemon.player.challenge-consequence-party-view.v1":
            raise ValueError("party context view schema differs")
        return cls(ConsequenceExample.from_document(document["row"]),PreparationPartyWitness.from_document(document["party_witness"]),document["source_context_sha256"],document["source_work_order_sha256"],document["role_evidence"])


@dataclass(frozen=True)
class ChallengeConsequenceHead:
    """Standalone ridge head; no modification to old models or their scores."""

    coefficients: object
    intercept: object
    feature_mean: object
    feature_scale: object
    evidence_sha256: str
    examples: int
    ridge: float
    provenance: str
    feedback_version: int = 1
    include_recovery_purchases: bool = False
    feature_version: int = 7
    cash_prediction: str = "independent"
    context_projection: str = "identity"

    def __post_init__(self):
        if (type(self.cash_prediction) is not str
                or self.cash_prediction not in {"independent", "certified_single_trainer_v1"}):
            raise ValueError("unsupported consequence cash prediction contract")
        if type(self.include_recovery_purchases) is not bool or (
            self.include_recovery_purchases and self.feedback_version != 2
        ):
            raise ValueError("recovery purchases require an explicit progress-head contract")
        _require_feature_version(self.feature_version)
        if self.context_projection==PARTY_PROJECTION and self.feature_version!=15:
            raise ValueError("party context requires explicit V15 consequence scope")
        width = len(consequence_feature_names(self.feature_version, self.context_projection))
        targets = consequence_contract(self.feedback_version)[1]
        arrays = (
            _validate_numeric_matrix(
                self.coefficients, (width, len(targets)), subject="consequence coefficients"
            ),
            _validate_numeric_vector(self.intercept, len(targets), subject="intercept"),
            _validate_numeric_vector(self.feature_mean, width, subject="mean"),
            _validate_numeric_vector(
                self.feature_scale, width, subject="scale", positive_only=True
            ),
        )
        for name, value in zip(
            ("coefficients", "intercept", "feature_mean", "feature_scale"), arrays, strict=True
        ):
            detached = value.copy()
            detached.setflags(write=False)
            object.__setattr__(self, name, detached)
        require_digest(self.evidence_sha256)
        if (
            type(self.examples) is not int
            or self.examples < 2
            or type(self.ridge) not in (int, float)
            or not isfinite(self.ridge)
            or self.ridge <= 0
            or self.provenance not in {"synthetic", "native_train"}
        ):
            raise ValueError("consequence head evidence differs")

    def predict(self, features, *, single_battle_loss_debit=None, party_context=None):
        x = _validate_numeric_vector(features, len(option_feature_names(self.feature_version)),
                                     subject="features")
        x = np.asarray(project_consequence_features(
            x, feature_version=self.feature_version, context_projection=self.context_projection, party_context=party_context,
        ), dtype=float)
        values = np.maximum(
            0.0, ((x - cast(np.ndarray, self.feature_mean)) / cast(np.ndarray, self.feature_scale))
            @ cast(np.ndarray, self.coefficients) + cast(np.ndarray, self.intercept)
        )
        values[:2] = np.clip(values[:2], 0.0, 1.0)
        values[1] = min(values[0], values[1])
        if self.feedback_version == 2:
            values[7:] = np.clip(values[7:], 0.0, 1.0)
        if single_battle_loss_debit is not None:
            if (self.cash_prediction != "certified_single_trainer_v1"
                    or type(single_battle_loss_debit) is not int
                    or not 0 <= single_battle_loss_debit <= 500000):
                raise ValueError("cash prediction requires a declared single-trainer exposure")
            # Known mechanics, learned attempt/completion probabilities. A free
            # failed lesson does not invent a battle or a blackout. Unknown
            # sequences retain the independently learned measured-debit target.
            values[4] = single_battle_loss_debit * (values[0] - values[1]) / TARGET_SCALES[4]
        return tuple(float(v) for v in values)

    def scores(self, menu, *, challenge_refs, single_battle_loss_debits=None, party_context=None):
        """Explicit homogeneous experiment only; never add duplicate atomic reward.

        Private refs bind alternatives to ONE challenge, not to policy features.
        Scoped provisional runtime adoption remains separate from global policy
        promotion; scoring never fits or opens an execution port.
        """
        available = menu.available_indices
        if single_battle_loss_debits is None:
            single_battle_loss_debits = (None,) * len(menu.candidates)
        if (type(single_battle_loss_debits) is not tuple
                or len(single_battle_loss_debits) != len(menu.candidates)
                or any(v is not None and (
                    self.cash_prediction != "certified_single_trainer_v1"
                    or type(v) is not int or not 0 <= v <= 500000)
                    for v in single_battle_loss_debits)):
            raise ValueError("consequence cash exposures differ from candidates")
        if (
            menu.feature_version not in (6, 7, 9, 10, 15)
            or menu.feature_version > self.feature_version
            or len(challenge_refs) != len(menu.candidates)
            or not available
            or len({challenge_refs[i] for i in available}) != 1
            or any(type(challenge_refs[i]) is not str or not challenge_refs[i] for i in available)
        ):
            raise ValueError("consequence scoring requires one explicit challenge context")
        candidates = [menu.candidates[i] for i in available]
        kinds = {
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.RESTORE,
            LivingDexOptionKind.UNLOCK_ACCESS,
        }
        if self.include_recovery_purchases:
            kinds.add(LivingDexOptionKind.RESUPPLY)
        if any(
            c.features.kind
            not in kinds
            or c.challenge is None
            or (c.features.kind is LivingDexOptionKind.DEVELOP) != supports_consequence_preparation(c, self.feature_version)
            for c in candidates
        ) or any(c.challenge != candidates[0].challenge for c in candidates):
            raise ValueError("consequence comparison requires matching prospective challenge facts")
        for candidate in candidates:
            require_preparation_workload(candidate, self.feature_version)
        return tuple(
            None
            if i not in available
            else sum(
                w * v
                for w, v in zip(
                    consequence_contract(self.feedback_version)[3],
                    self.predict(menu.candidate_vector(i, feature_version=self.feature_version),
                                 single_battle_loss_debit=single_battle_loss_debits[i],party_context=party_context),
                    strict=True
                )
            )
            for i in range(len(menu.candidates))
        )

    def document(self):
        schema, names, scales, utility = consequence_contract(self.feedback_version)
        version = 3 if self.include_recovery_purchases else self.feedback_version
        return dict(
            schema=f"pokemon.player.challenge-consequence-head.v{9 if self.context_projection == PARTY_PROJECTION else 8 if self.feature_version == 15 else 7 if self.context_projection == SHARED_CONTEXT else 6 if self.feature_version == 11 else 5 if self.feature_version == 10 else 4 if self.feature_version == 9 else version}",
            consequence_schema=schema,
            feature_names=list(consequence_feature_names(self.feature_version, self.context_projection)),
            target_names=list(names),
            scales=list(scales),
            utility=list(utility),
            coefficients=cast(np.ndarray, self.coefficients).tolist(),
            intercept=cast(np.ndarray, self.intercept).tolist(),
            feature_mean=cast(np.ndarray, self.feature_mean).tolist(),
            feature_scale=cast(np.ndarray, self.feature_scale).tolist(),
            evidence_sha256=self.evidence_sha256,
            examples=self.examples,
            ridge=self.ridge,
            provenance=self.provenance,
            **({"feature_version": self.feature_version} if self.feature_version in (9, 10, 11, 15) else {}),
            **({"include_recovery_purchases": True} if self.include_recovery_purchases else {}),
            **({"cash_prediction": self.cash_prediction} if self.cash_prediction != "independent" else {}),
            **context_projection_metadata(self.context_projection),
        )

    @property
    def model_sha256(self):
        return canonical_sha256(self.document())

    @classmethod
    def from_document(cls, document, *, expected_sha256):
        if canonical_sha256(document) != expected_sha256:
            raise ValueError("consequence head identity differs")
        head = cls(
            document["coefficients"], document["intercept"], document["feature_mean"],
            document["feature_scale"], document["evidence_sha256"], document["examples"],
            document["ridge"], document["provenance"],
            feedback_version=(2 if document.get("consequence_schema")
                              == PROGRESS_CONSEQUENCE_SCHEMA else 1),
            include_recovery_purchases=document.get("include_recovery_purchases", False),
            feature_version=document.get("feature_version", 7),
            cash_prediction=document.get("cash_prediction", "independent"),
            context_projection=document.get("context_projection", "identity"),
        )
        if head.model_sha256 != expected_sha256:
            raise ValueError("consequence head contract differs")
        return head



def _validate_retained_utility_budget_request(declarations, cap, *,
                                            retention_pairs, utility_absolute_loss):
    """An optional bound on the existing observed TRAIN utility residuals."""
    if type(declarations) is not tuple:
        raise ValueError('retained utility declarations must be an explicit tuple')
    if not declarations and cap is None:
        return False
    if (not declarations or cap is None or not retention_pairs
            or utility_absolute_loss is not True
            or type(cap) not in (int, float) or not isfinite(cap) or cap < 0.):
        raise ValueError('retained utility budget requires explicit rows, finite nonnegative cap and absolute order retention')
    for declaration in declarations:
        require_digest(declaration)
    if len(set(declarations)) != len(declarations):
        raise ValueError('retained utility declarations must be distinct')
    return True


def _fit_order_retained(z, y, pair_indices, utility, ridge=1.0, utility_absolute_loss=False,
                        retained_utility_indices=(), retained_utility_mae_cap=None):
    """Fixed-ridge forecast fit with observed TRAIN utility-order inequalities.

    z is the ordinary fitter's centered/normalized settled input matrix; y is
    its normalized nine-channel target matrix (NaN denotes a missing label).
    Every pair is already oriented (winner, loser) using complete outcomes.
    Return the usual feature-by-channel coefficients and target means.

    The projection basis is orthonormal in coefficient space: if z=U S Vt,
    coefficients=Vt[:rank].T @ theta.  Ridge penalizes theta, not U@theta.
    All public clipping bounds hold on fitted rows, so raw and public scoring
    agree there up to the declared 1e-8 feasibility tolerance.
    """
    from scipy.optimize import LinearConstraint, minimize

    if type(utility_absolute_loss) is not bool:
        raise ValueError('utility absolute loss must be an explicit boolean')
    started = time.monotonic()

    def check_time():
        if time.monotonic() - started > 60.0:
            raise TimeoutError('order-retained fit exceeded 60 numerical seconds')

    def require(ok, message):
        if not ok:
            raise ValueError(message)

    require(type(retained_utility_indices) is tuple,
            'retained utility indices must be an explicit tuple')
    budget_requested = bool(retained_utility_indices) or retained_utility_mae_cap is not None
    if budget_requested:
        require(utility_absolute_loss is True and bool(retained_utility_indices)
                and type(retained_utility_mae_cap) in (int, float)
                and isfinite(retained_utility_mae_cap) and retained_utility_mae_cap >= 0.,
                'retained utility budget requires complete absolute loss and a finite nonnegative cap')
    require(type(ridge) in (int, float) and not isinstance(ridge, bool)
            and ridge == 1.0, 'order retention requires fixed ridge one')
    z = np.asarray(z, dtype=float)
    y = np.asarray(y, dtype=float)
    utility = np.asarray(utility, dtype=float)
    require(z.ndim == 2 and z.shape[0] > 1 and z.shape[1] > 0
            and np.isfinite(z).all(), 'order retention needs finite input rows')
    require(y.shape == (z.shape[0], 9) and not np.isinf(y).any(),
            'order retention needs nine finite-or-missing target channels')
    require(utility.shape == (9,) and np.array_equal(
        utility, np.asarray((0., 1., -.1, -.1, -.25, 0., -.05, -.5, .25))),
        'order retention requires the existing feedback-two utility')
    require(type(pair_indices) is tuple and len(pair_indices) > 0,
            'order retention requires explicit ordered pairs')
    require(np.max(np.abs(np.mean(z, axis=0))) <= 1e-10,
            'order retention requires ordinary centered normalization')
    if budget_requested:
        require(all(type(i) is int and 0 <= i < z.shape[0] for i in retained_utility_indices)
                and len(set(retained_utility_indices)) == len(retained_utility_indices),
                'retained utility indices must be distinct existing rows')
    observed = np.isfinite(y)
    require(np.all(observed.sum(axis=0) >= 2), 'all target channels need two actual labels')
    if utility_absolute_loss:
        require(np.all(observed), 'utility absolute loss requires complete nine-channel targets')
    require(np.all(y[observed] >= 0.), 'negative normalized outcome target')
    probability = (0, 1, 7, 8)
    for channel in probability:
        require(np.all(y[observed[:, channel], channel] <= 1.),
                'outcome probability/progress target exceeds one')
    joint = observed[:, 0] & observed[:, 1]
    require(np.all(y[joint, 1] <= y[joint, 0]),
            'completion target exceeds attempted target')
    ym = np.nanmean(y, axis=0)
    require(np.isfinite(ym).all() and ym[1] <= ym[0],
            'fixed target means cannot satisfy completion bounds')

    pairs = []
    seen = set()
    for pair in pair_indices:
        require(type(pair) is tuple and len(pair) == 2
                and all(type(v) is int and 0 <= v < z.shape[0] for v in pair)
                and pair[0] != pair[1], 'invalid oriented outcome pair')
        key = tuple(sorted(pair))
        require(key not in seen, 'duplicate or inverse outcome pair')
        seen.add(key)
        winner, loser = pair
        require(np.all(observed[[winner, loser]]),
                'ordered outcomes require all nine actual target labels')
        gap = float((y[winner] - y[loser]) @ utility)
        require(np.isfinite(gap) and gap > 0.,
                'ordered pair must agree with observed outcome utility')
        pairs.append((winner, loser, min(.01, .1 * gap)))

    check_time()
    try:
        _, singular, vh = np.linalg.svd(z, full_matrices=False)
    except np.linalg.LinAlgError as exc:
        raise ValueError('order-retained input SVD failed') from exc
    require(np.isfinite(singular).all() and singular.size > 0
            and singular[0] > 0., 'no identifiable order-retention direction')
    ranks = [int(np.count_nonzero(singular > singular[0] * tolerance))
             for tolerance in (1e-12, 1e-10, 1e-8)]
    require(ranks[0] == ranks[1] == ranks[2] and ranks[0] > 0,
            'order-retention input rank is numerically unstable')
    basis = vh[:ranks[0]].T
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        projected = z @ basis
    require(np.isfinite(projected).all(), 'nonfinite order-retention projection')

    # These boundary means, together with centered inputs and fitted-row public
    # bounds, force the predictions to be constant.  A positive constant cost
    # is NOT frozen: pair inequalities can make its variation useful.
    frozen = tuple(channel for channel in range(9)
                   if np.all(observed[:, channel])
                   and np.all(y[:, channel] == ym[channel])
                   and (ym[channel] == 0.
                        or (channel in probability and ym[channel] == 1.)))
    active = tuple(channel for channel in range(9) if channel not in frozen)
    require(len(active) > 0, 'no nonconstant order-retention output direction')
    positions = {channel: position for position, channel in enumerate(active)}
    variables = ranks[0] * len(active)
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        expanded = np.kron(projected, np.eye(len(active)))
    require(np.isfinite(expanded).all(), 'nonfinite order-retention design')

    def design(row, channel):
        if channel not in positions:
            return np.zeros(variables)
        return expanded[row * len(active) + positions[channel]]

    constraints, lower, upper = [], [], []
    for row in range(z.shape[0]):
        for channel in active:
            constraints.append(design(row, channel))
            lower.append(-ym[channel])
            upper.append(1. - ym[channel] if channel in probability else np.inf)
        constraints.append(design(row, 1) - design(row, 0))
        lower.append(-np.inf)
        upper.append(ym[0] - ym[1])
    for winner, loser, margin in pairs:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            contrast = sum((utility[channel]
                            * (design(winner, channel) - design(loser, channel))
                            for channel in active), np.zeros(variables))
        require(np.isfinite(contrast).all() and np.any(contrast != 0.),
                'observed order has no identifiable feature direction')
        constraints.append(contrast)
        lower.append(margin)
        upper.append(np.inf)
    matrix = np.asarray(constraints)
    lb, ub = np.asarray(lower), np.asarray(upper)
    require(np.isfinite(matrix).all()
            and not np.isnan(lb).any() and not np.isnan(ub).any(),
            'nonfinite order-retention linear constraints')

    initial = np.zeros(variables)
    if utility_absolute_loss:
        # Epigraph rows use the same observed utility, not a new reward.
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            utility_rows = np.asarray([
                sum((utility[channel] * design(row, channel) for channel in active),
                    np.zeros(variables))
                for row in range(z.shape[0])])
            utility_offsets = (ym - y) @ utility
        require(np.isfinite(utility_rows).all() and np.isfinite(utility_offsets).all(),
                'nonfinite utility epigraph input')
        identity = np.eye(z.shape[0])
        matrix = np.vstack((
            np.column_stack((matrix, np.zeros((len(matrix), z.shape[0])))),
            np.column_stack((utility_rows, -identity)),
            np.column_stack((-utility_rows, -identity)),
        ))
        lb = np.concatenate((lb, np.full(2 * z.shape[0], -np.inf)))
        ub = np.concatenate((ub, -utility_offsets, utility_offsets))
        initial = np.concatenate((initial, np.abs(utility_offsets)))
        require(np.isfinite(matrix).all() and np.isfinite(initial).all(),
                'nonfinite utility epigraph design')
        if budget_requested:
            # Existing epigraph slacks bound exactly the observed utility MAE.
            # This changes constraints only; the fixed objective is unchanged.
            retained_mean = np.zeros(z.shape[0])
            retained_mean[list(retained_utility_indices)] = 1. / len(retained_utility_indices)
            matrix = np.vstack((matrix, np.concatenate((np.zeros(variables), retained_mean))))
            lb = np.concatenate((lb, [-np.inf]))
            ub = np.concatenate((ub, [retained_utility_mae_cap]))

    def objective(theta_flat):
        check_time()
        theta_values = theta_flat[:variables] if utility_absolute_loss else theta_flat
        theta = theta_values.reshape(ranks[0], len(active))
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            predictions = projected @ theta + ym[list(active)]
            residual = np.where(observed[:, active], predictions - y[:, active], 0.)
            loss = float(np.sum(residual * residual) + ridge * np.sum(theta * theta))
        if utility_absolute_loss:
            with np.errstate(over='raise', invalid='raise'):
                loss += float(np.sum(theta_flat[variables:]))
        require(np.isfinite(loss), 'nonfinite order-retention objective')
        return loss

    def gradient(theta_flat):
        check_time()
        theta_values = theta_flat[:variables] if utility_absolute_loss else theta_flat
        theta = theta_values.reshape(ranks[0], len(active))
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            predictions = projected @ theta + ym[list(active)]
            residual = np.where(observed[:, active], predictions - y[:, active], 0.)
            grad = 2. * (projected.T @ residual + ridge * theta)
        require(np.isfinite(grad).all(), 'nonfinite order-retention gradient')
        if utility_absolute_loss:
            return np.concatenate((grad.reshape(-1), np.ones(z.shape[0])))
        return grad.reshape(-1)

    def callback(_theta):
        check_time()

    check_time()
    result = minimize(objective, initial, method='SLSQP', jac=gradient,
                      constraints=(LinearConstraint(matrix, lb, ub),),
                      callback=callback,
                      options=dict(maxiter=300, ftol=1e-10, disp=False))
    check_time()
    require(result.success and np.isfinite(result.x).all(),
            'order-retention optimization did not converge')
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        values = matrix @ result.x
    require(np.isfinite(values).all()
            and np.all(values >= lb - 1e-8) and np.all(values <= ub + 1e-8),
            'order-retention optimization violates its linear constraints')
    theta_values = result.x[:variables] if utility_absolute_loss else result.x
    theta = theta_values.reshape(ranks[0], len(active))
    coefficients = np.zeros((z.shape[1], 9))
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        coefficients[:, active] = basis @ theta
        fitted = z @ coefficients + ym
    require(np.isfinite(coefficients).all() and np.isfinite(fitted).all(),
            'nonfinite serialized order-retention coefficients')
    require(np.all(fitted >= -1e-8)
            and np.all(fitted[:, probability] <= 1. + 1e-8)
            and np.all(fitted[:, 1] <= fitted[:, 0] + 1e-8),
            'order-retention rowspace reconstruction violates public bounds')
    for winner, loser, margin in pairs:
        require(float((fitted[winner] - fitted[loser]) @ utility) >= margin - 1e-8,
                'order-retention reconstructed utility margin failed')
    if utility_absolute_loss:
        slacks = result.x[variables:]
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            actual_absolute_utility_error = np.abs((fitted - y) @ utility)
            expected_objective = float(np.sum((fitted - y) ** 2)
                                       + ridge * np.sum(theta * theta)
                                       + np.sum(slacks))
        require(np.isfinite(actual_absolute_utility_error).all()
                and np.all(slacks >= -1e-8)
                and np.all(slacks >= actual_absolute_utility_error - 1e-8)
                and np.max(np.abs(slacks - actual_absolute_utility_error)) <= 1e-7,
                'utility epigraph is infeasible or not tight')
        if budget_requested:
            retained = list(retained_utility_indices)
            require(float(np.mean(slacks[retained])) <= retained_utility_mae_cap + 1e-8
                    and float(np.mean(actual_absolute_utility_error[retained]))
                        <= retained_utility_mae_cap + 1e-8,
                    'reconstructed retained utility MAE exceeds its declared budget')
        require(np.isfinite(expected_objective) and np.isfinite(result.fun)
                and abs(float(result.fun) - expected_objective)
                    <= 1e-7 * max(1., abs(expected_objective)),
                'utility epigraph objective readback differs')
    return coefficients, ym


def fit_challenge_consequence(
    rows, *, ridge=1.0, feedback_version=1, include_recovery_purchases=False,
    feature_version=None, cash_prediction="independent", context_projection="identity",
    reference_head=None, retained_rows=(), reference_residual_mode="coordinate_zero",
    retention_pairs=(), utility_absolute_loss=False,
    retained_utility_declarations=(), retained_utility_mae_cap=None,
):
    """Unit-weight prospective teacher lessons, not comparative/IPS labels.

    Native callers must use authenticated recorder loaders. No automatic fit or
    adoption: this numerical function cannot authenticate arbitrary caller rows.
    """
    budget_requested = _validate_retained_utility_budget_request(
        retained_utility_declarations, retained_utility_mae_cap,
        retention_pairs=retention_pairs, utility_absolute_loss=utility_absolute_loss)
    # This opt-in full ridge fit retains TRAIN decision orders, not every old
    # forecast. Pair orientation comes only from the observed fixed utility.
    if type(retention_pairs) is not tuple:
        raise ValueError("consequence retention pairs must be an explicit tuple")
    if retention_pairs and (
        reference_head is not None or retained_rows or reference_residual_mode != "coordinate_zero"
        or feature_version not in (None, 15) or feedback_version != 2
        or context_projection != PARTY_PROJECTION or ridge != 1.0
        or cash_prediction != "independent" or include_recovery_purchases is not False
    ):
        raise ValueError("order retention requires full ridge1 independent V15 PARTY feedback2")
    if type(utility_absolute_loss) is not bool or (utility_absolute_loss and not retention_pairs):
        raise ValueError("absolute utility loss requires explicit order-retention pairs")
    original_rows=tuple(rows)
    retained_original_rows=tuple(retained_rows)
    if (type(reference_residual_mode) is not str
            or reference_residual_mode not in ("coordinate_zero", "affine_nullspace")):
        raise ValueError("unsupported reference consequence residual mode")
    if reference_residual_mode == "affine_nullspace" and (
        reference_head is None or ridge != 1.0 or cash_prediction != "independent"
        or include_recovery_purchases is not False
    ):
        raise ValueError("affine nullspace requires an explicit ridge1 independent reference")
    if reference_head is None and retained_original_rows:
        raise ValueError("retained consequence rows require a reference head")
    if reference_head is not None and (
        type(reference_head) is not ChallengeConsequenceHead or not retained_original_rows
    ):
        raise ValueError("reference consequence fitting requires the original retained rows")
    if reference_head is not None and (
        feature_version not in (None, 15) or feedback_version != 2
        or context_projection != PARTY_PROJECTION
    ):
        raise ValueError("reference consequence residual requires a V15 PARTY progress head")
    party_contexts=None
    if context_projection==PARTY_PROJECTION:
        if not original_rows or any(type(r) is not ConsequencePartyView for r in original_rows):
            raise ValueError("party-context fitting requires explicit authenticated additive views")
        if feature_version not in (None,15):raise ValueError("party views preserve raw V15")
        ordered_views=tuple(sorted(original_rows,key=lambda r:r.row.declaration_sha256))
        party_contexts={r.row.declaration_sha256:r.party_witness.counts for r in ordered_views}
        evidence_documents=[r.document() for r in ordered_views]
        rows=tuple(r.row for r in ordered_views)
    else:
        rows = tuple(sorted(original_rows, key=lambda r: r.declaration_sha256))
        evidence_documents=[r.document() for r in rows]
    target_names = consequence_contract(feedback_version)[1]
    if type(include_recovery_purchases) is not bool or (
        include_recovery_purchases and feedback_version != 2
    ):
        raise ValueError("recovery purchases require an explicit progress-head contract")
    if (
        len(rows) < 2
        or any(type(r) is not ConsequenceExample for r in rows)
        or len({r.declaration_sha256 for r in rows}) != len(rows)
        or len({r.provenance for r in rows}) != 1
        or type(ridge) not in (int, float)
        or not isfinite(ridge)
        or ridge <= 0
        or any(r.feedback_version > feedback_version for r in rows)
    ):
        raise ValueError("consequence fit needs distinct compatible declared lessons")
    if feature_version is None:
        feature_version = max(r.feature_version for r in rows)
    raw_width = _require_feature_version(feature_version)
    width = len(consequence_feature_names(feature_version, context_projection))
    if any(r.feature_version > feature_version for r in rows):
        raise ValueError("consequence fit cannot truncate observed workload features")
    settled = [r for r in rows if r.outcome is not None]
    if len(settled) < 2:
        raise ValueError("consequence fit lacks observed outcomes")
    # Older native rows retain their exact prefix. Appended zeros mean that the
    # newer fields were unobserved; no XP or preparation facts are backfilled.
    def projected(row):
        if feature_version == 15 and row.feature_version < 15:
            # V11 products are derived from recorded V10 facts. Later observed
            # capture/matchup fields remain unknown; never backfill a forecast.
            prefix = row.features + (0.0,) * (len(option_feature_names(10)) - len(row.features))
            derived = project_move_context_features(prefix)
            raw = derived + (0.0,) * (raw_width - len(derived))
            return project_consequence_features(raw, feature_version=feature_version,
                                                context_projection=context_projection)
        if feature_version == 11:
            # Preserve native records; derive only products of their observed
            # V10 facts. Older unknown move blocks remain zero.
            prefix = row.features + (0.0,) * (len(option_feature_names(10)) - len(row.features))
            return project_move_context_features(prefix)
        raw = row.features + (0.0,) * (raw_width - len(row.features))
        return project_consequence_features(raw, feature_version=feature_version,
                                            context_projection=context_projection,party_context=None if party_contexts is None else party_contexts[row.declaration_sha256])
    x = np.asarray([projected(r) for r in settled], dtype=float)
    # Keep every legacy target, without inventing its unavailable progress label.
    y = np.full((len(settled), len(target_names)), np.nan)
    for index, row in enumerate(settled):
        values = row.outcome.vector()
        y[index, :len(values)] = values
    if reference_head is not None:
        # An explicit ridge penalty on a semantic residual, with the original
        # normalizer/intercept fixed. The ordinary full-refit path below stays
        # operation-for-operation unchanged when no reference is supplied.
        if (reference_head.feature_version != feature_version
                or reference_head.feedback_version != feedback_version
                or reference_head.include_recovery_purchases != include_recovery_purchases
                or reference_head.cash_prediction != cash_prediction
                or reference_head.context_projection != context_projection
                or reference_head.ridge != ridge
                or reference_head.provenance != rows[0].provenance):
            raise ValueError("reference consequence fit contract differs")
        expected_type = ConsequencePartyView if context_projection == PARTY_PROJECTION else ConsequenceExample
        if any(type(r) is not expected_type for r in retained_original_rows):
            raise ValueError("reference consequence retained row type differs")
        retained_ordered = tuple(sorted(retained_original_rows, key=lambda r: (
            r.row.declaration_sha256 if context_projection == PARTY_PROJECTION else r.declaration_sha256)))
        retained = tuple(r.row if context_projection == PARTY_PROJECTION else r for r in retained_ordered)
        retained_ids = {r.declaration_sha256 for r in retained}
        retained_documents = [r.document() for r in retained_ordered]
        full_documents = {r.declaration_sha256: canonical_sha256(d)
                          for r, d in zip(rows, evidence_documents, strict=True)}
        if (len(retained_ids) != len(retained)
                or canonical_sha256(retained_documents) != reference_head.evidence_sha256
                or reference_head.examples != sum(r.outcome is not None for r in retained)
                or any(full_documents.get(r.declaration_sha256) != canonical_sha256(d)
                       for r, d in zip(retained, retained_documents, strict=True))):
            raise ValueError("reference consequence original evidence or retained subset differs")
        mean = reference_head.feature_mean
        scale = reference_head.feature_scale
        retained_x = np.asarray([projected(r) for r in retained], dtype=float)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore", under="ignore"):
            z = (x - mean) / scale
            retained_z = (retained_x - mean) / scale
        if not np.isfinite(z).all() or not np.isfinite(retained_z).all():
            raise ValueError("reference consequence normalized inputs are nonfinite")
        new_settled = np.asarray([r.declaration_sha256 not in retained_ids for r in settled], dtype=bool)
        if reference_residual_mode == "affine_nullspace":
            # Separate opt-in contract: preserve affine forecasts to declared
            # tolerances, not P18 coordinate-zero coefficient/prediction bits.
            # Do not center these rows again: the reference intercept is fixed.
            if width != 321 or not np.any(new_settled):
                raise ValueError("affine nullspace requires new settled semantic input")
            try:
                _, singular, vt = np.linalg.svd(retained_z, full_matrices=True)
            except np.linalg.LinAlgError as error:
                raise ValueError("affine nullspace SVD failed") from error
            if (not np.isfinite(singular).all() or not np.isfinite(vt).all()
                    or vt.shape != (width, width)):
                raise ValueError("affine nullspace basis is nonfinite or malformed")
            leading = float(singular[0]) if len(singular) else 0.0
            ranks = tuple(int(np.count_nonzero(singular > leading * relative))
                          for relative in (1e-12, 1e-10, 1e-8))
            if len(set(ranks)) != 1:
                raise ValueError("affine nullspace retained rank is numerically unstable")
            basis = vt[ranks[1]:].T
            if not basis.shape[1]:
                raise ValueError("affine nullspace has no residual dimension")
            with np.errstate(over="ignore", invalid="ignore"):
                retained_basis = retained_z @ basis
                projected_z = z @ basis
                new_norm = np.linalg.norm(z[new_settled], axis=1)
                off_span = np.linalg.norm(projected_z[new_settled], axis=1)
            if (not np.isfinite(retained_basis).all() or not np.isfinite(projected_z).all()
                    or not np.isfinite(new_norm).all() or not np.isfinite(off_span).all()):
                raise ValueError("affine nullspace projected inputs are nonfinite")
            if not np.allclose(retained_basis, 0.0, atol=1e-10, rtol=0.0):
                raise ValueError("affine nullspace retained basis leakage exceeds contract")
            if not np.any(off_span > 1e-10 * np.maximum(1.0, new_norm)):
                raise ValueError("affine nullspace has no identifiable new direction")
            if np.any(np.isfinite(y).sum(axis=0) < 2):
                raise ValueError("consequence fit needs two actual labels per feedback channel")
            coefficients = reference_head.coefficients.copy()
            for column in range(len(target_names)):
                observed = np.isfinite(y[:, column])
                selected = projected_z[observed]
                with np.errstate(over="ignore", invalid="ignore"):
                    residual = y[observed, column] - (
                        z[observed] @ reference_head.coefficients[:, column]
                        + reference_head.intercept[column])
                    gram = selected @ selected.T
                    system = gram + ridge * np.eye(len(selected))
                if (not np.isfinite(residual).all() or not np.isfinite(gram).all()
                        or not np.isfinite(system).all()):
                    raise ValueError("affine nullspace residual system is nonfinite")
                with np.errstate(over="ignore", invalid="ignore"):
                    delta = basis @ (selected.T @ np.linalg.solve(system, residual))
                    coefficients[:, column] += delta
                if not np.isfinite(delta).all() or not np.isfinite(coefficients[:, column]).all():
                    raise ValueError("affine nullspace corrected coefficients are nonfinite")
            candidate = ChallengeConsequenceHead(
                coefficients, reference_head.intercept, mean, scale,
                canonical_sha256(evidence_documents), len(settled), ridge,
                rows[0].provenance, feedback_version, include_recovery_purchases,
                feature_version, cash_prediction, context_projection,
            )
            with np.errstate(over="ignore", invalid="ignore"):
                before_affine = retained_z @ reference_head.coefficients + reference_head.intercept
                after_affine = retained_z @ candidate.coefficients + candidate.intercept
            if (not np.isfinite(before_affine).all() or not np.isfinite(after_affine).all()
                    or not np.allclose(before_affine, after_affine, atol=1e-10, rtol=0.0)):
                raise ValueError("affine nullspace retained affine output leakage exceeds contract")
            # These are real public linear-prediction calls. A paid native-TRAIN
            # worker must meter 2*len(retained) here plus its external readback.
            def public_outputs(head):
                return np.asarray([
                    head.predict(r.features, party_context=party_contexts[r.declaration_sha256])
                    for r in retained
                ], dtype=float)
            before_public = public_outputs(reference_head)
            after_public = public_outputs(candidate)
            if (not np.isfinite(before_public).all() or not np.isfinite(after_public).all()
                    or not np.allclose(before_public, after_public, atol=1e-10, rtol=0.0)):
                raise ValueError("affine nullspace retained public output leakage exceeds contract")
            utility = np.asarray(consequence_contract(feedback_version)[3], dtype=float)
            if not np.allclose(before_public @ utility, after_public @ utility,
                               atol=1e-6, rtol=0.0):
                raise ValueError("affine nullspace retained utility leakage exceeds contract")
            return candidate
        # Compare before division too: a tiny nonzero numerator must not become
        # an eligible apparent zero through floating-point underflow.
        eligible = (np.all(retained_x == mean, axis=0)
                    & np.all(retained_z == 0.0, axis=0)
                    & np.any(z[new_settled] != 0.0, axis=0))
        if not np.any(eligible):
            raise ValueError("reference consequence has no new semantic zero-basis support")
        if np.any(np.isfinite(y).sum(axis=0) < 2):
            raise ValueError("consequence fit needs two actual labels per feedback channel")
        coefficients = reference_head.coefficients.copy()
        for column in range(len(target_names)):
            observed = np.isfinite(y[:, column])
            selected = z[observed][:, eligible]
            with np.errstate(over="ignore", invalid="ignore"):
                residual = y[observed, column] - (
                    z[observed] @ reference_head.coefficients[:, column]
                    + reference_head.intercept[column])
            if not np.isfinite(residual).all():
                raise ValueError("reference consequence affine residual is nonfinite")
            with np.errstate(over="ignore", invalid="ignore"):
                gram = selected @ selected.T
                system = gram + ridge * np.eye(len(selected))
            if not np.isfinite(gram).all() or not np.isfinite(system).all():
                raise ValueError("reference consequence residual Gram system is nonfinite")
            with np.errstate(over="ignore", invalid="ignore"):
                delta = selected.T @ np.linalg.solve(system, residual)
            if not np.isfinite(delta).all():
                raise ValueError("reference consequence residual solution is nonfinite")
            coefficients[eligible, column] += delta
        if not np.isfinite(coefficients).all():
            raise ValueError("reference consequence corrected coefficients are nonfinite")
        return ChallengeConsequenceHead(
            coefficients, reference_head.intercept, mean, scale,
            canonical_sha256(evidence_documents), len(settled), ridge,
            rows[0].provenance, feedback_version, include_recovery_purchases,
            feature_version, cash_prediction, context_projection,
        )
    mean = x.mean(axis=0)
    scale = consequence_normalization_scale(
        x, feature_version=feature_version, context_projection=context_projection,
    )
    z = (x - mean) / scale
    if retention_pairs:
        by_id = {view.row.declaration_sha256: view for view in original_rows}
        settled_index = {row.declaration_sha256: index for index, row in enumerate(settled)}
        seen = set()
        oriented = []
        utility = np.asarray(consequence_contract(feedback_version)[3], dtype=float)
        for pair in retention_pairs:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError("retention pair requires two explicit declaration identities")
            left, right = pair
            require_digest(left)
            require_digest(right)
            identity = tuple(sorted(pair))
            if left == right or identity in seen or any(k not in settled_index for k in pair):
                raise ValueError("retention pair is repeated, missing or unsettled")
            seen.add(identity)
            a, b = by_id[left], by_id[right]
            if (a.row.feedback_version != 2 or b.row.feedback_version != 2
                    or a.row.source_origin_sha256 != b.row.source_origin_sha256
                    or a.source_context_sha256 != b.source_context_sha256
                    or a.party_witness.document() != b.party_witness.document()):
                raise ValueError("retention pair must share its original source and context")
            i, j = settled_index[left], settled_index[right]
            gap = float((y[i] - y[j]) @ utility)
            if not isfinite(gap) or abs(gap) <= 1e-8:
                raise ValueError("retention pair lacks an informative observed utility order")
            oriented.append((i, j) if gap > 0 else (j, i))
        if budget_requested:
            if (rows[0].provenance != 'native_train'
                    or any(k not in settled_index for k in retained_utility_declarations)):
                raise ValueError('retained utility budget requires distinct settled native TRAIN declarations')
            retained_indices = tuple(sorted(settled_index[k] for k in retained_utility_declarations))
        if utility_absolute_loss:
            if budget_requested:
                coefficients, ym = _fit_order_retained(
                    z, y, tuple(sorted(oriented)), utility, ridge=ridge, utility_absolute_loss=True,
                    retained_utility_indices=retained_indices,
                    retained_utility_mae_cap=retained_utility_mae_cap)
            else:
                coefficients, ym = _fit_order_retained(
                    z, y, tuple(sorted(oriented)), utility, ridge=ridge, utility_absolute_loss=True)
        else:
            coefficients, ym = _fit_order_retained(z, y, tuple(sorted(oriented)), utility, ridge=ridge)
        return ChallengeConsequenceHead(
            coefficients, ym, mean, scale, canonical_sha256(evidence_documents),
            len(settled), ridge, rows[0].provenance, feedback_version,
            include_recovery_purchases, feature_version, cash_prediction, context_projection,
        )
    # Dual ridge avoids solving a hundreds-wide matrix for a small declared batch.
    if feedback_version == 1:
        # Preserve the legacy numerical operation and resulting frozen identity.
        ym = y.mean(axis=0)
        coefficients = z.T @ np.linalg.solve(z @ z.T + ridge * np.eye(len(z)), y - ym)
    else:
        if np.any(np.isfinite(y).sum(axis=0) < 2):
            raise ValueError("consequence fit needs two actual labels per feedback channel")
        ym = np.nanmean(y, axis=0)
        coefficients = np.zeros((x.shape[1], len(target_names)))
        for column in range(len(target_names)):
            observed = np.isfinite(y[:, column])
            selected = z[observed]
            coefficients[:, column] = selected.T @ np.linalg.solve(
                selected @ selected.T + ridge * np.eye(len(selected)),
                y[observed, column] - ym[column],
            )
    return ChallengeConsequenceHead(
        coefficients,
        ym,
        mean,
        scale,
        canonical_sha256(evidence_documents),
        len(settled),
        ridge,
        rows[0].provenance,
        feedback_version,
        include_recovery_purchases,
        feature_version,
        cash_prediction,
        context_projection,
    )
