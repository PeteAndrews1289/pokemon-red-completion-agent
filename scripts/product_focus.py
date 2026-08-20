"""Machine-checked product focus for the cross-game Pokemon agent.

The JSON contract is the single editable source.  ``ACTIVE_PRODUCT_STATE.md`` and the
view-only focus dashboard are projections of it.  Keeping parsing, validation and rendering in
one small ROM-free module makes a stale or weakened focus declaration fail CI instead of becoming
another contradictory handoff section.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOCUS_CONFIG = PROJECT_ROOT / "configs" / "active-product-focus.json"
DEFAULT_FOCUS_DOCUMENT = PROJECT_ROOT / "ACTIVE_PRODUCT_STATE.md"
FOCUS_SCHEMA = "pokemon.product-focus.v3"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_LANE_KINDS = {"learning", "maintenance"}
_RIGOR_TIERS = {"development", "benchmark", "sealed"}
_OUTPUT_KINDS = {
    "atomic_goal_episode",
    "authority_promotion",
    "causal_train_example",
    "composition_attempt",
    "development_episode",
    "model_fit",
    "outcome_question",
    "synthetic_rootless_atomic_goal_episode",
    "synthetic_rootless_train_outcome",
    "transfer_result",
    "unseen_comparison",
    "verified_composition_episode",
    "verified_outcome_example",
}
_REORIENTATION_EVIDENCE_KINDS = _OUTPUT_KINDS | {"qualification"}
_OUTPUT_PARTITIONS = {"development", "none", "train", "transfer"}
_REQUIRED_DEVELOPMENT_PROHIBITIONS = {
    "consumed_trial_retry",
    "crystal_execution",
    "full_game_replay",
    "sealed_red_evaluation",
    "teacher_route_hardening",
}
_REQUIRED_STATUS_FIELDS = {
    "active_lane",
    "authority_delta",
    "blocker",
    "current_counters",
    "learning_output",
    "next_decision",
    "product_goal",
    "stop_condition",
    "time_box",
    "transfer_result",
}


class ProductFocusError(ValueError):
    """Raised when the active product contract is missing, stale or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class ProductFocusState:
    """Validated focus state with the one active lane selected."""

    document: Mapping[str, object]
    active_lane: Mapping[str, object]
    retired_lanes: tuple[Mapping[str, object], ...]

    @property
    def product(self) -> Mapping[str, object]:
        return _mapping(self.document, "product", subject="product focus")

    @property
    def progress(self) -> Mapping[str, object]:
        return _mapping(self.active_lane, "progress", subject="active lane")

    @property
    def measurable_outputs(self) -> tuple[Mapping[str, object], ...]:
        return tuple(
            _mapping_value(value, subject="measurable output")
            for value in _sequence(
                self.active_lane,
                "measurable_outputs",
                subject="active lane",
            )
        )


def canonical_focus_json(document: Mapping[str, object]) -> bytes:
    """Return the review-friendly canonical bytes required for the tracked contract."""

    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def load_product_focus(
    path: Path = DEFAULT_FOCUS_CONFIG,
    *,
    project_root: Path = PROJECT_ROOT,
) -> ProductFocusState:
    """Load canonical unique-key JSON and validate every focus invariant."""

    try:
        payload = path.read_bytes()
    except OSError:
        raise ProductFocusError("active product focus config is unavailable") from None
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError("active product focus config is invalid JSON") from None
    if not isinstance(value, dict):
        raise ProductFocusError("active product focus config must be an object")
    if payload != canonical_focus_json(value):
        raise ProductFocusError("active product focus config is not canonical JSON")
    return validate_product_focus_document(value, project_root=project_root)


