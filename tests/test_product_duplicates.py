import unittest
from core.product_duplicates import detect_duplicates, match_reason, require_duplicate_decisions
from core.shop_connection import ConnectionFailure


def item(name, **extra):
    return {'line': 2, 'sku': 'NEW', 'name': name, 'state': 'new', 'payload': {'name': name, 'sku': 'NEW', **extra}}


class DuplicateTests(unittest.TestCase):
    def test_normalization_particles_and_word_order(self):
        self.assertTrue(match_reason(item('SAC À MAIN Émilie'), {'name': 'Emilie — sac main'}))
        self.assertIsNone(match_reason(item('Sac'), {'name': 'Portefeuille'}))

    def test_controlled_synonym(self):
        self.assertTrue(match_reason(item('Sac porté épaule Emilie'), {'name': 'Sac porté bandoulière Emilie'}))

    def test_minor_typo(self):
        self.assertTrue(match_reason(item('Sac main Emilie'), {'name': 'Sac main Emillie'}))

    def test_distinct_products(self):
        for a, b in [('Sac Emilie noir', 'Sac Emilie rouge'), ('Sac Emilie mini', 'Sac Emilie maxi'), ('Sac Emilie 123', 'Sac Emilie 124')]:
            self.assertIsNone(match_reason(item(a), {'name': b}))
        self.assertIsNone(match_reason(item('Sac Emilie', global_unique_id='123'), {'name': 'Sac Emilie', 'global_unique_id': '124'}))
        self.assertIsNone(match_reason(item('Sac Emilie', brands=[{'id': 1}]), {'name': 'Sac Emilie', 'brands': [{'id': 2}]}))
        self.assertIsNone(match_reason(item('Sac Emilie', attributes=[{'name': 'Couleur', 'options': ['Noir']}]), {'name': 'Sac Emilie', 'attributes': [{'name': 'Couleur', 'options': ['Rouge']}]}))

    def test_exact_ean_even_when_names_differ(self):
        self.assertEqual(match_reason(item('Sac', global_unique_id='123'), {'name': 'Autre nom', 'global_unique_id': '123'}), 'Même EAN')

    def test_file_and_shop_candidates_require_decision(self):
        first, second = item('Sac main Emilie'), item('Sac à main Emilie')
        second['line'] = 3
        plan = {'items': [first, second]}
        detect_duplicates(plan, [{'id': 12, 'name': 'Sac main Emilie', 'sku': 'OLD'}])
        self.assertEqual(len(second['duplicate_candidates']), 2)
        with self.assertRaises(ConnectionFailure):
            require_duplicate_decisions(plan)
        first['duplicate_decision'] = 'create'
        second['duplicate_decision'] = 'skip'
        require_duplicate_decisions(plan)
