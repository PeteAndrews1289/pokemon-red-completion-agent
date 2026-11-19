"""Observed cost of collecting a level evolution, including zero-yield attempts."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isfinite

from .provenance import canonical_sha256


@dataclass(frozen=True, slots=True)
class CollectionTrainingCost:
    attempts: int = 0
    zero_yield: int = 0
    target_xp: int = 0
    frames: int = 0
    microseconds: int = 0
    heals: int = 0

    def __post_init__(self):
        counts = asdict(self)
        if any(type(n) is not int or not 0 <= n < 2**53 for n in counts.values()):
            raise ValueError("invalid collection training cost")
        if (self.zero_yield > self.attempts or (self.attempts == 0 and any(counts.values()))
                or (self.attempts and (self.frames < self.attempts or self.microseconds < self.attempts))
                or (self.target_xp == 0) != (self.zero_yield == self.attempts)
                or self.target_xp < self.attempts - self.zero_yield):
            raise ValueError("inconsistent collection training cost")

    def plus(self, observed: CollectionTrainingCost) -> CollectionTrainingCost:
        return CollectionTrainingCost(**{k: v + getattr(observed, k) for k, v in asdict(self).items()})

    def require_extension(self, old: CollectionTrainingCost) -> None:
        CollectionTrainingCost(**{k: v - getattr(old, k) for k, v in asdict(self).items()})

    def forecast(self, remaining_xp: int) -> dict:
        if type(remaining_xp) is not int or remaining_xp < 1:
            raise ValueError("a collection forecast needs positive remaining target XP")
        return dict(observed=asdict(self), remaining_xp=remaining_xp,
                    estimated_frames=self.frames * remaining_xp / self.target_xp if self.target_xp else None,
                    estimated_seconds=self.microseconds * remaining_xp / (1_000_000 * self.target_xp) if self.target_xp else None)


def level_cost_context(binding, candidate, facts):
    """Keep subject and location private. A party or encounter-area change starts a new estimate."""
    transition = getattr(binding, "level_evolution_transition", None)
    workload = getattr(candidate, "level_workload", None)
    if transition is None or workload is None:
        return None
    boxed_ref = getattr(binding, "level_evolution_boxed_ref", None)
    trainee = trainee_ref(transition, facts, boxed_ref)
    key = observed_context_key(transition, facts, trainee)
    if key is None:
        return None
    initial_xp = binding.level_evolution_initial_xp
    if type(initial_xp) is not int or initial_xp < 0:
        return None
    return dict(key=key, transition=list(transition), trainee_ref=trainee, boxed_ref=boxed_ref, initial_xp=initial_xp)


def trainee_ref(transition, facts, boxed_ref):
    if boxed_ref is not None:
        return boxed_ref
    from .red_collection import red_internal_species_id

    source = transition[0]
    if not source.startswith("pokemon:national:") or not source.split(":")[-1].isdigit():
        return None
    internal = red_internal_species_id(int(source.split(":")[-1]))
    party = (facts.get("player_lesson") or {}).get("party") or ()
    present = [m.get("specimen_ref") for m in party if isinstance(m, dict) and m.get("species_id") == internal]
    return present[0] if len(present) == 1 else None


def observed_context_key(transition, facts, trainee):
    area = (facts.get("diagnostics") or {}).get("map_id")
    party = (facts.get("player_lesson") or {}).get("party")
    if (type(area) is not int or not isinstance(trainee, str) or not trainee
            or not isinstance(party, (list, tuple)) or not party):
        return None
    members = []
    for member in party:
        if not isinstance(member, dict) or type(member.get("specimen_ref")) is not str:
            return None
        members.append(member["specimen_ref"])
    if len(set(members)) != len(members):
        return None
    return canonical_sha256(dict(transition=transition, trainee=trainee, source_area=area, roster=sorted(members)))


def measured_training_cost(outcome, transition, *, context=None):
    if (outcome.get("error_type") is not None or outcome.get("safe_terminal") is not True
            or outcome.get("selected_kind") != "evolve_species"):
        return None
    ev = outcome.get("evidence") or {}
    origin, destination = transition
    if ev.get("retained_active_roster_restored") is not True:
        return None
    if outcome.get("verification") == "succeeded":
        newly_owned = set(outcome["after"]["owned_species"]) - set(outcome["before"]["owned_species"])
        if ev.get("exact_evolution_transition") is not True or destination not in newly_owned:
            return None
    elif not (outcome.get("ordinary_setback") is True and ev.get("evolution_partial") is True
              and ev.get("source_species_ref") == origin and ev.get("target_species_ref") == destination):
        return None
    initial, terminal, xp = (ev.get(k) for k in ("trainee_initial_xp", "trainee_terminal_xp", "trainee_xp_gained"))
    if any(type(n) is not int or n < 0 for n in (initial,terminal,xp)) or terminal-initial != xp:
        return None
    if context is not None and (context["initial_xp"] != initial
            or ev.get("zero_progress_trainee_ref", context["trainee_ref"]) != context["trainee_ref"]):
        return None
    cost = outcome.get("observed_cost") or {}
    frames = cost.get("frames")
    phases = outcome.get("phase_seconds") or {}
    phase_keys = ("menu_and_boundary_observation", "selection_and_receipt", "selection_diagnostics",
                  "execution", "verification", "terminal_observation", "outcome_diagnostics")
    if (type(frames) is not int or frames <= 0 or any(
        type(phases.get(k)) not in (int,float) or not isfinite(phases[k]) or phases[k] < 0 for k in phase_keys
    )):
        return None
    heals = ev.get("healing_trips")
    if type(heals) is not int or heals < 0:
        return None
    micros = round(sum(phases[k] for k in phase_keys) * 1_000_000)
    if micros < 1:
        return None
    return CollectionTrainingCost(1, int(xp == 0), xp, frames, micros, heals)


def menu_with_collection_costs(options, memory, facts, frame_horizon):
    """Quote earned target XP under this run's measured cost. Preserve all executable options."""
    if type(frame_horizon) is not int or frame_horizon < 1:
        raise ValueError("a collection cost quote needs a positive frame horizon")
    candidates = []
    quotes = []
    contexts = {}
    for binding, candidate in zip(options.bindings, options.menu.candidates, strict=True):
        context = level_cost_context(binding, candidate, facts)
        if context is not None:
            contexts[binding.binding_ref] = context
        key = context["key"] if context is not None else None
        history = memory.collection_training_cost(key) if key is not None else None
        if history is not None:
            quote = history.forecast(candidate.level_workload.remaining_xp)
            frames = quote["estimated_frames"]
            previous = candidate.features.execution_effort
            effort = previous if frames is None else frames / (frames + frame_horizon)
            quotes.append(dict(binding_ref=binding.binding_ref, context_sha256=key, **quote,
                               original_effort=previous, quoted_effort=effort, frame_horizon=frame_horizon))
            if frames is not None:
                candidate = replace(candidate, features=replace(candidate.features, execution_effort=effort))
        candidates.append(candidate)
    projected = replace(options, menu=replace(options.menu, candidates=tuple(candidates))) if quotes else options
    return projected, quotes, contexts


