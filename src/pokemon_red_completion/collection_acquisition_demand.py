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


def useful_registered_capture_counts(
    targets: frozenset[str],
    registered: frozenset[str],
    counts: Mapping[str, int],
    edges: tuple[tuple[str, str], ...],
    capture_species: tuple[str, ...],
    *,
    protected_counts: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Marginal copies for registration, not coexistence of every form.

    One specimen can register every missing species along one directed path,
    but cannot take two branches simultaneously. A min-cost flow assigns actual
    unreserved stock to paths, awarding each missing registration at most once.
    Each capture candidate is evaluated independently and must be recomputed
    after a real action. Declared edges do not prove executor/resource readiness.
    """
    # Reuse legacy graph/type validation only; never its living-copy demand.
    useful_capture_counts(targets | registered, counts, edges, capture_species)
    protected = dict(protected_counts or {})
    if any(not isinstance(s, str) or not s.strip() for s in protected):
        raise ValueError("protected species references must be nonempty strings")
    if any(type(n) is not int or n < 0 for n in protected.values()):
        raise ValueError("protected counts must be nonnegative integers")
    if any(n > counts.get(s, 0) for s, n in protected.items()):
        raise ValueError("cannot reserve nonexistent physical stock")
    if not {s for s, n in counts.items() if n} <= registered:
        raise ValueError("physical stock must have verified registration")
    missing = targets - registered
    if not missing:
        return dict.fromkeys(capture_species, 0)
    species = sorted(targets | counts.keys() | set(capture_species)
                     | {s for edge in edges for s in edge})
    indices = {s: 2 * i for i, s in enumerate(species)}
    source, sink = 2 * len(species), 2 * len(species) + 1
    bound = len(missing)

    def coverage(stock: Mapping[str, int]) -> int:
        # Residual edges are [destination, reverse-index, capacity, cost].
        network: list[list[list[int]]] = [[] for _ in range(sink + 1)]

        def add(start: int, end: int, capacity: int, cost: int) -> None:
            forward = [end, len(network[end]), capacity, cost]
            reverse = [start, len(network[start]), 0, -cost]
            network[start].append(forward)
            network[end].append(reverse)

        for s, node in indices.items():
            add(source, node, min(bound, stock.get(s, 0)), 0)
            if s in missing:
                add(node, node + 1, 1, -1)
            add(node, node + 1, bound, 0)
            add(node + 1, sink, bound, 0)
        for source_species, target_species in set(edges):
            add(indices[source_species] + 1, indices[target_species], bound, 0)

        gain = 0
        # Successive shortest residual paths also repair earlier branch choices.
        # Bellman-Ford is adequate for the small species graph and negative costs.
        while True:
            distance = [float("inf")] * len(network)
            previous: list[tuple[int, int] | None] = [None] * len(network)
            distance[source] = 0
            for _ in range(len(network) - 1):
                changed = False
                for start, outgoing in enumerate(network):
                    for i, (end, _, capacity, cost) in enumerate(outgoing):
                        if capacity and distance[start] + cost < distance[end]:
                            distance[end] = distance[start] + cost
                            previous[end] = start, i
                            changed = True
                if not changed:
                    break
            if distance[sink] >= 0:
                return gain
            gain -= int(distance[sink])
            node = sink
            while node != source:
                step = previous[node]
                assert step is not None
                start, i = step
                edge = network[start][i]
                edge[2] -= 1
                network[node][edge[1]][2] += 1
                node = start

    stock = {s: n - protected.get(s, 0) for s, n in counts.items()}
    baseline = coverage(stock)
    result = {}
    for candidate in capture_species:
        alternative = dict(stock)
        current, copies = baseline, 0
        while current < len(missing):
            alternative[candidate] = alternative.get(candidate, 0) + 1
            new = coverage(alternative)
            if new <= current:
                break
            copies += 1
            current = new
        result[candidate] = copies
    return result
