# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Two retention failures; focused Astra design review is next

The prior [Astra review](docs/reviews/red-trainer-astra-focused-review-2026-09-17.md)
led to corrected TRAIN targets: average each actual action over declared
timings, then compare actions and apply softmax. Across 80 distinct head inputs
there are zero mean-return ranking mismatches. Complete control-plus-child
action regret is now recorded. The first corrected 52-context cold fit
missed the original-44 attack gate by 0.0017.

One prospectively bounded [old-weight continuation](docs/evidence/red-trainer-warm-attack-retention-2026-09-17.json)
reused the same 52 admitted TRAIN contexts with no gameplay. It ran 100 attack
updates from the compatible older 44-context weights while fitting control
and switch heads for 2400 epochs. Original-44 attack regret reached 0.08566
(gate <=0.0554); all-52 reached 0.08497 (gate <=0.0648). Complete-action
regret reached 0.11260 (gate <=0.1609). Only two original attack predictions
flipped. One gained 0.0189 return and the other lost 1.6276.

On corrected attack targets, cross-entropy improved from 0.78434 at the old
weights to 0.77082 after continuation while observed-return regret worsened
from 0.04475 to 0.08497. The continuation receipt incorrectly calls the
seeded random starting loss the initial loss; the source diagnostic has now
been corrected, and the retained receipt has not been rewritten. This
optimizer/objective conflict is the next decision, not evidence for larger
capacity. The [Astra brief](docs/reviews/red-trainer-next-astra-retention-brief-2026-09-17.md)
asks for one bounded successor design.

Do not run the proposed four-scenario terminal HP pilot or fit again under
the current recipe. Both retention results are preserved. The earlier
correlated League DEVELOPMENT comparison remains failed and consumed; no
DEVELOPMENT data entered these fits. No new natural test ran. The older
frozen control retains authority.

Model137 stays 137 examples / 92 successes / 58 economy-qualified;
Red stays 96/124; fresh acceptance stays 0/5. Gameplay is stopped.
No full game, ROM hack, Crystal work or GitHub push occurred. Pete
decides publication. Recommended next review: Astra High, Fast off.
