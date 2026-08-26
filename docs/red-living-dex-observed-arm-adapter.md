# Red living-Pokédex observed-arm adapter

Status: ROM-free implementation published as main `0320a5a8` through PR 52 and green GitHub CI
`32930451851/1` on 2026-08-26. The exact artifact and verification record is the
[path-free qualification](evidence/red-living-dex-observed-arm-adapter-qualification-v1-2026-08-26.json).
No ROM, private checkpoint,
teacher, model prediction, controller input, emulator frame, outcome campaign, fit, learning
counter, or authority counter was opened by this work.

This is the Red integration boundary for the shared
[living-Pokédex option-value contract](living-dex-option-value-contract.md). It is an engineering
prerequisite for learning from real Red decisions, not evidence that a model can yet play Red or
transfer to Crystal.

## Mission contribution

The final product remains a transferable agent that can complete multiple Pokémon games and build
a living Pokédex, including version-specific acquisition, trade/evolution dependencies, storage,
party development, resources, access puzzles, and legendary encounters. This boundary contributes
one narrow capability: it lets Red expose genuine high-level collection choices to a title-neutral
learner without teaching species, map, item, route, or button identities.

It grants learned authority **zero**. Authority remains behind symbolic availability and living-
collection invariants until real outcomes, a train-only fit, held-out Red evidence, and later
frozen-weight Crystal transfer evidence exist.

## Implemented boundary

Three modules now separate private mechanics from public learning data:

- `red_living_dex_option_adapter.py` derives normalized context and candidate rows from one frozen
  Red snapshot, declared bounds, semantic facts, and private executable bindings;
- `red_living_dex_option_collector.py` performs one replayable full-support randomized selection,
  executes only that binding once, and settles only its independently observed outcome;
- `red_living_dex_option_calibration.py` audits coverage, censoring, behavior probabilities,
  family/location disjointness, and executor provenance before it exposes train rows to fitting.

The public learner sees only portable kinds and normalized values. Private bindings retain the
species, location, transformation family, resource pool, scenario, and executable. A Red-shaped
fixture and a Crystal-shaped fixture with different private identities produce the same policy
input.

## Complete menus and hard masks

The calibration adapter requires at least three available, policy-distinguishable rows. Additional
unavailable or unknown rows remain visible with identity-free reasons but receive behavior
probability zero. The adapter derives hard masks for:

- a living-collection invariant violation;
- a missing option-specific resource pool rather than merely low aggregate inventory;
- insufficient storage headroom;
- a declared mechanical, access, temporary, or unknown-world-state blocker.

Every context pressure and candidate ratio retains its raw numerator and denominator in path-free
normalization provenance. Action and frame bounds are frozen prospectively. Candidate ordering is
a SHA-256-seeded neutral permutation over source ordinals and never uses a private binding value.

## Randomization and propensity integrity

The behavior policy assigns non-uniform rank weights `1..N` to all available rows, gives every
available option positive support, and records the full probability vector. A single CSPRNG value
is bound to the frozen scenario, partition, and complete policy menu. Separate probability-order
and weighted-ticket seeds derive from that commitment, so the distribution and selected row can be
replayed exactly.

The authentic materializer must do four things durably:

1. claim the scenario before selection;
2. issue exactly one system-random commitment after the complete menu is frozen;
3. persist that commitment before controller input;
4. forbid reissue or retry after the claim.

This obligation is load-bearing. Searching randomization values until a desired arm wins would
make the logged inverse-propensity weight false. The public collector no longer accepts separate
caller-selected probability and draw seeds, and the calibration fixture no longer searches seeds
to manufacture kind/family coverage. Manually constructed fixture commitments are provenance-
marked synthetic and cannot open the calibration fit; counted rows require the system CSPRNG
issuer. Cross-process once-only durability belongs to the next materializer and remains a stop
condition until implemented and mutation-tested.

## Genuine executor provenance

Raw callables are marked `synthetic_test` and can exercise ROM-free schemas, but a selected
synthetic binding cannot open the fit gate. Counted settled examples must trace to one of the two
established Red semantic boundaries:

