from __future__ import annotations

import hashlib
import json
import runpy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/build_acquisition_replanning_context_plan.py")
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )


def _write(path: Path, value: object) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    assert isinstance(payload, bytes)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _profile(slot_id: str) -> bytes:
    corridor = {
        "source_id": "wild:PokemonMansion1F:grass",
        "label": "Mansion source-local corridor",
        "map_id": int(MapId.POKEMON_MANSION_1F),
        "player_x": 5,
        "player_y": 21,
        "forward_directions": ["up"],
        "starting_endpoint": "south",
        "maximum_legs": 8,
        "maximum_seek_steps": 64,
        "maximum_encounters": 16,
    }
    return build_red_goal_context_profile_payload(
        profile_id=slot_id,
        providers=(
            (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
            (
                GoalKind.ACQUIRE_SPECIES,
                RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                corridor,
            ),
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
            (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}),
            (
                GoalKind.EXPLORE,
                RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
                corridor,
            ),
        ),
    )


def _root(
    slot_id: str,
    *,
    index: int,
    state_sha256: str,
    envelope_sha256: str,
) -> dict[str, object]:
    assignment = hashlib.sha256(f"assignment:{slot_id}".encode()).hexdigest()
    return {
        "assignment_id": assignment,
        "available_goal_kinds": ["acquire_species", "explore"],
        "available_menu_sha256": "1" * 64,
        "binding_manifest_sha256": "2" * 64,
        "capture_id": slot_id,
        "entry_index": index,
        "envelope_file_sha256": "3" * 64,
        "envelope_sha256": envelope_sha256,
        "focus_kind": "acquire_species",
        "policy_context_sha256": "4" * 64,
        "profile_file_sha256": "5" * 64,
        "question_sha256": "6" * 64,
        "root_lineage_id": f"red-goal-root-{assignment}",
        "state_file_sha256": "7" * 64,
        "state_sha256": state_sha256,
    }


def _campaign(root: dict[str, object], source_plan_sha256: str) -> dict[str, object]:
    document: dict[str, object] = {
        "candidate": {},
        "context_plan_sha256": source_plan_sha256,
        "numpy_runtime_sha256": "8" * 64,
        "outcome_objective": {},
        "private_root_identity_sha256": "9" * 64,
        "roots": [root],
        "runner_sha256": "a" * 64,
        "runtime_sha256": "b" * 64,
        "schema": SCRIPT["REPEATABLE_SCHEMA"],
        "skill_manifest_sha256": "c" * 64,
        "source_bundle_sha256": "d" * 64,
        "source_commit": "e" * 40,
        "trials": [],
    }
    return {"campaign_id": SCRIPT["canonical_sha256"](document), **document}


def _paired(
    root: dict[str, object],
    source_plan_sha256: str,
    prior_campaign_sha256: str,
) -> dict[str, object]:
    identity: dict[str, object] = {
        "base": {},
        "behavior": {},
        "candidate": {},
        "context_plan_sha256": source_plan_sha256,
        "development_runner_sha256": "1" * 64,
        "endpoint": {},
        "numpy_runtime_sha256": "2" * 64,
        "prior_campaign_sha256": [prior_campaign_sha256],
        "private_root_identity_sha256": "3" * 64,
        "root": root,
        "root_consumption_sha256": SCRIPT["root_consumption_sha256"](
            state_sha256=str(root["state_sha256"]),
            envelope_sha256=str(root["envelope_sha256"]),
        ),
        "runner_sha256": "4" * 64,
        "runtime_sha256": "5" * 64,
        "schema": SCRIPT["PAIRED_SCHEMA"],
        "selection": {},
        "skill_manifest_sha256": "6" * 64,
        "source_bundle_sha256": "7" * 64,
        "source_commit": "8" * 40,
    }
    return {
        "arms": [],
        **identity,
        "screen_id": SCRIPT["canonical_sha256"](identity),
    }


