import unittest
from core.category_classification import classify


class ClassificationTests(unittest.TestCase):
    def test_type_takes_precedence_over_collection(self):
        rules = {'rules': [{'source': 'kind', 'equals': 'WALLET', 'category': 'Small goods'}, {'source': 'kind', 'equals': 'BAG', 'category': 'Bags'}]}
        self.assertEqual(classify({'name': 'Same collection', 'kind': 'WALLET'}, rules), ('Small goods', 'Classé'))
        self.assertEqual(classify({'name': 'Same collection', 'kind': 'BAG'}, rules), ('Bags', 'Classé'))

    def test_unknown_and_ambiguous_types_need_review(self):
        rules = {'fallback_field': 'kind', 'rules': [{'source': 'kind', 'equals': 'CASE', 'review': True, 'label': 'Case type'}]}
        self.assertEqual(classify({'kind': 'CASE'}, rules), ('À classer : Case type', 'À vérifier'))
        self.assertEqual(classify({'kind': 'NEW'}, rules), ('À classer : NEW', 'À vérifier'))
