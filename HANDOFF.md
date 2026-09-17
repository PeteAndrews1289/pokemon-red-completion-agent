# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 16, 2026.

## Assisted battle pilot improved a choice, but did not earn promotion

This session used four authenticated red-battle-v2 captures from distinct
upstream Red-goal roots, split two train and two development before outcomes.
A disclosed trainer-only state edit inserted Guillotine with five PP in physical
move slot 4; this is not a final-player action. Both train captures and both
reserved development captures completed their two fixed frame trials without
quarantine. The frozen ranker had 3.132 expected-utility regret on one train
choice, so a private two-example last-layer pilot fit was justified. It
corrected that choice and preserved the other train choice.

Development predictions were committed before outcomes. On the first reserved
root, frozen chose the risky attack (utility 0), the pilot chose a safer attack
(0.218), but another move was best (0.566). On the second, both chose the best
move (utility 3). Thus the pilot won once and tied once versus frozen but tied
the fixed heuristic twice. Both models made only one of two best choices. The
two assisted examples per partition are far below ordinary four-root/four-example
train coverage; the roots were pre-existing, not newly earned full-player runs.
No authority or transfer claim follows. [Evidence](docs/evidence/red-choice-rich-battle-pilot-2026-09-16.json).

The previous near-boundary and timing work remains in
[its evidence](docs/evidence/red-battle-timing-and-contrast-2026-09-16.json):
one-root easy states supplied no corrective regret, and a consumed sleeping
state may explain timing mismatch but must never be replayed.

Next: inventory natural battle captures for at least four independent train
roots with four distinct informative examples per root and separately reserved
development roots. Freeze a bounded curriculum only if that supply exists;
otherwise reconsider the battle representation or data strategy. Do not clone
the slot-4 OHKO pilot, fit on development, or promote a model that merely ties
the fixed heuristic. Red remains 96/124, 74 specimens, 198 cash; Model137 and
frozen battle authority remain unchanged; fresh acceptance 0/5. Gameplay
stopped; no GitHub push. Sol High, Fast off for this bounded inventory/design.

Earlier evidence: [live model-controlled attacks](docs/evidence/red-earned-learned-battle-2026-09-16.json) ·
[rejected assisted OHKO candidate](docs/evidence/red-ohko-expected-utility-2026-09-16.json) ·
[live faint qualification](docs/evidence/red-live-faint-outcome-2026-09-16.json).
