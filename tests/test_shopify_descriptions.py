import unittest
from unittest.mock import patch
from core.enrichment import SupplierDescriptions


class ShopifyDescriptionsTest(unittest.TestCase):
    def provider(self):
        return SupplierDescriptions({'enabled': True, 'provider': 'shopify_catalog',
            'base_url': 'https://supplier.example', 'reference_remove_chars': '-', 'delay_seconds': 0}).provider

    def product(self, sku='ABC01', barcode='123'):
        return {'id': 1, 'handle': 'bag', 'body_html': '<p>Un sac.</p><script>bad()</script>',
                'variants': [{'id': 2, 'sku': sku, 'barcode': barcode}]}

    def test_exact_reference_and_cached_catalogue(self):
        provider = self.provider()
        with patch.object(provider, 'fetch', return_value=[self.product()]) as fetch:
            self.assertEqual(provider.get({'sku': '123', 'model': 'ABC-01', 'ean': '123'}), 'Un sac.')
            self.assertIsNone(provider.get({'model': 'ABC02'}))
            self.assertIsNone(provider.get({'model': 'ABC01', 'ean': '456'}))
            fetch.assert_called_once()
        self.assertEqual(provider.records[0]['status'], 'retrieved')

    def test_ambiguity_and_network_failure_are_reported(self):
        provider = self.provider()
        p = self.product(); p['variants'].append(dict(p['variants'][0], id=3))
        with patch.object(provider, 'fetch', return_value=[p]):
            self.assertIsNone(provider.get({'model': 'ABC01'}))
        provider = self.provider()
        with patch.object(provider, 'fetch', side_effect=TimeoutError('timeout')) as fetch:
            self.assertIsNone(provider.get({'model': 'ABC01'}))
            self.assertIsNone(provider.get({'model': 'ABC02'}))
            fetch.assert_called_once()
        self.assertIn('timeout', provider.records[0]['reason'])

    def test_incomplete_catalogue_is_not_used(self):
        provider = self.provider(); provider.settings['max_pages'] = 1
        page = [dict(self.product(), id=i) for i in range(250)]
        with patch.object(provider, 'fetch', return_value=page):
            self.assertIsNone(provider.get({'model': 'ABC01'}))
        self.assertIn('incomplet', provider.records[0]['reason'])
