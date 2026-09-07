# Center control boundary audit

## Verdict

The apparent wall collision was an unfinished nurse interaction. The healed party and idle
movement flags were real, but they did not prove that overworld movement was available.
The diagnostic screenshot showed the farewell text. Two requested eastward moves produced no
displacement (4 actions / 96 frames). No terrain or route changes were needed.

The repair recognizes Red's standard text-box border in the observation adapter and completes
the healed Center interaction under a finite cancel/wait budget. The restore skill cannot
return while that box remains. Native evolution also handles old healed-but-dialogue-open
checkpoints; it does not silently reinterpret their recorded readiness or failed outcomes.
The decoder is a narrow standard-box detector, **not a general menu/overworld classifier**.

In one separate component qualification, farewell completion took 8 actions, the unchanged
computed 11-step route passed with zero replanning, and Bill's PC opened. Total: 31 actions /
2304 frames. Party and all boxes were unchanged. Source for the mechanism:
[Center interaction ordering](https://github.com/pret/pokered/blob/master/engine/events/pokecenter.asm)
and [text-frame character encoding](https://github.com/pret/pokered/blob/master/constants/charmap.asm).
The measurements come from our actual private game diagnostic, not from those references.

## Findings that prevent an end-to-end claim

1. **Training capability mismatch:** the existing evolution trainer forces participation-only
   experience, and its fixed escort stops fighting at level 55. The current escort is level 63.
   This combination cannot deliberately earn the required experience. Availability and execution
   now reject a missing/capped escort before routing or storage changes. The cap is not raised.
2. **PC facing is not bound by native routing:** the standalone qualification explicitly faced
   the PC before invoking its existing menu specialist. The native boxed engine only requests a
   destination coordinate; it does not establish that orientation. Thus successful standalone PC
   opening is not proof that the native evolution operation now works end-to-end. Do not hide
   that diagnostic action inside a claimed production success.
3. **Partial training remains unqualified:** the current boxed-only offer rejects a precursor
   already moved into the party. A battle-budget stop needs a resumable semantic development
   operation, not a reset or another deposit/withdrawal. The 32-battle cap also has no proof of
   being sufficient for the current precursor's complete evolution.

No new learner fit, model-selected outcome, capture, evolution or transferable-performance
result occurred. Model `1b26aa44` retains 35 examples. Useful memory-aware play remains 2/5.
The original saved checkpoint remains unchanged and still contains farewell dialogue. Component
diagnostics are private, closed and excluded from fitting; they did not replace the player save.

## Reorientation

This is maintenance that unblocks the named evolution alternative, not learned progress. The
one-session anti-drift alarm is now due: do not launch another acquisition-only learning loop or
add model features. The next bounded session must qualify a complete useful operation.

1. Bind PC interaction orientation as a verified specialist boundary, not a walk-string route.
2. Replace the mandatory capped-escort dependency with safe direct trainee participation where
   matchups and PP permit, or another explicitly eligible support strategy. Preserve battle
   safety and avoid raising the cap merely to let the overpowered starter do everything.
3. Support safe, durable partial evolution progress and re-entry from the current party. Check
   budget feasibility before sending storage inputs. Stop and reorient if this is a new trainer
   project rather than a small extension of the existing battle/party skills.
4. Only after that works, collect model-selected contrasts, retaining failures and all 35 rows.

The delivery order remains useful Red play, sustained Red competence, living collection,
compatible unfamiliar Red modification, then Crystal. No baseline exit was weakened.

## Verification

370 focused ROM-free tests passed across observation, goal skills, native evolution, goal context,
resource routing, continuation, route execution, boxed evolution, PC storage and team training.
These include boundary-value escort tests (54/55/63), stale-offer rechecking, multi-page farewell,
permanently stuck dialogue, unsafe-start refusal and independent text-frame corruption fixtures.
No complete-suite result from the prior session is relabeled as a current result.

112 protocol/focus/roadmap checks also passed (partly overlapping a broader registry selection).
That earlier selection had 162 passes and one stale current-source golden; all three regenerated
source/teacher/registry identity assertions were updated together and the complete affected
protocol file passed. Historical outcome evidence was not rewritten. Type checking passed for
400 source files; lint, documentation/focus, public-artifact and diff checks passed. The regenerated
infographic was visually inspected. The full approximately 17-minute suite was not rerun here;
the qualification uses focused coverage of every changed execution seam.
