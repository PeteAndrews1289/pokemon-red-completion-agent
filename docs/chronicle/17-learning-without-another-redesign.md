# September24–25: finish the trainer, measure the remaining trade-off

The [composed-learning session](../work-sessions/2026-09-24-composed-learning.md)
finally repaired the training handoff between choosing a reserve and choosing
whether to switch. Its complete comparison produced32/72wins versus27/72for
both references, but missed the original risk/resource gates. That failure stayed
visible rather than becoming another declaration of a finished player.

Pete then requested a finite sequence: freeze the working trainer, measure the
missing cases, fit once, and run one fresh comparison. The
[risk/cost experiment](../work-sessions/2026-09-25-risk-cost-learning.md) did that
without changing executable trainer code, rewards or acceptance thresholds.

Twelve isolated TRAIN setups varied HP,PP and status while retaining their
source lineage.360 measured alternative continuations supplied the labels; no
unplayed alternative was called correct. One update lowered full-action training
error55.9% while preserving37 old numeric checks and591 status predictions.
This was fitted model learning, not Pokémon leveling or another software-only repair.

All216 fresh comparison battles completed. Risk flags fell to21 versus52/27for
the two references, and total resource use fell. Wins were29/72 versus30/72,
however, and shared wins needed six extra decisions against the older parent.
The strict qualification remained failed. Low-HP/forced-replacement scenarios
were the clearest remaining concern; first-choice divergences locate a question,
not proof of a counterfactual win or a reason to train on the held-out cases.

No second fit followed. The actual post-Bruno save and deployed actor remained
untouched. The outcome is a working, measured training process and a more precise
policy question—not a fresh Red completion, a population-significance claim,
or permission to quietly turn a failed screen into a pass.
