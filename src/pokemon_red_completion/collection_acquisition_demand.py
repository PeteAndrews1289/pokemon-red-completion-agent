"""Marginal useful capture stock for a living collection, not a shopping list.

One physical specimen can satisfy one living target. Directed transformations
may consume it, never clone it. This projection grants no route/skill authority.
"""

from __future__ import annotations

from collections.abc import Mapping


def useful_capture_counts(
    targets: frozenset[str],
    counts: Mapping[str, int],
    edges: tuple[tuple[str, str], ...],
    capture_species: tuple[str, ...],
) -> dict[str, int]:
    """Count useful additional copies of each capture species independently.

    Preserve one already-held copy of each required form. Match surplus copies
    onto missing reachable targets, then measure each candidate's marginal
    coverage through augmenting paths. Candidate counts are alternative choices:
    after ANY capture recompute, rather than adding up all candidates' counts.
    Registration flags, action choices, outcomes and rewards are not inputs.
    """
    if any(not isinstance(s, str) or not s.strip() for s in (*targets, *counts, *capture_species)):
        raise ValueError("species references must be nonempty strings")
    if any(type(n) is not int or n < 0 for n in counts.values()):
        raise ValueError("specimen counts must be nonnegative integers")
    if len(set(capture_species)) != len(capture_species):
        raise ValueError("capture candidates must be unique")
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if (not isinstance(edge, tuple) or len(edge) != 2
                or any(not isinstance(s, str) or not s.strip() for s in edge)):
            raise ValueError("transformation edges must contain two species references")
        source, target = edge
        adjacency.setdefault(source, set()).add(target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def check_acyclic(source: str) -> None:
        if source in visiting:
            raise ValueError("transformation graph must be acyclic")
        if source in visited:
            return
        visiting.add(source)
        for target in adjacency.get(source, ()):
            check_acyclic(target)
        visiting.remove(source)
        visited.add(source)

    for source in adjacency:
        check_acyclic(source)

    missing = targets.difference(s for s, n in counts.items() if n)
    options: dict[str, tuple[str, ...]] = {}

    def destinations(source: str) -> tuple[str, ...]:
        if source not in options:
            reached: set[str] = set()
            pending = [source]
            while pending:
                current = pending.pop()
                if current not in reached:
                    reached.add(current)
                    pending.extend(adjacency.get(current, ()))
            options[source] = tuple(sorted(reached.intersection(missing)))
        return options[source]

    stock = [
        source for source, quantity in sorted(counts.items())
        for _ in range(min(len(missing), max(0, quantity - int(source in targets))))
        if destinations(source)
    ]

    def augment(
        token: int, species: list[str], owners: dict[str, int], seen: set[str],
    ) -> bool:
        for target in destinations(species[token]):
            if target in seen:
                continue
            seen.add(target)
            owner = owners.get(target)
            if owner is None or augment(owner, species, owners, seen):
                owners[target] = token
                return True
        return False

    baseline: dict[str, int] = {}
    for token in range(len(stock)):
        augment(token, stock, baseline, set())
    result = {}
    for candidate in capture_species:
        species, owners = list(stock), dict(baseline)
        useful = 0
        while len(owners) < len(missing):
            species.append(candidate)
            if not augment(len(species) - 1, species, owners, set()):
                break
            useful += 1
        result[candidate] = useful
    return result
