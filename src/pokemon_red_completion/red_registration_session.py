"""Private frozen batch bindings and durable imports from authenticated Red state.

Only the launcher, after authenticating a restore or completed terminal, calls
these functions. A ledger digest alone is not proof of gameplay.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .collection import CollectionLocation, CollectionObservation, LivingSpecimen
from .private_artifacts import PrivateArtifactRoot
from .provenance import canonical_sha256
from .red_collection import RED_COLLECTION_GAME_ID, red_species_ref
from .red_goal_manager import RedGoalObservation
from .red_registration_policy import RedRegistrationPolicy
from .registration_memory import (
    RegistrationMemory,
    RegistrationObservation,
    RegistrationSnapshot,
    observation_from_collection,
)

SESSION_KIND = "red_registration_session"
SESSION_SCHEMA = "pokemon.red.private-registration-session.v1"


def read_registration_state(
    emulator: Any, runtime: Any
) -> tuple[RedGoalObservation, frozenset[int]]:
    """Observe an exact stable field state; sampling may never advance the game."""
    state, frame = emulator.save_state_bytes(), emulator.frame_count
    observed = runtime.adapter.observe()
    seen = runtime.reader.read_pokedex_state().seen_species
    if (
        emulator.save_state_bytes() != state
        or emulator.frame_count != frame
        or emulator.pressed_buttons
        or observed.raw.battle_state
        or not observed.input_ready
    ):
        raise ValueError("registration import needs an action-free stable field")
    return observed, frozenset(seen)


def validate_terminal_registration(
    terminal: dict[str, Any],
    policy: RedRegistrationPolicy,
    *,
    sequence: int,
    rom_sha256: str,
) -> RegistrationObservation:
    """Join registration evidence to an already authenticated terminal checkpoint."""
    from .red_player_checkpoint import (
        REGISTERED_PLAYER_CHECKPOINT_SCHEMA,
        REGISTERED_RECOVERY_CHECKPOINT_SCHEMA,
    )
    from .red_recorded_support import (
        REGISTERED_MEASURED_CHECKPOINT_SCHEMA,
        REGISTERED_SUPPORT_CHECKPOINT_SCHEMA,
    )
    from .registered_checkpoint import RegisteredCollectionCheckpoint

    if terminal.get("schema") not in {
        REGISTERED_PLAYER_CHECKPOINT_SCHEMA,
        REGISTERED_RECOVERY_CHECKPOINT_SCHEMA,
        REGISTERED_SUPPORT_CHECKPOINT_SCHEMA,
        REGISTERED_MEASURED_CHECKPOINT_SCHEMA,
    }:
        raise ValueError("registered terminal schema differs")
    checkpoint = RegisteredCollectionCheckpoint.from_public(terminal["collection"])
    row = registration_row(terminal["registration_observation"])
    if (
        checkpoint.binding_sha256 != policy.sha256
        or row.run_id != policy.run_id
        or row.sequence != sequence
        or row.cartridge_sha256 != rom_sha256
        or row.game_id != RED_COLLECTION_GAME_ID
        or row.adapter_id != "red-registration-v1"
        or row.snapshot_sha256 != terminal["state_sha256"]
        or {red_species_ref(n) for n in row.owned} != set(checkpoint.local_species)
        or {red_species_ref(n): count for n, count in row.physical_counts.items()}
        != dict(checkpoint.specimen_counts)
    ):
        raise ValueError("registered terminal evidence differs from its saved state")
    return row


def session_record_id(name: str) -> str:
    if not isinstance(name, str) or not name or len(name) > 100:
        raise ValueError("registration session name differs")
    return "rrs-" + canonical_sha256({"name": name, "schema": SESSION_SCHEMA})


def registration_row(document: Any) -> RegistrationObservation:
    if not isinstance(document, dict):
        raise ValueError("registration observation document differs")
    data = dict(document)
    data.pop("schema", None)
    pairs = data.pop("physical_counts", ())
    if not isinstance(pairs, list) or len(dict(pairs)) != len(pairs):
        raise ValueError("registration physical inventory differs")
    result = RegistrationObservation(**data, physical_counts=dict(pairs))
    if result.document() != document:
        raise ValueError("registration observation schema differs")
    return result


def observe_registration(
    observed: RedGoalObservation,
    *,
    seen: frozenset[int],
    run_id: str,
    rom_sha256: str,
    snapshot_sha256: str,
    sequence: int,
) -> RegistrationObservation:
    return observation_from_collection(
        observed.collection_observation,
        seen_species=frozenset(red_species_ref(n) for n in seen),
        national_ids={red_species_ref(n): n for n in range(1, 152)},
        run_id=run_id,
        game_id=RED_COLLECTION_GAME_ID,
        adapter_id="red-registration-v1",
        cartridge_sha256=rom_sha256,
        snapshot_sha256=snapshot_sha256,
        sequence=sequence,
    )


def publish_registration_session(
    store: PrivateArtifactRoot,
    *,
    name: str,
    ledger_path: Path,
    observation: RedGoalObservation,
    row: RegistrationObservation,
    anchor_episode_id: str,
    anchor_checkpoint_sha256: str,
) -> dict[str, Any]:
    """Freeze once after a read-only authenticated restore; no controller access."""
    ledger = RegistrationMemory(ledger_path)
    ledger.record(row)
    memory = ledger.snapshot()
    # Protect actual party occupants conservatively (HM/story roles included).
    # Boxed surplus remains available; no artificial spare-base-form quota.
    protected: dict[str, int] = {}
    for specimen in observation.collection_observation.specimens:
        if specimen.location is CollectionLocation.PARTY:
            protected[specimen.species_ref] = protected.get(specimen.species_ref, 0) + 1
    policy = RedRegistrationPolicy(
        memory,
        row.run_id,
        row.snapshot_sha256,
        observation.collection_observation,
        protected,
    )
    collection = asdict(observation.collection_observation)
    collection["owned_species"] = sorted(collection["owned_species"])
    # JSON normalizes tuples/enums without creating a game observation.
    collection = json.loads(json.dumps(collection))
    document = {
        "schema": SESSION_SCHEMA,
        "policy_sha256": policy.sha256,
        "anchor_episode_id": anchor_episode_id,
        "anchor_checkpoint_sha256": anchor_checkpoint_sha256,
        "policy": policy.document(),
        "memory": json.loads(memory.export_json()),
        "initial_collection": collection,
    }
    store.publish_sealed_record(session_record_id(name), kind=SESSION_KIND, record=document)
    return document


def load_registration_policy(document: dict[str, Any]) -> RedRegistrationPolicy:
    if document.get("schema") != SESSION_SCHEMA:
        raise ValueError("registration session schema differs")
    memory = RegistrationSnapshot(
        tuple(registration_row(r) for r in document["memory"]["observations"])
    )
    if json.loads(memory.export_json()) != document["memory"]:
        raise ValueError("registration session memory differs")
    data = dict(document["initial_collection"])
    data["owned_species"] = frozenset(data["owned_species"])
    data["box_counts"] = tuple(data["box_counts"])
    data["specimens"] = tuple(
        LivingSpecimen(
            **{**s, "location": CollectionLocation(s["location"])},
        )
        for s in data["specimens"]
    )
    initial = CollectionObservation(**data)
    binding = document["policy"]
    result = RedRegistrationPolicy(
        memory,
        binding["run_id"],
        binding["initial_snapshot_sha256"],
        initial,
        binding["protected_counts"],
    )
    if result.document() != binding or result.sha256 != document["policy_sha256"]:
        raise ValueError("registration session policy differs")
    return result