def test_build_extends_exactly_four_unused_acquisition_profiles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    slot_ids = tuple(f"acquisition-{index}" for index in range(6))
    entries = []
    for slot_id in slot_ids:
        state = tmp_path / f"{slot_id}.state"
        envelope = tmp_path / f"{slot_id}.state.json"
        profile = tmp_path / f"{slot_id}.json"
        state.write_bytes(slot_id.encode("ascii"))
        envelope.write_bytes(_canonical({"slot": slot_id}))
        profile.write_bytes(_profile(slot_id))
        entries.append(
            {
                "envelope": str(envelope),
                "profile": str(profile),
                "slot_id": slot_id,
                "state": str(state),
            }
        )
    source = tmp_path / "source-plan.json"
    source_sha = _write(
        source,
        {
            "entries": entries,
            "registry_sha256": "a" * 64,
            "schema": SCRIPT["PLAN_SCHEMA"],
            "source_commit": "b" * 40,
        },
    )
    catalog = tmp_path / "catalog.json"
    catalog_sha = _write(catalog, {"synthetic": True})
    captures = {
        slot_id: (
            hashlib.sha256(f"state:{slot_id}".encode()).hexdigest(),
            hashlib.sha256(f"envelope:{slot_id}".encode()).hexdigest(),
            hashlib.sha256(slot_id.encode()).hexdigest(),
            hashlib.sha256(_canonical({"slot": slot_id})).hexdigest(),
        )
        for slot_id in slot_ids
    }
    campaign = tmp_path / "campaign.json"
    campaign_document = _campaign(
        _root(
            slot_ids[0],
            index=0,
            state_sha256=captures[slot_ids[0]][0],
            envelope_sha256=captures[slot_ids[0]][1],
        ),
        source_sha,
    )
    campaign_sha = _write(
        campaign,
        campaign_document,
    )
    paired = tmp_path / "paired.json"
    paired_document = _paired(
        _root(
            slot_ids[1],
            index=1,
            state_sha256=captures[slot_ids[1]][0],
            envelope_sha256=captures[slot_ids[1]][1],
        ),
        source_sha,
        campaign_sha,
    )
    paired_sha = _write(
        paired,
        paired_document,
    )

    assignments = {
        slot_id: SimpleNamespace(partition="train", focus_kind=GoalKind.ACQUIRE_SPECIES)
        for slot_id in slot_ids
    }
    registry = SimpleNamespace(
        registry_sha256="a" * 64,
        slots=tuple(SimpleNamespace(slot_id=slot_id) for slot_id in slot_ids),
        assignment=assignments.__getitem__,
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "load_committed_goal_manager_registry_at_revision",
        lambda _root, _revision: registry,
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "_source_attestation",
        lambda _args: {
            "source_commit": "f" * 40,
            "source_bundle_sha256": "1" * 64,
            "runner_sha256": "2" * 64,
        },
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__, "APPROVED_SOURCE_PLAN_SHA256", source_sha
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "APPROVED_CONTEXT_CATALOG_SHA256",
        catalog_sha,
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "APPROVED_PRIOR_CAMPAIGN_SHA256",
        (campaign_sha,),
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__, "APPROVED_PAIRED_PLAN_SHA256", paired_sha
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "_context_catalog",
        lambda _path, *, expected_sha256, registry: SimpleNamespace(),
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "_source_profile_manifest",
        lambda _registry, *, source_plan_sha256: (
            {
                entry["slot_id"]: hashlib.sha256(
                    Path(entry["profile"]).read_bytes()
                ).hexdigest()
                for entry in entries
            },
            "9" * 64,
        ),
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "_source_capture_index",
        lambda _entries, _catalog: captures,
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: tmp_path,
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda _registry, *, exclusive: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "root_claim_is_available",
        lambda _registry, _identity: True,
    )
    args = SimpleNamespace(
        source_plan=source,
        expected_source_plan_sha256=source_sha,
        context_catalog=catalog,
        expected_context_catalog_sha256=catalog_sha,
        prior_campaign=[campaign],
        expected_prior_campaign_sha256=[campaign_sha],
        paired_plan=paired,
        expected_paired_plan_sha256=paired_sha,
        expected_source_commit="f" * 40,
        expected_source_bundle_sha256="1" * 64,
        expected_runner_sha256="2" * 64,
        output_root=tmp_path / "output",
    )

    result = SCRIPT["_run"](args)
    plan = json.loads((tmp_path / "output/plan.json").read_text())

    assert result["extended_unused_acquisition_roots"] == 4
    assert result["excluded_used_acquisition_roots"] == 2
    assert result["controller_actions"] == 0
    manifest = json.loads(
        (tmp_path / "output/profile-lineage.json").read_text()
    )
    assert manifest["output_plan_sha256"] == result["output_plan_sha256"]
    assert len(manifest["entries"]) == 6
    assert sum(bool(row["transformed"]) for row in manifest["entries"]) == 4
    assert all(row["source_profile_sha256"] for row in manifest["entries"])
    for index, entry in enumerate(plan["entries"]):
        profile = parse_red_goal_context_profile(Path(entry["profile"]).read_bytes())
        kinds = tuple(provider.kind for provider in profile.providers)
        assert (GoalKind.DEVELOP_TEAM in kinds) is (index >= 2)


