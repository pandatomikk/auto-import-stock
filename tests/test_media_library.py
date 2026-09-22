import unittest
from unittest.mock import Mock
from core.media_library import MediaLibrary, upload_name
from core.shop_connection import ConnectionFailure

class MediaLibraryTests(unittest.TestCase):
    def library(self,items):
        return MediaLibrary(Mock(listing=Mock(return_value=items)))

    def test_wordpress_domain_protection_and_long_names(self):
        name='a'*100+'-01__123456789abc-www.example.fr.webp'
        self.assertTrue(upload_name(name).endswith('www.example.fr.webp'))
        lib=self.library([{'id':5,'source_url':'https://example.test/'+name.replace('.fr.','.fr_.')}])
        self.assertEqual(lib.find(name)['id'],5)

    def test_original_image_metadata(self):
        lib=self.library([{'id':6,'source_url':'https://example.test/photo-scaled.jpg','media_details':{'original_image':'photo.jpg'}}])
        self.assertEqual(lib.find('photo.jpg')['id'],6)

    def test_partial_name_is_never_reused(self):
        lib=self.library([{'id':5,'source_url':'https://example.test/photo-blue.webp'}])
        self.assertIsNone(lib.find('photo.webp'))

    def test_confirmed_id_resolves_even_if_filename_changed(self):
        lib=self.library([{'id':6,'source_url':'https://example.test/renamed.webp'}])
        self.assertEqual(lib.find('old.webp',{'state':'uploaded','id':6})['id'],6)

    def test_deleted_confirmed_image_not_reused(self):
        self.assertIsNone(self.library([]).find('old.webp',{'state':'uploaded','id':6}))