def replay_collection_cost_step(step, outcome, intent, memory, frame_horizon):
    """Rebuild the quote from the sealed prefix and the selected outcome's own target measurements."""
    import json
    from .living_dex_policy_codec import restore_living_dex_policy_menu

    before_path, after_path = step / "collection-cost-before.json", step / "collection-cost-after.json"
    if intent["menu"]["schema"] == "pokemon.red.player-support.v1":
        if before_path.exists() or after_path.exists():
            raise ValueError("support has an unexpected collection cost receipt")
        return
    envelope = json.loads(before_path.read_bytes())
    menu = restore_living_dex_policy_menu(intent["menu"]["menu"])
    bindings = intent["private_selection_authority"]["live_bindings"]
    contexts = envelope["contexts"]
    refs = [binding["binding_ref"] for binding in bindings]
    if (envelope.get("frame_horizon") != frame_horizon or envelope.get("state_sha256") != outcome["before_state_sha256"]
            or not set(contexts) <= set(refs) or len(refs) != len(set(refs))):
        raise ValueError("collection cost binding or boundary differs")
    originals = []
    expected_quotes = []
    for binding, candidate in zip(bindings, menu.candidates, strict=True):
        ref = binding["binding_ref"]
        context = contexts.get(ref)
        if context is not None:
            transition = context.get("transition")
            if (candidate.level_workload is None or binding["policy"]["kind"] != "evolve_species"
                    or not isinstance(transition, list) or len(transition) != 2
                    or not all(isinstance(x, str) and x for x in transition) or transition[0] == transition[1]
                    or context["trainee_ref"] != trainee_ref(transition, outcome["before"], context["boxed_ref"])
                    or context["key"] != observed_context_key(transition, outcome["before"], context["trainee_ref"])):
                raise ValueError("collection cost context differs")
            previous = memory.collection_training_cost(context["key"])
            if previous is not None:
                pos = len(expected_quotes)
                if pos >= len(envelope["quotes"]):
                    raise ValueError("collection cost quote missing")
                original_effort = envelope["quotes"][pos]["original_effort"]
                estimate = previous.forecast(candidate.level_workload.remaining_xp)
                frames = estimate["estimated_frames"]
                effort = original_effort if frames is None else frames / (frames + frame_horizon)
                if candidate.features.execution_effort != effort:
                    raise ValueError("collection cost quoted policy effort differs")
                expected_quotes.append(dict(binding_ref=ref, context_sha256=context["key"], **estimate,
                                            original_effort=original_effort, quoted_effort=effort, frame_horizon=frame_horizon))
                candidate = replace(candidate, features=replace(candidate.features, execution_effort=original_effort))
        originals.append(candidate)
    if (envelope["original_menu_sha256"] != replace(menu, candidates=tuple(originals)).policy_sha256
            or envelope["quotes"] != expected_quotes):
        raise ValueError("collection cost quote or original menu differs")
    selected = contexts.get(refs[outcome["choice"]["selected_candidate_index"]])
    observed = measured_training_cost(outcome, selected["transition"], context=selected) if selected is not None else None
    if observed is None:
        if after_path.exists():
            raise ValueError("unmeasured collection cost recorded")
        return
    if json.loads(after_path.read_bytes()) != dict(
        state_sha256=outcome["terminal_state_sha256"], context_sha256=selected["key"],
        observed=asdict(observed), outcome_sha256=canonical_sha256(outcome),
    ):
        raise ValueError("collection cost outcome receipt differs")
    memory.record_collection_training_cost(selected["key"], observed)