def validate_product_focus_document(
    document: Mapping[str, object],
    *,
    project_root: Path | None = None,
) -> ProductFocusState:
    """Validate product, lane, rigor, budget, alarm, evidence and reporting contracts."""

    _require_keys(
        document,
        {
            "alarms",
            "lanes",
            "product",
            "review_roles",
            "rigor_policy",
            "schema",
            "session_budget_percent",
            "status_report",
        },
        subject="product focus",
    )
    if document.get("schema") != FOCUS_SCHEMA:
        raise ProductFocusError("active product focus schema is unsupported")
    _validate_product(_mapping(document, "product", subject="product focus"))

    lanes = tuple(
        _mapping_value(value, subject="focus lane")
        for value in _sequence(document, "lanes", subject="product focus")
    )
    if not lanes:
        raise ProductFocusError("product focus must declare at least one lane")
    lane_ids: set[str] = set()
    active: list[Mapping[str, object]] = []
    retired: list[Mapping[str, object]] = []
    for lane in lanes:
        lane_id = _identifier(lane, "id", subject="focus lane")
        if lane_id in lane_ids:
            raise ProductFocusError("focus lane identifiers must be unique")
        lane_ids.add(lane_id)
        status = _text(lane, "status", subject="focus lane")
        if status == "active":
            _validate_active_lane(lane)
            active.append(lane)
        elif status == "retired":
            _validate_retired_lane(lane)
            retired.append(lane)
        else:
            raise ProductFocusError("focus lane status must be active or retired")
    if len(active) != 1:
        raise ProductFocusError("product focus must contain exactly one active lane")

    _validate_rigor_policy(_mapping(document, "rigor_policy", subject="product focus"))
    _validate_session_budget(_mapping(document, "session_budget_percent", subject="product focus"))
    _validate_alarms(_mapping(document, "alarms", subject="product focus"))
    _validate_status_report(_mapping(document, "status_report", subject="product focus"))
    _validate_review_roles(_mapping(document, "review_roles", subject="product focus"))
    _validate_progress_evidence(active[0], project_root=project_root)
    return ProductFocusState(document, active[0], tuple(retired))


def focus_progress_fraction(state: ProductFocusState) -> float:
    """Return the mean capped completion fraction across declared learning outputs."""

    progress = state.progress
    fractions: list[float] = []
    for output in state.measurable_outputs:
        minimum = _positive_int(output, "minimum", subject="measurable output")
        current = _current_output_count(progress, output)
        fractions.append(min(current / minimum, 1.0))
    return sum(fractions) / len(fractions) if fractions else 0.0


def focus_scorecard(state: ProductFocusState) -> tuple[tuple[str, int, int], ...]:
    """Return human-readable current/minimum rows in their declared order."""

    rows: list[tuple[str, int, int]] = []
    for output in state.measurable_outputs:
        kind = _text(output, "kind", subject="measurable output")
        partition = _text(output, "partition", subject="measurable output")
        minimum = _positive_int(output, "minimum", subject="measurable output")
        label = kind.replace("_", " ").title()
        if partition != "none":
            label = f"{label} · {partition}"
        rows.append((label, _current_output_count(state.progress, output), minimum))
    return tuple(rows)


