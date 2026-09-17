"""TRAIN-only adapter from admitted executed contrasts to three stat-aware heads."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES as LEGACY_MOVE_NAMES,
)
from pokemon_red_completion.battle_semantics import (
    BattleFeatureBatch,
)
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_features import (
    CONTROL_FEATURE_NAMES_V2,
    CONTROL_SCHEMA_ID,
    MOVE_FEATURE_NAMES,
    MOVE_SCHEMA_ID,
    SWITCH_FEATURE_NAMES_V2,
    SWITCH_SCHEMA_ID,
    project_trainer_control_features,
    project_trainer_move_features,
    project_trainer_switch_features,
)
from pokemon_red_completion.red_trainer_practice_head import (
    TrainerHeadExample,
    TrainerHeadModel,
)

CONTROL_ACTION_FEATURE_NAMES = (
    *CONTROL_FEATURE_NAMES_V2,
    "action.attack_or_decline",
    "action.switch",
)
CONTROL_ACTION_SCHEMA_ID = f"{CONTROL_SCHEMA_ID}.action-v1"


class TrainerPracticeFitError(ValueError):
    """A target set or corpus does not justify a switch-aware fit."""


@dataclass(frozen=True, slots=True)
class TrainerPracticeThreeHeadModel:
    move: TrainerHeadModel
    control: TrainerHeadModel
    switch: TrainerHeadModel
    train_capture_ids: tuple[str, ...]
    train_root_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        expected = (
            (self.move, MOVE_SCHEMA_ID, MOVE_FEATURE_NAMES),
            (self.control, CONTROL_ACTION_SCHEMA_ID, CONTROL_ACTION_FEATURE_NAMES),
            (self.switch, SWITCH_SCHEMA_ID, SWITCH_FEATURE_NAMES_V2),
        )
        if any(
            head.schema_id != schema or head.feature_names != names
            for head, schema, names in expected
        ):
            raise TrainerPracticeFitError("three-head schemas are incompatible")
        if not self.train_capture_ids or not self.train_root_ids:
            raise TrainerPracticeFitError("three-head training lineage is missing")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.trainer-practice-three-head-model.v1",
            "move": self.move.to_dict(),
            "control": self.control.to_dict(),
            "switch": self.switch.to_dict(),
            "train_capture_ids": list(self.train_capture_ids),
            "train_root_ids": list(self.train_root_ids),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> TrainerPracticeThreeHeadModel:
        if value.get("schema") != "pokemon.red.trainer-practice-three-head-model.v1":
            raise TrainerPracticeFitError("three-head model schema differs")
        move_data, control_data, switch_data = (
            value.get("move"),
            value.get("control"),
            value.get("switch"),
        )
        if any(not isinstance(item, Mapping) for item in (move_data, control_data, switch_data)):
            raise TrainerPracticeFitError("three-head checkpoint heads differ")
        assert isinstance(move_data, Mapping)
        assert isinstance(control_data, Mapping)
        assert isinstance(switch_data, Mapping)
        try:
            move = TrainerHeadModel.from_dict(
                move_data,
                schema_id=MOVE_SCHEMA_ID,
                feature_names=MOVE_FEATURE_NAMES,
            )
            control = TrainerHeadModel.from_dict(
                control_data,
                schema_id=CONTROL_ACTION_SCHEMA_ID,
                feature_names=CONTROL_ACTION_FEATURE_NAMES,
            )
            switch = TrainerHeadModel.from_dict(
                switch_data,
                schema_id=SWITCH_SCHEMA_ID,
                feature_names=SWITCH_FEATURE_NAMES_V2,
            )
            capture_ids = value["train_capture_ids"]
            root_ids = value["train_root_ids"]
            if not isinstance(capture_ids, list) or not isinstance(root_ids, list):
                raise TrainerPracticeFitError("three-head lineage differs")
            if any(not isinstance(item, str) or not item for item in (*capture_ids, *root_ids)):
                raise TrainerPracticeFitError("three-head lineage differs")
            return cls(move, control, switch, tuple(capture_ids), tuple(root_ids))
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, TrainerPracticeFitError):
                raise
            raise TrainerPracticeFitError("three-head model checkpoint differs") from error


def fit_trainer_practice_three_heads(
    targets: Iterable[Mapping[str, object]],
    *,
    seed: int,
    catalog: PokemonRedBattleCatalog | None = None,
    require_corpus_floor: bool = True,
    epochs: int = 300,
) -> TrainerPracticeThreeHeadModel:
    records = tuple(targets)
    if not records:
        raise TrainerPracticeFitError("TRAIN target corpus is empty")
    root_counts: Counter[str] = Counter()
    capture_ids: list[str] = []
    for target in records:
        if (
            target.get("schema") != "pokemon.red.trainer-practice-three-head-targets.v1"
            or target.get("partition") != "train"
            or target.get("scenario_count") != 1
            or target.get("observation_schema") != OBSERVATION_SCHEMA_V2
            or not isinstance(target.get("root_lineage_id"), str)
            or not isinstance(target.get("capture_id"), str)
        ):
            raise TrainerPracticeFitError("target lacks admitted TRAIN identity")
        root_counts[target["root_lineage_id"]] += 1  # type: ignore[index]
        capture_ids.append(target["capture_id"])  # type: ignore[arg-type]
    if len(set(capture_ids)) != len(capture_ids):
        raise TrainerPracticeFitError("one capture was counted twice")
    if require_corpus_floor and (
        len(root_counts) < 4 or any(count < 4 for count in root_counts.values())
    ):
        raise TrainerPracticeFitError(
            "four independent TRAIN roots with four scenarios each required"
        )
    if require_corpus_floor and any(target.get("timing_count") != 5 for target in records):
        raise TrainerPracticeFitError("five declared timing offsets per scenario required")
    resolver = catalog if catalog is not None else PokemonRedBattleCatalog()
    examples: dict[str, list[TrainerHeadExample]] = {"move": [], "control": [], "switch": []}
    for target in records:
        _append_examples(examples, target, resolver)
    if any(not examples[head] for head in examples):
        raise TrainerPracticeFitError("move, control and switch contrasts are all required")
    return TrainerPracticeThreeHeadModel(
        move=TrainerHeadModel.fit(
            schema_id=MOVE_SCHEMA_ID,
            feature_names=MOVE_FEATURE_NAMES,
            examples=examples["move"],
            seed=seed,
            epochs=epochs,
        ),
        control=TrainerHeadModel.fit(
            schema_id=CONTROL_ACTION_SCHEMA_ID,
            feature_names=CONTROL_ACTION_FEATURE_NAMES,
            examples=examples["control"],
            seed=seed + 1,
            epochs=epochs,
        ),
        switch=TrainerHeadModel.fit(
            schema_id=SWITCH_SCHEMA_ID,
            feature_names=SWITCH_FEATURE_NAMES_V2,
            examples=examples["switch"],
            seed=seed + 2,
            epochs=epochs,
        ),
        train_capture_ids=tuple(capture_ids),
        train_root_ids=tuple(sorted(root_counts)),
    )


def _append_examples(
    examples: dict[str, list[TrainerHeadExample]],
    target: Mapping[str, object],
    catalog: PokemonRedBattleCatalog,
) -> None:
    observation = target.get("observation")
    heads = target.get("heads")
    if not isinstance(observation, Mapping) or not isinstance(heads, Mapping):
        raise TrainerPracticeFitError("target observation or heads differ")
    base = _legacy_batch(target.get("legacy_model_input"))
    for name in ("move", "control", "switch"):
        head = heads.get(name)
        if head is None:
            continue
        if not isinstance(head, Mapping):
            raise TrainerPracticeFitError("target head differs")
        refs, returns, best = head.get("choice_refs"), head.get("returns"), head.get("best_indices")
        if (
            not isinstance(refs, list)
            or not isinstance(returns, list)
            or not isinstance(best, list)
            or len(refs) != len(returns)
            or len(refs) < 2
            or len(set(refs)) != len(refs)
        ):
            raise TrainerPracticeFitError("target head choice inventory differs")
        if name == "move":
            if base is None:
                raise TrainerPracticeFitError("move input was not retained")
            projected = project_trainer_move_features(observation, base)
            rows = _rows_for_refs(refs, projected.candidate_slots, projected.candidate_vectors)
        elif name == "switch":
            projected = project_trainer_switch_features(observation, catalog)
            rows = _rows_for_refs(refs, projected.candidate_slots, projected.candidate_vectors)
        else:
            common = tuple(
                project_trainer_control_features(
                    observation, catalog=catalog, move_batch=base
                ).tolist()
            )
            attack_value = max(
                float(value)
                for ref, value in zip(refs, returns, strict=True)
                if ":move:" in ref or ref.endswith("decline-switch")
            )
            switch_value = max(
                float(value) for ref, value in zip(refs, returns, strict=True) if ":switch:" in ref
            )
            rows = ((*common, 1.0, 0.0), (*common, 0.0, 1.0))
            best = list(_tied_values((attack_value, switch_value)))
        examples[name].append(TrainerHeadExample(tuple(rows), tuple(best)))


def _tied_values(values: tuple[float, ...]) -> tuple[int, ...]:
    maximum = max(values)
    return tuple(index for index, value in enumerate(values) if maximum - value <= 0.02)


def _rows_for_refs(
    refs: list[object], slots: tuple[int, ...], vectors: tuple[tuple[float, ...], ...]
) -> tuple[tuple[float, ...], ...]:
    rows = []
    for ref in refs:
        if not isinstance(ref, str) or not ref.rsplit(":", 1)[-1].isdecimal():
            raise TrainerPracticeFitError("head choice reference differs")
        slot = int(ref.rsplit(":", 1)[-1])
        if slot not in slots:
            raise TrainerPracticeFitError("chosen slot is absent from actor candidates")
        rows.append(vectors[slots.index(slot)])
    return tuple(rows)


def _legacy_batch(value: object) -> BattleFeatureBatch | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or value.get("feature_names") != list(LEGACY_MOVE_NAMES):
        raise TrainerPracticeFitError("retained move input differs from legacy schema")
    try:
        vectors = tuple(tuple(float(item) for item in row) for row in value["candidate_vectors"])  # type: ignore[index]
        slots = tuple(int(item) - 1 for item in value["candidate_move_slots"])  # type: ignore[index]
        return BattleFeatureBatch(
            feature_names=LEGACY_MOVE_NAMES,
            candidate_vectors=vectors,
            legal_mask=tuple(value["legal_mask"]),  # type: ignore[arg-type]
            current_pp=tuple(value["current_pp"]),  # type: ignore[arg-type]
            slot_indices=slots,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise TrainerPracticeFitError("retained legacy move input is invalid") from error
