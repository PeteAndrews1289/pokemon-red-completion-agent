"""Admit the opt-in Red forward stream alongside authenticated native choices.

Only complete private episodes are admitted. The existing reader authenticates
all files and replays the actual stochastic choices. This layer additionally
checks the prospective goal header, first-choice join, current semantic verifier
evidence, cumulative consumable spending and the executed action/frame prefix.
No emulator is opened. Source-bound trusted observations remain observations,
not cryptographic proof that an arbitrary outside recorder told the truth.
"""

from typing import cast

from .domain import GameMode, GameState
from .forward_goal import ForwardGoalOutcome, ForwardGoalPlan
from .forward_goal_records import _mapping, read_forward_goal_events
from .goal_manager import GoalKind, GoalSelectionMode
from .goal_manager_trajectory import GOAL_MANAGER_OUTCOME_KIND, load_goal_manager_episode
from .living_dex_option_value import LivingDexOptionValueModel, option_feature_names
from .private_artifacts import PrivateArtifactRoot, PrivateEpisodeReader
from .provenance import canonical_sha256
from .red_forward_goal import (
    _CONSUMABLES,
    RED_FORWARD_CONTEXT_NAMES,
    red_forward_continuation_sha256,
    red_forward_execution_flags,
    red_forward_goal_facts,
    red_forward_verifier_sha256,
)
from .red_player_training_dataset import (
    RedPlayerTrainingDataset,
    _audit_red_player_training_reader,
    _require_player_training_origin,
)
from .red_player_training_plan import RedPlayerTrainingPlan
from .referee import CompletionReferee


def _evidence(value: object, objective: str) -> tuple[bool, tuple[float, ...], dict[str, int]]:
    row = _mapping(value)
    if set(row) != {"mode", "current_facts", "context", "consumables"}:
        raise ValueError("Red forward observation fields differ")
    facts, context = row["current_facts"], row["context"]
    if (
        not isinstance(facts, list)
        or any(not isinstance(f, str) or not f for f in facts)
        or sorted(set(facts)) != facts
        or not isinstance(context, list)
        or len(context) != len(RED_FORWARD_CONTEXT_NAMES)
        or any(type(x) not in (int, float) or not 0 <= x <= 1 for x in context)
    ):
        raise ValueError("Red forward current evidence is malformed")
    stock = _mapping(row["consumables"])
    if set(stock) != {str(k) for k in _CONSUMABLES} or any(
        type(count) is not int or not 0 <= count <= 99 for count in stock.values()
    ):
        raise ValueError("Red forward consumable evidence differs")
    state = GameState(GameMode(cast(str, row["mode"])), frozenset(facts))
    goal = (
        CompletionReferee().inspect(state).complete
        if objective in {"defeat_champion", "enter_hall_of_fame"}
        else red_forward_goal_facts(objective) <= state.facts
    )
    return goal, tuple(context), cast(dict[str, int], dict(stock))


def load_red_forward_episode(
    store: PrivateArtifactRoot,
    *,
    episode_id: str,
    expected_manifest_sha256: str,
    training_plan: RedPlayerTrainingPlan,
    behavior_model: LivingDexOptionValueModel,
    forward_plan: ForwardGoalPlan,
    objective_id: str,
) -> ForwardGoalOutcome:
    _require_red_forward_scope(training_plan, forward_plan, objective_id)
    _require_player_training_origin(store, episode_id, training_plan, behavior_model)
    reader = store.open_episode(episode_id)
    immediate = _audit_red_player_training_reader(
        reader,
        episode_id=episode_id,
        expected_manifest_sha256=expected_manifest_sha256,
        plan=training_plan,
        behavior_model=behavior_model,
    )
    return _audit_red_forward_reader(
        reader,
        immediate=immediate,
        training_plan=training_plan,
        forward_plan=forward_plan,
        objective_id=objective_id,
    )


def _require_red_forward_scope(
    training_plan: RedPlayerTrainingPlan,
    forward_plan: ForwardGoalPlan,
    objective_id: str,
) -> None:
    if (
        forward_plan.goal_family != "red-story-objective"
        or forward_plan.verifier_sha256 != red_forward_verifier_sha256(objective_id)
        or forward_plan.max_macros != 2
        or training_plan.document["decision_limit"] != 2
        or training_plan.document.get("curriculum_contract") is not None
        or forward_plan.max_actions != training_plan.maximum_actions * 2
        or forward_plan.max_frames != training_plan.maximum_frames * 2
        or forward_plan.max_resources < 2
    ):
        raise ValueError("Red forward admission scope differs")