def render_product_focus_markdown(state: ProductFocusState) -> str:
    """Render the one-page human source of current product truth."""

    product = state.product
    lane = state.active_lane
    authority = _mapping(lane, "learned_authority", subject="active lane")
    time_box = _mapping(lane, "time_box", subject="active lane")
    time_box_sessions = _positive_int(time_box, "maximum_sessions", subject="time box")
    time_box_session_label = "session" if time_box_sessions == 1 else "sessions"
    progress = state.progress
    reorientation = _mapping(
        lane,
        "latest_reorientation",
        subject="active lane",
    )
    reorientation_evidence = _mapping(
        reorientation,
        "evidence",
        subject="latest reorientation",
    )
    reorientation_evidence_kind = _text(
        reorientation_evidence,
        "kind",
        subject="reorientation evidence",
    ).replace("_", " ")
    reorientation_evidence_path = _text(
        reorientation_evidence,
        "path",
        subject="reorientation evidence",
    )
    budgets = _mapping(
        state.document,
        "session_budget_percent",
        subject="product focus",
    )
    alarms = _mapping(state.document, "alarms", subject="product focus")
    rigor = _mapping(state.document, "rigor_policy", subject="product focus")
    roles = _mapping(state.document, "review_roles", subject="product focus")
    status = _mapping(state.document, "status_report", subject="product focus")
    data_budget = _count(budgets, "data_and_scenarios", subject="session budget")
    model_budget = _count(budgets, "model_and_evaluation", subject="session budget")
    maintenance_budget = _count(budgets, "maintenance_and_docs", subject="session budget")
    session_alarm = _count(
        alarms,
        "maximum_sessions_without_measured_learning_output",
        subject="alarms",
    )
    ci_alarm = _count(alarms, "maximum_consecutive_ci_only_repairs", subject="alarms")
    lines = [
        "<!-- Generated from configs/active-product-focus.json by scripts/product_focus.py. -->",
        "<!-- Edit the JSON source, then run scripts/check_product_focus.py. -->",
        "# Active product state",
        "",
        "This is the compact answer to **what are we building, what are we doing now, and what",
        (
            "evidence must exist before we move on?** It is subordinate only to "
            "[MISSION.md](MISSION.md)"
        ),
        "and [NORTH_STAR.md](NORTH_STAR.md). Older roadmap and handoff sections are history when",
        "they conflict with this page.",
        "",
        "## Product",
        "",
        _text(product, "goal", subject="product"),
        "",
        f"**Environment role:** {_text(product, 'environment_role', subject='product')}",
        "",
        "Success means:",
        "",
    ]
    lines.extend(
        f"- {item}" for item in _text_sequence(product, "success_conditions", subject="product")
    )
    lines.extend(
        [
            "",
            "Not the product:",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in _text_sequence(product, "non_goals", subject="product"))
    lines.extend(
        [
            "",
            "## One active lane",
            "",
            f"**{_text(lane, 'name', subject='active lane')}** "
            f"(`{_identifier(lane, 'id', subject='active lane')}`)",
            "",
            f"- Kind: **{_text(lane, 'kind', subject='active lane')}**",
            f"- Rigor: **{_text(lane, 'rigor', subject='active lane')}**",
            f"- Next decision: {_text(lane, 'next_decision', subject='active lane')}",
            "",
            "### Mandatory mission check",
            "",
            "| Question | Current answer |",
            "| --- | --- |",
            _table_row("Reusable capability", _text(lane, "capability", subject="active lane")),
            _table_row(
                "Authority now",
                _text(authority, "current", subject="learned authority"),
            ),
            _table_row(
                "Authority target",
                _text(authority, "target", subject="learned authority"),
            ),
            _table_row("Transfer test", _text(lane, "transfer_test", subject="active lane")),
            _table_row(
                "Cheapest falsifier",
                _text(lane, "cheapest_falsifier", subject="active lane"),
            ),
            (
                f"| Time box | {time_box_sessions} {time_box_session_label} / "
                f"{_positive_int(time_box, 'maximum_hours', subject='time box')} hours |"
            ),
            "",
            "### Required learning outputs",
            "",
            "| Output | Current | Minimum for the next decision |",
            "| --- | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {label} | {current} | {minimum} |" for label, current, minimum in focus_scorecard(state)
    )
    lines.extend(
        [
            "",
            "Each counter changes only when tracked, path-free evidence supports it.",
            (
                "Infrastructure, preflights, teacher runs, CI passes, and frozen inputs are not "
                "learning"
            ),
            "outputs.",
            "",
            "### Latest session reorientation",
            "",
            (
                f"**{_text(reorientation, 'session_id', subject='latest reorientation')}** · "
                f"status **{_text(reorientation, 'status', subject='latest reorientation')}** · "
                f"evidence [{reorientation_evidence_kind}]({reorientation_evidence_path})"
            ),
            "",
            "| Check | Session conclusion |",
            "| --- | --- |",
            _table_row(
                "Product alignment",
                _text(reorientation, "product_alignment", subject="latest reorientation"),
            ),
            _table_row(
                "Learning output",
                _text(reorientation, "learning_output", subject="latest reorientation"),
            ),
            _table_row(
                "Authority delta",
                _text(reorientation, "authority_delta", subject="latest reorientation"),
            ),
            _table_row(
                "Transfer result",
                _text(reorientation, "transfer_result", subject="latest reorientation"),
            ),
            _table_row(
                "Blocker",
                _text(reorientation, "blocker", subject="latest reorientation"),
            ),
            _table_row(
                "Decision",
                _text(reorientation, "decision", subject="latest reorientation"),
            ),
            _table_row(
                "Next session",
                _text(reorientation, "next_session_goal", subject="latest reorientation"),
            ),
            _table_row(
                "Next falsifier",
                _text(reorientation, "next_falsifier", subject="latest reorientation"),
            ),
            _table_row(
                "Stop condition",
                _text(reorientation, "stop_condition", subject="latest reorientation"),
            ),
            "",
            "### Stop conditions",
            "",
        ]
    )
    lines.extend(
        f"- {item}" for item in _text_sequence(lane, "stop_conditions", subject="active lane")
    )
    lines.extend(
        [
            "",
            "### Hard boundaries for this lane",
            "",
        ]
    )
    lines.extend(
        f"- **Prohibited:** {item.replace('_', ' ')}"
        for item in _text_sequence(lane, "prohibited_actions", subject="active lane")
    )
    lines.extend(
        [
            "",
            "## Rigor belongs to the risk",
            "",
            (
                "| Tier | Repeatable | Per-case owner authorization | Exact source/CI binding | "
                "External review |"
            ),
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for tier in ("development", "benchmark", "sealed"):
        policy = _mapping(rigor, tier, subject="rigor policy")
        lines.append(
            "| "
            f"{tier.title()} | {_yes_no(_bool(policy, 'repeatable', subject=tier))} | "
            f"{_yes_no(_bool(policy, 'owner_authorization_per_case', subject=tier))} | "
            f"{_yes_no(_bool(policy, 'exact_source_ci_binding', subject=tier))} | "
            f"{_text(policy, 'external_review', subject=tier).replace('_', ' ')} |"
        )
    lines.extend(
        [
            "",
            "Development is the fast learning loop. Benchmark and sealed rigor are reserved for",
            "claims that justify their cost; they must not be copied into routine data generation.",
            "",
            "## Session allocation and alarms",
            "",
            f"- **{data_budget}%** data and scenarios",
            f"- **{model_budget}%** model and evaluation",
            f"- **{maintenance_budget}%** maintenance and documentation",
            "",
            (
                "Stop and reassess after **"
                f"{session_alarm}"
                "** session without a measured learning output, after **"
                f"{ci_alarm}** consecutive CI-only repair, or before any full replay. Repeated "
                "fixed-route patches"
            ),
            "and unmeasured teacher-label copying are also hard alarms.",
            "",
            "## Reviewer use",
            "",
            f"- **Codex:** {_text(roles, 'codex', subject='review roles')}",
            f"- **Claude:** {_text(roles, 'claude', subject='review roles')}",
            f"- **Antigravity:** {_text(roles, 'antigravity', subject='review roles')}",
            "",
            "## Retired leading edges",
            "",
        ]
    )
    for retired in state.retired_lanes:
        lines.append(
            f"- **{_text(retired, 'name', subject='retired lane')}:** "
            f"{_text(retired, 'reason', subject='retired lane')} Evidence is preserved; retry is "
            f"{_yes_no(_bool(retired, 'retry_allowed', subject='retired lane')).lower()}."
        )
    lines.extend(
        [
            "",
            "## Required status report",
            "",
            f"Counter source: {_text(status, 'counter_source', subject='status report')}",
            "",
            "Every meaningful update reports:",
            "",
        ]
    )
    lines.extend(
        f"- {field.replace('_', ' ')}"
        for field in _text_sequence(status, "required_fields", subject="status report")
    )
    evidence = _sequence(progress, "evidence", subject="active lane progress")
    lines.extend(
        [
            "",
            f"Current evidence entries: **{len(evidence)}**.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_product(product: Mapping[str, object]) -> None:
    _require_keys(
        product,
        {"environment_role", "goal", "non_goals", "success_conditions"},
        subject="product",
    )
    goal = _text(product, "goal", subject="product")
    lowered = goal.lower()
    if "living pokedex" not in lowered or "mainline games" not in lowered:
        raise ProductFocusError("product goal must retain the cross-game living Pokedex objective")
    if len(_text_sequence(product, "success_conditions", subject="product")) < 3:
        raise ProductFocusError("product success conditions are incomplete")
    if len(_text_sequence(product, "non_goals", subject="product")) < 3:
        raise ProductFocusError("product non-goals are incomplete")
    _text(product, "environment_role", subject="product")


def _validate_active_lane(lane: Mapping[str, object]) -> None:
    _require_keys(
        lane,
        {
            "capability",
            "cheapest_falsifier",
            "id",
            "kind",
            "latest_reorientation",
            "learned_authority",
            "maintenance_unblocks",
            "measurable_outputs",
            "name",
            "next_decision",
            "prohibited_actions",
            "progress",
            "rigor",
            "status",
            "stop_conditions",
            "time_box",
            "transfer_test",
        },
        subject="active lane",
    )
    kind = _text(lane, "kind", subject="active lane")
    if kind not in _LANE_KINDS:
        raise ProductFocusError("active lane kind is unsupported")
    rigor = _text(lane, "rigor", subject="active lane")
    if rigor not in _RIGOR_TIERS:
        raise ProductFocusError("active lane rigor tier is unsupported")
    for key in (
        "capability",
        "cheapest_falsifier",
        "name",
        "next_decision",
        "transfer_test",
    ):
        _text(lane, key, subject="active lane")
    authority = _mapping(lane, "learned_authority", subject="active lane")
    _require_keys(authority, {"current", "target"}, subject="learned authority")
    _text(authority, "current", subject="learned authority")
    _text(authority, "target", subject="learned authority")
    time_box = _mapping(lane, "time_box", subject="active lane")
    _require_keys(time_box, {"maximum_hours", "maximum_sessions"}, subject="time box")
    if _positive_int(time_box, "maximum_sessions", subject="time box") > 3:
        raise ProductFocusError("active lane time box exceeds three sessions")
    _positive_int(time_box, "maximum_hours", subject="time box")
    if len(_text_sequence(lane, "stop_conditions", subject="active lane")) < 2:
        raise ProductFocusError("active lane must declare at least two stop conditions")

    unblocks = lane.get("maintenance_unblocks")
    outputs = tuple(
        _mapping_value(value, subject="measurable output")
        for value in _sequence(lane, "measurable_outputs", subject="active lane")
    )
    if kind == "learning":
        if unblocks is not None:
            raise ProductFocusError("learning lane cannot declare a maintenance unblock")
        _validate_learning_outputs(outputs)
    else:
        if not isinstance(unblocks, str) or _IDENTIFIER.fullmatch(unblocks) is None:
            raise ProductFocusError("maintenance lane must name the learning lane it unblocks")
        if outputs:
            raise ProductFocusError("maintenance lane cannot claim learning outputs")

    prohibited = set(_text_sequence(lane, "prohibited_actions", subject="active lane"))
    if rigor == "development" and not prohibited >= _REQUIRED_DEVELOPMENT_PROHIBITIONS:
        raise ProductFocusError("development lane is missing a protected-action prohibition")
    progress = _mapping(lane, "progress", subject="active lane")
    _validate_progress(progress)
    _validate_latest_reorientation(
        _mapping(lane, "latest_reorientation", subject="active lane"),
    )


def _validate_retired_lane(lane: Mapping[str, object]) -> None:
    _require_keys(
        lane,
        {
            "id",
            "kind",
            "name",
            "preserve_evidence",
            "reason",
            "retry_allowed",
            "rigor",
            "status",
        },
        subject="retired lane",
    )
    if _text(lane, "kind", subject="retired lane") not in _LANE_KINDS:
        raise ProductFocusError("retired lane kind is unsupported")
    if _text(lane, "rigor", subject="retired lane") not in _RIGOR_TIERS:
        raise ProductFocusError("retired lane rigor is unsupported")
    _text(lane, "name", subject="retired lane")
    _text(lane, "reason", subject="retired lane")
    if not _bool(lane, "preserve_evidence", subject="retired lane"):
        raise ProductFocusError("retired lane evidence must remain preserved")
    if _bool(lane, "retry_allowed", subject="retired lane"):
        raise ProductFocusError("retired consumed lane cannot allow retry")


def _validate_learning_outputs(outputs: Sequence[Mapping[str, object]]) -> None:
    if not outputs:
        raise ProductFocusError("learning lane must declare measurable outputs")
    identities: set[tuple[str, str]] = set()
    kinds: set[str] = set()
    minima: dict[str, int] = {}
    for output in outputs:
        _require_keys(output, {"kind", "minimum", "partition"}, subject="measurable output")
        kind = _text(output, "kind", subject="measurable output")
        partition = _text(output, "partition", subject="measurable output")
        if kind not in _OUTPUT_KINDS or partition not in _OUTPUT_PARTITIONS:
            raise ProductFocusError("measurable output kind or partition is unsupported")
        if (
            kind
            in {
                "atomic_goal_episode",
                "composition_attempt",
                "development_episode",
                "verified_composition_episode",
                "verified_outcome_example",
            }
            and partition != "development"
        ):
            raise ProductFocusError(
                "model-led development output must use the development partition"
            )
        if kind == "causal_train_example" and partition != "train":
            raise ProductFocusError("causal train example must use the train partition")
        if (
            kind
            in {
                "synthetic_rootless_atomic_goal_episode",
                "synthetic_rootless_train_outcome",
            }
            and partition != "train"
        ):
            raise ProductFocusError("synthetic rootless output must use the train partition")
        identity = (kind, partition)
        if identity in identities:
            raise ProductFocusError("measurable output identities must be unique")
        identities.add(identity)
        kinds.add(kind)
        minima[kind] = _positive_int(output, "minimum", subject="measurable output")
    legacy_contract = {"outcome_question", "model_fit", "unseen_comparison"} <= kinds
    development_contract = {
        "development_episode",
        "verified_outcome_example",
    } <= kinds
    causal_train_contract = "causal_train_example" in kinds
    synthetic_rootless_contract = {
        "synthetic_rootless_atomic_goal_episode",
        "synthetic_rootless_train_outcome",
    } <= kinds
    if synthetic_rootless_contract and (
        minima["synthetic_rootless_atomic_goal_episode"]
        != minima["synthetic_rootless_train_outcome"]
    ):
        raise ProductFocusError("synthetic rootless output minima must match")
    if (
        not legacy_contract
        and not development_contract
        and not causal_train_contract
        and not (synthetic_rootless_contract)
    ):
        raise ProductFocusError(
            "learning lane must require either the legacy fit/evaluation outputs or "
            "model-led development episodes with verified outcomes, a causal train example, "
            "or paired synthetic rootless outputs"
        )


def _validate_progress(progress: Mapping[str, object]) -> None:
    _require_keys(
        progress,
        {
            "authority_promotions",
            "atomic_goal_episodes",
            "causal_train_examples",
            "composition_attempts",
            "development_episode_attempts",
            "evidence",
            "model_fits",
            "outcome_questions",
            "synthetic_rootless_atomic_goal_episodes",
            "synthetic_rootless_train_outcomes",
            "transfer_results",
            "unseen_comparisons",
            "verified_composition_episodes",
            "verified_outcome_examples",
        },
        subject="active lane progress",
    )
    outcomes = _mapping(progress, "outcome_questions", subject="active lane progress")
    _require_keys(outcomes, {"development", "train"}, subject="outcome progress")
    _count(outcomes, "train", subject="outcome progress")
    _count(outcomes, "development", subject="outcome progress")
    for key in (
        "authority_promotions",
        "atomic_goal_episodes",
        "causal_train_examples",
        "composition_attempts",
        "development_episode_attempts",
        "model_fits",
        "synthetic_rootless_atomic_goal_episodes",
        "synthetic_rootless_train_outcomes",
        "transfer_results",
        "unseen_comparisons",
        "verified_composition_episodes",
        "verified_outcome_examples",
    ):
        _count(progress, key, subject="active lane progress")
    evidence = _sequence(progress, "evidence", subject="active lane progress")
    seen_paths: set[str] = set()
    for raw in evidence:
        item = _mapping_value(raw, subject="progress evidence")
        _require_keys(item, {"kind", "path", "sha256"}, subject="progress evidence")
        kind = _text(item, "kind", subject="progress evidence")
        if kind not in _OUTPUT_KINDS:
            raise ProductFocusError("progress evidence kind is unsupported")
        path = _text(item, "path", subject="progress evidence")
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or path in seen_paths:
            raise ProductFocusError("progress evidence path is unsafe or duplicated")
        seen_paths.add(path)
        digest = _text(item, "sha256", subject="progress evidence")
        if _SHA256.fullmatch(digest) is None:
            raise ProductFocusError("progress evidence SHA-256 is invalid")


def _validate_latest_reorientation(
    reorientation: Mapping[str, object],
) -> None:
    _require_keys(
        reorientation,
        {
            "authority_delta",
            "blocker",
            "decision",
            "evidence",
            "learning_output",
            "next_falsifier",
            "next_session_goal",
            "product_alignment",
            "session_id",
            "status",
            "stop_condition",
            "transfer_result",
        },
        subject="latest reorientation",
    )
    _identifier(reorientation, "session_id", subject="latest reorientation")
    if _text(reorientation, "status", subject="latest reorientation") not in {
        "active",
        "closed",
    }:
        raise ProductFocusError("latest reorientation status is unsupported")
    for key in (
        "authority_delta",
        "blocker",
        "decision",
        "learning_output",
        "next_falsifier",
        "next_session_goal",
        "product_alignment",
        "stop_condition",
        "transfer_result",
    ):
        _text(reorientation, key, subject="latest reorientation")
    evidence = _mapping(reorientation, "evidence", subject="latest reorientation")
    _require_keys(evidence, {"kind", "path", "sha256"}, subject="reorientation evidence")
    kind = _text(evidence, "kind", subject="reorientation evidence")
    if kind not in _REORIENTATION_EVIDENCE_KINDS:
        raise ProductFocusError("reorientation evidence kind is unsupported")
    path = _text(evidence, "path", subject="reorientation evidence")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise ProductFocusError("reorientation evidence path is unsafe")
    digest = _text(evidence, "sha256", subject="reorientation evidence")
    if _SHA256.fullmatch(digest) is None:
        raise ProductFocusError("reorientation evidence SHA-256 is invalid")


def _validate_progress_evidence(
    lane: Mapping[str, object],
    *,
    project_root: Path | None,
) -> None:
    progress = _mapping(lane, "progress", subject="active lane")
    counts = _current_progress_counts(progress)
    evidence = tuple(
        _mapping_value(value, subject="progress evidence")
        for value in _sequence(progress, "evidence", subject="active lane progress")
    )
    if any(counts) and not evidence:
        raise ProductFocusError("nonzero learning progress requires tracked evidence")
    if not any(counts) and evidence:
        raise ProductFocusError("zero learning progress cannot cite advancement evidence")
    if project_root is None:
        return
    root = project_root.resolve()
    reorientation = _mapping(lane, "latest_reorientation", subject="active lane")
    reorientation_evidence = _mapping(
        reorientation,
        "evidence",
        subject="latest reorientation",
    )
    evidence_to_check = tuple((item, "progress evidence") for item in evidence) + (
        (reorientation_evidence, "reorientation evidence"),
    )
    for item, subject in evidence_to_check:
        relative = _text(item, "path", subject=subject)
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ProductFocusError(f"{subject} file is unavailable")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != _text(item, "sha256", subject=subject):
            raise ProductFocusError(f"{subject} file digest differs")


def _validate_rigor_policy(policy: Mapping[str, object]) -> None:
    _require_keys(policy, _RIGOR_TIERS, subject="rigor policy")
    for tier in _RIGOR_TIERS:
        entry = _mapping(policy, tier, subject="rigor policy")
        _require_keys(
            entry,
            {
                "exact_source_ci_binding",
                "external_review",
                "owner_authorization_per_case",
                "purpose",
                "repeatable",
            },
            subject=f"{tier} rigor",
        )
        _bool(entry, "repeatable", subject=f"{tier} rigor")
        _bool(entry, "owner_authorization_per_case", subject=f"{tier} rigor")
        _bool(entry, "exact_source_ci_binding", subject=f"{tier} rigor")
        _text(entry, "external_review", subject=f"{tier} rigor")
        _text(entry, "purpose", subject=f"{tier} rigor")
    development = _mapping(policy, "development", subject="rigor policy")
    benchmark = _mapping(policy, "benchmark", subject="rigor policy")
    sealed = _mapping(policy, "sealed", subject="rigor policy")
    if (
        not _bool(development, "repeatable", subject="development rigor")
        or _bool(
            development,
            "owner_authorization_per_case",
            subject="development rigor",
        )
        or _bool(development, "exact_source_ci_binding", subject="development rigor")
    ):
        raise ProductFocusError("development rigor must preserve a fast repeatable loop")
    if not _bool(benchmark, "exact_source_ci_binding", subject="benchmark rigor"):
        raise ProductFocusError("benchmark rigor must bind exact source and CI")
    if (
        _bool(sealed, "repeatable", subject="sealed rigor")
        or not _bool(
            sealed,
            "owner_authorization_per_case",
            subject="sealed rigor",
        )
        or not _bool(sealed, "exact_source_ci_binding", subject="sealed rigor")
    ):
        raise ProductFocusError("sealed rigor must remain one-shot and owner-authorized")


def _validate_session_budget(budget: Mapping[str, object]) -> None:
    _require_keys(
        budget,
        {"data_and_scenarios", "maintenance_and_docs", "model_and_evaluation"},
        subject="session budget",
    )
    data = _count(budget, "data_and_scenarios", subject="session budget")
    model = _count(budget, "model_and_evaluation", subject="session budget")
    maintenance = _count(budget, "maintenance_and_docs", subject="session budget")
    if data + model + maintenance != 100:
        raise ProductFocusError("session budget must sum to 100 percent")
    if data + model < 75 or maintenance > 25:
        raise ProductFocusError("session budget gives too little time to learning work")


def _validate_alarms(alarms: Mapping[str, object]) -> None:
    _require_keys(
        alarms,
        {
            "maximum_consecutive_ci_only_repairs",
            "maximum_full_replays_during_active_lane",
            "maximum_sessions_without_measured_learning_output",
            "stop_on_repeated_fixed_route_patch",
            "stop_on_unmeasured_teacher_label_copy",
        },
        subject="alarms",
    )
    if (
        _count(
            alarms,
            "maximum_sessions_without_measured_learning_output",
            subject="alarms",
        )
        > 1
    ):
        raise ProductFocusError("learning-output alarm cannot exceed one session")
    if _count(alarms, "maximum_consecutive_ci_only_repairs", subject="alarms") > 1:
        raise ProductFocusError("CI-only repair alarm cannot exceed one repair")
    if _count(alarms, "maximum_full_replays_during_active_lane", subject="alarms") != 0:
        raise ProductFocusError("active development lane cannot permit a full replay")
    if not _bool(alarms, "stop_on_repeated_fixed_route_patch", subject="alarms"):
        raise ProductFocusError("fixed-route drift alarm must remain enabled")
    if not _bool(alarms, "stop_on_unmeasured_teacher_label_copy", subject="alarms"):
        raise ProductFocusError("teacher-label drift alarm must remain enabled")


def _validate_status_report(status: Mapping[str, object]) -> None:
    _require_keys(status, {"counter_source", "required_fields"}, subject="status report")
    _text(status, "counter_source", subject="status report")
    fields = set(_text_sequence(status, "required_fields", subject="status report"))
    if fields != _REQUIRED_STATUS_FIELDS:
        raise ProductFocusError("status report fields do not cover the required product truth")


def _validate_review_roles(roles: Mapping[str, object]) -> None:
    _require_keys(roles, {"antigravity", "claude", "codex"}, subject="review roles")
    for role in ("codex", "claude", "antigravity"):
        _text(roles, role, subject="review roles")


def _current_output_count(
    progress: Mapping[str, object],
    output: Mapping[str, object],
) -> int:
    kind = _text(output, "kind", subject="measurable output")
    partition = _text(output, "partition", subject="measurable output")
    if kind == "outcome_question":
        outcomes = _mapping(progress, "outcome_questions", subject="active lane progress")
        if partition not in {"train", "development"}:
            raise ProductFocusError("outcome question must use train or development partition")
        return _count(outcomes, partition, subject="outcome progress")
    progress_key = {
        "atomic_goal_episode": "atomic_goal_episodes",
        "authority_promotion": "authority_promotions",
        "causal_train_example": "causal_train_examples",
        "composition_attempt": "composition_attempts",
        "development_episode": "development_episode_attempts",
        "model_fit": "model_fits",
        "synthetic_rootless_atomic_goal_episode": ("synthetic_rootless_atomic_goal_episodes"),
        "synthetic_rootless_train_outcome": "synthetic_rootless_train_outcomes",
        "transfer_result": "transfer_results",
        "unseen_comparison": "unseen_comparisons",
        "verified_composition_episode": "verified_composition_episodes",
        "verified_outcome_example": "verified_outcome_examples",
    }.get(kind)
    if progress_key is None:
        raise ProductFocusError("measurable output has no progress counter")
    return _count(progress, progress_key, subject="active lane progress")


def _current_progress_counts(progress: Mapping[str, object]) -> tuple[int, ...]:
    outcomes = _mapping(progress, "outcome_questions", subject="active lane progress")
    return (
        _count(outcomes, "train", subject="outcome progress"),
        _count(outcomes, "development", subject="outcome progress"),
        _count(progress, "model_fits", subject="active lane progress"),
        _count(progress, "unseen_comparisons", subject="active lane progress"),
        _count(progress, "authority_promotions", subject="active lane progress"),
        _count(progress, "transfer_results", subject="active lane progress"),
        _count(progress, "development_episode_attempts", subject="active lane progress"),
        _count(progress, "verified_outcome_examples", subject="active lane progress"),
        _count(progress, "atomic_goal_episodes", subject="active lane progress"),
        _count(progress, "causal_train_examples", subject="active lane progress"),
        _count(progress, "composition_attempts", subject="active lane progress"),
        _count(progress, "verified_composition_episodes", subject="active lane progress"),
        _count(
            progress,
            "synthetic_rootless_train_outcomes",
            subject="active lane progress",
        ),
        _count(
            progress,
            "synthetic_rootless_atomic_goal_episodes",
            subject="active lane progress",
        ),
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    del value
    raise ValueError("non-finite JSON number")


def _require_keys(
    value: Mapping[str, object],
    expected: set[str],
    *,
    subject: str,
) -> None:
    if set(value) != expected:
        raise ProductFocusError(f"{subject} fields are incomplete or unsupported")


def _mapping(
    source: Mapping[str, object],
    key: str,
    *,
    subject: str,
) -> Mapping[str, object]:
    return _mapping_value(source.get(key), subject=f"{subject} {key.replace('_', ' ')}")


def _mapping_value(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ProductFocusError(f"{subject} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ProductFocusError(f"{subject} keys must be text")
    return value


def _sequence(
    source: Mapping[str, object],
    key: str,
    *,
    subject: str,
) -> Sequence[object]:
    value = source.get(key)
    if not isinstance(value, list):
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} must be a list")
    return value


def _text(
    source: Mapping[str, object],
    key: str,
    *,
    subject: str,
    maximum: int = 500,
) -> str:
    value = source.get(key)
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > maximum
        or any(character in value for character in ("\n", "\r", "\x00"))
    ):
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} must be one-line text")
    return value


def _identifier(source: Mapping[str, object], key: str, *, subject: str) -> str:
    value = _text(source, key, subject=subject, maximum=96)
    if _IDENTIFIER.fullmatch(value) is None:
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} is not an identifier")
    return value


def _text_sequence(
    source: Mapping[str, object],
    key: str,
    *,
    subject: str,
) -> tuple[str, ...]:
    values = _sequence(source, key, subject=subject)
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ProductFocusError(f"{subject} {key.replace('_', ' ')} contains non-text")
        item = {"value": value}
        result.append(_text(item, "value", subject=subject))
    if len(result) != len(set(result)):
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} contains duplicates")
    return tuple(result)


def _count(source: Mapping[str, object], key: str, *, subject: str) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} must be a count")
    return value


def _positive_int(source: Mapping[str, object], key: str, *, subject: str) -> int:
    value = _count(source, key, subject=subject)
    if value < 1:
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} must be positive")
    return value


def _bool(source: Mapping[str, object], key: str, *, subject: str) -> bool:
    value = source.get(key)
    if not isinstance(value, bool):
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} must be boolean")
    return value


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _table_text(value: str) -> str:
    return value.replace("|", "\\|")


def _table_row(label: str, value: str) -> str:
    return f"| {label} | {_table_text(value)} |"
