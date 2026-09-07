"""Player-native model records; historical campaign records remain unchanged."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.living_dex_goal_model_record import (
    LivingDexGoalModelRecord,
    load_living_dex_goal_model_record_bytes,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel

PLAYER_MODEL_SCHEMA = "pokemon.red.native-player-model.v1"


@dataclass(frozen=True, slots=True)
class RedPlayerModelRecord:
    model: LivingDexOptionValueModel
    file_sha256: str
    source_commit: str
    source_bundle_sha256: str
    corpus_sha256: str
    prior_model_sha256: str
    retained_example_sha256: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": PLAYER_MODEL_SCHEMA,
            "authority": "bounded_development_only",
            "file_sha256": self.file_sha256,
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "model_sha256": self.model.model_sha256,
            "corpus_sha256": self.corpus_sha256,
            "settled_examples": self.model.settled_examples,
            "prior_model_sha256": self.prior_model_sha256,
            "independent_evaluation": False,
            "ci_is_training_dependency": False,
            "private_path_fields": 0,
        }


def load_player_goal_model_record(
    path: Path, *, expected_model_sha256: str
) -> LivingDexGoalModelRecord | RedPlayerModelRecord:
    payload = path.read_bytes()
    return load_player_goal_model_record_bytes(payload, expected_model_sha256=expected_model_sha256)


def load_player_goal_model_record_bytes(
    payload: bytes, *, expected_model_sha256: str
) -> LivingDexGoalModelRecord | RedPlayerModelRecord:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate player model field")
            result[key] = value
        return result

    document = json.loads(payload, object_pairs_hook=unique)
    if not isinstance(document, dict) or document.get("schema") != PLAYER_MODEL_SCHEMA:
        return load_living_dex_goal_model_record_bytes(
            payload, expected_model_sha256=expected_model_sha256
        )
    if (
        set(document)
        != {
            "schema",
            "authority",
            "model",
            "model_sha256",
            "source_commit",
            "source_bundle_sha256",
            "corpus_sha256",
            "prior_model_sha256",
            "retained_example_sha256",
        }
        or document["authority"] != "bounded_development_only"
    ):
        raise ValueError("native player model contract differs")
    for key in ("model_sha256", "source_bundle_sha256", "corpus_sha256", "prior_model_sha256"):
        if (
            not isinstance(document[key], str)
            or re.fullmatch(r"[0-9a-f]{64}", document[key]) is None
        ):
            raise ValueError("native player model digest differs")
    if (
        not isinstance(document["source_commit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", document["source_commit"]) is None
    ):
        raise ValueError("native player model source differs")
    model = LivingDexOptionValueModel.from_dict(document["model"])
    hashes = document["retained_example_sha256"]
    if (
        model.model_sha256 != expected_model_sha256
        or document["model_sha256"] != expected_model_sha256
        or not isinstance(hashes, list)
        or len(hashes) != model.settled_examples + model.censored_examples
        or any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in hashes
        )
        or len(set(hashes)) != len(hashes)
    ):
        raise ValueError("native player model corpus binding differs")
    return RedPlayerModelRecord(
        model,
        hashlib.sha256(payload).hexdigest(),
        document["source_commit"],
        document["source_bundle_sha256"],
        document["corpus_sha256"],
        document["prior_model_sha256"],
        tuple(hashes),
    )
