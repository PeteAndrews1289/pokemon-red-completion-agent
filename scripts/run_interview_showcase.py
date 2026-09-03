#!/usr/bin/env python3
# ruff: noqa: E501
"""Run four authentic Red states as a truthful, view-only interview showcase."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.actions import MacroAction, MacroActionKind  # noqa: E402
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.progress_dashboard import encode_rgb_png  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8768
CAPTURE_IDS = (
    "red-goal-v1-044-restore_team-validation-02",
    "red-goal-v1-061-manage_storage-validation-01",
    "red-goal-v1-035-evolve_species-validation-02",
    "red-goal-v1-016-acquire_species-validation-01",
)


class InterviewShowcaseError(RuntimeError):
    """Raised when the showcase cannot authenticate its display inputs."""


@dataclass(frozen=True, slots=True)
class Probe:
    capture_id: str
    available_goal_kinds: tuple[str, ...]
    selected_kind: str
    state_path: Path
    receipt_sha256: str
    model_sha256: str

    def public_dict(
        self,
        *,
        ordinal: int,
        logical_frame: int,
        controller_actions: int,
        last_action: str,
    ) -> dict[str, object]:
        return {
            "ordinal": ordinal,
            "label": _label(self.capture_id),
            "available_goal_kinds": list(self.available_goal_kinds),
            "selected_kind": self.selected_kind,
            "candidate_count": len(self.available_goal_kinds),
            "logical_frame": logical_frame,
            "receipt_sha256": self.receipt_sha256,
            "model_sha256": self.model_sha256,
            "controller_actions": controller_actions,
            "last_action": last_action,
        }


class _FrameStore:
    def __init__(
        self,
        probes: tuple[Probe, ...],
        *,
        emulation_multiplier: int,
        movement_demo: bool,
    ) -> None:
        self.probes = probes
        self.emulation_multiplier = emulation_multiplier
        self.movement_demo = movement_demo
        self._lock = threading.Lock()
        self._frames = [b""] * len(probes)
        self._logical_frames = [0] * len(probes)
        self._controller_actions = [0] * len(probes)
        self._last_actions = ["waiting"] * len(probes)
        self.started_at = time.monotonic()

    def publish(self, ordinal: int, payload: bytes, logical_frame: int) -> None:
        with self._lock:
            self._frames[ordinal] = payload
            self._logical_frames[ordinal] = logical_frame

    def frame(self, ordinal: int) -> tuple[bytes, int]:
        with self._lock:
            return self._frames[ordinal], self._logical_frames[ordinal]

    def record_action(self, ordinal: int, action: str) -> None:
        with self._lock:
            self._controller_actions[ordinal] += 1
            self._last_actions[ordinal] = action

    def status(self) -> bytes:
        with self._lock:
            logical_frames = tuple(self._logical_frames)
            controller_actions = tuple(self._controller_actions)
            last_actions = tuple(self._last_actions)
        document = {
            "schema": "pokemon.red.interview-showcase.v1",
            "status": "running",
            "view_only": True,
            "controller_authority": (
                "deterministic_demonstration_only_model_authority_locked"
                if self.movement_demo
                else "locked_pending_paired_episode_gate"
            ),
            "movement_demo": self.movement_demo,
            "emulators": len(self.probes),
            "emulation_multiplier": self.emulation_multiplier,
            "total_logical_frames": sum(logical_frames),
            "total_controller_actions": sum(controller_actions),
            "uptime_seconds": round(time.monotonic() - self.started_at, 1),
            "planner_agreement": {"agreed": 4, "compared": 4},
            "probes": [
                probe.public_dict(
                    ordinal=index,
                    logical_frame=logical_frames[index],
                    controller_actions=controller_actions[index],
                    last_action=last_actions[index],
                )
                for index, probe in enumerate(self.probes)
            ],
        }
        return json.dumps(document, separators=(",", ":"), sort_keys=True).encode("ascii")


class _FrameObserver:
    def __init__(self, store: _FrameStore, ordinal: int) -> None:
        self.store = store
        self.ordinal = ordinal
        self._next_capture_at = 0.0

    def wants_frame(self, logical_frame: int) -> bool:
        del logical_frame
        now = time.monotonic()
        if now < self._next_capture_at:
            return False
        self._next_capture_at = now + 0.125
        return True

    def publish_frame(self, width: int, height: int, rgb: bytes, logical_frame: int) -> None:
        self.store.publish(
            self.ordinal,
            encode_rgb_png(width, height, rgb),
            logical_frame,
        )


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, store: _FrameStore, port: int) -> None:
        self.store = store
        super().__init__((HOST, port), _Handler)


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", _HTML.encode())
            return
        if path == "/api/status":
            self._send(HTTPStatus.OK, "application/json", self.server.store.status())
            return
        if path.startswith("/frame/") and path.endswith(".png"):
            try:
                ordinal = int(path.removeprefix("/frame/").removesuffix(".png"))
                payload, version = self.server.store.frame(ordinal)
            except (ValueError, IndexError):
                self._send(HTTPStatus.NOT_FOUND, "text/plain", b"not found\n")
                return
            if not payload:
                self._send(HTTPStatus.SERVICE_UNAVAILABLE, "text/plain", b"warming up\n")
                return
            self._send(
                HTTPStatus.OK,
                "image/png",
                payload,
                etag=f'"frame-{ordinal}-{version}"',
            )
            return
        if path == "/healthz":
            self._send(HTTPStatus.OK, "text/plain", b"ok\n")
            return
        self._send(HTTPStatus.NOT_FOUND, "text/plain", b"not found\n")

    def _send(
        self,
        status: HTTPStatus,
        content_type: str,
        payload: bytes,
        *,
        etag: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
        )
        if etag is not None:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--preflight-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--emulation-multiplier", type=int, default=4)
    parser.add_argument("--movement-demo", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    return parser


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_probes(capture_dir: Path, preflight_dir: Path) -> tuple[Probe, ...]:
    receipts: dict[str, dict[str, object]] = {}
    for path in sorted(preflight_dir.glob("*.json")):
        value = json.loads(path.read_text(encoding="ascii"))
        if isinstance(value, dict) and isinstance(value.get("capture_id"), str):
            receipts[value["capture_id"]] = {**value, "_receipt_sha256": _sha256(path)}
    probes: list[Probe] = []
    for capture_id in CAPTURE_IDS:
        state_path = capture_dir / f"{capture_id}.state"
        receipt = receipts.get(capture_id)
        if receipt is None or not state_path.is_file():
            raise InterviewShowcaseError(f"missing authenticated probe {capture_id}")
        if _sha256(state_path) != receipt.get("capture_state_sha256"):
            raise InterviewShowcaseError(f"state authentication failed for {capture_id}")
        choices = receipt.get("choices")
        kinds = receipt.get("available_goal_kinds")
        if (
            not isinstance(choices, list)
            or len(choices) != 2
            or not isinstance(kinds, list)
            or not all(isinstance(item, str) for item in kinds)
            or any(not isinstance(item, dict) for item in choices)
            or choices[0].get("selected_kind") != choices[1].get("selected_kind")
        ):
            raise InterviewShowcaseError(f"preflight contract failed for {capture_id}")
        probes.append(
            Probe(
                capture_id=capture_id,
                available_goal_kinds=tuple(kinds),
                selected_kind=str(choices[0]["selected_kind"]),
                state_path=state_path,
                receipt_sha256=str(receipt["_receipt_sha256"]),
                model_sha256=str(receipt["model_sha256"]),
            )
        )
    return tuple(probes)


def _label(capture_id: str) -> str:
    if "restore_team" in capture_id:
        return "Team recovery"
    if "manage_storage" in capture_id:
        return "Storage pressure"
    if "evolve_species" in capture_id:
        return "Evolution opportunity"
    return "Species acquisition"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 0 <= args.port <= 65_535:
        raise InterviewShowcaseError("port must be between zero and 65535")
    if not 1 <= args.emulation_multiplier <= 16:
        raise InterviewShowcaseError("emulation multiplier must be between 1 and 16")
    probes = _load_probes(args.capture_dir.resolve(), args.preflight_dir.resolve())
    store = _FrameStore(
        probes,
        emulation_multiplier=args.emulation_multiplier,
        movement_demo=args.movement_demo,
    )
    emulators = tuple(
        PyBoyAdapter(
            resolve_rom_path(args.rom),
            frame_observer=_FrameObserver(store, ordinal),
        )
        for ordinal in range(len(probes))
    )
    started: list[PyBoyAdapter] = []
    executors: list[CountingExecutor] = []
    server = _Server(store, args.port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    try:
        for emulator, probe in zip(emulators, probes, strict=True):
            emulator.start()
            started.append(emulator)
            emulator.load_state(probe.state_path)
            emulator.tick(1)
            executors.append(
                CountingExecutor(
                    FrameSafeExecutor(
                        emulator,
                        DEFAULT_NEW_GAME_TIMING.controller_timing(),
                    )
                )
            )
        thread.start()
        url = f"http://{HOST}:{server.server_address[1]}/"
        print(
            json.dumps(
                {
                    "url": url,
                    "emulators": len(probes),
                    "authentic_snapshots": len(probes),
                    "controller_actions": 0,
                    "movement_demo": args.movement_demo,
                    "view_only": True,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if not args.no_browser:
            webbrowser.open(url)
        movement_patterns = (
            ("left", "right", "up", "down"),
            ("up", "down", "right", "left"),
            ("right", "left", "down", "up"),
            ("down", "up", "left", "right"),
        )
        movement_index = 0
        next_movement_at = time.monotonic()
        while True:
            now = time.monotonic()
            if args.movement_demo and now >= next_movement_at:
                for ordinal, executor in enumerate(executors):
                    direction = movement_patterns[ordinal][
                        movement_index % len(movement_patterns[ordinal])
                    ]
                    executor.execute(MacroAction(MacroActionKind.MOVE, direction))
                    store.record_action(ordinal, direction)
                movement_index += 1
                next_movement_at = now + 0.45
            for emulator in started:
                emulator.tick(args.emulation_multiplier)
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        return 0
    finally:
        server.shutdown()
        server.server_close()
        for emulator in reversed(started):
            emulator.close()
    return 0


_HTML = r"""<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pokémon Agent · Live Systems Showcase</title>
<style>
:root{color-scheme:dark;--bg:#050908;--panel:#0c1512;--line:#254236;--green:#69efa5;--amber:#ffd66b;--muted:#91aa9e}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0,#173c2b 0,transparent 34rem),var(--bg);color:#f1f7f3;font-family:Inter,ui-sans-serif,system-ui}
main{max-width:1500px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;align-items:end;gap:18px;margin-bottom:18px}.eyebrow{color:var(--green);font:700 12px ui-monospace;letter-spacing:.16em;text-transform:uppercase}h1{margin:5px 0 0;font-size:clamp(28px,4vw,48px);letter-spacing:-.04em}.live{display:flex;align-items:center;gap:9px;color:#c4d5cc}.dot{width:10px;height:10px;border-radius:50%;background:var(--green);box-shadow:0 0 18px #69efa5;animation:pulse 1.4s infinite}@keyframes pulse{50%{opacity:.45}}
.hero{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;margin-bottom:16px}.panel{background:#0b1411e8;border:1px solid var(--line);border-radius:18px;box-shadow:0 18px 60px #0008}.mission{padding:20px}.mission h2{font-size:23px;margin:5px 0 8px}.mission p{color:#bed0c6;line-height:1.55;margin:0}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);overflow:hidden}.stat{background:var(--panel);padding:17px}.stat strong{display:block;font-size:28px}.stat span{font-size:12px;color:var(--muted)}
.flow{padding:15px;display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.node{border:1px solid var(--line);border-radius:11px;padding:12px;text-align:center;background:#101e19}.node b{display:block;color:var(--green);font-size:12px}.node span{font-size:11px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.probe{overflow:hidden}.screen{position:relative;aspect-ratio:160/144;background:#17201b;border-bottom:1px solid var(--line)}.screen img{width:100%;height:100%;object-fit:fill;image-rendering:pixelated;filter:saturate(.8) contrast(1.06)}.badge{position:absolute;top:9px;right:9px;background:#06100ddd;border:1px solid #69efa566;border-radius:999px;padding:5px 8px;color:var(--green);font:700 9px ui-monospace;letter-spacing:.09em}.probe-body{padding:15px}.probe h3{margin:0 0 5px;font-size:16px}.meta{font:11px ui-monospace;color:var(--muted)}.choice{margin:13px 0 9px;padding:11px;border:1px solid #69efa555;background:#69efa50d;border-radius:10px}.choice span{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.12em}.choice strong{color:var(--green);font-size:17px}.goals{display:flex;gap:5px;flex-wrap:wrap}.goal{padding:4px 6px;border-radius:5px;background:#182821;color:#bed0c6;font-size:10px}.footer{margin-top:16px;display:flex;justify-content:space-between;gap:16px;padding:15px 18px;color:#b8cbc1;font-size:12px}.lock{color:var(--amber)}
@media(max-width:1050px){.grid{grid-template-columns:repeat(2,1fr)}.hero{grid-template-columns:1fr}}@media(max-width:620px){.grid{grid-template-columns:1fr}.flow{grid-template-columns:1fr}.top{align-items:start;flex-direction:column}.stats{grid-template-columns:1fr}}
</style>
<main><header class="top"><div><div class="eyebrow">Four parallel Red environments · deterministic movement demonstration</div><h1>Pokémon Agent Systems Observatory</h1></div><div class="live"><span class="dot"></span><span id="runtime">4 emulators live</span></div></header>
<section class="hero"><div class="panel mission"><div class="eyebrow">North-star product</div><h2>A transferable agent for story completion and a living Pokédex</h2><p>The model chooses semantic objectives. Deterministic, tested skills handle navigation, battles, captures, party management and safety. A fresh cartridge-derived ledger verifies progress. Red is the first curriculum; Crystal is the first transfer test.</p></div><div class="panel stats"><div class="stat"><strong id="frames">0</strong><span>authentic emulator frames</span></div><div class="stat"><strong>4 / 4</strong><span>planner agreement</span></div><div class="stat"><strong id="actions">0</strong><span>demo controller actions</span></div></div></section>
<section class="panel flow"><div class="node"><b>OBSERVE</b><span>Cartridge memory</span></div><div class="node"><b>ABSTRACT</b><span>Title-neutral state</span></div><div class="node"><b>RANK</b><span>Learned goal manager</span></div><div class="node"><b>EXECUTE</b><span>Deterministic skills</span></div><div class="node"><b>VERIFY</b><span>Living-dex ledger</span></div></section>
<section class="grid" id="probes"></section>
<section class="panel footer"><span><b>Current evidence:</b> four genuine Red states, 12 semantic options, authenticated model decisions.</span><span class="lock">Movement is a deterministic skill demo—not training · model authority remains locked</span></section></main>
<script>
const pretty=s=>s.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
function render(d){document.getElementById('frames').textContent=d.total_logical_frames.toLocaleString();document.getElementById('actions').textContent=d.total_controller_actions.toLocaleString();document.getElementById('runtime').textContent=`${d.emulators} emulators live · ${d.emulation_multiplier}× · ${d.uptime_seconds.toFixed(1)}s`;
document.getElementById('probes').innerHTML=d.probes.map(p=>`<article class="panel probe"><div class="screen"><img src="/frame/${p.ordinal}.png?v=${p.logical_frame}" alt="Authentic Pokemon Red state"><span class="badge">LIVE · DEMO INPUT</span></div><div class="probe-body"><h3>${p.label}</h3><div class="meta">AUTHENTICATED SNAPSHOT · ${p.candidate_count} GOALS · ${p.controller_actions} MOVES · ${pretty(p.last_action)}</div><div class="choice"><span>Recorded model selection</span><strong>${pretty(p.selected_kind)}</strong></div><div class="goals">${p.available_goal_kinds.map(g=>`<span class="goal">${pretty(g)}</span>`).join('')}</div></div></article>`).join('')}
async function update(){try{const r=await fetch('/api/status',{cache:'no-store'});if(r.ok)render(await r.json())}catch{document.getElementById('runtime').textContent='reconnecting'}}update();setInterval(update,250);
</script>"""


if __name__ == "__main__":
    raise SystemExit(main())
