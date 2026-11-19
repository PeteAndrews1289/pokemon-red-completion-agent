"""Read-only admission audit for recorded story-branch TRAIN collection cases.

A decision is admissible only when, replayed from the case's own recorded documents:
  * the native state chain is continuous (each outcome's terminal state hash equals the
    stored terminal.state bytes and the next outcome's before-state hash);
  * the story-branch tracker and segment chain recompute exactly from recorded outcomes;
  * story_branch_selection reproduces the recorded index, probabilities, exploration flag
    and segment from the receipt's recorded inputs (same pure code as the live child);
  * the identity-free continuity/history and candidate-scalar features match their
    replayed tracker and the recorded menu candidate.
Route features (executor-private quotes) are carried as recorded and declared as such.
No emulator, model query, fit or file write happens here.
"""

from types import SimpleNamespace

from .goal_manager import GoalKind
from .red_story_branch_value import (
    StoryBranchSegment,
    StoryBranchTracker,
    segment_after_outcome,
    story_branch_selection,
    tracker_after_outcome,
)

ADMISSION_SCHEMA = "pokemon.red.story-branch-admission-audit.v1"


def _segment(document):
    if document is None:
        return None
    values = {k: v for k, v in document.items() if k != "schema"}
    return StoryBranchSegment(**values)


def _clean(outcome):
    return outcome.get("error_type") is None and (
        outcome.get("verification") == "succeeded"
        or (outcome.get("verification") == "failed" and outcome.get("ordinary_setback") is True
            and outcome.get("safe_terminal") is True)
    )


def _candidate_scalars(candidate):
    values = (candidate.get("features") or {}).get("values") or []
    names = (candidate.get("features") or {}).get("feature_names") or []
    by = dict(zip(names, values))
    ch = candidate.get("challenge")
    challenge = (0.0, 0.0, 0.0, 0.0, 0.0) if ch is None else (
        1.0, float(ch["combat_required"]), float(ch["opposition_known"]),
        max(-1.0, min(1.0, float(ch["median_level_deficit"]))), max(-1.0, min(1.0, float(ch["maximum_level_deficit"]))))
    unit = candidate.get("story_unit")
    story = (0.0, 0.0, 0.0) if unit is None else (
        float(unit["mode"] == "movement"), float(unit["mode"] == "interaction"), float(unit["requires_further_selected_unit"]))
    return (float(by["execution_effort"]), float(by["party_risk"]), *challenge, *story)


def _candidate_readiness(candidate):
    from .player_readiness import PlayerReadiness
    from .red_story_branch_value import readiness_branch_vector
    doc = candidate.get("readiness")
    ch = candidate.get("challenge")
    return readiness_branch_vector(None if doc is None else PlayerReadiness.from_public(doc),
                                   combat_required=0.0 if ch is None else float(ch["combat_required"]))


def audit_story_branch_case(outcomes, steps, *, segment_lengths=None):
    """Audit one case. steps[ordinal] = dict(intent=..., decision=..., private=... or None,
    terminal_sha256=<sha of stored terminal.state bytes or None>).

    Returns dict(case_chain_ok, decisions={ordinal: dict(ok, reasons)}).
    """
    if segment_lengths is not None:
        segment_lengths = tuple(segment_lengths)
    chain_reasons = []
    for k, o in enumerate(outcomes):
        st = steps.get(o["ordinal"]) or {}
        if st.get("terminal_sha256") != o.get("terminal_state_sha256"):
            chain_reasons.append("step %s terminal state hash differs" % o["ordinal"])
        if k + 1 < len(outcomes) and outcomes[k + 1].get("before_state_sha256") != o.get("terminal_state_sha256"):
            chain_reasons.append("state chain breaks after step %s" % o["ordinal"])
    tracker, segment, decisions = StoryBranchTracker(), None, {}
    for o in outcomes:
        st = steps.get(o["ordinal"]) or {}
        intent, decision, private = st.get("intent") or {}, st.get("decision") or {}, st.get("private")
        selected_index = decision.get("selected_candidate_index")
        contexts = intent.get("private_story_contexts") or []
        kind = GoalKind(o["selected_kind"])
        objective = None
        if kind is GoalKind.ADVANCE_STORY and isinstance(selected_index, int) and selected_index < len(contexts):
            objective = contexts[selected_index].get("objective_ref")
        if private is not None:
            reasons = []
            if private.get("tracker") != tracker.document() or private.get("tracker_sha256") != tracker.sha256:
                reasons.append("tracker replay differs")
            if private.get("head_sha256") is not None:
                reasons.append("headed receipts are not replayable by this audit")
            indices = tuple(private["story_indices"]); refs = tuple(private["objective_refs"])
            objective_of = dict(zip(indices, refs, strict=True))
            prior = segment if segment_lengths is not None else None
            try:
                sel = story_branch_selection(indices=indices, objective_of=objective_of,
                                             parent_index=private["parent_selected_candidate_index"],
                                             branch_scores=(None,) * len(indices), candidate_count=len(private["probabilities"]),
                                             exploration_probability=private["exploration_probability"], seed=private["seed"],
                                             segment=prior, segment_lengths=segment_lengths)
            except Exception as error:  # noqa: BLE001 - any replay failure rejects the decision
                reasons.append("selection replay failed: %s" % type(error).__name__)
                sel = None
            if sel is not None:
                if sel["selected"] != private["selected_candidate_index"] or sel["selected"] != selected_index:
                    reasons.append("selected index differs")
                if list(sel["probabilities"]) != list(private["probabilities"]):
                    reasons.append("behaviour probabilities differ")
                if sel["explored"] != private["explored"]:
                    reasons.append("exploration flag differs")
                recorded_segment = private.get("segment")
                replayed_segment = None if sel["segment"] is None else sel["segment"].document()
                if segment_lengths is not None and recorded_segment != replayed_segment:
                    reasons.append("segment differs")
                if segment_lengths is not None:
                    segment = sel["segment"]
            menu = (intent.get("menu") or {}).get("menu") or intent.get("menu") or {}
            candidates = menu.get("candidates") or []
            for pos, (i, ref) in enumerate(zip(indices, refs, strict=True)):
                f = private["features"][pos]
                if f[3] != float(tracker.previous_objective_ref == ref) or tuple(f[4:12]) != tracker.history(ref).vector():
                    reasons.append("continuity/history features differ at index %d" % i)
                if i < len(candidates):
                    try:
                        if tuple(f[12:22]) != _candidate_scalars(candidates[i]) or (len(f) > 22 and tuple(f[22:]) != _candidate_readiness(candidates[i])):
                            reasons.append("candidate scalar features differ at index %d" % i)
                    except (KeyError, TypeError, ValueError):
                        reasons.append("candidate scalars unavailable at index %d" % i)
                else:
                    reasons.append("recorded menu lacks candidate %d" % i)
            objective = refs[indices.index(private["selected_candidate_index"])] if private["selected_candidate_index"] in indices else objective
            decisions[o["ordinal"]] = dict(ok=not reasons and not chain_reasons, reasons=reasons + chain_reasons, clean=_clean(o))
        binding = SimpleNamespace(kind=kind, story_objective_ref=objective)
        tracker = tracker_after_outcome(tracker, binding, o)
        if segment_lengths is not None:
            segment = segment_after_outcome(segment, binding, o)
    return dict(schema=ADMISSION_SCHEMA, case_chain_ok=not chain_reasons, chain_reasons=chain_reasons, decisions=decisions,
                route_features="executor-private route quotes carried as recorded (not replayable offline)")
