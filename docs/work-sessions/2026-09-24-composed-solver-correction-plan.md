# Composed fit: equivalent solver correction

The first composed fit is closed and retained. Its control coverage and finish
stages accepted zero updates: their minimum-L1 solver reached its limit before
any neural trial. The candidate retained all 35 checks but improved new full
control regret by 0%; no native comparison episode was opened.

This correction replaces the minimum-L1 epigraph with signed nonnegative
variables, d = u - v, bounded by the original radius. Minimizing sum(u + v)
is equivalent to minimizing the L1 displacement; cancellation cannot improve
the objective. This removes two inequality rows per parameter without changing
the feasible displacement set. Gain fraction, time/iteration limits, numerical
residual checks, trust schedule, nonlinear acceptance and final gates stay fixed.
Different solutions of a degenerate linear program are possible.

Mission check: improve the actual composed battle learner; no runtime authority
change; transfer still requires the original unused 216-battle comparison;
first falsifiers are small-program objective equivalence and a 4,576-parameter
structural regression; original 02:18 UTC session cutoff remains; stop on
invalid evidence, exhausted declared bounds, or failed original qualification.

After tests and an immutable source/plan freeze, run one corrective three-stage
fit from the same parent and admitted training records using the existing
600-attempt/radius-0.05 schedule. Save it in a new packet, pin the first composed
failure, and independently recompute every accepted checkpoint and the original
35 final checks. Only a passing fit opens the original comparison. Do not alter
closed packets, use comparison outcomes for training, promote a model, advance
the campaign, or publish anything.
