"""ROM-free fault injection into the configured copy wrapper."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as NS
import json
import pytest
import run_configured_red_player as driver
import pokemon_red_completion.red_level_evolution_options as options
import pokemon_red_completion.red_player_party_loan as party_loan


class NativeControllerFault(RuntimeError):
    reason_code = "controller_frame_limit"


def chained_execution_failure():
    try:
        raise NativeControllerFault("counted native tail")
    except NativeControllerFault as cause:
        raise RuntimeError("route wrapper") from cause


@pytest.mark.parametrize("export_fails", [False, True])
@pytest.mark.parametrize("observed_debits", [0, 13])
def test_copy_failure_retains_causes_terminal_and_costs(tmp_path, monkeypatch, export_fails, observed_debits):
    @dataclass
    class World:
        full_event_offsets: bool = False
        observe_terrain: bool = False
        route_world: str = "world"

    class Emulator:
        frame_count = 0
        pressed_buttons = set()
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def load_state_bytes(self, payload): pass
        def save_state_bytes(self): return b"exact-failed-terminal"

    rom = tmp_path / "fixture.rom"
    rom.write_bytes(b"fixture-only")
    reader = NS(preparation_specimen_refs=lambda: ("retained",))
    guard = NS(refs=("retained",), reader=reader)
    runtime = NS(adapter=NS(party_guard=guard,
        observe=lambda: NS(collection_observation=NS(specimens=()))))
    controller = NS(input_enabled=True, frames_executed=49)
    recorder = NS(enabled=False, trace=list(range(7)))
    session = NS(runtime=runtime, actions=NS(actions_executed=7,observe_cash=lambda:1,
        observed_cash_debits=observed_debits,observed_cash_rewards=27,observed_cash_changes=3), recorder=recorder,
        controller=controller, wall=NS(elapsed_seconds=1.5),
        heals=2, training_healing_trips=1, support_restorations=1)
    holder = {"plan": NS(roster=()), "observe_history": lambda: None}
    monkeypatch.setattr(driver, "assemble_configured_player", lambda *a, **k:
        (b"source", lambda _: None, None, holder, NS()))
    monkeypatch.setattr(driver, "initialize_private_root", lambda *a, **k: NS())
    monkeypatch.setattr(driver, "NativePlayerSession", lambda **k: session)
    monkeypatch.setattr(driver, "_field_ready", lambda _: True)
    monkeypatch.setattr(driver, "authenticate_parent", lambda *a: None)
    monkeypatch.setattr(driver, "verify_pins", lambda _: None)
    monkeypatch.setattr(party_loan, "_stock", lambda _: Counter([("trainee", 88, 18, 7290)]))
    monkeypatch.setattr(options, "enumerate_red_level_evolutions", lambda *a, **k: ())
    binding = NS(binding_ref="fixture-binding", execute=chained_execution_failure)
    monkeypatch.setattr(driver, "evolution_copy_choice", lambda *a:
        (NS(binding=binding, execution_effort=.1),
         NS(parameters={"source_species_ref": "pokemon:national:147"})))
    def export(*args, spent, **kwargs):
        if export_fails:
            try:
                raise OSError("export sink unavailable")
            except OSError as cause:
                raise ValueError("context export failed") from cause
        return {"spent": spent, "state_sha256": sha256(b"exact-failed-terminal").hexdigest()}
    monkeypatch.setattr(driver, "capture_player_continuation", export)
    digest = lambda p: sha256(Path(p).read_bytes()).hexdigest()
    backend = NS(c=NS(PyBoyAdapter=lambda _: Emulator(), ROM=rom, REPO=tmp_path,
        digest=digest), shared=NS(RedVermilionGroundTransition=NS(from_rom=lambda _: World())))
    plan = dict(cutoff_utc=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
        seed=11, protected={})
    prior = dict(decisions=2, actions=11, frames=17, seconds=3., heals=4, cash_debits=5)
    driver.verify_evolution_copy(NS(seconds=90), plan, tmp_path, backend,
        NS(sha256="c"*64, goal_model_sha256="d"*64, to_dict=lambda: {}),
        tmp_path/"parent", dict(state_sha256="a"*64, spent=prior),
        dict(actions=20000, frames=2000000, decisions=1, seconds=90, heals=10))
    folder = next(tmp_path.glob("diagnostics/evolution-*"))
    result = json.loads((folder/"RESULT.json").read_text())
    assert not result["passed"]
    assert result["error"] == "route wrapper"
    assert result["error_chain"] == [
        {"error_type": "RuntimeError", "error": "route wrapper"},
        {"error_type": "NativeControllerFault", "error": "counted native tail",
         "reason_code": "controller_frame_limit"}]
    assert (result["actions"], result["frames"], result["heals"], result["seconds"]) == (7,49,2,1.5)
    assert controller.input_enabled is False and recorder.enabled is False
    assert result["released"] and result["original_roles_restored"]
    assert (folder/"terminal.state").read_bytes() == b"exact-failed-terminal"
    assert result["state_sha256"] == digest(folder/"terminal.state")
    if export_fails:
        assert not (folder/"CONTEXT.json").exists()
        assert result["context_error_type"] == "ValueError"
        assert [r["error_type"] for r in result["context_error_chain"]] == ["ValueError","OSError"]
    else:
        context = json.loads((folder/"CONTEXT.json").read_text())
        assert context["spent"] == dict(decisions=3,actions=18,frames=66,seconds=4.5,heals=6,cash_debits=5+observed_debits)
        assert result["context_sha256"] == digest(folder/"CONTEXT.json")