def test_build_rejects_a_changed_source_plan_before_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source-plan.json"
    source.write_bytes(b"{}\n")
    args = SimpleNamespace(
        source_plan=source,
        expected_source_plan_sha256="0" * 64,
        context_catalog=source,
        expected_context_catalog_sha256="0" * 64,
        prior_campaign=[],
        expected_prior_campaign_sha256=[],
        paired_plan=source,
        expected_paired_plan_sha256="0" * 64,
        expected_source_commit="0" * 40,
        expected_source_bundle_sha256="0" * 64,
        expected_runner_sha256="0" * 64,
        output_root=tmp_path / "output",
    )

    monkeypatch.setitem(
        SCRIPT["_run"].__globals__, "_source_attestation", lambda _args: {}
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "_approved_inputs",
        lambda _args: ("0" * 64, "0" * 64, (), "0" * 64),
    )

    try:
        SCRIPT["_run"](args)
    except SCRIPT["AcquisitionReplanningPlanError"] as error:
        assert str(error) == "source plan authentication"
    else:  # pragma: no cover - required fail-closed branch
        raise AssertionError("changed plan was accepted")
    assert not args.output_root.exists()


def test_predecessor_physical_identity_cannot_be_remapped() -> None:
    captures = {
        "slot-a": ("1" * 64, "2" * 64, "3" * 64, "4" * 64),
        "slot-b": ("5" * 64, "6" * 64, "7" * 64, "8" * 64),
    }
    remapped = _root(
        "slot-b",
        index=1,
        state_sha256="1" * 64,
        envelope_sha256="2" * 64,
    )

    try:
        SCRIPT["_physical_slot"](remapped, captures, subject="prior root")
    except SCRIPT["AcquisitionReplanningPlanError"] as error:
        assert str(error) == "prior root physical identity"
    else:  # pragma: no cover - required fail-closed branch
        raise AssertionError("remapped predecessor root was accepted")


def test_main_sanitizes_domain_errors(monkeypatch, capsys) -> None:
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_run",
        lambda _args: (_ for _ in ()).throw(
            RedGoalContextProfileError("/private/profile.json")
        ),
    )
    argv = [
        "--source-plan",
        "source",
        "--expected-source-plan-sha256",
        "0" * 64,
        "--context-catalog",
        "catalog",
        "--expected-context-catalog-sha256",
        "0" * 64,
        "--prior-campaign",
        "campaign",
        "--expected-prior-campaign-sha256",
        "0" * 64,
        "--paired-plan",
        "paired",
        "--expected-paired-plan-sha256",
        "0" * 64,
        "--expected-source-commit",
        "0" * 40,
        "--expected-source-bundle-sha256",
        "0" * 64,
        "--expected-runner-sha256",
        "0" * 64,
        "--output-root",
        "output",
    ]
    try:
        SCRIPT["main"](argv)
    except SystemExit as error:
        assert error.code == 2
    else:  # pragma: no cover - argparse always exits on parser.error
        raise AssertionError("sanitized failure did not exit")
    stderr = capsys.readouterr().err
    assert "private/profile" not in stderr
    assert "Traceback" not in stderr

    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_run",
        lambda _args: (_ for _ in ()).throw(
            SCRIPT["CollectionProtocolError"]("/private/source.py")
        ),
    )
    try:
        SCRIPT["main"](argv)
    except SystemExit as error:
        assert error.code == 2
    else:  # pragma: no cover - argparse always exits on parser.error
        raise AssertionError("sanitized failure did not exit")
    stderr = capsys.readouterr().err
    assert "private/source" not in stderr
    assert "Traceback" not in stderr


def test_capture_inventory_rejects_bytes_that_differ_from_catalog(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = tmp_path / "root.state"
    envelope = tmp_path / "root.state.json"
    state.write_bytes(b"state")
    envelope.write_bytes(b"envelope")
    entry = {
        "envelope": str(envelope),
        "profile": str(tmp_path / "unused.json"),
        "slot_id": "acquisition-root",
        "state": str(state),
    }
    observed = SimpleNamespace(
        capture_id="acquisition-root",
        state_sha256="1" * 64,
        envelope_sha256="2" * 64,
    )
    expected = SimpleNamespace(
        capture_id="acquisition-root",
        state_sha256="3" * 64,
        envelope_sha256="2" * 64,
    )
    catalog = SimpleNamespace(entry=lambda _slot: expected)
    monkeypatch.setitem(
        SCRIPT["_source_capture_index"].__globals__,
        "parse_goal_manager_context_capture",
        lambda _state, _envelope: observed,
    )

    try:
        SCRIPT["_source_capture_index"]((entry,), catalog)
    except SCRIPT["AcquisitionReplanningPlanError"] as error:
        assert str(error) == "source capture authentication"
    else:  # pragma: no cover - required fail-closed branch
        raise AssertionError("catalog-substituted capture was accepted")
