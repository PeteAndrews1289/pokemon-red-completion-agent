# Travel capture connected: Koffing retained, destination failed

## Mission check

- Reusable capability: acquire missing registrations encountered during ordinary acquisition travel.
- Learned authority: retain the actor's sampled destination; capture mechanics remain deterministic.
- Transfer test: vary missing/credited species, active boxes, resources and routes in ROM-free tests. This is not a cross-game evaluation.
- Cheapest falsifier: a capture bypasses dispatch limits or a partial collection gain is mislabeled as a completed destination.
- Time box: one focused integration session, targeted tests and one fresh model47 destination choice; no broad route rewrite.
- Stop condition: retain any failure and costs, stop at the declared single step, never replay a consumed attempt.

## Verified result

One fresh destination choice selected RockTunnelB1F from eight alternatives. During departure
from Mansion1F, the bounded deterministic capture controller caught level32 Koffing.
The verifier then stopped the trip: it expected the new boxed specimen at the end of the
active box, whereas Red inserted it at the front. This was our verifier assumption, not a
failed catch or evidence that the model had reached its destination.

- Registered species: **55 to56**; physical specimens: **48 to49**; living species:45.
- Registered-objective examples: **47 to48**, one actual destination fit.
- Goal outcome: **failed**, with the catch and costs retained separately.
- Recorded gameplay: **211 actions /17,028 frames**; cycle232.271seconds including preparation.
- Supplies: six to three ordinary capture items; money8 unchanged.
- Terminal: Mansion1F, field-ready, outside battle, no pending trainer, all six party members alive and status-free.

[Path-free learning evidence](../evidence/red-travel-capture-learning-2026-09-10.json)
and [saved collection](../evidence/red-travel-capture-saved-2026-09-10.json).
Played source: `ff45a1941816026b0c5707ea89ea2b7a9e7e5bd9`.
The later repair was not present in this run. No retry, refund, reset or success relabeling occurred.
Gameplay is stopped at closeout.

## Connected runtime

Travel capture is an explicit prospective acquisition-only profile transition. Historical
profiles reconstruct unchanged. Indoor departure, walking and post-Fly acquisition segments
reuse the existing recorded controller chain with nested hard action/frame bounds. Trainer,
uncatchable, already-credited, missing-resource and unsafe-party cases retain guarded fallback.
The feature currently requires a full party and space in the active box.

A destination acknowledgement may avoid a redundant local survey only after actual arrival
and verified travel-capture receipts establish the selected source is satisfied. It introduces
no encounter-level training labels. A later navigation failure remains a failed parent goal,
even if a missing species was acquired earlier. Successful route reports now project the
verified capture metrics without private route fields; this report change is prospective too.

## Diagnosis and prospective correction

Independent reads authenticated the exact saved checkpoint and collection without controller
input, frames, predictions or fitting. The active box held Golbat and Graveler before the catch.
Afterward it held Koffing at slot0, Golbat at slot1 and Graveler at slot2. Other boxes and stock
were unchanged. The original empty-box fixtures did not distinguish prepend from append.

The corrected verifier expects every old active-box slot to shift by exactly one after a catch,
with the new specimen at slot0. It still rejects lost stock, altered levels, reordered old
specimens and changes to other boxes. New nonempty-box contradiction cases exercise each of
those boundaries. Hard action/frame caps, profile compatibility, actual-arrival acknowledgement
and private-field projection are covered by targeted tests. Tests do not prove live route
resumption: that remains the next gameplay falsifier.

## Learning interpretation and reorientation

Closeout validation: **401 targeted tests passed** across travel capture, dispatch budgets,
route/Fly/indoor integration, profiles, player arguments, product focus and roadmap. Targeted
lint and two-source-file type checks passed, as did documentation links, product-focus evidence,
prospective registry freshness and diff checks. The infographic was regenerated and visually
inspected. This is a targeted local result, not a claim that the full hosted suite has passed.

The destination policy mixes25percent uniform exploration with75percent model softmax;
RockTunnelB1F was not a greedy top-score selection. The forced singleton acquisition macro
is not a second training example. Fitting uses actual selected-arm outcomes, including failure
and collection gain; it is not training button-level capture behavior.

The current48-row training corpus contains24 acquisition,9 evolution,9 restoration and6 supply
examples. These same-lineage, in-sample counts are not independent success rates, evidence of
fresh-game autonomy, or transfer to Blue/Crystal. The earlier114-example objective remains separate.

The travel checklist stays **1/3**: a caught Pokemon and a fitted failed trip are real progress,
but do not yet establish the complete capture-and-resume capability. Stage IDs and exits remain
unchanged. The end goal remains a model that can play adaptively and register available Pokemon,
not an expanding collection of species-specific routes. No level100 or living-form requirement
has been reintroduced.

## External review

Gemini3.8 Flash High completed a supplied-code, no-tools review in115.777seconds, one turn.
Both reported code defects were false positives: an excerpt cut off an existing return, and
two concatenated excerpts appeared to put a delegate return in the wrong method. Full source
inspection rejected both. Our excerpt boundaries caused that ambiguity; future review packets
should include complete files or explicit boundaries. The live run and exact-state diagnosis,
not this review, identified the box-order bug. No external edits were integrated.

The CLI reported16,749 input tokens and41,360 output tokens, with40,788 thinking tokens and
8,157 cache-read tokens as additional vendor fields. These may overlap and are not additive
quota estimates. Five-hour and weekly service quota were unavailable. Claude was not used;
no review remains running. This review did not materially accelerate the correction.

## Next bounded session

Start from the retained V checkpoint and model48, preserving all previous profile/source
transitions. Collect a fresh bounded model-selected choice under the qualified prospective
repair. Observe whether a useful travel capture resumes its actual route, and retain any partial
gain or failure without relabeling. Do not force Koffing evolution or replay the consumed trip.
Address a demonstrated blocker locally; do not begin another navigation framework or broad audit.

Expected scope: one focused session, approximately30–60minutes if the retained state admits
a useful choice; this is not an estimate to full-game autonomy or complete Pokédex training.
Recommended setup: Astra High, Fast off. The immediate work is bounded integration and evidence
review, not an architectural redesign requiring a standing external-review gate.
