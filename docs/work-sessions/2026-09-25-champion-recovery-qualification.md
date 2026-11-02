# Recovery and PC withdrawal verified; exact shopping admission corrected

[Evidence](../evidence/red-champion-recovery-qualification-2026-09-25.json).
Maintenance supporting the next learned Champion attempt, not new learning.

## Native result

One DEVELOPMENT continuation began from the retained losing Champion copy's
native blackout endpoint. No battle was repeated and no save memory was edited.
The declared cap was 2000 actions, 200000 frames, 120 seconds and 11100 spending;
the attempt closed at its first failure, with every action and endpoint retained.

Verified: entering Indigo cleared the League challenge latch and four boss flags;
the native Center interaction completed with full HP/status/PP; Fly reached Saffron;
the PC withdrew exactly seven owned Potions; all menus closed; navigation reached
the Saffron clerk. Party, boxes, registrations and cash stayed unchanged.
The starting blackout state was already fully healed: this is a verified Center
interaction/full-resource endpoint, not a measured additional healing gain.

Shopping was masked before any clerk interaction or purchase. The old resource
score treats all recovery items as interchangeable: seven Potions, five Parlyz
Heals, one Antidote and one Awakening exceed its eight-item target. Thus the score
is 1.0 despite zero Revives and zero Hyper Potions. The correct response is to
represent the declared item deficits, not raise the generic target until it passes.

Retained cost: **178 actions, 11460 frames, 1.06 runtime seconds, zero money spent**.
The endpoint remains at Saffron Mart with 11921 cash and all seven Potions.
Shopping and the return to Indigo are **not yet native-qualified**. No earned
campaign dispatch occurred. The failed receipt remains failed.

## Implemented corrections

- New exact-quantity PC API handles full/partial stacks and merges, verifies the
  selected item and quantity before confirmation, bounds input attempts, rejects
  wrong inventory changes, and protects party, boxes, position and money.
  The old singleton API retains its stricter absent-bag/exact-singleton rules.
- Explicit Mart reserve targets require each order to exactly fill its declared
  deficit. Already-satisfied/stale targets, insufficient cash, capacity failures,
  invalid targets, sales and incompatible affordable-ball mode are rejected.
  Exact money, inventory, party, collection and story checks replace only this
  opt-in mode's aggregate-progress test; historical behavior stays unchanged.
- A read-only reopening of the retained clerk endpoint reproduces the old mask
  and verifies the corrected 11100 quote/admission, with zero frames or actions.
  The operator declared these reserves; this is not a learned supply decision.

639 targeted tests pass, including 59 new cases. Changed Python files pass lint.
This is not a full-suite pass or proof of a future battle win. The private audit
checks every retained state and all 178 paired action-log entries. Executed source
is retained at local commit f8d7c7b9; the initially audited reserve correction
diff is preserved separately, followed only by lint cleanup.

## Next bounded objective

Start at the retained clerk endpoint, not the blackout origin. Prospectively
bind one remaining shopping/return segment: buy three Hyper Potions, four Revives
and one Full Heal for 11100, then return to Indigo with 821 cash, full resources
and the seven Potions. Carry the prior 178 actions/11460 frames forward in totals.
No PC/healing replay, sale, battle, fit, memory edit or campaign import.
Once this passes, bind a genuine Champion attempt plus conditional natural-loss
recovery; do not force a loss or substitute an assisted win.

Actual463 and all 464 campaign stage hashes remain unchanged; stage464 is absent.
Story34/36, separate shared collection109/124, fresh Red0/5, TRAIN135 unchanged.
Both models unchanged. All gameplay stopped. No GitHub publication.
Next shopping/return verification estimate30–60minutes, AstraHigh, Fastoff.
