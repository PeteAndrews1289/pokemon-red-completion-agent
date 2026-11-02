"""Optional in-memory spectator feed, never a gameplay or controller service."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from .progress_dashboard import DashboardFrameObserver, DashboardState, ProgressDashboardServer
from .red_run_spectator import RedRunReader


def declared_spectator(plan: dict) -> dict | None:
    """A future frozen plan must pin presentation settings before launch."""
    spec = plan.get("spectator")
    if spec is None:
        return None
    if (
        not isinstance(spec, dict)
        or set(spec) != {"port", "maximum_fps"}
        or type(spec["port"]) is not int
        or not 1024 <= spec["port"] <= 65535
        or type(spec["maximum_fps"]) is not int
        or not 1 <= spec["maximum_fps"] <= 30
    ):
        raise ValueError("spectator requires a loopback port and integer frame rate only")
    return dict(spec)


class _ProducerState(DashboardState):
    def __init__(self, reader: RedRunReader) -> None:
        self.reader = reader
        snapshot, self.metadata = reader.read()
        super().__init__(snapshot)

    def refresh(self) -> None:
        snapshot, metadata = self.reader.read()
        with self._lock:
            self.metadata = metadata
        self.publish(snapshot)

    def status_bytes(self) -> tuple[bytes, int]:
        payload, version = super().status_bytes()
        value = json.loads(payload)
        with self._lock:
            value["run"] = self.metadata
        return json.dumps(value, allow_nan=False).encode(), version


class RunFrameFeed:
    """Opt-in context for one owner emulator; default-off is a no-op.

    Presentation failure must not terminate an otherwise healthy player. A port
    collision disables this observer; malformed frozen settings fail validation
    before gameplay. The feed owns no emulator or controller reference.
    """

    def __init__(self, plan: dict, root: Path, *, enabled: bool = True) -> None:
        self.spec = declared_spectator(plan) if enabled else None
        self.root = Path(root)
        self.adapter_options: dict = {}
        self._stop = threading.Event()
        self._server: ProgressDashboardServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> RunFrameFeed:
        if self.spec is None:
            return self
        try:
            state = _ProducerState(RedRunReader(self.root, owner_running=True))
            self._server = ProgressDashboardServer(state, port=self.spec["port"]).start()
            self.adapter_options = {
                "frame_observer": DashboardFrameObserver(
                    state, maximum_fps=self.spec["maximum_fps"]
                )
            }
            self._thread = threading.Thread(
                target=self._poll, args=(state,), daemon=True, name="red-spectator-receipts"
            )
            self._thread.start()
        except (OSError, ValueError, TypeError):
            self._close()
            print("Spectator feed unavailable; player remains unchanged.", file=sys.stderr)
        return self

    def _poll(self, state: _ProducerState) -> None:
        while not self._stop.wait(0.5):
            try:
                state.refresh()
            except (OSError, ValueError, TypeError, KeyError, IndexError):
                # An unfinished receipt is not a player error or a new goal.
                continue

    def _close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        if self._server is not None:
            self._server.close()
        self.adapter_options = {}
        self._server = None

    def __exit__(self, *_: object) -> None:
        self._close()
