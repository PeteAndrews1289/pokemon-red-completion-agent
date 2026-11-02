import json
from hashlib import sha256
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_player_origins as origins
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import ControllerFrameBudgetError


class Emulator:
    instances = []

    def __init__(self, *args, **kwargs):
        self.frame_count = 0
        self.pressed_buttons = set()
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def press(self, button):
        self.pressed_buttons.add(button)

    def release(self, button):
        self.pressed_buttons.discard(button)

    def tick(self, frames):
        self.frame_count += frames

    def save_state_bytes(self):
        return str(self.frame_count).encode()

    def load_state_bytes(self, payload):
        pytest.fail("must not reach delegate state loading")


def fixture(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    (repository / "src/pokemon_red_completion").mkdir(parents=True)
    (repository / "src/pokemon_red_completion/unit.py").write_text("# initial code\n")
    rom = tmp_path / "fixture.gb"
    rom.write_bytes(b"fixture-not-a-cartridge")
    monkeypatch.setattr(origins, "RED_ROM_SHA256", sha256(rom.read_bytes()).hexdigest())
    monkeypatch.setattr(origins, "PyBoyAdapter", Emulator)
    Emulator.instances = []

    def opening(path, *, new_game_timing, _emulator, _executor):
        _executor.execute(MacroAction(MacroActionKind.WAIT, repeat=new_game_timing.boot_frames))
        _executor.execute(MacroAction(MacroActionKind.CONFIRM))
        return SimpleNamespace(passed=True, public_dict=lambda: {"fixture": True})

    monkeypatch.setattr(origins, "run_opening_chapter", opening)
    output = tmp_path / "origins"
    digest = origins.freeze_origin_plan(
        output, repository=repository, source_commit="a" * 40,
        rom_sha256=origins.RED_ROM_SHA256,
    )
    return output, dict(repository=repository, rom_path=rom, expected_plan_sha256=digest)


def test_separate_instances_prospective_partitions_and_durable_transcripts(tmp_path, monkeypatch):
    output, kwargs = fixture(tmp_path, monkeypatch)
    results = [origins.capture_origin(output, key, **kwargs) for key in origins.ASSIGNMENTS]
    assert len(Emulator.instances) == 3
    assert len({id(em) for em in Emulator.instances}) == 3
    assert [r["partition"] for r in results] == ["train", "development", "development"]
    assert len({r["terminal_sha256"] for r in results}) == 3
    for row in results:
        assert row["passed"] and row["actions_attempted"] == row["actions_completed"] == 2
        assert row["state_loads"] == row["policy_queries"] == row["fits"] == 0
        directory = output / row["source_id"]
        assert (directory / "claim.json").exists()
        terminal_hash = sha256((directory / "terminal.state").read_bytes()).hexdigest()
        assert terminal_hash == row["terminal_sha256"]
        receipts = [
            json.loads(p.read_bytes()) for p in sorted(directory.glob("action-*-result.json"))
        ]
        assert origins.canonical_sha256(receipts) == row["transcript_sha256"]
        assert receipts[-1]["end_frame"] == row["frames"]
    with pytest.raises(FileExistsError):
        origins.capture_origin(output, "train-01", **kwargs)
    assert len(Emulator.instances) == 3


@pytest.mark.parametrize("fault", ["load", "frames", "failure"])
def test_failed_creation_retains_claim_and_actual_terminal(tmp_path, monkeypatch, fault):
    output, kwargs = fixture(tmp_path, monkeypatch)

    def fail(path, *, _emulator, _executor, **ignored):
        _executor.execute(MacroAction(MacroActionKind.WAIT, repeat=3))
        if fault == "load":
            _emulator.load_state_bytes(b"old state")
        if fault == "frames":
            _executor.execute(MacroAction(MacroActionKind.WAIT, repeat=80001))
        raise ValueError("opening failed")

    monkeypatch.setattr(origins, "run_opening_chapter", fail)
    with pytest.raises((ValueError, ControllerFrameBudgetError)):
        origins.capture_origin(output, "train-01", **kwargs)
    row = json.loads((output / "train-01/result.json").read_bytes())
    assert not row["passed"] and row["frames"] == 3
    assert (output / "train-01/terminal.state").read_bytes() == b"3"
    with pytest.raises(FileExistsError):
        origins.capture_origin(output, "train-01", **kwargs)


@pytest.mark.parametrize("fault", ["code", "rom", "plan", "source"])
def test_preflight_refuses_before_initialization(tmp_path, monkeypatch, fault):
    output, kwargs = fixture(tmp_path, monkeypatch)
    source_id = "train-01"
    if fault == "code":
        (kwargs["repository"] / "src/pokemon_red_completion/unit.py").write_text("# changed\n")
    if fault == "rom":
        kwargs["rom_path"].write_bytes(b"changed")
    if fault == "plan":
        kwargs["expected_plan_sha256"] = "0" * 64
    if fault == "source":
        source_id = "invented"
    with pytest.raises(ValueError):
        origins.capture_origin(output, source_id, **kwargs)
    assert not Emulator.instances and not (output / source_id).exists()


@pytest.mark.parametrize("tranche,assignments", [
    ("comparison-05-06", origins.BRANCH_COMPARISON_ASSIGNMENTS),
    ("comparison-07-08", origins.PREPARATION_COMPARISON_ASSIGNMENTS),
    ("comparison-09-10", origins.FOCUSED_PREPARATION_COMPARISON_ASSIGNMENTS),
    ("comparison-11-12", origins.CONNECTED_PREPARATION_COMPARISON_ASSIGNMENTS),
])
def test_branch_tranche_cannot_reopen_prior_assignments(
    tmp_path, monkeypatch, tranche, assignments,
):
    _, kwargs = fixture(tmp_path, monkeypatch)
    output = tmp_path / 'branch-origins'
    digest = origins.freeze_origin_plan(output, repository=kwargs['repository'],
        source_commit='b'*40, rom_sha256=origins.RED_ROM_SHA256,tranche=tranche)
    kwargs['expected_plan_sha256'] = digest
    old = (set(origins.ASSIGNMENTS) | set(origins.COMPARISON_ASSIGNMENTS)
           | (set(origins.BRANCH_COMPARISON_ASSIGNMENTS) - set(assignments))
           | (set(origins.PREPARATION_COMPARISON_ASSIGNMENTS) - set(assignments))
           | (set(origins.FOCUSED_PREPARATION_COMPARISON_ASSIGNMENTS) - set(assignments))
           | (set(origins.CONNECTED_PREPARATION_COMPARISON_ASSIGNMENTS) - set(assignments)))
    for name in old:
        with pytest.raises(ValueError):
            origins.capture_origin(output,name,**kwargs,tranche=tranche)
    assert not Emulator.instances
    rows = [origins.capture_origin(output,name,**kwargs,tranche=tranche)
            for name in assignments]
    assert all(r['partition']=='development' and r['state_loads']==0 for r in rows)
    assert len(Emulator.instances)==2
    with pytest.raises(FileExistsError):
        origins.capture_origin(output,next(iter(assignments)),**kwargs,tranche=tranche)


def test_focused_preparation_tranche_is_exact_and_not_a_training_allocation():
    assignments, schema, authorization = origins._tranche("comparison-09-10")
    assert assignments == {
        "comparison-09": ("development", 337),
        "comparison-10": ("development", 373),
    }
    assert schema == "pokemon.red.player-independent-origins.v5"
    assert authorization == "docs/work-sessions/2026-09-30-learned-preparation-v1.md"
    assert dict(actions=450, frames=80000, seconds=180) == origins.LIMITS
    with pytest.raises(ValueError, match="undeclared"):
        origins._tranche("comparison-13-14")


def test_connected_preparation_origins_are_two_development_starts_only():
    assignments, schema, authorization = origins._tranche("comparison-11-12")
    assert assignments == {
        "comparison-11": ("development", 409),
        "comparison-12": ("development", 443),
    }
    assert schema == "pokemon.red.player-independent-origins.v6"
    assert authorization == "docs/work-sessions/2026-09-30-preparation-three-gates.md"
    assert set(assignments).isdisjoint(origins.FOCUSED_PREPARATION_COMPARISON_ASSIGNMENTS)
    assert dict(actions=450, frames=80000, seconds=180) == origins.LIMITS
