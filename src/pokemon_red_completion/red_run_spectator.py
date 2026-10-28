"""Bounded, read-only projections of one run's existing durable receipts.

No emulator, save loader, trainer or controller is imported here. Partial writes
retain the last parsed observation; only recent step folders are inspected. The
viewer never scans journals or chooses a different run by filesystem recency.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .dashboard_relay import DashboardRelayState
from .observation import MapId
from .progress_dashboard import (
    DashboardModelState,
    DashboardPartyMember,
    DashboardSnapshot,
    ProgressDashboardError,
)
from .red_collection import red_internal_species_number

_PRIVATE = re.compile(r"(?:file://|/(?:Users|Volumes|home|private|tmp)/|0x[0-9a-f]{4,})", re.I)
_GOALS = {
    "advance_story": "Continue the story",
    "unlock_access": "Continue the story",
    "develop_team": "Train the party",
    "develop": "Train the party",
    "acquire_species": "Search for Pokémon",
    "acquire": "Search for Pokémon",
    "evolve_species": "Evolve a Pokémon",
    "evolve": "Evolve a Pokémon",
    "restore_team": "Heal the party",
    "restore": "Heal the party",
    "resupply": "Gather supplies",
    "manage_storage": "Manage party and storage",
    "recover_control": "Recover game control",
}
# Display metadata only. Identifier conversion stays in the existing Red adapter.
_NAMES = tuple(
    [
        "Bulbasaur",
        "Ivysaur",
        "Venusaur",
        "Charmander",
        "Charmeleon",
        "Charizard",
        "Squirtle",
        "Wartortle",
        "Blastoise",
        "Caterpie",
        "Metapod",
        "Butterfree",
        "Weedle",
        "Kakuna",
        "Beedrill",
        "Pidgey",
        "Pidgeotto",
        "Pidgeot",
        "Rattata",
        "Raticate",
        "Spearow",
        "Fearow",
        "Ekans",
        "Arbok",
        "Pikachu",
        "Raichu",
        "Sandshrew",
        "Sandslash",
        "Nidoran♀",
        "Nidorina",
        "Nidoqueen",
        "Nidoran♂",
        "Nidorino",
        "Nidoking",
        "Clefairy",
        "Clefable",
        "Vulpix",
        "Ninetales",
        "Jigglypuff",
        "Wigglytuff",
        "Zubat",
        "Golbat",
        "Oddish",
        "Gloom",
        "Vileplume",
        "Paras",
        "Parasect",
        "Venonat",
        "Venomoth",
        "Diglett",
        "Dugtrio",
        "Meowth",
        "Persian",
        "Psyduck",
        "Golduck",
        "Mankey",
        "Primeape",
        "Growlithe",
        "Arcanine",
        "Poliwag",
        "Poliwhirl",
        "Poliwrath",
        "Abra",
        "Kadabra",
        "Alakazam",
        "Machop",
        "Machoke",
        "Machamp",
        "Bellsprout",
        "Weepinbell",
        "Victreebel",
        "Tentacool",
        "Tentacruel",
        "Geodude",
        "Graveler",
        "Golem",
        "Ponyta",
        "Rapidash",
        "Slowpoke",
        "Slowbro",
        "Magnemite",
        "Magneton",
        "Farfetch’d",
        "Doduo",
        "Dodrio",
        "Seel",
        "Dewgong",
        "Grimer",
        "Muk",
        "Shellder",
        "Cloyster",
        "Gastly",
        "Haunter",
        "Gengar",
        "Onix",
        "Drowzee",
        "Hypno",
        "Krabby",
        "Kingler",
        "Voltorb",
        "Electrode",
        "Exeggcute",
        "Exeggutor",
        "Cubone",
        "Marowak",
        "Hitmonlee",
        "Hitmonchan",
        "Lickitung",
        "Koffing",
        "Weezing",
        "Rhyhorn",
        "Rhydon",
        "Chansey",
        "Tangela",
        "Kangaskhan",
        "Horsea",
        "Seadra",
        "Goldeen",
        "Seaking",
        "Staryu",
        "Starmie",
        "Mr._Mime",
        "Scyther",
        "Jynx",
        "Electabuzz",
        "Magmar",
        "Pinsir",
        "Tauros",
        "Magikarp",
        "Gyarados",
        "Lapras",
        "Ditto",
        "Eevee",
        "Vaporeon",
        "Jolteon",
        "Flareon",
        "Porygon",
        "Omanyte",
        "Omastar",
        "Kabuto",
        "Kabutops",
        "Aerodactyl",
        "Snorlax",
        "Articuno",
        "Zapdos",
        "Moltres",
        "Dratini",
        "Dragonair",
        "Dragonite",
        "Mewtwo",
        "Mew",
    ]
)  # noqa: SIM905


def _text(value: object, fallback: str = "Not reported", maximum: int = 180) -> str:
    if not isinstance(value, str) or not value or _PRIVATE.search(value):
        return fallback
    return " ".join(value.split())[:maximum]


def _count(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _date(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def _goal(kind: object, objective: object = None) -> str:
    if isinstance(objective, str) and re.fullmatch(r"[a-z_]{1,64}", objective):
        return objective.replace("_", " ").capitalize()
    return _GOALS.get(str(kind), "Player goal")


def _authority(choice: dict, support: object) -> str:
    if str(choice.get("mode", "")).startswith("model"):
        return "Model"
    if support == "forced_singleton":
        return "Single-option support"
    return "Support" if support or choice.get("mode") else "Not reported"


def _species(internal: object) -> str:
    if type(internal) is not int:
        return "Pokémon"
    try:
        number = red_internal_species_number(internal)
        return _NAMES[number - 1].replace("_", " ")
    except (ValueError, TypeError, IndexError):
        return "Pokémon"


def worker_is_running(launch: dict, root: Path) -> bool:
    """PID alone is insufficient: require the recorded plan and driver command."""
    pid, command = launch.get("worker_pid"), launch.get("command")
    if type(pid) is not int or pid <= 0 or not isinstance(command, list):
        return False
    required = [str(root / "PLAN.json")]
    required += [v for v in command[1:] if isinstance(v, str) and v.endswith(".py")]
    if len(required) < 2:
        return False
    try:
        actual = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        ).stdout
        return bool(actual.strip()) and all(v in actual for v in required)
    except (OSError, subprocess.TimeoutExpired):
        return False


class RedRunReader:
    """Read one selected output directory; never open terminal.state or ROMs."""

    def __init__(
        self,
        root: Path,
        *,
        owner_running: bool = False,
        process_probe: Callable = worker_is_running,
    ) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir() or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", self.root.name):
            raise ProgressDashboardError("run directory identity is invalid")
        self.owner_running, self.process_probe = owner_running, process_probe
        self._cache: OrderedDict = OrderedDict()
        self._segments: dict = {}
        self.observed_at: str | None = None

    def document(self, path: Path, *, outcome: bool = False) -> dict:
        """Bound each JSON read and retain cached data during an unfinished write."""
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            return {}
        cache = self._cache
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            if path in cache and cache[path][0] == stamp:
                return cache[path][1]
            limit = (64 if outcome else 16) * 1024 * 1024
            if stat.st_size > limit:
                return cache.get(path, (None, {}))[1]
            with path.open("rb") as stream:
                payload = stream.read(limit + 1)
            if len(payload) > limit:
                return cache.get(path, (None, {}))[1]
            value = json.loads(payload)
            if not isinstance(value, dict):
                return {}
            if outcome:
                value = {
                    k: value[k]
                    for k in (
                        "selected_kind",
                        "support_role",
                        "verification",
                        "ordinary_setback",
                        "elapsed_seconds",
                        "observed_cost",
                        "error",
                        "error_type",
                        "failure_reason",
                        "after",
                        "before",
                    )
                    if k in value
                } | {"evidence": {"objective": (value.get("evidence") or {}).get("objective")}}
            cache[path] = (stamp, value)
            cache.move_to_end(path)
            while len(cache) > 160:
                cache.popitem(last=False)
            return value
        except (OSError, ValueError, TypeError):
            return cache.get(path, (None, {}))[1]

    def segment_counts(self, path: Path) -> dict:
        """Read only flat counters at the ends of the existing indented receipt.

        Huge nested outcomes are deliberately not loaded. Exact two-space keys
        exclude nested counters, and accounting must reconcile before admission.
        A different serialization layout remains unknown rather than guessed.
        """
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            return {}
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            if path in self._segments and self._segments[path][0] == stamp:
                return self._segments[path][1]
            with path.open("rb") as stream:
                head = stream.read(32768)
                stream.seek(max(len(head), stat.st_size - 32768))
                tail = stream.read(32768)
            matches = re.findall(
                rb'^  "(model_decisions|support_decisions|ordinary_setbacks|'
                rb'executed_decisions)": (\d+),?$',
                head + b"\n" + tail,
                re.M,
            )
            counts = {key.decode(): int(value) for key, value in matches}
            if (
                len(counts) != 4
                or counts["model_decisions"] + counts["support_decisions"]
                != counts["executed_decisions"]
            ):
                previous = self._segments.get(path, (None, {}))[1]
                return previous | {"partial": True} if previous else {}
            self._segments[path] = (stamp, counts)
            return counts
        except OSError:
            previous = self._segments.get(path, (None, {}))[1]
            return previous | {"partial": True} if previous else {}

    def read(self) -> tuple[DashboardSnapshot, dict]:
        root = self.root
        launch, plan = self.document(root / "LAUNCH.json"), self.document(root / "PLAN.json")
        terminal, exit_record = (
            self.document(root / "RESULT.json"),
            self.document(root / "PROCESS-EXIT.json"),
        )
        if "checkpoint_lifecycle" in terminal:
            # An in-process receipt can report guest closure, never host exit.
            # Probe even after a guest-closed receipt; a live matching process
            # takes precedence over a stale external exit record.
            probed_running = bool(self.process_probe(launch, root))
            closed = (not self.owner_running and not probed_running
                and exit_record.get("worker_exit_confirmed") is True)
            running = bool(self.owner_running or probed_running)
        else:
            # Retained legacy viewer records keep their original display rules.
            closed = not self.owner_running and bool(
                terminal.get("worker_stopped") or exit_record.get("worker_exit_confirmed")
            )
            running = not closed and (self.owner_running or self.process_probe(launch, root))
        segments = sorted((root / "runs").glob("segment-*"))[-600:]
        totals = dict(model_decisions=0, support_decisions=0, ordinary_setbacks=0)
        counts_observed = bool(segments)
        checkpoint = self.document(root / "initial" / "CONTEXT.json")
        for segment in segments:
            counts = self.segment_counts(segment / "native" / "episode" / "result.json")
            counts_observed = counts_observed and bool(counts) and not counts.get("partial", False)
            for key in totals:
                totals[key] += counts.get(key, 0)
        # Only the newest durable context is needed. Scanning every old context
        # would evict recent (sometimes large) outcomes from the bounded cache.
        for segment in reversed(segments):
            context = self.document(segment / "CONTEXT.json")
            if context:
                checkpoint = context
                break
        steps = []
        for segment in segments[-2:]:
            steps.extend(sorted((segment / "native" / "episode").glob("step-*"))[-24:])
        recent: list[dict] = []
        facts: dict = {}
        activity, failure = "Starting the game", None
        for step in steps[-24:]:
            before = self.document(step / "before.json")
            outcome = self.document(step / "outcome.json", outcome=True)
            decision = self.document(step / "decision.json")
            intent = self.document(step / "intent.json")
            admission = self.document(step / "admission-failure.json")
            facts = outcome.get("after") or before.get("facts") or facts
            kind = outcome.get("selected_kind") or decision.get("selected_option_kind")
            if kind:
                objective = (outcome.get("evidence") or {}).get("objective")
                if not objective:
                    index = decision.get("selected_candidate_index")
                    contexts = intent.get("private_story_contexts") or []
                    if type(index) is int and 0 <= index < len(contexts):
                        objective = contexts[index].get("objective_ref")
                activity = _goal(kind, objective)
                recent.append(
                    dict(
                        goal=activity,
                        authority=_authority(decision, outcome.get("support_role")),
                        result=(
                            "Safe setback"
                            if outcome.get("ordinary_setback")
                            else "Completed"
                            if outcome.get("verification") == "succeeded"
                            else "Failed"
                            if outcome
                            else "In progress"
                        ),
                        seconds=round(float(outcome.get("elapsed_seconds") or 0), 2),
                        actions=_count((outcome.get("observed_cost") or {}).get("actions")),
                    )
                )
            if admission:
                failure = _text(admission.get("error"), "Menu construction failed")
            elif outcome.get("error_type"):
                failure = _text(outcome.get("error"), "Goal execution failed")
            if before or outcome:
                source = step / ("outcome.json" if outcome else "before.json")
                self.observed_at = datetime.fromtimestamp(source.stat().st_mtime, UTC).isoformat()
        native = terminal.get("native_facts") if closed else {}
        native = native or {}
        diag = facts.get("diagnostics") or {}
        levels = diag.get("party_levels") or native.get("party_levels") or []
        party = []
        arrays = (
            diag.get("party_species_ids") or [],
            levels,
            diag.get("party_hp") or [],
            diag.get("party_max_hp") or [],
        )
        for index, (species, level, hp, maximum) in enumerate(
            zip(*arrays, strict=True) if len({len(a) for a in arrays}) == 1 else ()
        ):
            status = (diag.get("party_status") or [0] * len(levels))[index]
            label = (
                "fainted"
                if hp == 0
                else "asleep"
                if status & 7
                else "poisoned"
                if status & 8
                else "burned"
                if status & 16
                else "frozen"
                if status & 32
                else "paralyzed"
                if status & 64
                else "healthy"
            )
            party.append(
                DashboardPartyMember(index + 1, _species(species), level, hp, maximum, label)
            )
        spent = (terminal.get("spent") if closed else None) or checkpoint.get("spent") or {}
        registered = _count(native.get("registrations"))
        if not native and diag.get("collection_ledger"):
            registered = len(diag["collection_ledger"].get("local_registered_species") or [])
        target = len(plan.get("required_species") or []) or 124
        bags: list = (
            diag.get("bag_items") if "bag_items" in diag else native.get("bag_stock")
        ) or []
        balls = 0
        for item, quantity in bags:
            if item in {1, 2, 3, 4, 8}:
                balls += _count(quantity)
        badges = (
            _count(native.get("badges")) if native else _count(diag.get("badge_bits")).bit_count()
        )
        badge_bits = _count(native.get("badge_bits", diag.get("badge_bits")))
        try:
            location = MapId(diag.get("map_id")).name.replace("_", " ").title()
        except (ValueError, TypeError):
            location = "Location not yet recorded"
        start = _date(launch.get("started_at_utc"))
        end = (_date(exit_record.get("exited_at_utc")) if closed else None) or datetime.now(UTC)
        elapsed = (
            max(0, (end - start).total_seconds()) if start else float(spent.get("seconds") or 0)
        )
        reason = _text(terminal.get("terminal_reason"), "No terminal result")
        complete = closed and reason == "curriculum_complete" and terminal.get("passed") is True
        status = (
            "passed" if complete else "failed" if closed else "running" if running else "waiting"
        )
        message = (
            (failure or f"Stopped: {reason}")
            if closed
            else (
                f"{activity}. Statistics below are from the last recorded boundary."
                if running
                else "No authenticated running worker. "
                "The retained checkpoint is shown without resuming it."
            )
        )
        snapshot = DashboardSnapshot(
            game="Pokémon Red",
            run_status=status,
            stage=activity,
            message=message,
            frame_count=_count(spent.get("frames")),
            actions=_count(spent.get("actions")),
            location=location,
            registered_species=registered,
            collection_target=target,
            collection_observed=bool(native or diag),
            capture_items=balls,
            party=tuple(party),
            model=DashboardModelState(
                mode="model" if totals["model_decisions"] else "waiting",
                candidate="Local goal model · disclosed hybrid player",
                choice=activity,
                decisions=totals["model_decisions"],
            ),
        )
        metadata = dict(
            id=root.name,
            lifecycle="stopped" if closed else "running" if running else "not_connected",
            badges=badges,
            badge_bits=badge_bits,
            money=_count(native.get("cash", facts.get("cash")))
            if "cash" in native or "cash" in facts
            else None,
            balls=balls if "bag_items" in diag or "bag_stock" in native else None,
            units=_count(spent.get("decisions")),
            **totals,
            counts_observed=counts_observed,
            elapsed_seconds=round(elapsed, 1),
            recorded_at_utc=self.observed_at,
            started_at_utc=start.isoformat() if start else None,
            activity=activity,
            failure=failure,
            terminal_reason=reason if closed else None,
            completed_objectives=[
                value
                for value in (
                    (checkpoint.get("lesson") or {}).get("completed_objectives")
                    or facts.get("completed_objectives")
                    or []
                )
                if isinstance(value, str) and re.fullmatch(r"[a-z_]{1,64}", value)
            ][:64],
            recent=recent[-10:],
            weights_updated=0,
            checkpoint_only=True,
        )
        return snapshot, metadata


class RunViewerState(DashboardRelayState):
    """Join only this run's metadata with the same run's optional live frames."""

    def __init__(self, reader: RedRunReader, *, live_port: int) -> None:
        self.reader = reader
        self._retained_frame: bytes | None = None
        self._retained_at = 0.0
        self._retained_version = 0
        self._retained_token = None
        snapshot, self.run_metadata = reader.read()
        super().__init__(snapshot, live_port=live_port)

    def refresh(self) -> None:
        snapshot, self.run_metadata = self.reader.read()
        self.publish(snapshot)
        self.poll()

    def poll(self) -> bool:
        connected = super().poll()
        with self._lock:
            if (
                connected
                and self._remote_frame is not None
                and self._remote_version != self._retained_token
            ):
                self._retained_frame = self._remote_frame
                self._retained_token = self._remote_version
                self._retained_version += 1
                age = float(self._remote[1].get("frame_age_seconds") or 0) if self._remote else 0
                self._retained_at = time.monotonic() - age
        return connected

    def frame_bytes(self) -> tuple[bytes, int]:
        with self._lock:
            if self._retained_frame is not None:
                return self._retained_frame, self._retained_version
        return super().frame_bytes()

    def _get(self, endpoint: str) -> bytes:
        payload = super()._get(endpoint)
        if endpoint == "/api/status":
            document = json.loads(payload)
            if (document.get("run") or {}).get("id") != self.reader.root.name:
                raise ProgressDashboardError("live frame belongs to a different run")
        return payload

    def status_bytes(self) -> tuple[bytes, int]:
        payload, version = super().status_bytes()
        value = json.loads(payload)
        with self._lock:
            value["run"] = self.run_metadata | {"frame_source_connected": self._remote is not None}
            if self._retained_frame is not None:
                value["dashboard"].update(
                    frame_ready=True,
                    frame_version=self._retained_version,
                    frame_age_seconds=max(0, time.monotonic() - self._retained_at),
                )
        return json.dumps(value, allow_nan=False).encode(), version
