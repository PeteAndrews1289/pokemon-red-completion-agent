"""Synthetic retained-utility budget math and public API guards; no native data."""
from dataclasses import replace
import unittest
from unittest.mock import patch
import numpy as np
import scipy.optimize
import pokemon_red_completion.player_challenge_consequence as h
from pokemon_red_completion.living_dex_option_value import option_feature_names
from pokemon_red_completion.player_preparation_party_context import PreparationPartyWitness
from pokemon_red_completion.provenance import canonical_sha256

U = np.asarray((0.0, 1.0, -0.1, -0.1, -0.25, 0.0, -0.05, -0.5, 0.25))
RECIPE = dict(ridge=1.0, feedback_version=2, feature_version=15, context_projection='prospective_preparation_party_context_v1', utility_absolute_loss=True)
COUNTS = dict(synthetic_optimizer_runs=0, public_prediction_attempts=0, actual_TRAIN_data_fits=0, native_loads=0)

def data():
    z = np.eye(4) - np.full((4, 4), 0.25)
    y = np.asarray([[1.0, 0.0, 0.2, 0.2, 1.0, 0.0, 0.25, 0.0, 0.2], [1.0, 1.0, 0.1, 0.1, 0.0, 0.3, 0.0, 0.0, 1.0], [1.0, 0.0, 0.3, 0.3, 1.0, 0.0, 0.5, 0.0, 0.1], [1.0, 1.0, 0.2, 0.2, 0.0, 0.5, 0.25, 0.0, 0.9]])
    return (z, y, ((1, 0), (3, 2)))

def synthetic_view(module, label, effort, actions):
    names = option_feature_names(15)
    x = [0.0] * len(names)
    x[names.index('kind.unlock_access')] = 1.0
    x[names.index('execution_effort')] = effort
    out = module.ChallengeConsequence(True, True, actions, actions * 60, 0, 100 + actions, 0, 2, False, 1.0)
    row = module.ConsequenceExample(canonical_sha256(dict(synthetic_budget_unit=label)), 'a' * 64, tuple(x), out, None, 'synthetic', 2, 15)
    return module.ConsequencePartyView(row, PreparationPartyWitness('b' * 64, (('unit-1', 'combat'), ('unit-2', 'combat'))), 'c' * 64, 'd' * 64, 'work_order_context_pin')

