# A second real finite-goal learner, with the failed attempt included

The [Agatha fit receipt](../evidence/red-agatha-controller-fit-2026-09-09.json)
records a separate three-return shadow model. Its complete intended batch includes
two heal-then-story completions and the immediate-story controller stop. No
success-only filtering, discarded negative, cancelled-trial label or gameplay
retry occurred. Native model82 and the four-return Bruno model32 are unchanged.

The independent reopening audit re-admitted the whole batch, matched every stored
outcome and the model's dataset fingerprint, restored its parameters, and
recomputed weighted prediction losses without another optimization. Completion
training MSE fell from0.24987155 to0.00000294415; cost MSE from0.00700970 to
0.0000000825930. Those are in-sample errors on three correlated returns from one
initial context, not calibrated confidence, evaluation accuracy or generalization.

At that observed input the head estimates story completion/cost near0.00168/0.00276
and healing near0.99824/0.16968. The near-extreme scores are not probabilities we
can trust. They describe the retained experience under a particular controller:
the unhealed story attempt hit an unsupported entry-screen guard with all six
Pokémon alive. It does not prove a human or a better battle controller would lose.

## Publication fault and correction

The first optimization completed but artifact publication rejected an overlong
identifier before writing a candidate. The CLI test had mocked publication and
therefore missed the storage constraint. It now writes through the real artifact
store. A documented, deterministic recomputation used the same three outcomes,
ridge1 and importance cap10 after shortening only the prefix: **two computations,
one published candidate**, not two gameplay attempts or a clean first-attempt fit.
The original failure log is retained. No hyperparameter search occurred.

## Next bounded control question

A different successful post-Bruno training endpoint has changed resources and
two genuine Agatha/restoration choices. It was checked with zero input or frames.
Two private preparation mistakes were retained: an unpushed source was rejected,
then an invocation that dropped the required ancestor chain was rejected. Using
the original parent's complete declaration passed without changing any guard.

The ordinary forward-probe loader still rejects controller-return fit artifacts.
A separately named loader, selected by an explicit CLI flag, re-admits the entire
controller batch and checks stored outcomes, counts, dataset, goal, profile and
frozen tail before granting bounded training-probe scope. The fit contract is
visible in the probe header. The internal reviewer found no critical blocker.

Only one new first-choice training probe is planned: Agatha head first, independently
seeded old82 tail if needed, two-macro limit, no fitting or promotion, no retry.
It uses another historical training endpoint, not failed Agatha03. That remains
correlated practice, not an untouched evaluation. Do not start after10:20UTC in
this overnight session; overall work stops10:42:58UTC. A result gets its own receipt.

Phase4 remains open. Its exit still requires model-directed completion with
concurrent Champion and Hall-of-Fame evidence under the declared authority. The
long-term objective remains a transferable player and living Pokédex, not a
collection of polished teacher routes.
