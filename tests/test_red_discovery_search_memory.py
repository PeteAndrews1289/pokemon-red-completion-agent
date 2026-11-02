"""Discovery history through continuous player recording and projection.

Synthetic observations and the existing synthetic ranker only. These are not
native qualification, trained-player predictions, fits, or gameplay evidence.
"""

import json
from dataclasses import replace

import pytest
from test_post_battle_strategy import menu
from test_red_integrated_play import _facts
from test_red_live_option_menu import _binding, _fishing_candidate, _model, _no_ordinary_bindings, _situation

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind, upgrade_option_value_model_for_readiness
from pokemon_red_completion.player_readiness import PlayerReadiness
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot, run_autonomous_options
from pokemon_red_completion.red_integrated_play import menu_with_search_history, objective_key
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set, supplemental_live_option


class _DiscoveryMemoryProbe:
    """Exercise the real continuous recorder/projection with no acquisition row."""

    source = "pokemon.red:discovery:wild:Route1:grass"
    objective = "c" * 64

    def __init__(self, *, failure=None, successful=False, tracked=True):
        self.n = 0
        self.failure = failure
        self.successful = successful
        self.tracked = tracked
        self.configuration = "first"
        self.observed = []
        prior = menu()
        self.readiness = PlayerReadiness.from_context(prior.context, prior.remaining_budget)

    def snapshot(self):
        facts = dict(_facts(self.n), cash=5000, completed_objectives=["first"])
        if self.n and self.failure == "partial":
            facts["completed_actions"] -= 1
        return AutonomousSnapshot(
            str(self.n).encode(), facts,
            not (self.n and self.failure == "unsafe"),
        )

    def execute(self):
        self.n += 1
        if self.failure == "exception":
            raise RuntimeError("native evidence fixture: failed after one counted input")
        return GoalExecutionReport(1, 10, dict(
            bounded=True, search_exhausted=not self.successful,
            captures=0, new_sighting_count=int(self.successful),
            search_stop_reason="survey_leg_limit_exceeded",
        ))

    def verify(self, _report):
        if self.failure == "unverified":
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if self.successful:
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED)

    def options(self):
        bindings = tuple(replace(
            _binding(GoalKind.EXPLORE, binding_ref=f"discovery:{i}:config-{self.configuration}", calls=[]),
            execute=self.execute, verify=self.verify,
            search_source_ref=self.source if self.tracked else None,
            search_objective_sha256=self.objective if self.tracked else None,
        ) for i in range(2))
        supplements = []
        for i, binding in enumerate(bindings):
            candidate = _fishing_candidate(binding.binding_ref, travel=0.1 + 0.5 * i)
            candidate = replace(candidate, features=replace(
                candidate.features, kind=LivingDexOptionKind.EXPLORE,
            ))
            supplements.append(supplemental_live_option(binding, candidate))
        return build_red_live_option_set(
            situation=_situation(resources=0.1), binding_set=_no_ordinary_bindings(),
            supplements=tuple(supplements), model_feature_version=5,
            ordering_seed_sha256="a" * 64, readiness=self.readiness,
        )

    def observe(self, _ordinal):
        self.observed.append(self.n)
        return self.options()

    def run(self, output, retained, *, decisions=2, stop=None):
        return run_autonomous_options(
            model=upgrade_option_value_model_for_readiness(_model()),
            output=output, snapshot=self.snapshot, observe=self.observe,
            seed=17, maximum_decisions=decisions, continuous_player=True,
            maximum_cash_spent=None, initial_search_memory=retained,
            stop_after_outcome=stop, provenance={"test_only": True},
        )


def _discovery_intent_histories(output, ordinal):
    document = json.loads((output / f"step-{ordinal:03d}/intent.json").read_text())
    return [candidate["search_history"] for candidate in document["menu"]["menu"]["candidates"]]


