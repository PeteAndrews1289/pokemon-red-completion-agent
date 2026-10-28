"""Finite, separately scoped TRAIN actors with one ordered native history.

No trainer selection, model fitting, source creation or partition conversion.
The caller must authenticate the TRAIN source and experiment prospectively.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from .executor import NativeLessonController
from .post_battle_strategy import BattleAftermath, BattleResult
from .provenance import canonical_sha256
from .red_autonomous_player import _record
from .red_learned_trainer import (
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
    FrozenTrainerBattler,
    TrainRiskStoryScope,
)
from .red_player_battle_history import NativeBattlerHistory
from .red_story_battle import StoryTrainerContract
from .scenario_lab import ScenarioPartition


def scoped_train_root_lineage_id(origin_sha256: str) -> str:
    """Canonical private capture lineage for an authenticated TRAIN origin.

    This formats identity only; it does not authenticate a source or grant TRAIN
    authority. Callers retain the original human origin in their prospective plan.
    """
    if (type(origin_sha256) is not str or len(origin_sha256) != 64
            or any(c not in "0123456789abcdef" for c in origin_sha256)):
        raise ValueError("scoped TRAIN origin requires a lowercase SHA256")
    return "red-goal-root-" + origin_sha256


class _ScopedActor(FrozenTrainerBattler):
    _pool: "ScopedTrainingBattlers"

    def _play(self, *args: Any, **kwargs: Any) -> Any:
        if self._pool._production_admission is not None:
            reader = args[0] if args else kwargs.get("reader")
            if reader is not self._pool._production_reader:
                raise ValueError("production TRAIN actor cannot replace its registered reader")
        operation = super()._play
        return self._pool._invoke(self, lambda: operation(*args, **kwargs))


@dataclass(frozen=True)
class ScopedBattleOutcome:
    ordinal: int
    before_frame: int
    after_frame: int
    result: BattleResult
    receipt_sha256: str


class ScopedTrainingBattlers:
    @classmethod
    def for_native_source(
        cls, prototype: FrozenTrainerBattler, *, source: Mapping[str, Any],
        contracts: tuple[StoryTrainerContract, ...], output: Path,
        experiment_sha256: str, initial: BattleAftermath | None = None,
        native_plan_sha256: str | None = None,
    ) -> "ScopedTrainingBattlers":
        """Bind a fresh ordinary K prototype to caller-authenticated source metadata.

        Source custody and the original human origin remain the caller's duty.
        Validate TRAIN/state/commit/origin before the constructor can read the
        native session or create output. Only the cloned root metadata changes;
        model, session, parameters and the original prototype are untouched.
        Embedded risk overrides keep the existing explicit constructor path.
        """
        if not isinstance(source, Mapping):
            raise ValueError("scoped TRAIN native source requires a mapping")
        root = scoped_train_root_lineage_id(source.get("origin_sha256"))
        state, commit = source.get("state_sha256"), source.get("source_commit")
        if (source.get("partition") != "train"
                or type(source.get("partition")) is not str
                or type(state) is not str or len(state) != 64
                or any(c not in "0123456789abcdef" for c in state)
                or type(commit) is not str or len(commit) != 40
                or any(c not in "0123456789abcdef" for c in commit)
                or type(prototype) is not FrozenTrainerBattler
                or prototype.source_partition is not ScenarioPartition.TRAIN
                or prototype.source_state_sha256 != state
                or prototype.source_commit != commit
                or type(prototype.root_lineage_id) is not str
                or not prototype.root_lineage_id):
            raise ValueError("scoped TRAIN native source identity differs")
        existing = prototype.root_lineage_id
        prefix = "red-goal-root-"
        if (existing.startswith(prefix) and len(existing) == len(prefix) + 64
                and all(c in "0123456789abcdef" for c in existing[len(prefix):])
                and existing != root):
            raise ValueError("scoped TRAIN canonical origin differs")
        bound = replace(prototype, root_lineage_id=root)
        return cls(bound, contracts=contracts, output=output,
                   experiment_sha256=experiment_sha256, initial=initial,
                   native_plan_sha256=native_plan_sha256)

    @classmethod
    def for_production_source(cls, wild, story, *, admission, source, output, reader, initial=None):
        """Register exact already-configured actors; never construct another player."""
        from .red_production_train_admission import ProductionTrainAdmission
        if type(admission) is not ProductionTrainAdmission or not isinstance(source, Mapping):
            raise ValueError("production TRAIN pool needs typed admission and source")
        if (source.get("partition") != "train"
            or source.get("state_sha256") != admission.source_state_sha256
            or source.get("origin_sha256") != admission.source_origin_sha256
            or source.get("source_commit") != admission.source_commit
            or source.get("experiment_sha256") != admission.work_order_sha256):
            raise ValueError("production TRAIN pool source differs")
        if (type(wild) is not FrozenTrainerBattler or type(story) is not FrozenTrainerBattler
            or wild.session is not story.session
            or wild.public_species_base_stats != story.public_species_base_stats
            or wild.development_preparation_scope is None
            or story.development_story_scope is None
            or wild.development_preparation_scope.train_admission != admission
            or story.development_story_scope.train_admission != admission):
            raise ValueError("production TRAIN pool actor ownership differs")
        wild.wild_authority(15)
        contract = story.development_story_scope.contract
        story.require_story_contract(contract)
        return cls(wild, contracts=(contract,), output=output,
            experiment_sha256=admission.work_order_sha256, initial=initial,
            native_plan_sha256=admission.work_order_sha256,
            story_overrides=(replace(story, train_story_contract=contract),),
            production_admission=admission, production_reader=reader)

    def __init__(
        self, prototype: FrozenTrainerBattler, *, contracts: tuple[StoryTrainerContract, ...],
        output: Path, experiment_sha256: str, initial: BattleAftermath | None = None,
        native_plan_sha256: str | None = None,
        story_overrides: tuple[FrozenTrainerBattler, ...] = (),
        production_admission=None, production_reader=None,
    ) -> None:
        self._production_admission = production_admission
        self._production_reader = production_reader
        if production_admission is not None:
            from .red_production_train_admission import ProductionTrainAdmission
            if (type(production_admission) is not ProductionTrainAdmission
                or type(prototype) is not FrozenTrainerBattler
                or prototype.development_preparation_scope is None
                or prototype.development_preparation_scope.train_admission != production_admission
                or experiment_sha256 != production_admission.work_order_sha256
                or native_plan_sha256 != production_admission.work_order_sha256
                or len(contracts) != 1 or len(story_overrides) != 1
                or not callable(getattr(production_reader, "read", None))):
                raise ValueError("production TRAIN pool declaration differs")
            prototype.wild_authority(15)
        if (
            type(prototype) is not FrozenTrainerBattler
            or type(prototype.calls) is not int or prototype.calls != 0
            or prototype.source_partition is not ScenarioPartition.TRAIN
            or (production_admission is None and (prototype.model_sha256 != FROZEN_K_SHA256
                or prototype.qualification_sha256 != K_QUALIFICATION_SHA256))
            or prototype.train_story_contract is not None
            or prototype.train_funding_diagnostic is not False
            or prototype.story_chain_scope is not None
            or prototype.train_risk_story_scope is not None
            or prototype.evaluation_story_scope is not None
            or type(contracts) is not tuple or not 1 <= len(contracts) <= 32
            or any(type(c) is not StoryTrainerContract for c in contracts)
            or type(experiment_sha256) is not str or len(experiment_sha256) != 64
            or any(c not in "0123456789abcdef" for c in experiment_sha256)
        ):
            raise ValueError("scoped TRAIN actor declaration differs")
        documents = tuple(asdict(c) for c in contracts)
        if len({canonical_sha256(c) for c in documents}) != len(contracts):
            raise ValueError("scoped TRAIN actor declaration repeats a contract")
        if len({(c.map_id, c.trainer_identity, c.defeated_event)
                for c in contracts}) != len(contracts):
            raise ValueError("scoped TRAIN actor declaration aliases a native trainer")
        if type(story_overrides) is not tuple:
            raise ValueError("TRAIN story overrides must be an explicit tuple")
        overrides = {}
        for actor in story_overrides:
            if (type(actor) is not FrozenTrainerBattler
                or (production_admission is None and type(actor.train_risk_story_scope) is not TrainRiskStoryScope)
                or type(actor.calls) is not int or actor.calls != 0
                or actor.session is not prototype.session
                or actor.source_commit != prototype.source_commit
                or actor.source_state_sha256 != prototype.source_state_sha256
                or actor.root_lineage_id != prototype.root_lineage_id
                or actor.public_species_base_stats != prototype.public_species_base_stats
                or (production_admission is None and actor.train_risk_story_scope.experiment_sha256 != experiment_sha256)
                or (production_admission is not None and (
                    actor.development_story_scope is None
                    or actor.development_story_scope.train_admission != production_admission))):
                raise ValueError("TRAIN story override differs from the declared lesson")
            contract = actor.require_train_story_scope()
            if contract not in contracts or contract in overrides:
                raise ValueError("TRAIN story override is undeclared or duplicated")
            overrides[contract] = actor
        self._frame(prototype)
        if native_plan_sha256 is not None and (
            type(native_plan_sha256) is not str or len(native_plan_sha256) != 64
            or any(c not in "0123456789abcdef" for c in native_plan_sha256)
            or not isinstance(prototype.session, NativeLessonController)
            or prototype.session.frames_executed != 0
            or sha256(prototype.session.save_state_bytes()).hexdigest()
            != prototype.source_state_sha256
        ):
            raise ValueError("scoped TRAIN native plan must bind before any input")
        self._frame_origin = self._frame(prototype)
        self._native_plan_sha256 = native_plan_sha256
        self.output = Path(output)
        self.initial = initial
        self._actors = tuple(_ScopedActor(**{
            **{f.name: getattr(overrides.get(contract, prototype), f.name)
               for f in fields(FrozenTrainerBattler)},
            "output": self.output / f"actor-{i:03d}", "train_story_contract": contract,
        }) for i, contract in enumerate((*contracts, None)))
        self._histories = tuple(
            NativeBattlerHistory(actor, initial=initial) for actor in self._actors
        )
        self._identities = tuple(self._identity(actor) for actor in self._actors)
        for actor in self._actors:
            actor._pool = self
        self._entries: list[dict[str, Any]] = []
        self.receipts: tuple[str, ...] = ()
        self.failed = False
        self._active = False
        declaration = dict(
            schema=("pokemon.red.scoped-train-battlers.v1" if production_admission is None
                else "pokemon.red.scoped-train-battlers.v2"), experiment_sha256=experiment_sha256,
            source_commit=prototype.source_commit, root_lineage_id=prototype.root_lineage_id,
            source_state_sha256=prototype.source_state_sha256, source_partition="train",
            model_sha256=prototype.model_sha256,
            qualification_sha256=prototype.qualification_sha256,
            actors=[dict(index=i, scope="wild" if c is None else "story",
                         contract=None if c is None else asdict(c),
                         model_sha256=self._actors[i].model_sha256,
                         qualification_sha256=self._actors[i].qualification_sha256,
                         train_risk_story_scope=self._actors[i]._train_risk_story_document())
                    for i, c in enumerate((*contracts, None))],
            fit_allowed=False, authority_promotion=False,
            native_plan_sha256=native_plan_sha256, frame_origin=self._frame_origin,
        )
        if production_admission is not None:
            declaration["production_admission"] = production_admission.document()
            for record, actor in zip(declaration["actors"], self._actors, strict=True):
                scope = actor.development_story_scope if record["scope"] == "story" else actor.development_preparation_scope
                record["production_scope"] = scope.document()
        self.declaration_sha256 = canonical_sha256(declaration)
        self.output.mkdir(mode=0o700, exist_ok=False)
        _record(self.output / "declaration.json", declaration)

    @staticmethod
    def _frame(actor: FrozenTrainerBattler) -> int:
        frame = getattr(actor.session, "frame_count", None)
        if type(frame) is not int or frame < 0:
            raise ValueError("scoped TRAIN actor requires a measured session frame counter")
        return frame

    @staticmethod
    def _identity(actor: FrozenTrainerBattler) -> tuple[Any, ...]:
        contract = actor.train_story_contract
        if contract is not None and not isinstance(contract, StoryTrainerContract):
            raise ValueError("scoped TRAIN actor contract type changed")
        return (
            actor.output.resolve(), actor.source_commit, actor.root_lineage_id,
            actor.source_state_sha256, actor.source_partition, actor.model_sha256,
            actor.qualification_sha256, actor.train_funding_diagnostic, actor.story_chain_scope,
            canonical_sha256(None if contract is None else asdict(contract)),
            canonical_sha256(None if actor.train_risk_story_scope is None
                             else actor.train_risk_story_scope.document()),
            id(actor.model), id(actor.session),
            canonical_sha256(sorted(actor.public_species_base_stats.items())),
        )

    def _check(self, *, permit_failed: bool = False) -> None:
        if self._active or (self.failed and not permit_failed):
            raise ValueError("scoped TRAIN actor group is active or stopped")
        if tuple(self._identity(a) for a in self._actors) != self._identities:
            raise ValueError("scoped TRAIN actor identity changed")
        if any(a._pool is not self for a in self._actors):
            raise ValueError("scoped TRAIN actor owner changed")
        for actor in self._actors:
            if self._production_admission is not None:
                if actor.train_story_contract is None:
                    actor.wild_authority(15)
                else:
                    actor.require_train_story_scope()
            if actor.train_risk_story_scope is not None:
                actor.require_train_story_scope()
        if canonical_sha256(json.loads((self.output / "declaration.json").read_bytes())) != (
            self.declaration_sha256
        ):
            raise ValueError("scoped TRAIN actor declaration changed")
        expected = [0] * len(self._actors)
        if set(self.output.glob("battle-*.json")) != {
            self.output / f"battle-{i:03d}-{phase}.json"
            for i in range(len(self._entries)) for phase in ("start", "end")
        }:
            raise ValueError("scoped TRAIN invocation artifact census differs")
        for row in self._entries:
            end = self.output / f"battle-{row['ordinal']:03d}-end.json"
            start = self.output / f"battle-{row['ordinal']:03d}-start.json"
            expected_start = {k: v for k, v in row.items()
                              if k not in {"calls_after", "after_frame", "error"}}
            expected_start["schema"] = "pokemon.red.scoped-train-battle-start.v1"
            if (canonical_sha256(json.loads(end.read_bytes())) != canonical_sha256(row)
                or canonical_sha256(json.loads(start.read_bytes())) != canonical_sha256(
                    expected_start,
                )):
                raise ValueError("scoped TRAIN invocation record changed")
            expected[row["actor"]] += row["calls_after"] - row["calls_before"]
        if any(type(a.calls) is not int or a.calls != n for a, n in zip(
            self._actors, expected, strict=True,
        )):
            raise ValueError("scoped TRAIN actor invocation census differs")

    def story(self, contract: StoryTrainerContract) -> FrozenTrainerBattler:
        self._check()
        self.history()
        matches = [a for a in self._actors if a.train_story_contract == contract
                   and a.train_story_contract is not None]
        if len(matches) != 1:
            raise ValueError("undeclared TRAIN story contract")
        matches[0].require_story_contract(contract)
        return matches[0]

    @property
    def wild(self) -> FrozenTrainerBattler:
        self._check()
        self.history()
        return self._actors[-1]

    def _invoke(self, actor: _ScopedActor, operation: Callable[[], Any]) -> Any:
        self._check()
        self.history()  # Reject missing/tampered older evidence before another battle.
        index = next((i for i, a in enumerate(self._actors) if a is actor), None)
        if index is None:
            raise ValueError("foreign scoped TRAIN actor")
        before = self._frame(actor)
        if self._entries and before < self._entries[-1]["after_frame"]:
            raise ValueError("scoped TRAIN session frame counter moved backward")
        ordinal = len(self._entries)
        start: dict[str, Any] = dict(
            schema="pokemon.red.scoped-train-battle-start.v1", ordinal=ordinal, actor=index,
            declaration_sha256=self.declaration_sha256, calls_before=actor.calls,
            before_frame=before,
        )
        _record(self.output / f"battle-{ordinal:03d}-start.json", start)
        self._active = True
        error = None
        try:
            result = operation()
            if actor.calls != start["calls_before"] + 1:
                raise ValueError("scoped TRAIN dispatch did not produce one battle")
            if self._frame(actor) < before:
                raise ValueError("scoped TRAIN session frame counter moved backward")
            return result
        except BaseException as caught:
            error = dict(type=type(caught).__name__, message=str(caught))
            self.failed = True
            raise
        finally:
            end = dict(
                start, schema="pokemon.red.scoped-train-battle-end.v1", calls_after=actor.calls,
                after_frame=getattr(actor.session, "frame_count", None), error=error,
            )
            self._entries.append(end)
            self._active = False
            _record(self.output / f"battle-{ordinal:03d}-end.json", end)

    def history(self) -> BattleAftermath | None:
        self._check(permit_failed=True)
        latest = [history() for history in self._histories]
        joined = []
        last = self.initial
        for row in self._entries:
            i = row["actor"]
            if row["calls_after"] != row["calls_before"]:
                if row["calls_after"] != row["calls_before"] + 1:
                    raise ValueError("scoped TRAIN actor has unaccounted battles")
                receipt = self._histories[i].receipts[row["calls_before"]]
                joined.append(canonical_sha256(dict(
                    declaration_sha256=self.declaration_sha256, invocation=row,
                    battle_receipt=receipt,
                )))
                last = latest[i]
        if tuple(joined[:len(self.receipts)]) != self.receipts:
            raise ValueError("scoped TRAIN battle history changed")
        self.receipts = tuple(joined)
        return last

    def verified_outcomes(
        self, *, expected_native_plan_sha256: str, expected_declaration_sha256: str,
        source_sha256: str,
    ) -> tuple[ScopedBattleOutcome, ...]:
        """Read complete recorded pool battles; not proof that no bypass actor ran."""
        self.history()
        declaration = json.loads((self.output / "declaration.json").read_bytes())
        if (expected_declaration_sha256 != self.declaration_sha256
            or declaration["native_plan_sha256"] != expected_native_plan_sha256
            or self._native_plan_sha256 != expected_native_plan_sha256
            or declaration["frame_origin"] != self._frame_origin
            or declaration["source_state_sha256"] != source_sha256
            or self.failed):
            raise ValueError("scoped TRAIN loss evidence is not bound to this native run")
        result = []
        for row, receipt in zip(self._entries, self.receipts, strict=True):
            if (row["error"] is not None or row["calls_after"] != row["calls_before"] + 1
                or row["after_frame"] <= row["before_frame"]):
                raise ValueError("scoped TRAIN loss coverage is incomplete")
            outcome = self._histories[row["actor"]].outcomes[row["calls_before"]]
            if outcome.result is BattleResult.UNRESOLVED:
                raise ValueError("unresolved battle cannot be a zero-loss target")
            result.append(ScopedBattleOutcome(
                row["ordinal"], row["before_frame"] - self._frame_origin,
                row["after_frame"] - self._frame_origin, outcome.result, receipt,
            ))
        return tuple(result)


def resolve_story_battler(battler, contract):
    """Resolve only exact opt-in pools; ordinary existing actors are unchanged."""
    return battler.story(contract) if isinstance(battler, ScopedTrainingBattlers) else battler


def validate_scoped_wild_battler(battler):
    """Check a captured pool actor again before preparation travel consumes input."""
    if isinstance(battler, _ScopedActor) and battler._pool.wild is not battler:
        raise ValueError("scoped wild preparation cannot use a story actor")