class Budget(unittest.TestCase):

    def setUp(self):
        guard = patch.object(h.ChallengeConsequenceHead, 'predict', side_effect=AssertionError('Synthetic budget checks must not query a model'))
        guard.start()
        self.addCleanup(guard.stop)

    def test_actual_epigraph_budget_enforced_without_objective_change(self):
        z, y, pairs = data()
        real = scipy.optimize.minimize
        captured = []

        def checked(fun, x0, **kw):
            n = len(z)
            A = np.asarray(kw['constraints'][0].A)
            ub = np.asarray(kw['constraints'][0].ub)
            self.assertTrue(np.array_equal(A[-1, -n:], (0.5, 0.5, 0.0, 0.0)))
            self.assertTrue(np.all(A[-1, :-n] == 0.0))
            self.assertEqual(ub[-1], 0.0)
            self.assertTrue(np.array_equal(kw['jac'](x0)[-n:], np.ones(n)))
            captured.append(True)
            COUNTS['synthetic_optimizer_runs'] += 1
            return real(fun, x0, **kw)
        with patch.object(scipy.optimize, 'minimize', checked):
            c, mean = h._fit_order_retained(z, y, pairs, U, utility_absolute_loss=True, retained_utility_indices=(0, 1), retained_utility_mae_cap=0.0)
        self.assertEqual(captured, [True])
        pred = z @ c + mean
        self.assertLessEqual(float(np.mean(np.abs((pred[:2] - y[:2]) @ U))), 1e-08)
        self.assertTrue(np.all(pred >= -1e-08))
        self.assertTrue(np.all(pred[:, (0, 1, 7, 8)] <= 1.0 + 1e-08))
        for winner, loser in pairs:
            self.assertGreaterEqual(float((pred[winner] - pred[loser]) @ U), 0.01 - 1e-08)

    def test_invalid_private_budgets_never_enter_optimizer(self):
        z, y, pairs = data()
        changes = [dict(retained_utility_indices=[]), dict(retained_utility_indices=(0,)), dict(retained_utility_mae_cap=0.1), dict(retained_utility_indices=(0, 0), retained_utility_mae_cap=0.1), dict(retained_utility_indices=(4,), retained_utility_mae_cap=0.1), dict(retained_utility_indices=(True,), retained_utility_mae_cap=0.1)]
        changes += [dict(retained_utility_indices=(0,), retained_utility_mae_cap=v) for v in (-1.0, True, float('nan'), float('inf'), '1')]
        with patch.object(scipy.optimize, 'minimize', side_effect=AssertionError('invalid budget must not reach solver')):
            for change in changes:
                with self.subTest(change=change), self.assertRaises(ValueError):
                    h._fit_order_retained(z, y, pairs, U, utility_absolute_loss=True, **change)
            with self.assertRaises(ValueError):
                h._fit_order_retained(z, y, pairs, U, retained_utility_indices=(0,), retained_utility_mae_cap=0.1)

    def test_public_budget_request_shape_digest_and_options(self):
        f = h._validate_retained_utility_budget_request
        valid = '1' * 64
        pair = (('1' * 64, '2' * 64),)
        self.assertFalse(f((), None, retention_pairs=(), utility_absolute_loss=False))
        self.assertTrue(f((valid,), 0.0, retention_pairs=pair, utility_absolute_loss=True))
        for declarations, cap, pairs, mode in [((), 0.1, pair, True), ((valid,), None, pair, True), ([valid], 0.1, pair, True), ((valid, valid), 0.1, pair, True), (('not-digest',), 0.1, pair, True), ((valid,), 0.1, (), True), ((valid,), 0.1, pair, False), ((valid,), True, pair, True), ((valid,), -1.0, pair, True), ((valid,), float('nan'), pair, True)]:
            with self.subTest(declarations=declarations, cap=cap), self.assertRaises(ValueError):
                f(declarations, cap, retention_pairs=pairs, utility_absolute_loss=mode)

    def test_public_api_maps_declarations_to_sorted_settled_indices_only(self):
        rows = tuple((synthetic_view(h, n, e, a) for n, e, a in [('winner', 0.0, 100), ('loser', 0.5, 1000), ('other', 1.0, 0)]))
        rows = tuple((replace(v, row=replace(v.row, provenance='native_train')) for v in rows))
        declarations = tuple((v.row.declaration_sha256 for v in rows[:2]))
        pair = (declarations,)
        seen = []

        def stub(z, y, pairs, utility, *, ridge, utility_absolute_loss, retained_utility_indices, retained_utility_mae_cap):
            ordered = sorted((v.row.declaration_sha256 for v in rows))
            self.assertEqual(retained_utility_indices, tuple(sorted((ordered.index(d) for d in declarations))))
            self.assertEqual(retained_utility_mae_cap, 0.25)
            seen.append(1)
            return (np.zeros((z.shape[1], 9)), np.mean(y, axis=0))
        with patch.object(h, '_fit_order_retained', stub):
            h.fit_challenge_consequence(rows, retention_pairs=pair, retained_utility_declarations=declarations, retained_utility_mae_cap=0.25, **RECIPE)
        self.assertEqual(seen, [1])
        with patch.object(h, '_fit_order_retained', side_effect=AssertionError('invalid public scope reached optimizer')):
            with self.assertRaises(ValueError):
                h.fit_challenge_consequence(rows, retention_pairs=pair, retained_utility_declarations=('f' * 64,), retained_utility_mae_cap=0.25, **RECIPE)
            synthetic = tuple((replace(v, row=replace(v.row, provenance='synthetic')) for v in rows))
            with self.assertRaises(ValueError):
                h.fit_challenge_consequence(synthetic, retention_pairs=pair, retained_utility_declarations=declarations, retained_utility_mae_cap=0.25, **RECIPE)

    def test_public_default_does_not_forward_new_keywords(self):
        rows = tuple((synthetic_view(h, n, e, a) for n, e, a in [('winner', 0.0, 100), ('loser', 0.5, 1000), ('other', 1.0, 0)]))
        seen = []

        def old_signature(z, y, pairs, utility, *, ridge, utility_absolute_loss):
            seen.append(1)
            return (np.zeros((z.shape[1], 9)), np.mean(y, axis=0))
        with patch.object(h, '_fit_order_retained', old_signature):
            h.fit_challenge_consequence(rows, retention_pairs=((rows[0].row.declaration_sha256, rows[1].row.declaration_sha256),), **RECIPE)
        self.assertEqual(seen, [1])

    def test_infeasible_budget_false_success_is_rejected(self):
        z, y, pairs = data()
        real = scipy.optimize.minimize

        def dishonest(fun, x0, **kw):
            constraint = kw['constraints'][0]
            kw['constraints'] = (scipy.optimize.LinearConstraint(constraint.A[:-1], constraint.lb[:-1], constraint.ub[:-1]),)
            COUNTS['synthetic_optimizer_runs'] += 1
            result = real(fun, x0, **kw)
            self.assertTrue(result.success)
            self.assertGreater(float(np.asarray(constraint.A)[-1] @ result.x), 1e-08)
            return result
        with patch.object(scipy.optimize, 'minimize', dishonest), self.assertRaisesRegex(ValueError, 'violates'):
            h._fit_order_retained(z, y, pairs, U, utility_absolute_loss=True, retained_utility_indices=(0, 1), retained_utility_mae_cap=0.0)

    def test_budget_public_illegal_recipe_combinations_fail_before_solver(self):
        rows = tuple((synthetic_view(h, n, e, a) for n, e, a in [('winner', 0.0, 100), ('loser', 0.5, 1000), ('other', 1.0, 0)]))
        rows = tuple((replace(v, row=replace(v.row, provenance='native_train')) for v in rows))
        declarations = tuple((v.row.declaration_sha256 for v in rows[:2]))
        changes = [dict(ridge=2.0), dict(feedback_version=1), dict(feature_version=10), dict(context_projection='identity'), dict(cash_prediction='certified_single_trainer_v1'), dict(include_recovery_purchases=True), dict(reference_head=object()), dict(retained_rows=(object(),)), dict(reference_residual_mode='affine_nullspace')]
        with patch.object(h, '_fit_order_retained', side_effect=AssertionError('illegal recipe reached optimizer')):
            for change in changes:
                recipe = dict(RECIPE, **change)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    h.fit_challenge_consequence(rows, retention_pairs=(declarations,), retained_utility_declarations=declarations, retained_utility_mae_cap=0.25, **recipe)