def test_discovery_history_records_two_misses_and_survives_rebuilt_runtime(tmp_path):
    probe = _DiscoveryMemoryProbe()
    memory = GoalSearchMemory()
    first = probe.run(tmp_path / "first", memory)
    assert first["executed_decisions"] == first["ordinary_setbacks"] == 2
    assert first["successful_decisions"] == 0
    assert probe.observed == [0, 1]
    assert [outcome["verification"] for outcome in first["outcomes"]] == ["failed", "failed"]
    for ordinal in range(2):
        histories = _discovery_intent_histories(tmp_path / "first", ordinal)
        assert all(h["attempts"] == h["exhausted"] == ordinal for h in histories)
        assert all((h["actions"], h["frames"]) == (ordinal, 10 * ordinal) for h in histories)
        after = json.loads((tmp_path / f"first/step-{ordinal:03d}/search-memory-after.json").read_text())
        assert after["objective_sha256"] == probe.objective
    restored = GoalSearchMemory.from_private_dict(first["search_memory"])
    assert restored is not memory
    assert restored.private_dict() == memory.private_dict()
    old_bindings = tuple(b.binding_ref for b in probe.options().bindings)
    probe.configuration = "renewed-different-private-identity"
    probe.successful = True
    new_bindings = tuple(b.binding_ref for b in probe.options().bindings)
    assert old_bindings != new_bindings
    second = probe.run(tmp_path / "second", restored, decisions=1)
    assert second["successful_decisions"] == 1
    histories = _discovery_intent_histories(tmp_path / "second", 0)
    assert all(h["attempts"] == h["exhausted"] == 2 for h in histories)
    history = restored.lookup(probe.source, probe.objective)
    assert (history.attempts, history.exhausted, history.actions, history.frames) == (3, 2, 3, 30)
    assert second["search_memory"] == restored.private_dict()
    projected = menu_with_search_history(probe.options(), restored, objective_key(probe.snapshot().facts))
    assert projected.menu.candidate_vector(0) != probe.options().menu.candidate_vector(0)
    public = json.dumps(projected.public_dict())
    assert probe.source not in public and probe.objective not in public


@pytest.mark.parametrize("failure", ["unsafe", "unverified", "exception", "partial"])
def test_discovery_invalid_tail_preserves_evidence_without_recording_search_history(tmp_path, failure):
    probe = _DiscoveryMemoryProbe(failure=failure)
    memory = GoalSearchMemory()
    before = memory.private_dict()
    result = probe.run(tmp_path / "failed", memory)
    assert probe.observed == [0]
    assert result["executed_decisions"] == 1
    assert result["ordinary_setbacks"] == 0
    assert result["search_memory"] == memory.private_dict() == before
    assert (tmp_path / "failed/step-000/terminal.state").read_bytes() == b"1"
    assert (tmp_path / "failed/step-000/outcome.json").is_file()
    assert not (tmp_path / "failed/step-000/search-memory-after.json").exists()
    if failure == "exception":
        outcome = result["outcomes"][0]
        assert outcome["error_type"] == "RuntimeError"
        assert "failed after one counted input" in outcome["error"]
        assert outcome["observed_cost"]["actions"] == 1


def test_generic_exploration_does_not_opt_into_search_memory(tmp_path):
    probe = _DiscoveryMemoryProbe(successful=True, tracked=False)
    memory = GoalSearchMemory()
    objective = objective_key(probe.snapshot().facts)
    options = probe.options()
    # Deliberately populate each exact legacy fallback key: exclusion must be
    # semantic, not an accidentally absent lookup or a mismatching fingerprint.
    for binding in options.bindings:
        memory.record(binding.binding_ref, objective, exhausted=True, actions=7, frames=70)
    before = memory.private_dict()
    projected = menu_with_search_history(options, memory, objective)
    assert all(candidate.search_history is None for candidate in projected.menu.candidates)
    assert projected == options
    result = probe.run(tmp_path / "generic", memory, decisions=1)
    assert result["successful_decisions"] == 1
    assert result["search_memory"] == memory.private_dict() == before
    assert not (tmp_path / "generic/step-000/search-memory-after.json").exists()


@pytest.mark.parametrize("successful", [False, True])
def test_discovery_consequence_stop_commits_last_measured_search(tmp_path, successful):
    probe = _DiscoveryMemoryProbe(successful=successful)
    memory = GoalSearchMemory()
    result = probe.run(tmp_path / "consequence", memory, stop=lambda: probe.n == 1)
    assert result["stop_reason"] == "declared_consequence_complete"
    assert result["executed_decisions"] == 1
    assert probe.observed == [0]
    history = memory.lookup(probe.source, probe.objective)
    assert (history.attempts, history.exhausted, history.actions, history.frames) == (
        1, int(not successful), 1, 10,
    )
    after = json.loads((tmp_path / "consequence/step-000/search-memory-after.json").read_text())
    assert result["search_memory"] == after["memory"] == memory.private_dict()


@pytest.mark.parametrize("source,objective", [("source", None), (None, "a" * 64)])
def test_discovery_requires_explicit_source_and_objective_together(source, objective):
    from pokemon_red_completion.goal_manager_runtime import GoalManagerRuntimeError
    with pytest.raises(GoalManagerRuntimeError, match="both source and objective"):
        replace(_binding(GoalKind.EXPLORE, binding_ref="generic", calls=[]),
                search_source_ref=source, search_objective_sha256=objective)
