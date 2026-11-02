"""New comparison supply cannot quietly reopen the old fixed assignments."""
import json

import pytest
from test_red_player_origins import Emulator, fixture

import pokemon_red_completion.red_player_origins as origins


def fresh(tmp_path, monkeypatch):
    _, kwargs = fixture(tmp_path, monkeypatch)
    output = tmp_path / "comparison"
    kwargs["tranche"] = "comparison-03-04"
    kwargs["expected_plan_sha256"] = origins.freeze_origin_plan(
        output, repository=kwargs["repository"], source_commit="a" * 40,
        rom_sha256=origins.RED_ROM_SHA256, tranche=kwargs["tranche"],
    )
    return output, kwargs


def test_new_tranche_is_exactly_two_development_initializations(tmp_path, monkeypatch):
    output, kwargs = fresh(tmp_path, monkeypatch)
    plan = json.loads((output / "plan.json").read_bytes())
    assert plan["schema"] == "pokemon.red.player-independent-origins.v2"
    assert plan["limits"] == dict(actions=450, frames=80000, seconds=180)
    assert set(plan["assignments"]) == {"comparison-03", "comparison-04"}
    rows = [origins.capture_origin(output, x, **kwargs) for x in plan["assignments"]]
    assert len(Emulator.instances) == 2
    assert all(r["passed"] and r["partition"] == "development" for r in rows)
    assert all(r["state_loads"] == r["policy_queries"] == r["fits"] == 0 for r in rows)
    with pytest.raises(FileExistsError):
        origins.capture_origin(output, "comparison-03", **kwargs)
    assert len(Emulator.instances) == 2


@pytest.mark.parametrize("source_id", [
    "train-01", "comparison-01", "comparison-02", "comparison-05",
])
def test_old_or_additional_assignments_cannot_initialize(tmp_path, monkeypatch, source_id):
    output, kwargs = fresh(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        origins.capture_origin(output, source_id, **kwargs)
    assert not Emulator.instances and not (output / source_id).exists()


@pytest.mark.parametrize("fault", [
    "partition", "offset", "caps", "code", "commit", "schema", "authorization",
    "checkpoint", "tranche",
])
def test_rehashed_modified_plan_is_not_authority(tmp_path, monkeypatch, fault):
    output, kwargs = fresh(tmp_path, monkeypatch)
    plan = json.loads((output / "plan.json").read_bytes())
    if fault == "partition":
        plan["assignments"]["comparison-03"]["partition"] = "train"
    elif fault == "offset":
        plan["assignments"]["comparison-03"]["extra_boot_frames"] += 1
    elif fault == "caps":
        plan["limits"]["actions"] += 1
    elif fault == "code":
        plan["source_bundle_sha256"] = "0" * 64
    elif fault == "commit":
        plan["source_commit"] = "invalid"
    elif fault == "tranche":
        kwargs["tranche"] = "initial"
    else:
        plan[fault] = "changed"
    (output / "plan.json").write_text(json.dumps(plan))
    kwargs["expected_plan_sha256"] = origins.canonical_sha256(plan)
    with pytest.raises(ValueError):
        origins.capture_origin(output, "comparison-03", **kwargs)
    assert not Emulator.instances and not (output / "comparison-03").exists()


def test_no_save_input_parameter_and_no_snapshot_load_during_creation(tmp_path, monkeypatch):
    output, kwargs = fresh(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        origins.capture_origin(output, "comparison-03", save_path="existing.sav", **kwargs)
    assert not Emulator.instances

    def opening(path, *, _emulator, **kw):
        _emulator.load_state_bytes(b"old state")

    monkeypatch.setattr(origins, "run_opening_chapter", opening)
    with pytest.raises(ValueError, match="never load"):
        origins.capture_origin(output, "comparison-03", **kwargs)
    result = json.loads((output / "comparison-03/result.json").read_bytes())
    assert not result["passed"] and result["frames"] == 0
    assert (output / "comparison-03/terminal.state").exists()