def _audit_red_forward_reader(
    reader: PrivateEpisodeReader,
    *,
    immediate: RedPlayerTrainingDataset,
    training_plan: RedPlayerTrainingPlan,
    forward_plan: ForwardGoalPlan,
    objective_id: str,
) -> ForwardGoalOutcome:
    """Audit one immutable authenticated reader, without changing its status."""
    if reader.manifest_sha256 != immediate.episode_manifest_sha256:
        raise ValueError("Red forward and native episode identities differ")
    metadata = _mapping(reader.read_header()["metadata"])
    if (
        metadata.get("forward_goal_plan") != forward_plan.public_dict()
        or metadata.get("forward_goal_plan_sha256") != forward_plan.sha256
        or metadata.get("forward_story_objective") != objective_id
        or metadata.get("forward_goal_authority") != "recording-only-existing-actor"
        or "forward_goal" not in reader.stream_names
    ):
        raise ValueError("Red forward prospective header is absent or differs")
    execution_flags = red_forward_execution_flags(metadata)
    if forward_plan.continuation_sha256 != red_forward_continuation_sha256(
        **{
            key: cast(str, training_plan.document[key])
            for key in (
                "behavior_policy_id",
                "model_sha256",
                "source_bundle_sha256",
                "profile_sha256",
            )
        },
        execution_flags=execution_flags,
    ):
        raise ValueError("Red forward continuation differs from authenticated execution flags")
    joined = load_goal_manager_episode(reader)
    if not joined.examples or not immediate.examples:
        raise ValueError("Red forward requires an executed native sampled first choice")
    first = joined.examples[0]
    if first.selection_mode is not GoalSelectionMode.AUTHORITY or any(
        decision.question.opportunities[i].kind
        not in {GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM}
        for decision in joined.examples
        for i in decision.question.available_indices
    ):
        raise ValueError("Red forward options are not the declared story/recovery scope")
    events = tuple(reader.iter_stream("forward_goal", max_records=forward_plan.max_macros + 3))
    generic = tuple({k: v for k, v in event.items() if k != "red_evidence"} for event in events)
    outcome = read_forward_goal_events(generic, expected_plan=forward_plan)
    menu = immediate.examples[0].menu
    first_row = immediate.examples[0]
    if (
        first_row.decision_sha256
        != canonical_sha256(
            {
                "decision_id": first.decision_id,
                "plan_sha256": training_plan.plan_sha256,
                "question_sha256": first.question.ordered_policy_input_sha256,
            }
        )
        or outcome.choice.decision_sha256
        != canonical_sha256(
            {
                "decision_id": first.decision_id,
                "training_plan_sha256": training_plan.plan_sha256,
            }
        )
        or outcome.choice.root_sha256
        != canonical_sha256({"root_lineage_id": joined.root_lineage_id})
        or outcome.choice.partition != "train"
        or outcome.choice.context_names != RED_FORWARD_CONTEXT_NAMES
        or outcome.choice.candidate_names != option_feature_names(3)
        or outcome.choice.candidates
        != tuple(menu.candidate_vector(i, feature_version=3) for i in range(len(menu.candidates)))
        or outcome.choice.selected_index != first_row.selected_candidate_index
        or outcome.choice.probabilities != first_row.behavior_probabilities
    ):
        raise ValueError("Red forward anchor differs from its authenticated first choice")
    initial_goal, context, stock = _evidence(events[0].get("red_evidence"), objective_id)
    if (
        initial_goal
        or context != outcome.choice.context
        or (events[1].get("red_evidence") != events[0].get("red_evidence"))
    ):
        raise ValueError("Red forward initial observation or anchor differs")
    executions = tuple(reader.iter_stream("executions"))
    macro_ends = [
        cast(int, event["step_index"])
        for event in reader.iter_stream("events")
        if event.get("kind") == GOAL_MANAGER_OUTCOME_KIND
    ]
    spent = 0
    prior_macros = 0
    for event in events[2:]:
        counters = _mapping(event["counters"])
        actions, frames, macros = (cast(int, counters[k]) for k in ("actions", "frames", "macros"))
        if actions > len(executions) or not prior_macros <= macros <= prior_macros + 1:
            raise ValueError("Red forward cumulative prefix differs")
        if macros > len(macro_ends) or (
            macros > prior_macros and macro_ends[macros - 1] != actions
        ):
            raise ValueError("Red forward macro does not end at the recorded action boundary")
        prefix = executions[:actions]
        trace_frames = sum(cast(int, entry["frames"]) for entry in prefix)
        if trace_frames > frames or (
            all(entry.get("status") == "success" for entry in prefix) and trace_frames != frames
        ):
            raise ValueError("Red forward frames differ from actual executions")
        if event["goal"] is None:
            if event.get("red_evidence") is not None:
                raise ValueError("censored Red goal cannot claim a current observation")
        else:
            goal, _, current = _evidence(event.get("red_evidence"), objective_id)
            if goal is not event["goal"]:
                raise ValueError("Red forward target differs from current verifier evidence")
            spent += sum(max(0, count - current[item]) for item, count in stock.items())
            stock = current
        if counters["resources"] != spent:
            raise ValueError("Red forward resource cost differs from observed consumption")
        prior_macros = macros
    if outcome.counters.actions != len(executions):
        raise ValueError("Red forward terminal omits played controller actions")
    if not outcome.censored and outcome.counters.macros != len(joined.examples):
        raise ValueError("Red forward terminal omits completed macros")
    return outcome
