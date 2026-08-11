# Strategic scenario registry audit — 2026-08-11

## Outcome

The duplicate whole-game campaign now has a prospective replacement. The public v2 registry fixes
48 quest situations before any short-scenario route cost, teacher outcome or model result is
observed:

| Partition | Situations | Status |
| --- | ---: | --- |
| train | 24 | unopened |
| validation | 12 | unopened |
| test | 12 | sealed |

The registry is a plan, not a dataset. It reports zero authenticated live policy contexts and keeps
collection closed. A later emulator rehearsal must still reach every learning frontier, measure
the genuine routes, join the teacher's selection to an outcome, and demonstrate that the 36
train/validation rows remain distinct after identity and candidate order are removed. The 12 test
frontiers stay sealed until final evaluation; running them in a rehearsal would open the test set.

## Where the situations came from

The completion graph has 166 dependency-reachable completion states and 129 states with at least
two legal objectives. The fixed qualified route visits only 14 of those branch states, and the
current strategic instrumentation records only three of them. That is why repeating the full game
could never supply the needed diversity.

The selection is prospective and stratified by the qualified teacher's next objective. It retains
sparse early choices instead of letting the combinatorially dense Surf/Strength region dominate:

| Teacher objective | Situations |
| --- | ---: |
| Help Bill | 1 |
| Defeat Misty | 2 |
| Clear Rocket Hideout | 3 |
| Rescue Mr. Fuji | 4 |
| Reach Fuchsia | 4 |
| Obtain Surf | 7 |
| Defeat Koga | 5 |
| Obtain Strength | 7 |
| Defeat Erika | 6 |
| Reach Saffron | 3 |
| Liberate Silph | 3 |
| Defeat Sabrina | 3 |

Candidate density is 21 two-way, 22 three-way, three four-way and two five-way situations. Thus 27
of 48 contexts have three to five legal story candidates. Binary frontiers remain where the graph
really offers only two; unreachable filler was not added to make the benchmark look harder.

## Baseline challenge stratum

Six validation situations are preregistered as cost-baseline challenge *hypotheses*. Their origin
is a region containing a legal non-teacher candidate—for example, Vermilion while the teacher
selects Misty, Celadon while the teacher selects Mr. Fuji or Surf, and Saffron while the teacher
selects Koga. This deliberately makes a nearby wrong objective tempting without declaring the
actual shortest route in advance.

The word “hypothesis” matters. Cartridge-derived routing must confirm that the cost baseline really
disagrees. If fewer than six validation contexts produce measured disagreement, the uncounted
rehearsal fails and the registry must be revised before collection. No model result may be used to
choose replacements.

## Fail-closed properties now implemented

- Candidate-order-invariant hashes cluster repeated policy inputs.
- Exact train/validation context overlap and conflicting targets reject model admission.
- At least 24 unique train and 12 unique validation contexts are required from collected data.
- Validation needs at least six unique teacher-versus-cost disagreements; five can never admit a
  model, while six permits a perfect scorer to reach a two-sided exact value of 0.03125.
- Scenario rows must match the quest graph's exact legal frontier and the frozen teacher order.
- Rocket Hideout cannot appear complete without the automatically obtained Silph Scope; Champion
  cannot appear complete without Hall of Fame.
- Context families cannot cross partitions. The ordinary accessor refuses the 12 test situations.
- Every row and the full canonical registry are content-addressed. Unknown or ignored fields are
  rejected.

## What remains before training

1. **Complete in code:** authenticated rehearsal assignments bind one non-test registry row to the
   committed execution, exact private capture envelope/state and one-shot episode identity.
2. **Complete in code:** the short executor preflights all candidates before writing, records the
   choice before movement, consumes one route outcome and strictly reloads exactly one decision.
3. **Next live gate:** publish the source, run the command's read-only preflight, then execute one
   uncounted learning scenario. Expand to all 36 train/validation situations only after the first
   artifact passes strict reload. Captures remain private and never enter the repository.
4. Audit measured uniqueness, candidate order, the six validation cost-baseline disagreements,
   route availability and failure/censoring. Only then open one-attempt counted train/validation
   collection. Keep all 12 test situations sealed until final evaluation.
5. Fit and compare the first permutation-equivariant scorer on unique contexts, then shadow it in a
   full game before granting bounded route-choice authority.

The command is intentionally two-stage:

```bash
.venv/bin/python scripts/rehearse_strategic_scenario.py \
  --scenario-id red-strategic-scenario-v2-001-train \
  --state "$SCENARIO_STATE" \
  --private-root "$PRIVATE_ROOT"

# Add --execute only after the read-only preflight reports ready.
```

It refuses dirty or unpublished source, never writes beside the ROM, and emits no private path in
its public result or failure message.

The old 703,275-record clean-power rehearsal remains the end-to-end integration proof. The old
5/2/5 whole-root registry remains historical and unauthorized. Neither is relabeled into the new
scenario collection.
