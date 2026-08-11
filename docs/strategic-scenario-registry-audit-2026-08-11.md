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
collection closed. A later emulator rehearsal must still reach every declared frontier, measure
the genuine routes, join the teacher's selection to an outcome, and demonstrate that the 48 rows
remain distinct after identity and candidate order are removed.

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

1. Add an authenticated scenario-execution assignment that binds one registry row to a source
   commit, private capture digest, trajectory episode and one-attempt outcome.
2. Create or derive clean source captures for the declared alternate progress frontiers. A capture
   is ROM-derived private material and never enters the repository.
3. Run an uncounted 48-scenario rehearsal. Audit measured uniqueness, candidate order, cost
   discordance, route outcomes, failures and interruptions.
4. Freeze the passing source and registry. Collect train and validation once; keep test unopened.
5. Fit and compare the first permutation-equivariant scorer on unique contexts, then shadow it in a
   full game before granting bounded route-choice authority.

The old 703,275-record clean-power rehearsal remains the end-to-end integration proof. The old
5/2/5 whole-root registry remains historical and unauthorized. Neither is relabeled into the new
scenario collection.