- the same-reset dual acquisition/evolution capability runtime; or
- an `ExecutableGoalBinding` supplied by a bounded Red goal skill, covering portable acquire,
  evolve, develop, manage-storage, resupply, explore, and access-unlock intents.

The goal-skill wrapper retains the execution report only for that skill's independent verifier.
The collector never interprets an executor return value as a label. Outcome deltas and costs still
come from the fresh post-action snapshot.

## Selected-arm settlement

Exactly one available binding receives authority, and that object becomes consumed before its
callable runs. Unselected and masked options execute zero times and receive zero targets.

An ordinary executor exception does not decide the label because cartridge state may already have
changed; the collector still attempts one fresh observation. Readable unchanged, partially
changed, successful, and failed states become settled evidence. Observation failure, an external
interruption, or a failed provenance join is target-free censoring. Process-level interruptions
remain visible to the durable outer runner.

Success is independently verified. A private verifier cannot override a realized loss of any
previously retained living target: such a row is forced to failure, and the aggregate loss enters
the irreversible-loss outcome. Scenario identity, monotone action/frame counters, party capacity,
menu hash, partition, randomization commitment, normalization provenance, selected binding,
family, and location are all joined into the decision record.

## Calibration gate

The first integration/variance pilot opens one train-only fit only after all of the following are
settled through authenticated executors:

- at least eight train examples;
- at least four train option kinds;
- at least three train transformation families;
- at least four development examples;
- at least four development families and four development locations;
- zero train/development family overlap;
- zero train/development location overlap;
- unique decision and scenario identities.

Censored attempts remain in the campaign record but cannot satisfy settled coverage or become
targets. No success/failure balance is required. The batch reports menu widths, offered and
selected kinds, behavior-probability range, importance-cap exercise, censoring by prospective risk
band, and the explicit fact that context-sampling propensity is not corrected.

The 8+4 minimum is deliberately too small for coefficient interpretation, policy-superiority
claims, or promotion. It is an integration and variance pilot that sizes the later powered paired
benchmark.

## Verification and review

The current ROM-free implementation has 30 focused passing tests and a 79-test related slice.
The complete non-integration repository gate is **4,778 passed · 3 deselected · 1 expected
failure**, with public-artifact, documentation, registry, Ruff, and full-package mypy checks green.
Tests discriminate identity removal,
normalization provenance, specific resource pools, every hard mask, neutral ordering, randomization
replay and tampering, one system draw, selected-only execution, no retry, censoring, process
interruption, menu/scenario/partition binding, realized living-specimen loss, semantic executor
wrapping, synthetic-executor exclusion, and family/location partition gates.

Claude's first read-only review returned `GO-WITH-FIXES`: it found that caller-supplied draw seeds
could be searched and that synthetic callables could satisfy the coverage gate. Both paths were
removed before publication. Antigravity's independent read-only milestone audit returned `GO` with
no P0 blocker and correctly kept context-distribution correction and authentic emulator execution
as later limitations. Claude's CLI session then lost authentication before the post-fix re-review;
that availability problem does not weaken the fixed tests or Antigravity review, but it is recorded
rather than silently represented as a second final approval.

We reject one non-blocking review suggestion: equal before/after observer hashes do not prove an
observation was reused. An independently invoked observer may legitimately return identical state
after a zero-action execution failure. Independence is established by the separate observer call
and the next materializer's durable observation receipt, not by requiring the state value to
change.

## Next engineering gate

Build the repeatable Red scenario materializer. It must enumerate real, complete 3+ option menus
from authenticated nonsealed checkpoints; bind at least four genuinely available semantic option
kinds; durably claim each scenario; issue and persist one behavior commitment; execute one selected
skill; settle one fresh outcome; and resume only never-claimed scenarios after interruption.

The cheapest falsifier is a ROM-free durable-runner rehearsal that kills mutations for reissuing a
commitment, selecting before the full menu is frozen, counting a synthetic executor, executing a
masked or second arm, retrying a claimed scenario, or accepting an unbound observer receipt. Stop
before any real collection until that runner, its public path-free plan, and exact-source CI gate
are green.

After the 8+4 pilot: fit once on train, report development descriptively, power a paired Red
benchmark, and reorient. Crystal remains a frozen-weight transfer test, not another Red-specific
teacher-script project.
