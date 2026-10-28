"""Optional private-fixture regression tests for scoped TRAIN readback.

Set POKEMON_TRAIN_CONSEQUENCE_FIXTURES to a JSON object with absolute "direct"
and "prepared" closed-case directories. The direct fixture must retain a failed
worker after a completed ordinary loss; the prepared fixture must retain wild
calls before its one completed story loss. No private path/data is embedded.
Without this opt-in, the twelve native-evidence readback tests are skipped.
All reads are pure; mutations below affect in-memory file reads only.
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import os
import unittest
from unittest.mock import patch

from pokemon_red_completion import red_challenge_consequence as module
from pokemon_red_completion.private_artifacts import (
    gitless_fast_path_worktree_probe, open_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_story_battle import StoryTrainerContract

read = lambda path: json.loads(path.read_bytes())


def _arguments(case):
    plan = read(case / "native/consequence-plan.json")
    result = read(case / "native/consequence-result.json")
    declaration = read(case / "scoped-battles/declaration.json")
    targets = read(case / "EXACT-TRAIN-BATTLE-SCOPES.json")
    document = next(
        dict(item) for item in targets["contracts"]
        if item["map_id"] == plan["spec"]["challenge_target"]["map_id"]
        and [item["defeated_event"]] == plan["spec"]["challenge_target"]["events"]
    )
    document["trainer_identity"] = tuple(document["trainer_identity"])
    document["victory_items"] = tuple(tuple(item) for item in document["victory_items"])
    package = Path(read(case / "PLAN.json")["package"]).parent
    store = open_private_root(
        case / "journal", repository_root=package / "checkout",
        allow_same_device=True, git_worktree_probe=gitless_fast_path_worktree_probe,
        native_input_storage="flat_sealed_v1",
    )
    return store, dict(
        declaration_sha256=canonical_sha256(plan),
        result_sha256=canonical_sha256(result),
        scoped_output=case / "scoped-battles",
        expected_scoped_declaration_sha256=canonical_sha256(declaration),
        expected_native_plan_sha256=plan["source"]["experiment_sha256"],
        expected_story_contract=StoryTrainerContract(**document),
    )


class _RecordProxy:
    def __init__(self, record, transform):
        self.record, self.transform = record, transform

    def read(self):
        return self.transform(deepcopy(self.record.read()))


class _StoreProxy:
    def __init__(self, store, result_id, transform):
        self.store, self.result_id, self.transform = store, result_id, transform

    def find_sealed_record(self, record_id, **kwargs):
        record = self.store.find_sealed_record(record_id, **kwargs)
        return (
            _RecordProxy(record, self.transform)
            if record_id == self.result_id else record
        )


class TestScopedTrainConsequencePrivateReadback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = os.environ.get("POKEMON_TRAIN_CONSEQUENCE_FIXTURES")
        if raw is None:
            raise unittest.SkipTest("private TRAIN readback fixtures not explicitly supplied")
        paths = json.loads(raw)
        if not isinstance(paths, dict) or set(paths) != {"direct", "prepared"}:
            raise ValueError("private fixture opt-in requires exactly direct and prepared paths")
        cls.cases = {key: Path(value) for key, value in paths.items()}
        if any(not path.is_absolute() or not path.is_dir() for path in cls.cases.values()):
            raise ValueError("private fixture paths must be existing absolute directories")

    def setUp(self):
        self.case = self.cases["direct"]
        self.store, self.kwargs = _arguments(self.case)

    def load(self):
        return module.load_scoped_train_challenge_consequence(self.store, **self.kwargs)

    def mutate_file(self, path, transform):
        original = Path.read_bytes
        target = path.resolve()

        def replacement(path):
            payload = original(path)
            if path.resolve() == target:
                value = json.loads(payload)
                transform(value)
                return json.dumps(value, sort_keys=True).encode()
            return payload

        return patch.object(Path, "read_bytes", replacement)

    def target_directory(self):
        declaration = read(self.case / "scoped-battles/declaration.json")
        contract = self.kwargs["expected_story_contract"]
        index = next(
            actor["index"] for actor in declaration["actors"]
            if actor["scope"] == "story"
            and actor["contract"]["defeated_event"] == contract.defeated_event
            and actor["contract"]["map_id"] == contract.map_id
        )
        return self.case / "scoped-battles" / f"actor-{index:03d}" / "battle-0001"

    def test_ordinary_loss_retains_failed_native_status(self):
        result = self.load()
        recorded = read(self.case / "native/consequence-result.json")
        self.assertFalse(result.row.outcome.completed)
        self.assertEqual(canonical_sha256(result.row.document()), canonical_sha256(recorded["row"]))
        self.assertFalse(read(self.case / "RESULT.json")["passed"])
        self.assertFalse(read(self.case / "TERMINAL-AUTHENTICATION.json")["passed"])
        self.assertFalse(hasattr(result, "native_worker_passed"))

    def test_prepared_global_call_is_not_actor_local_index(self):
        self.case = self.cases["prepared"]
        self.store, self.kwargs = _arguments(self.case)
        result = self.load()
        self.assertGreater(result.invocation_ordinal, 0)
        self.assertFalse(result.row.outcome.completed)
        recorded = read(self.case / "native/consequence-result.json")
        self.assertEqual(canonical_sha256(result.row.document()), canonical_sha256(recorded["row"]))

    def test_canonical_tuple_list_episode_equivalence(self):
        def tuples(value):
            if isinstance(value, list):
                return tuple(tuples(item) for item in value)
            if isinstance(value, dict):
                return {key: tuples(item) for key, item in value.items()}
            return value

        def transform(value):
            phase = value["phases"][-1]
            phase["challenge_episode"] = tuples(phase["challenge_episode"])
            return value

        original = self.load()
        self.store = _StoreProxy(
            self.store, "rcc-result-" + self.kwargs["result_sha256"], transform,
        )
        changed = self.load()
        self.assertEqual(original.episode_sha256, changed.episode_sha256)
        self.assertEqual(original.row.document(), changed.row.document())

    def test_different_typed_contract_refused(self):
        contract = self.kwargs["expected_story_contract"]
        self.kwargs["expected_story_contract"] = replace(
            contract, defeated_event=contract.defeated_event + 1,
        )
        with self.assertRaises(ValueError):
            self.load()

    def test_untyped_contract_refused(self):
        self.kwargs["expected_story_contract"] = {}
        with self.assertRaises(ValueError):
            self.load()

    def test_wrong_native_plan_refused(self):
        self.kwargs["expected_native_plan_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.load()

    def test_changed_source_rejected_even_with_recomputed_declaration_digest(self):
        path = self.case / "scoped-battles/declaration.json"
        changed = read(path)
        changed["source_state_sha256"] = "0" * 64
        self.kwargs["expected_scoped_declaration_sha256"] = canonical_sha256(changed)
        with self.mutate_file(path, lambda value: value.update(source_state_sha256="0" * 64)):
            with self.assertRaises(ValueError):
                self.load()

    def test_changed_native_outcome_refused(self):
        with self.mutate_file(
            self.target_directory() / "outcome.json",
            lambda value: value.update(battle_won=True),
        ):
            with self.assertRaises(ValueError):
                self.load()

    def test_changed_event_contract_refused(self):
        path = self.target_directory() / "events/event-00001.json"

        def change(value):
            value["payload"]["identity"]["train_story_contract"]["defeated_event"] += 1

        with self.mutate_file(path, change):
            with self.assertRaises(ValueError):
                self.load()

    def test_unaccounted_global_call_refused(self):
        path = self.case / "scoped-battles/battle-000-end.json"
        with self.mutate_file(path, lambda value: value.update(calls_after=2)):
            with self.assertRaises(ValueError):
                self.load()

    def test_sealed_cost_change_refused(self):
        def change(value):
            value["row"]["outcome"]["actions"] += 1
            return value

        self.store = _StoreProxy(
            self.store, "rcc-result-" + self.kwargs["result_sha256"], change,
        )
        with self.assertRaises(ValueError):
            self.load()

    def test_changed_native_terminal_event_refused(self):
        path = sorted((self.target_directory() / "events").glob("event-*.json"))[-1]

        def change(value):
            value["payload"]["outcome"]["actor_returned_win"] = True

        with self.mutate_file(path, change):
            with self.assertRaises(ValueError):
                self.load()


def test_untyped_target_rejects_before_store_access():
    class UnusedStore:
        def find_sealed_record(self, *args, **kwargs):
            raise AssertionError("malformed target must reject before evidence access")

    with unittest.TestCase().assertRaises(ValueError):
        module.load_scoped_train_challenge_consequence(
            UnusedStore(), declaration_sha256="0" * 64, result_sha256="0" * 64,
            scoped_output=Path("unused"), expected_scoped_declaration_sha256="0" * 64,
            expected_native_plan_sha256="0" * 64, expected_story_contract={},
        )
