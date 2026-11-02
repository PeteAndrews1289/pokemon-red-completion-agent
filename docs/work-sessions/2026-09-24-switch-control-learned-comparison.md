# Switch/control curriculum complete; learning improves wins, risk gate fails

[Evidence](../evidence/red-switch-control-learned-comparison-2026-09-24.json).

## Outcome

All36TRAIN lessons completed and were independently reconstructed from935measured
branches:22845branch decisions plus254context-selection trajectory decisions.
The approved continuation retained23and added13lessons. Its340collection episodes
and144comparison episodes completed without censoring. Earlier censored and
missing-phase packets remain unchanged; no old branch was replayed or relabeled.
All484new endpoints were independently reobserved with0inputs, and11718recorded
decisions reproduced. Costs:178127actions,15159525frames,4919PP,1831partyfaints;
165wins/319losses,0illegal/interventions.335prescribed TRAIN opening choices are
explicit experimental branches,not unprompted learner selections. Comparison
actions are learner-selected. Packet runtime1446.08seconds includes its fit/audit,
not preparation or the later independent audit. Allgame processes stopped.

One two-stage fit reduced new reserve-selection regret1.74509191→0.01473761
(99.16%) and composed stay/switch regret2.25879965→0.20717917(90.83%). All retained
groups were nonincreasing. Damage/reference and move/status components remained
identical; all591retainedstatus predictions matched. Independent recomputation
confirmed the saved-model regrets, provenance and frozen components without refitting.

| Untouched comparison | Baseline | Candidate |
| --- | ---: | ---: |
| Wins, out of72timings across24teams | 20 | 27 |
| All decisions | 1571 | 1473 |
| All PP spent | 623 | 604 |
| Decisions in13common wins | 253 | 244 |
| PP in13common wins | 127 | 121 |
| Type-immune attacks | 53 | 61 |
| Zero-coverage choices with covered alternative | 32 | 27 |
| Combined flags / learned decisions | 85/1571(5.41%) | 88/1473(5.97%) |
| Illegal actions / teacher interventions | 0/0 | 0/0 |

Wins and common-win cost gates pass. **The prospectively required risk improvement
fails. Candidateb106108e is retained but NOT promoted.** The run is closed after
one fit and all144comparisons; no optimizer sweep, holdout replay or changed gate.
Fourteen timing pairs were candidate-only wins,seven baseline-only,13both wins,
38both losses. Timing siblings and shared TRAIN roots are correlated; these are
24constructed teams,not72independent natural roots or a story win-rate estimate.

## Why the failure matters

Posthoc localization is diagnostic, not a new acceptance test. Most families gained
wins, but status attrition fell6→2 and forced replacement4→2. One status-family
team fell3/3→0/3 and contributes13additional flags:8poor-coverage reserve choices
and5immune attacks, all after at least one faint. Its five immune attacks occurred
while the existing attack-after-switch guard masked switching. This points to the
preceding reserve choices; it does not prove an alternative would have won.

Across all cases, immune attacks with a covered living reserve fell28→27; those
without one rose25→34. Thus the aggregate risk increase also reflects which
endgame states the actors reach, not simply worse attack selection. Every flagged
immune attack lacked positive-power coverage on the active member. Risk flags
remain proxies, not counterfactual regret. Do not discard this failed gate as noise:
the concentrated status/attrition loss deserves a targeted next lesson.

The attack/status head staying identical cannot guarantee identical full-battle
behavior: changed switches expose it to different later states. Successful fitting
of36capture decisions is not mastery of every downstream recovery decision.

## What changed and what stayed fixed

Source662b3a1d explicitly permits any faint count only for prospectively declared
optional-prompt TRAIN selections. Defaults and forced-replacement strata stay fixed;
13new regressions plus the focused suite pass(403tests including documentation).
The replacement rotated the own party once, preserving memberHP/PP/levels. It is
the same composition, not independent. All37remaining setups passed0input checks.
The three newly sampled optional prompts happened before faints; native after-faint
selection was permitted but not exercised by these three selected boundaries.

No campaign inputs, story objectives, registrations, publication or authority
promotion. Actual461/state359a96aa,unused462,actor4ea4cfde remain protected.
Story32/36,17registrations,11765cash; separate collection109/124 unchanged.

## Recommended next bounded objective

Keep this completed corpus and both frozen actors. Prospectively declare a small
fresh TRAIN later-state lesson covering depleted/status-afflicted parties and
forced/voluntary reserve choices after faints. Use state-based selection and measured
terminal branches under the candidate continuation, not labels from these opened
comparison cases. Check whether the current representation separates the important
alternatives before redesigning it. Preserve all prior training as retention.

Then, only under a new declared packet, one correction fit and a new disjoint
comparison. Keep the original comparison closed and failed. No more grinding,
partial-corpus restart, automatic candidate deployment or Agatha replay. Estimate
45–90minutes for the next measured lesson and decision, not guaranteed qualification.

Mission check: reusable switching/recovery; measured switch/control learning with
damage/status fixed; untouched composition teams; cheapest falsifier was target
audit then regret/retention/comparison;two-hour16:03UTC ceiling; stop on failed gate.
The risk gate ended this packet after a real but incomplete learning improvement.
